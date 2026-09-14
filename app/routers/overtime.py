import os
import io
import re
import tempfile
from datetime import date, datetime, timedelta, timezone # 👈 UPDATED IMPORTS
from typing import Any, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Query, BackgroundTasks, Body, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, cast, String
from pydantic import BaseModel
from PIL import Image

from app.database import get_db
from app import models

# Attachement settings
def _normalize_attachment_url(attachment_path: Optional[str]) -> Optional[str]:
    """
    Standardizes local attachment paths for Overtime.
    Returns None if the path is invalid or empty to prevent 404s.
    """
    if not attachment_path:
        return None

    path = str(attachment_path).strip()
    
    # 🛡️ THE DIRECTORY GUARD: 
    # Returns None for empty paths, directory folders, or "None" strings.
    if path in ["", "mcs", "mcs/", "/mcs/", "/uploads/mcs/", "None"]:
        return None

    # Already a full URL
    if path.startswith("http"):
        return path
        
    # Standardize format:
    # 1. Clean out existing prefixes so we don't end up with /uploads/mcs/uploads/mcs/file.jpg
    # 2. Add the clean path to the standard local storage directory
    clean_filename = path.replace("/uploads/mcs/", "").replace("mcs/", "").lstrip("/")
    
    return f"/uploads/mcs/{clean_filename}"

# 🛠️ HELPERS (FIXED: Offset-based for cross-platform stability)

# ============================================================
# 🕒 TIMEZONE UTILITIES (FIXED: UTC Saving, KL Display)
# ============================================================
KL_TZ = timezone(timedelta(hours=8))

def get_utc_timestamp():
    """Returns the current UTC time for saving to the database."""
    # ALWAYS save in UTC. This ensures the DB never has an offset baked in.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

def convert_utc_string_to_kl(history_str: str) -> str:
    """Converts a UTC string from the DB to KL (UTC+8) for the UI."""
    if not history_str: 
        return "Pending"
    
    def replacer(match):
        try:
            # 1. Parse the string as UTC
            dt = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
            utc_dt = dt.replace(tzinfo=timezone.utc)
            
            # 2. Convert to Kuala Lumpur time for display
            kl_dt = utc_dt.astimezone(KL_TZ)
            return f"({kl_dt.strftime('%Y-%m-%d %H:%M')})"
        except Exception as e:
            print(f"DEBUG: Conversion error: {e}")
            return match.group(0)

    return re.sub(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)", replacer, history_str)

def _find_user_by_name_or_username(db: Session, name: Optional[str]):
    if not name: return None
    cleaned = str(name).strip()
    if not cleaned: return None
    return db.query(models.User).filter(
        or_(models.User.full_name.ilike(cleaned), models.User.username.ilike(cleaned))
    ).first()


def _normalize_approver_list(value):
    if not value:
        return []

    if not isinstance(value, list):
        value = [value]

    return [
        str(x).strip()
        for x in value
        if x and str(x).strip()
    ]

# ============================================================
# 🌍 GLOBAL CONFIGURATION
# ============================================================

# Email imports with fallback
try:
    from app.utils.email_service import (
        send_email, 
        template_new_ot_request, 
        template_ot_decision,
        template_l2_ot_request,
        template_l3_ot_request,
        template_cancellation_request,
        template_cancellation_approved,
        template_cancellation_rejected,
        template_ot_cancellation_request,
        template_l2_ot_cancellation_request,
        template_l3_ot_cancellation_request,
        template_ot_cancellation_approved,
        template_ot_cancellation_rejected
    )
except ImportError:
    from app.utils.email_service import (
        send_email, 
        template_new_ot_request, 
        template_ot_decision,
        template_l2_ot_request,
        template_l3_ot_request
    )

router = APIRouter(prefix="/overtime", tags=["Overtime"])

# ✅ Schema for Cancellation Reason
class CancelRequestSchema(BaseModel):
    reason: Optional[str] = None

# 1. APPLY FOR OVERTIME (Refactored for ID-First Architecture)
@router.post("/apply")
async def apply_overtime(
    background_tasks: BackgroundTasks, 
    employee_name: str = Form(...),
    approver_name: str = Form(...),
    ot_date: str = Form(...),
    ot_type: str = Form(...),
    ot_unit: str = Form(...),
    reason: str = Form(...),
    start_time: str = Form(None),
    end_time: str = Form(None),
    applied_by: Optional[str] = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    employee_name = employee_name.strip()
    approver_name = approver_name.strip()
    ot_date_obj = date.fromisoformat(ot_date)

    # ============================================================
    # GLOBAL APPROVAL POLICY
    # Same workflow switches used by Leave
    # ============================================================
    policy = db.query(models.GlobalPolicy).filter(
        models.GlobalPolicy.id == 1
    ).first()

    l1_enabled = policy.l1_approval_enabled if policy else False
    l2_enabled = policy.l2_approval_enabled if policy else False

    # ============================================================
    # APPROVAL ID RESOLUTION
    # L1 = Team Lead       -> approver_l1_id
    # L2 = Line Manager    -> approver_id
    # L3 = HOD             -> approver_l2_id
    # ============================================================

    employee_user = db.query(models.User).filter(
        models.User.full_name == employee_name
    ).first()

    if not employee_user:
        raise HTTPException(
            status_code=404,
            detail="Employee record not found."
        )

    assigned_team_leads = _normalize_approver_list(
        employee_user.team_lead
    )

    assigned_line_managers = _normalize_approver_list(
        employee_user.line_manager
    )

    assigned_hods = _normalize_approver_list(
        employee_user.hod_name
    )

    # ------------------------------------------------------------
    # L1 - TEAM LEAD
    # ------------------------------------------------------------

    approver_l1_id = None
    team_lead = None

    if l1_enabled:
        if not assigned_team_leads:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing Team Lead approver configuration. "
                    "Please contact HR Admin."
                )
            )

        if not approver_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Please select a Team Lead approver "
                    "before submitting this overtime request."
                )
            )

        if approver_name not in assigned_team_leads:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid Team Lead approver selected. "
                    "Please contact HR Admin."
                )
            )

        team_lead = _find_user_by_name_or_username(
            db,
            approver_name
        )

        if not team_lead or not team_lead.is_active:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected Team Lead approver is not "
                    "available. Please contact HR Admin."
                )
            )

        approver_l1_id = team_lead.id

    # ------------------------------------------------------------
    # L2 - LINE MANAGER
    # ------------------------------------------------------------

    manager = None
    approver_id = None
    resolved_approver_name = None

    if assigned_line_managers:
        for manager_name in assigned_line_managers:
            candidate = _find_user_by_name_or_username(
                db,
                manager_name
            )

            if candidate and candidate.is_active:
                manager = candidate
                break

    if l2_enabled:
        if not assigned_line_managers:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing Line Manager approver configuration. "
                    "Please contact HR Admin."
                )
            )

        if not manager:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The assigned Line Manager approver is not available. "
                    "Please contact HR Admin."
                )
            )

        approver_id = manager.id
        resolved_approver_name = manager.full_name

    # ------------------------------------------------------------
    # L3 - HOD
    # HOD is always required as the final approval level.
    # ------------------------------------------------------------

    if not assigned_hods:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing HOD approver configuration. "
                "Please contact HR Admin."
            )
        )

    hod = None
    approver_l2_id = None
    approver_l2_name = None

    for hod_name in assigned_hods:
        candidate = _find_user_by_name_or_username(
            db,
            hod_name
        )

        if candidate and candidate.is_active:
            hod = candidate
            break

    if not hod:
        raise HTTPException(
            status_code=400,
            detail=(
                "The assigned HOD approver is not available. "
                "Please contact HR Admin."
            )
        )

    approver_l2_id = hod.id
    approver_l2_name = hod.full_name

    # ------------------------------------------------------------
    # INITIAL APPROVAL STATUS
    # ------------------------------------------------------------

    if l1_enabled:
        initial_status = "Pending"
    elif l2_enabled:
        initial_status = "Pending L2 Approval"
    else:
        initial_status = "Pending L3 Approval"

    # A. Check Duplicates
    existing_ot = db.query(models.Overtime).filter(
        models.Overtime.employee_name == employee_name,
        models.Overtime.ot_date == ot_date_obj,
        models.Overtime.ot_type == ot_type,
        models.Overtime.status.in_(["Pending", "Approved", "Pending L2 Approval", "Pending Cancel"])
    ).first()

    if existing_ot:
        raise HTTPException(status_code=400, detail=f"Duplicate Request: {existing_ot.status} claim exists.")

    # B. Local Upload Logic (Kept exactly same)
    saved_filename = None
    if file and file.filename:
        try:
            contents = await file.read()
            img = Image.open(io.BytesIO(contents))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_filename = Path(file.filename).stem 
            clean_name = f"{timestamp}_{clean_filename.replace(' ', '_')}.jpg"
            
            target_dir = "uploads/mcs"
            os.makedirs(target_dir, exist_ok=True)
            file_path = f"{target_dir}/{clean_name}"
            img.save(file_path, format="JPEG", quality=60, optimize=True)
            saved_filename = clean_name
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            raise HTTPException(status_code=500, detail="Could not upload attachment locally.")

    # C. Calculate Value (Kept exactly same)
    total_val = 1.0 
    if ot_unit == "hours" and start_time and end_time:
        try:
            t1 = datetime.strptime(start_time, "%H:%M")
            t2 = datetime.strptime(end_time, "%H:%M")
            diff = t2 - t1
            if diff.total_seconds() <= 0:
                raise HTTPException(status_code=400, detail="End time must be after start time")
            total_val = round(diff.total_seconds() / 3600, 2)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid time format.")

    # D. Create Record
    # ============================================================
    # Approval hierarchy:
    # L1 = Team Lead       -> approver_l1_id
    # L2 = Line Manager    -> approver_id
    # L3 = HOD             -> approver_l2_id
    # ============================================================

    new_ot = models.Overtime(
        employee_name=employee_name,

        # L1 - Team Lead
        approver_l1_id=approver_l1_id,

        # L2 - Line Manager
        approver_name=resolved_approver_name,
        approver_id=approver_id,

        # L3 - HOD
        approver_l2=approver_l2_name,
        approver_l2_id=approver_l2_id,

        ot_date=ot_date_obj,
        ot_type=ot_type,
        ot_unit=ot_unit,
        start_time=start_time,
        end_time=end_time,
        total_value=total_val,
        reason=reason,
        attachment_path=saved_filename,

        # Initial workflow status
        status=initial_status,

        status_history=f"Submitted ({get_utc_timestamp()})"
    )

    db.add(new_ot)
    db.commit()
    db.refresh(new_ot)

    # E. Email First Workflow Approver
    # L1 takes priority when L1 workflow is enabled.
    email_approver = team_lead if l1_enabled else manager

    if email_approver and email_approver.email:
        try:
            admin_name = applied_by if (applied_by and applied_by != employee_name) else None

            body = template_new_ot_request(
                manager_name=email_approver.full_name,
                employee_name=employee_name,
                ot_type=ot_type,
                ot_date=ot_date,
                duration=f"{total_val} {ot_unit}",
                admin_name=admin_name
            )

            background_tasks.add_task(
                send_email,
                email_approver.email,
                f"Action Required: OT Claim - {employee_name}",
                body
            )

            print(
                f"📧 OT Manager Notification queued for "
                f"{email_approver.email}"
            )

        except Exception as e:
            print(f"⚠️ OT Email Trigger Warning: {e}")

    return {
        "message": "Overtime request submitted successfully",
        "id": new_ot.id
    }


# 2. GET ALL REQUESTS (Admin Audit)
@router.get("/all-requests")
def get_all_overtime_requests(db: Session = Depends(get_db)):
    results = db.query(models.Overtime).order_by(models.Overtime.id.desc()).all()
    
    formatted = []
    for o in results:
        # 🚀 FIXED: Using the centralized helper to prevent 404s
        url = _normalize_attachment_url(o.attachment_path)

        formatted.append({
            "id": o.id,
            "employee_name": o.employee_name,

            # L2 - Line Manager
            "approver_name": o.approver_name,

            # L1 - Team Lead
            "approver_l1_id": o.approver_l1_id,

            # L2 - Line Manager ID
            "approver_id": o.approver_id,

            # L3 - HOD
            "approver_l2_id": o.approver_l2_id,

            "ot_date": o.ot_date.strftime("%Y-%m-%d"),
            "ot_type": o.ot_type,
            "ot_unit": o.ot_unit,
            "total_value": o.total_value,
            "status": o.status,
            "reason": o.reason,
            "attachment_path": url,
            "manager_remarks": o.manager_remarks or "",
            "status_history": convert_utc_string_to_kl(o.status_history)  # 👈 FIXED
        })

    return formatted

# 3. GET MANAGER PENDING & HISTORY REQUESTS (Unified)
@router.get("/manager-requests")
def get_manager_ot_requests(
    approver_name: str = Query(None),
    page: int = 1,
    page_size: int = 1000,
    db: Session = Depends(get_db),
    x_username: Optional[str] = Header(None)  # 👑 Intercept requester identity header
):
    # ============================================================
    # AUTHENTICATED USER
    # Resolve the actual requester from the security header.
    # The frontend already supplies x-username through fetchWithAuth().
    # ============================================================
    user = db.query(models.User).filter(
        models.User.username == x_username
    ).first()

    is_super = user and user.role == "superuser"

    # ============================================================
    # BASE QUERY
    # ============================================================
    query = db.query(models.Overtime)

    # ============================================================
    # SUPERUSER
    # Superusers retain the existing ability to see all OT records.
    # ============================================================
    if is_super:
        results = query.order_by(
            models.Overtime.id.desc()
        ).all()

    else:
        # ========================================================
        # NORMAL USER / MANAGER
        #
        # Security rule:
        # The authenticated database user ID is authoritative.
        # Do not use approver_name or status_history for access.
        # ========================================================
        if not user:
            return []

        manager_id = user.id

        # ========================================================
        # STAGE-SPECIFIC APPROVAL MATRIX
        #
        # L1 = Team Lead
        #     status = Pending
        #     ID     = approver_l1_id
        #
        # L2 = Line Manager
        #     status = Pending L2 Approval
        #     ID     = approver_id
        #
        # L3 = HOD
        #     status = Pending L3 Approval
        #     ID     = approver_l2_id
        #
        # IMPORTANT:
        # Pending Cancel is intentionally NOT changed here.
        # The cancellation workflow will be aligned separately
        # so we do not create a temporary authorization mismatch.
        # ========================================================
        query = query.filter(
            or_(
                # NORMAL L1 APPROVAL
                and_(
                    models.Overtime.status == "Pending",
                    models.Overtime.approver_l1_id == manager_id
                ),

                # CANCELLATION L1 APPROVAL
                and_(
                    models.Overtime.status == "Pending Cancel",
                    models.Overtime.approver_l1_id == manager_id
                ),

                # NORMAL L2 APPROVAL
                and_(
                    models.Overtime.status == "Pending L2 Approval",
                    models.Overtime.approver_id == manager_id
                ),

                # NORMAL / CANCELLATION L3 APPROVAL
                and_(
                    models.Overtime.status == "Pending L3 Approval",
                    models.Overtime.approver_l2_id == manager_id
                )
            )
        )

        results = query.order_by(
            models.Overtime.id.desc()
        ).all()

    # ============================================================
    # FORMAT RESPONSE
    # ============================================================
    formatted_results = []

    for o in results:
        # 🚀 Existing attachment handling preserved
        full_attachment_url = _normalize_attachment_url(
            o.attachment_path
        )

        # ========================================================
        # DETERMINE WHETHER THIS IS THE CURRENT USER'S TURN
        # ========================================================
        if is_super:
            is_my_turn = True
        else:
            is_my_turn = (
                # NORMAL L1 APPROVAL
                (
                    o.status == "Pending"
                    and o.approver_l1_id == user.id
                )
                or
                # CANCELLATION L1 APPROVAL
                (
                    o.status == "Pending Cancel"
                    and o.approver_l1_id == user.id
                )
                or
                # NORMAL L2 APPROVAL
                (
                    o.status == "Pending L2 Approval"
                    and o.approver_id == user.id
                )
                or
                # NORMAL / CANCELLATION L3 APPROVAL
                (
                    o.status == "Pending L3 Approval"
                    and o.approver_l2_id == user.id
                )
            )

        formatted_results.append({
            "id": o.id,
            "employee_name": o.employee_name,
            "approver_name": o.approver_name,
            "ot_date": o.ot_date.strftime("%Y-%m-%d"),
            "ot_type": o.ot_type,
            "ot_unit": o.ot_unit,
            "total_value": o.total_value,
            "status": o.status,
            "reason": o.reason,
            "attachment_path": full_attachment_url,
            "manager_remarks": o.manager_remarks or "",
            "status_history": convert_utc_string_to_kl(
                o.status_history
            ),

            # CRITICAL MATRIX INTERLOCK
            # Current approval turn is determined by
            # status + authoritative approver ID.
            "is_my_turn": is_my_turn,

            # ====================================================
            # APPROVAL IDS
            # Exposed for the frontend workflow update later.
            # ====================================================
            "approver_l1_id": o.approver_l1_id,
            "approver_id": o.approver_id,
            "approver_l2_id": o.approver_l2_id
        })

    return formatted_results

# 4. PROCESS MANAGER ACTION (Forensically Fixed)
@router.post("/manager-action/{ot_id}")
async def process_ot_action( 
    ot_id: int, 
    background_tasks: BackgroundTasks, 
    status: str, 
    remarks: str = "", 
    approver_name: str = "",
    l2_name: str = Query(None),
    l3_name: str = Query(None),
    db: Session = Depends(get_db),
    x_username: Optional[str] = Header(None) 
):
    print(f"DEBUG: >>> ENTERING process_ot_action for OT ID: {ot_id} <<<")
    
    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT record not found")

    acting_user = db.query(models.User).filter(models.User.username == x_username).first()
    is_superuser_override = acting_user and acting_user.role == "superuser"
    
    # 🚀 FIX: Effective approver name ensures auth works even if parameter is empty
    effective_approver_name = (
        approver_name
        if (approver_name and approver_name.strip())
        else (acting_user.full_name if acting_user else ot.approver_name)
    )

    # ============================================================
    # CURRENT OT STATUS
    # ============================================================
    current_status = ot.status

    # ============================================================
    # CANCELLATION JOURNEY DETECTION
    #
    # IMPORTANT:
    # Cancellation currently has its own existing workflow.
    # Do NOT apply the new normal L1/L2/L3 authorization matrix
    # to Pending Cancel yet.
    # ============================================================
    is_cancellation_journey = (
        current_status == "Pending Cancel"
    ) or (
        current_status == "Pending L2 Approval"
        and "Cancellation" in (ot.status_history or "")
    ) or (
        current_status == "Pending L3 Approval"
        and "Cancellation" in (ot.status_history or "")
    )

    # ============================================================
    # STAGE-AWARE APPROVAL AUTHORIZATION
    #
    # Normal OT workflow:
    #
    # L1 = Team Lead
    #     Pending
    #     approver_l1_id
    #
    # L2 = Line Manager
    #     Pending L2 Approval
    #     approver_id
    #
    # L3 = HOD
    #     Pending L3 Approval
    #     approver_l2_id
    #
    # Cancellation workflow:
    #
    # L1 = Team Lead
    #     Pending Cancel
    #     approver_l1_id
    #
    # L2 = Line Manager
    #     Pending L2 Approval + Cancellation history
    #     approver_id
    #
    # L3 = HOD
    #     Pending L3 Approval + Cancellation history
    #     approver_l2_id
    #
    # The authenticated user's database ID is authoritative.
    # ============================================================
    is_authorized = is_superuser_override

    if not is_authorized and acting_user:

        if is_cancellation_journey:

            # ----------------------------------------------------
            # CANCELLATION WORKFLOW
            # ----------------------------------------------------

            # L1 - Team Lead
            if (
                current_status == "Pending Cancel"
                and ot.approver_l1_id
                and acting_user.id == ot.approver_l1_id
            ):
                is_authorized = True

            # L2 - Line Manager
            elif (
                current_status == "Pending L2 Approval"
                and "Cancellation" in (ot.status_history or "")
                and ot.approver_id
                and acting_user.id == ot.approver_id
            ):
                is_authorized = True

            # L3 - HOD
            elif (
                current_status == "Pending L3 Approval"
                and "Cancellation" in (ot.status_history or "")
                and ot.approver_l2_id
                and acting_user.id == ot.approver_l2_id
            ):
                is_authorized = True

        else:

            # ----------------------------------------------------
            # NORMAL OT APPROVAL WORKFLOW
            # ----------------------------------------------------

            # L1 - Team Lead
            if (
                current_status == "Pending"
                and ot.approver_l1_id
                and acting_user.id == ot.approver_l1_id
            ):
                is_authorized = True

            # L2 - Line Manager
            elif (
                current_status == "Pending L2 Approval"
                and ot.approver_id
                and acting_user.id == ot.approver_id
            ):
                is_authorized = True

            # L3 - HOD
            elif (
                current_status == "Pending L3 Approval"
                and ot.approver_l2_id
                and acting_user.id == ot.approver_l2_id
            ):
                is_authorized = True

    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to approve this request."
        )

    # Contextual flags
    acting_mgr = _find_user_by_name_or_username(db, effective_approver_name)
    is_senior = getattr(acting_mgr, 'is_senior_manager', False)
    
    is_l1 = (ot.approver_id and acting_user and acting_user.id == ot.approver_id) or \
            (effective_approver_name and ot.approver_name and effective_approver_name.strip().lower() == ot.approver_name.strip().lower())

    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    l2_active = policy.l2_approval_enabled if policy else False
    
    timestamp = get_utc_timestamp()
    route_to_l2 = False
    route_to_l3 = False
    l2_user = None
    note_str = f" | Note: {remarks.strip()}" if remarks and remarks.strip() else ""
    
    user_record = db.query(models.User).filter(
        or_(models.User.full_name == ot.employee_name, models.User.username == ot.employee_name)
    ).first()

    display_approver = effective_approver_name.strip()

    # --- PROCESSING ---
    # Robust: Detects cancellation workflow stages
    is_cancellation_journey = (current_status == "Pending Cancel") or \
                              (current_status == "Pending L2 Approval" and "Cancellation" in (ot.status_history or "")) or \
                              (current_status == "Pending L3 Approval" and "Cancellation" in (ot.status_history or ""))

    if is_cancellation_journey:
        if status == "Approved":

            # ============================================================
            # CANCELLATION L1 -> L2
            #
            # L1 = Team Lead
            # Current status = Pending Cancel
            # Authoritative approver = approver_l1_id
            #
            # Reuse the originally captured L2 Line Manager.
            # ============================================================
            if (
                current_status == "Pending Cancel"
                and l2_active
                and ot.approver_l1_id
                and acting_user
                and acting_user.id == ot.approver_l1_id
                and ot.approver_id
                and not is_superuser_override
            ):
                l2_user = db.query(models.User).filter(
                    models.User.id == ot.approver_id
                ).first()

                if not l2_user or not l2_user.is_active:
                    raise HTTPException(
                        status_code=400,
                        detail="Assigned L2 Line Manager could not be found or is inactive."
                    )

                ot.status = "Pending L2 Approval"
                ot.approver_name = l2_user.full_name

                ot.status_history += (
                    f" > L1 Approved Cancellation by "
                    f"{display_approver}. "
                    f"Routed to L2 "
                    f"{l2_user.full_name} "
                    f"({timestamp}){note_str}"
                )

                route_to_l2 = True

            # ============================================================
            # CANCELLATION L2 -> L3 / HOD
            #
            # L2 = Line Manager
            # Current status = Pending L2 Approval
            # Authoritative approver = approver_id
            #
            # Reuse the originally captured HOD.
            # No new HOD selection during cancellation.
            # ============================================================
            elif (
                current_status == "Pending L2 Approval"
                and acting_user
                and ot.approver_id
                and acting_user.id == ot.approver_id
                and ot.approver_l2_id
                and not is_superuser_override
            ):
                l3_user = db.query(models.User).filter(
                    models.User.id == ot.approver_l2_id
                ).first()

                if not l3_user or not l3_user.is_active:
                    raise HTTPException(
                        status_code=400,
                        detail="Assigned L3 HOD approver could not be found or is inactive."
                    )

                ot.status = "Pending L3 Approval"
                ot.approver_l2 = l3_user.full_name

                ot.status_history += (
                    f" > L2 Approved Cancellation by "
                    f"{display_approver}. "
                    f"Routed to L3 HOD "
                    f"{l3_user.full_name} "
                    f"({timestamp}){note_str}"
                )

                route_to_l3 = True

            # ============================================================
            # CANCELLATION L3 / HOD -> FINAL
            #
            # L3 = HOD
            # Current status = Pending L3 Approval
            # Authoritative approver = approver_l2_id
            #
            # ONLY HERE do we reverse the OT bank.
            # ============================================================
            elif (
                current_status == "Pending L3 Approval"
                and acting_user
                and ot.approver_l2_id
                and acting_user.id == ot.approver_l2_id
                and not is_superuser_override
            ):
                if user_record:
                    user_record.overtime_bank = max(
                        0,
                        float(user_record.overtime_bank or 0.0)
                        - float(ot.total_value or 0.0)
                    )

                ot.status = "Cancelled"

                ot.status_history += (
                    f" > Cancellation FINALIZED by "
                    f"{display_approver} "
                    f"({timestamp}){note_str}"
                )

            # ============================================================
            # DIRECT / OVERRIDE CANCELLATION
            #
            # Preserve existing senior-manager / superuser behavior.
            # ============================================================
            elif is_superuser_override or is_senior:

                if user_record:
                    user_record.overtime_bank = max(
                        0,
                        float(user_record.overtime_bank or 0.0)
                        - float(ot.total_value or 0.0)
                    )

                ot.status = "Cancelled"

                ot.status_history += (
                    f" > Cancellation FINALIZED by "
                    f"{display_approver} "
                    f"({timestamp}){note_str}"
                )

            else:
                raise HTTPException(
                    status_code=403,
                    detail="You are not authorized for this cancellation stage."
                )

        else:
            # ============================================================
            # CANCELLATION REJECTION
            #
            # Rejection at any cancellation stage returns the OT claim
            # to Approved. The OT bank is not changed.
            # ============================================================
            ot.status = "Approved"

            if ot.approver_l2:
                ot.approver_name = ot.approver_l2

            ot.status_history += (
                f" > Cancellation REJECTED by "
                f"{display_approver} "
                f"({timestamp}){note_str}"
            )

            # Trigger Notification
            if user_record and user_record.email:
                try:
                    subject = f"❌ OT Cancellation REJECTED - {ot.ot_date}"
                    body = template_cancellation_rejected(
                        ot.employee_name,
                        display_approver,
                        str(ot.ot_date),
                        remarks or "No remarks provided."
                    )
                    background_tasks.add_task(
                        send_email,
                        user_record.email,
                        subject,
                        body
                    )
                except Exception as e:
                    print(f"⚠️ Cancellation Rejection Email Error: {e}")

    else: # --- NORMAL JOURNEY ---

        if status == "Approved":

            # ============================================================
            # L1 -> L2
            #
            # L1 = Team Lead
            # Current status = Pending
            # Authoritative approver = approver_l1_id
            # ============================================================
            if (
                current_status == "Pending"
                and acting_user
                and ot.approver_l1_id
                and acting_user.id == ot.approver_l1_id
                and l2_active
                and not is_superuser_override
            ):

                # --------------------------------------------------------
                # L2 is already preassigned during OT submission.
                #
                # If the frontend supplies l2_name, validate that it is
                # one of the employee's configured Line Managers.
                # Otherwise retain the preassigned L2.
                # --------------------------------------------------------
                if l2_name:

                    employee_user = db.query(models.User).filter(
                        models.User.full_name == ot.employee_name
                    ).first()

                    if not employee_user:
                        raise HTTPException(
                            status_code=400,
                            detail="Employee profile could not be found for L2 routing."
                        )

                    assigned_line_managers = _normalize_approver_list(
                        employee_user.line_manager
                    )

                    if not any(
                        str(manager).strip().lower()
                        == l2_name.strip().lower()
                        for manager in assigned_line_managers
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Selected L2 Line Manager is not configured "
                                "for this employee."
                            )
                        )

                    selected_l2_user = _find_user_by_name_or_username(
                        db,
                        l2_name
                    )

                    if (
                        not selected_l2_user
                        or not selected_l2_user.is_active
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Selected L2 Line Manager could not be found "
                                "or is inactive."
                            )
                        )

                    ot.approver_id = selected_l2_user.id
                    ot.approver_name = selected_l2_user.full_name
                    l2_user = selected_l2_user

                else:

                    if not ot.approver_id:
                        raise HTTPException(
                            status_code=400,
                            detail="L2 Line Manager is not configured for this request."
                        )

                    l2_user = db.query(models.User).filter(
                        models.User.id == ot.approver_id
                    ).first()

                    if not l2_user or not l2_user.is_active:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "L2 Line Manager could not be found "
                                "or is inactive."
                            )
                        )

                ot.status = "Pending L2 Approval"

                ot.status_history += (
                    f" > L1 Approved by "
                    f"{display_approver}. "
                    f"Routed to L2 "
                    f"{l2_user.full_name} "
                    f"({timestamp}){note_str}"
                )

                route_to_l2 = True

            # ============================================================
            # L2 -> L3
            #
            # L2 = Line Manager
            # Current status = Pending L2 Approval
            # Authoritative approver = approver_id
            # ============================================================
            elif (
                current_status == "Pending L2 Approval"
                and acting_user
                and ot.approver_id
                and acting_user.id == ot.approver_id
                and l2_active
                and not is_superuser_override
            ):

                # --------------------------------------------------------
                # L3 / HOD selection
                #
                # The employee's hod_name contains the configured
                # L3/HOD candidates.
                #
                # If l3_name is supplied by the frontend, validate and
                # store the selected HOD.
                # Otherwise retain the preassigned HOD.
                # --------------------------------------------------------
                if l3_name:

                    employee_user = db.query(models.User).filter(
                        models.User.full_name == ot.employee_name
                    ).first()

                    if not employee_user:
                        raise HTTPException(
                            status_code=400,
                            detail="Employee profile could not be found for L3 routing."
                        )

                    assigned_hods = _normalize_approver_list(
                        employee_user.hod_name
                    )

                    if not any(
                        str(hod).strip().lower()
                        == l3_name.strip().lower()
                        for hod in assigned_hods
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Selected L3 HOD approver is not configured "
                                "for this employee."
                            )
                        )

                    selected_l3_user = _find_user_by_name_or_username(
                        db,
                        l3_name
                    )

                    if (
                        not selected_l3_user
                        or not selected_l3_user.is_active
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Selected L3 HOD approver could not be found "
                                "or is inactive."
                            )
                        )

                    ot.approver_l2_id = selected_l3_user.id
                    ot.approver_l2 = selected_l3_user.full_name
                    l3_user = selected_l3_user

                else:

                    if not ot.approver_l2_id:
                        raise HTTPException(
                            status_code=400,
                            detail="L3 HOD approver is not configured for this request."
                        )

                    l3_user = db.query(models.User).filter(
                        models.User.id == ot.approver_l2_id
                    ).first()

                    if not l3_user or not l3_user.is_active:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "L3 HOD approver could not be found "
                                "or is inactive."
                            )
                        )

                ot.status = "Pending L3 Approval"

                ot.status_history += (
                    f" > L2 Approved by "
                    f"{display_approver}. "
                    f"Routed to L3 HOD "
                    f"{l3_user.full_name} "
                    f"({timestamp}){note_str}"
                )

                route_to_l3 = True

            # ============================================================
            # L3 -> FINAL APPROVAL
            #
            # L3 = HOD
            # Current status = Pending L3 Approval
            # Authoritative approver = approver_l2_id
            #
            # THIS is the only normal approval stage where the OT Bank
            # is credited.
            # ============================================================
            elif (
                current_status == "Pending L3 Approval"
                and acting_user
                and ot.approver_l2_id
                and acting_user.id == ot.approver_l2_id
                and not is_superuser_override
            ):

                if user_record:
                    user_record.overtime_bank = (
                        float(user_record.overtime_bank or 0.0)
                        + float(ot.total_value or 0.0)
                    )

                ot.status = "Approved"

                ot.status_history += (
                    f" > Fully Approved by "
                    f"{display_approver} "
                    f"({timestamp}){note_str}"
                )

            # ============================================================
            # DIRECT / OVERRIDE APPROVAL
            #
            # Preserve existing senior-manager / superuser behavior.
            #
            # IMPORTANT:
            # Superuser override is already authorized above.
            # ============================================================
            elif is_superuser_override or is_senior:

                if user_record:
                    user_record.overtime_bank = (
                        float(user_record.overtime_bank or 0.0)
                        + float(ot.total_value or 0.0)
                    )

                ot.status = "Approved"

                ot.status_history += (
                    f" > Final Approval by "
                    f"{display_approver} "
                    f"({timestamp}){note_str}"
                )

            else:
                raise HTTPException(
                    status_code=403,
                    detail="You are not authorized for this approval stage."
                )

        elif status == "Rejected":

            ot.status = "Rejected"

            ot.status_history += (
                f" > Rejected by "
                f"{display_approver} "
                f"({timestamp}){note_str}"
            )
            
    ot.manager_remarks = remarks

    # --- DEBUG TRACE ---
    print(f"DEBUG: Saving OT ID: {ot.id}")
    print(f"DEBUG: OT Status: {ot.status}")
    print(f"DEBUG: Approver Name: {ot.approver_name}")
    print(f"DEBUG: Approver L2: {ot.approver_l2}")
    print(f"DEBUG: Route to L2: {route_to_l2}")
    # -------------------

    db.commit()
    

    # --- EMAIL NOTIFICATION FLOW ---
    #
    # Cancellation and normal OT approval journeys are intentionally
    # separated so cancellation never sends normal OT approval emails.
    # ---------------------------------------------------------------

    if is_cancellation_journey:

        # ============================================================
        # CANCELLATION EMAIL FLOW
        # ============================================================

        if status == "Approved":

            # --------------------------------------------------------
            # Cancellation L1 -> L2
            # --------------------------------------------------------
            if route_to_l2 and l2_user and l2_user.email:
                try:
                    body = template_l2_ot_cancellation_request(
                        l2_manager_name=l2_user.full_name or l2_user.username,
                        l1_manager_name=approver_name or display_approver,
                        employee_name=ot.employee_name,
                        ot_type=ot.ot_type,
                        ot_date=str(ot.ot_date),
                        duration=str(ot.total_value)
                    )

                    background_tasks.add_task(
                        send_email,
                        l2_user.email,
                        f"ACTION REQUIRED: OT Cancellation Approval - {ot.employee_name}",
                        body
                    )
                except Exception as e:
                    print(f"OT L2 Cancellation Email Error: {e}")

            # --------------------------------------------------------
            # Cancellation L2 -> L3 / HOD
            # --------------------------------------------------------
            elif route_to_l3 and l3_user and l3_user.email:
                try:
                    body = template_l3_ot_cancellation_request(
                        l3_manager_name=l3_user.full_name or l3_user.username,
                        l2_manager_name=approver_name or display_approver,
                        employee_name=ot.employee_name,
                        ot_type=ot.ot_type,
                        ot_date=str(ot.ot_date),
                        duration=str(ot.total_value)
                    )

                    background_tasks.add_task(
                        send_email,
                        l3_user.email,
                        f"ACTION REQUIRED: OT Cancellation Approval - {ot.employee_name}",
                        body
                    )
                except Exception as e:
                    print(f"OT L3 Cancellation Email Error: {e}")

            # --------------------------------------------------------
            # Cancellation final approval -> Employee
            # --------------------------------------------------------
            elif not route_to_l2 and not route_to_l3 and user_record and user_record.email:
                try:
                    subject = f"OT Cancellation APPROVED - {ot.ot_date}"

                    body = template_ot_cancellation_approved(
                        employee_name=ot.employee_name,
                        manager_name=display_approver,
                        ot_type=ot.ot_type,
                        ot_date=str(ot.ot_date),
                        duration=str(ot.total_value)
                    )

                    background_tasks.add_task(
                        send_email,
                        user_record.email,
                        subject,
                        body
                    )
                except Exception as e:
                    print(f"OT Cancellation Approval Email Error: {e}")

        # ------------------------------------------------------------
        # Cancellation rejection -> Employee
        # ------------------------------------------------------------
        elif status == "Rejected" and user_record and user_record.email:
            try:
                subject = f"OT Cancellation REJECTED - {ot.ot_date}"

                body = template_ot_cancellation_rejected(
                    employee_name=ot.employee_name,
                    manager_name=display_approver,
                    ot_type=ot.ot_type,
                    ot_date=str(ot.ot_date),
                    duration=str(ot.total_value),
                    remarks=remarks or "No remarks provided."
                )

                background_tasks.add_task(
                    send_email,
                    user_record.email,
                    subject,
                    body
                )
            except Exception as e:
                print(f"OT Cancellation Rejection Email Error: {e}")

    else:

        # ============================================================
        # NORMAL OT EMAIL FLOW
        #
        # IMPORTANT:
        # Existing normal OT email logic is preserved.
        # ============================================================

        if status == "Approved":

            # STATE 1: L1 -> L2 Routing
            if route_to_l2 and l2_user and l2_user.email:
                try:
                    body = template_l2_ot_request(
                        l2_manager_name=l2_user.full_name or l2_user.username,
                        l1_manager_name=approver_name or display_approver,
                        employee_name=ot.employee_name,
                        ot_type=ot.ot_type,
                        ot_date=str(ot.ot_date),
                        duration=str(ot.total_value)
                    )

                    background_tasks.add_task(
                        send_email,
                        l2_user.email,
                        f"ACTION REQUIRED: L2 Approval Needed - {ot.employee_name}",
                        body
                    )
                except Exception as e:
                    print(f"OT L2 Email Error: {e}")

            # STATE 2: L2 -> L3 / HOD Routing
            elif route_to_l3 and l3_user and l3_user.email:
                try:
                    body = template_l3_ot_request(
                        l3_manager_name=l3_user.full_name or l3_user.username,
                        l2_manager_name=approver_name or display_approver,
                        employee_name=ot.employee_name,
                        ot_type=ot.ot_type,
                        ot_date=str(ot.ot_date),
                        duration=str(ot.total_value)
                    )

                    background_tasks.add_task(
                        send_email,
                        l3_user.email,
                        f"ACTION REQUIRED: HOD Approval Needed - {ot.employee_name}",
                        body
                    )
                except Exception as e:
                    print(f"OT L3 Email Error: {e}")

            # STATE 3: Final L3 Approval -> Employee Notification
            elif not route_to_l2 and not route_to_l3 and user_record and user_record.email:
                try:
                    print(f"DEBUG: Triggering Final Approval email to {user_record.email}")

                    subject = f"OT Claim APPROVED - {ot.ot_date}"

                    body = template_ot_decision(
                        ot.employee_name,
                        display_approver,
                        "Approved",
                        ot.ot_type,
                        str(ot.ot_date),
                        remarks or "No remarks provided."
                    )

                    background_tasks.add_task(
                        send_email,
                        user_record.email,
                        subject,
                        body
                    )
                except Exception as e:
                    print(f"OT Approval Email Error: {e}")

        # STATE 4: Standard Rejection -> Employee Notification
        elif status == "Rejected" and user_record and user_record.email:
            try:
                subject = f"OT Claim REJECTED - {ot.ot_date}"

                body = template_ot_decision(
                    ot.employee_name,
                    display_approver,
                    "Rejected",
                    ot.ot_type,
                    str(ot.ot_date),
                    remarks or "No remarks provided."
                )

                background_tasks.add_task(
                    send_email,
                    user_record.email,
                    subject,
                    body
                )
            except Exception as e:
                print(f"OT Rejection Email Error: {e}")


# 5. CANCEL/WITHDRAW REQUEST (SECURED)
@router.put("/{ot_id}/cancel")
async def cancel_overtime_request( # 👈 Renamed to match leave.py style
    ot_id: int, 
    background_tasks: BackgroundTasks,
    payload: CancelRequestSchema = Body(None),
    db: Session = Depends(get_db),
    x_username: str = Header(None) # 🔒 SECURITY: ID Badge Required
):
    # 1. Security Check
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT claim not found")

    # 2. Ownership Verification
    current_user = db.query(models.User).filter(models.User.username == x_username).first()
    
    # Block if user is NOT the owner AND NOT a superuser
    if not current_user or (ot.employee_name != current_user.full_name and current_user.role != "superuser"):
        raise HTTPException(status_code=403, detail="You do not have permission to cancel this request.")

    timestamp = get_utc_timestamp()
    current_status = ot.status
    
    # Extract Reason safely
    reason_val = payload.reason if (payload and payload.reason) else "No reason provided"
    reason_text = f" (Reason: {reason_val})"

    # --- STATUS LOGIC ---
    
    # CASE A: WITHDRAWAL (Pending -> Withdrawn)
    if current_status in ["Pending", "Pending L2 Approval"]:
        ot.status = "Withdrawn"
        # The timestamp string will be captured in the history and localized on the UI
        ot.status_history = (ot.status_history or "") + f"\n > Withdrawn by Employee{reason_text} ({timestamp})"
        msg = "Overtime claim successfully withdrawn."
        
    # CASE B: CANCELLATION (Approved -> Pending Cancel)
    elif current_status == "Approved":
        ot.status = "Pending Cancel"
        ot.status_history = (ot.status_history or "") + f"\n > Cancellation Requested by Employee{reason_text} ({timestamp})"
        msg = "Cancellation request sent to L1 Manager."
        
        # --- 🚀 FIX 1: REWIND DASHBOARD VISIBILITY BACK TO L1 ---
        manager_email = None
        manager_name = ot.approver_name 

        try:
            # Look up the original L1 using the immutable approver_id safely stored at submission
            l1_manager = db.query(models.User).filter(
            models.User.id == ot.approver_l1_id
        ).first() if ot.approver_l1_id else None
            
            if l1_manager:
                ot.approver_name = l1_manager.full_name # Route back to L1's dashboard
                manager_email = l1_manager.email
                manager_name = l1_manager.full_name
            else:
                # Fallback just in case ID is missing
                manager = db.query(models.User).filter(models.User.full_name == ot.approver_name).first()
                if manager:
                    manager_email = manager.email
                    manager_name = manager.full_name

            # Email L1 Manager safely
            if manager_email and 'template_ot_cancellation_request' in globals():
                body = template_ot_cancellation_request(
                    manager_name,
                    ot.employee_name,
                    ot.ot_type,
                    str(ot.ot_date),
                    str(ot.total_value),
                    reason_val
                )
                background_tasks.add_task(
                    send_email,
                    manager_email,
                    "Action Required: OT Cancellation",
                    body
                )
        except Exception as e:
            print(f"⚠️ Email trigger failed: {e}")
            
    else:
        raise HTTPException(status_code=400, detail="Cannot cancel this claim in its current state.")

    try:
        db.commit()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database Error during cancellation")

# In app/routers/overtime.py

@router.get("/my-requests")
def get_my_overtime_requests(employee_name: str, db: Session = Depends(get_db)):
    try:
        results = db.query(models.Overtime).filter(
            models.Overtime.employee_name == employee_name
        ).order_by(models.Overtime.ot_date.desc()).all()
        
        formatted_results = []
        for o in results:
            # 🚀 FIXED: Using the centralized helper to prevent 404s
            full_attachment_url = _normalize_attachment_url(o.attachment_path)

            formatted_results.append({
                "id": o.id,
                "employee_name": o.employee_name,
                "ot_date": o.ot_date.strftime("%Y-%m-%d"),
                "ot_type": o.ot_type,
                "ot_unit": o.ot_unit,
                "total_value": o.total_value,
                "status": o.status,
                "reason": o.reason,
                "approver_name": o.approver_name,

                # L1 - Team Lead
                "approver_l1_id": o.approver_l1_id,

                # L2 - Line Manager
                "approver_id": o.approver_id,

                # L3 - HOD
                "approver_l2_id": o.approver_l2_id,

                "attachment_path": full_attachment_url,
                "manager_remarks": o.manager_remarks or "",
                "status_history": convert_utc_string_to_kl(o.status_history)  # 👈 FIXED: Localized timestamp
            })

        return formatted_results

    except Exception as e:
        print(f"Error fetching personal OT history: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not load overtime history")
    

    # ADD THIS AT THE BOTTOM OF app/routers/overtime.py

@router.get("/manager/all")
def get_all_manager_overtime(
    user_role: str = "",          
    approver_name: str = None, 
    db: Session = Depends(get_db),
    x_username: Optional[str] = Header(None)  # 👑 Intercept requester identity header
):
    query = db.query(models.Overtime)
    
    # Check if the requester has authoritative Superuser privileges via identity token match
    user = db.query(models.User).filter(models.User.username == x_username).first()
    is_admin_or_super = "hr_admin" in user_role.lower() or (user and user.role == "superuser")
    
    # 1. RBAC: Managers only see what they touched. Admins and Superusers see all.
    if not is_admin_or_super:
        if approver_name:
            query = query.filter(
                or_(
                    models.Overtime.approver_name.ilike(approver_name.strip()),
                    models.Overtime.approver_l2.ilike(approver_name.strip()),
                    models.Overtime.status_history.ilike(f"%{approver_name.strip()}%") 
                )
            )
        else:
            return []
            
    results = query.order_by(models.Overtime.id.desc()).all()
    
    formatted_results = []
    for o in results:
        # 🚀 FIXED: Using the centralized helper to prevent 404s
        full_attachment_url = _normalize_attachment_url(o.attachment_path)

        formatted_results.append({
            "id": o.id,
            "employee_name": o.employee_name,
            "approver_name": o.approver_name,
            "ot_date": o.ot_date.strftime("%Y-%m-%d"),
            "ot_type": o.ot_type,
            "ot_unit": o.ot_unit,
            "total_value": o.total_value,
            "status": o.status,
            "reason": o.reason,
            "attachment_path": full_attachment_url,
            "manager_remarks": o.manager_remarks or "",
            "status_history": convert_utc_string_to_kl(o.status_history) # 👈 FIXED: Localized timestamp
        })
        
    return formatted_results

@router.get("/balance")
def get_overtime_balance(
    employee_name: str,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(models.User).filter(
            or_(
                models.User.full_name == employee_name,
                models.User.username == employee_name
            )
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="Employee not found")

        return {
            "balance": float(user.overtime_bank or 0.0)
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"Error fetching overtime balance: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not load overtime balance")


