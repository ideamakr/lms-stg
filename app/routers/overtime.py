import os
import io # 👈 Added for image processing
import re
import tempfile
from datetime import date, datetime
from typing import Any, Optional
from pathlib import Path # 👈 Added for filename handling

# 🚀 CLEAN FASTAPI IMPORTS (Combined into one line)
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Query, BackgroundTasks, Body, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from pydantic import BaseModel
from PIL import Image # 👈 Added for image compression

from app.database import get_db
from app import models



def _find_user_by_name_or_username(db: Session, name: Optional[str]):
    if not name:
        return None

    cleaned = str(name).strip()
    if not cleaned:
        return None

    return db.query(models.User).filter(
        or_(
            models.User.full_name.ilike(cleaned),
            models.User.username.ilike(cleaned),
        )
    ).first()

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
        template_cancellation_request,      
        template_cancellation_approved,
        template_cancellation_rejected
    )
except ImportError:
    from app.utils.email_service import (
        send_email, 
        template_new_ot_request, 
        template_ot_decision,
        template_l2_ot_request
    )

router = APIRouter(prefix="/overtime", tags=["Overtime"])

# ✅ Schema for Cancellation Reason
class CancelRequestSchema(BaseModel):
    reason: Optional[str] = None

# 1. APPLY FOR OVERTIME (Cloud Native)
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
    applied_by: Optional[str] = Form(None), # 🚀 NEW: Captures HR Admin name
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    employee_name = employee_name.strip()
    approver_name = approver_name.strip()
    ot_date_obj = date.fromisoformat(ot_date)

    # A. Check Duplicates
    existing_ot = db.query(models.Overtime).filter(
        models.Overtime.employee_name == employee_name,
        models.Overtime.ot_date == ot_date_obj,
        models.Overtime.ot_type == ot_type,
        models.Overtime.status.in_(["Pending", "Approved", "Pending L2 Approval", "Pending Cancel"])
    ).first()

    if existing_ot:
        raise HTTPException(status_code=400, detail=f"Duplicate Request: {existing_ot.status} claim exists.")

# B. Local Upload Logic
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
            
            # Ensure the local directory exists
            target_dir = "uploads/mcs"
            os.makedirs(target_dir, exist_ok=True)
            
            # Define full path and save directly to disk with same compression
            file_path = f"{target_dir}/{clean_name}"
            img.save(file_path, format="JPEG", quality=60, optimize=True)
            
            # Keep exact assignment to prevent breaking Step D (Create Record)
            saved_filename = clean_name
            
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            raise HTTPException(status_code=500, detail="Could not upload attachment locally.")

    # C. Calculate Value
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
    new_ot = models.Overtime(
        employee_name=employee_name,
        approver_name=approver_name,
        ot_date=ot_date_obj,
        ot_type=ot_type,
        ot_unit=ot_unit,
        start_time=start_time,
        end_time=end_time,
        total_value=total_val,
        reason=reason,
        attachment_path=saved_filename,
        status="Pending",
        status_history=f"Submitted ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    )
    db.add(new_ot)
    db.commit()
    db.refresh(new_ot)

    # E. Email Manager (🚀 UPDATED FOR PROXY CONTEXT)
    manager = db.query(models.User).filter(models.User.full_name == approver_name).first()
    if manager and manager.email:
        try:
            # Determine if this was an override by Natasha/HR
            admin_name = applied_by if (applied_by and applied_by != employee_name) else None
            
            body = template_new_ot_request(
                manager_name=manager.full_name, 
                employee_name=employee_name, 
                ot_type=ot_type, 
                ot_date=ot_date, 
                duration=f"{total_val} {ot_unit}",
                admin_name=admin_name # Pass the HR Admin name to the template
            )
            background_tasks.add_task(send_email, manager.email, f"Action Required: OT Claim - {employee_name}", body)
            print(f"📧 OT Manager Notification queued for {manager.email}")
        except Exception as e:
            print(f"⚠️ OT Email Trigger Warning: {e}")

    return {"message": "Overtime request submitted successfully", "id": new_ot.id}


# 2. GET ALL REQUESTS (Admin Audit)
@router.get("/all-requests")
def get_all_overtime_requests(db: Session = Depends(get_db)):
    results = db.query(models.Overtime).order_by(models.Overtime.id.desc()).all()
    return [{
        "id": o.id,
        "employee_name": o.employee_name,
        "approver_name": o.approver_name,
        "ot_date": o.ot_date.strftime("%Y-%m-%d"),
        "ot_type": o.ot_type,
        "ot_unit": o.ot_unit,
        "total_value": o.total_value,
        "status": o.status,
        "reason": o.reason,
        "attachment_path": f"/uploads/mcs/{o.attachment_path}" if o.attachment_path else None,
        "manager_remarks": o.manager_remarks or "",
        "status_history": o.status_history or "Pending"
    } for o in results]

# 3. GET MANAGER PENDING & HISTORY REQUESTS (Unified)
@router.get("/manager-requests")
def get_manager_ot_requests(
    approver_name: str = Query(None),
    page: int = 1,
    page_size: int = 1000,
    db: Session = Depends(get_db),
    x_username: Optional[str] = Header(None)  # 👑 Intercept requester identity header
):
    # Check if the requester has authoritative Superuser privileges
    user = db.query(models.User).filter(models.User.username == x_username).first()
    is_super = user and user.role == "superuser"

    query = db.query(models.Overtime)
    
    # If the user is NOT a superuser, apply strict manager assignment constraints
    if not is_super:
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
    
    # 1. Initialize the empty list FIRST
    formatted_results = []
    
    # 2. START THE LOOP: This ensures 'o' is defined for every record
    for o in results:
        # 🚀 FIX: GENERATE LOCAL URL (Supabase code completely removed)
        full_attachment_url = o.attachment_path
        
        # If a file path exists and is not already a full URL or local path, point it to local uploads
        if full_attachment_url and not full_attachment_url.startswith(("/uploads", "http")):
            full_attachment_url = f"/uploads/mcs/{o.attachment_path}"

        # 3. APPEND TO LIST: Must be indented inside the loop
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
            "status_history": o.status_history or "Pending",
            
            # 👑 CRITICAL MATRIX INTERLOCK: Force 'is_my_turn' to True for Superusers 
            # This ensures they bypass frontend layout button-hiding filters completely!
            "is_my_turn": True if is_super else (o.approver_name == approver_name.strip() if approver_name else False)
        })
        
    # 4. RETURN OUTSIDE THE LOOP: Un-indent this line so it returns the full list
    return formatted_results


# 4. PROCESS MANAGER ACTION
@router.post("/manager-action/{ot_id}")
async def process_ot_action( 
    ot_id: int, 
    background_tasks: BackgroundTasks, 
    status: str, 
    remarks: str = "", 
    approver_name: str = "", 
    l2_name: str = Query(None), 
    db: Session = Depends(get_db),
    x_username: Optional[str] = Header(None)  # 👑 Intercept requester identity header
):
    try:
        from app.routers.leave import log_activity
    except ImportError:
        log_activity = None

    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT record not found")

    # 👑 Identify if an authoritative Superuser is executing this action
    acting_user = db.query(models.User).filter(models.User.username == x_username).first()
    is_superuser_override = acting_user and acting_user.role == "superuser"

    acting_mgr = _find_user_by_name_or_username(db, approver_name)
    is_senior = getattr(acting_mgr, 'is_senior_manager', False)
    is_l1 = bool(
        approver_name and ot.approver_name and
        str(approver_name).strip().lower() == str(ot.approver_name).strip().lower()
    )

    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    l2_active = policy.l2_approval_enabled if policy else False
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    current_status = ot.status
    route_to_l2 = False
    l2_user = None
    
    # 🛡️ THE AUDIT FIX: Pre-compile clean remarks tracking string to append into histories
    note_str = f" | Note: {remarks.strip()}" if remarks and remarks.strip() else ""
    
    user_record = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()

    is_cancellation_journey = (
        current_status == "Pending Cancel" or 
        "Cancellation" in (ot.status_history or "")
    )

# 👑 Set audit trail naming context based on authority level
    if is_superuser_override:
        display_approver = f"System Administrator (Override on behalf of {ot.approver_name or 'Manager'})"
    else:
        # Fallback Logic: Use parameter, else DB record, else generic "Manager"
        display_approver = (approver_name or ot.approver_name or "Manager").strip()

    # =========================================================
    # A. CANCELLATION LOGIC
    # =========================================================
    if is_cancellation_journey:
        if status == "Approved":
            # 👑 Superuser overrides bypass standard multi-stage routing loops to force instant resolution
            if current_status == "Pending Cancel" and l2_active and is_l1 and not is_senior and ot.approver_l2 and not is_superuser_override:
                ot.status = "Pending L2 Approval"
                ot.status_history += f" > L1 Approved Cancellation by {display_approver}. Routed to {ot.approver_l2} ({timestamp}){note_str}"
                db.commit()
                return {"message": "Cancellation approved by L1. Routed to L2."}
            
            if user_record:
                current_bank = float(user_record.overtime_bank or 0.0)
                user_record.overtime_bank = max(0, current_bank - float(ot.total_value or 0.0))

            ot.status = "Cancelled"
            ot.status_history += f" > Cancellation FINALIZED by {display_approver} ({timestamp}){note_str}"

        else:
            ot.status = "Approved"
            ot.status_history += f" > Cancellation REJECTED by {display_approver} ({timestamp}){note_str}"

# =========================================================
    # B. NORMAL APPROVAL LOGIC
    # =========================================================
    else:
        if status == "Approved":
            # 👑 Superuser overrides bypass the standard L2 routing step to allow instant clearance
            if l2_active and current_status in ["Pending", "Pending L2 Approval"] and not is_senior and not is_superuser_override:
                if l2_name:
                    ot.approver_name = l2_name 
                    ot.approver_l2 = l2_name
                    ot.status = "Pending L2 Approval"
                    # FIXED: Corrected the log string below
                    ot.status_history += f" > L1 Approved by {display_approver}. Routed to L2: {l2_name} ({timestamp}){note_str}"
                    route_to_l2 = True
                    l2_user = _find_user_by_name_or_username(db, l2_name)
                else:
                    # Final Approval Path when no L2 manager is supplied
                    if user_record:
                        current_bank = float(user_record.overtime_bank or 0.0)
                        user_record.overtime_bank = current_bank + float(ot.total_value or 0.0)

                    ot.status = "Approved"
                    ot.status_history += f" > Final Approval by {display_approver} ({timestamp}){note_str}"
            else:
                # Final Approval Path (No L2 needed, Senior Manager acting, or Admin Override)
                if user_record:
                    current_bank = float(user_record.overtime_bank or 0.0)
                    user_record.overtime_bank = current_bank + float(ot.total_value or 0.0)

                ot.status = "Approved"
                ot.status_history += f" > Final Approval by {display_approver} ({timestamp}){note_str}"

        elif status == "Rejected":
            ot.status = "Rejected"
            ot.status_history += f" > Rejected by {display_approver} ({timestamp}){note_str}"
            
    ot.manager_remarks = remarks
    db.commit() # 💾 Commit changes to the OT record

# 📧 --- 🚀 NOTIFY NEXT APPROVER OR EMPLOYEE OF THE DECISION ---
    if status == "Approved":
        # 🚀 STATE 1: L2 Routing
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
                background_tasks.add_task(send_email, l2_user.email, f"ACTION REQUIRED: Final Approval Needed - {ot.employee_name}", body)
            except Exception as e:
                print(f"⚠️ OT L2 Email Error: {e}")
        
        # 🚀 STATE 2: Final Approval (Employee Notification)
        elif not route_to_l2 and user_record and user_record.email:
            try:
                subject = f"✅ OT Claim APPROVED - {ot.ot_date}"
                body = template_ot_decision(ot.employee_name, display_approver, "Approved", ot.ot_type, str(ot.ot_date), remarks or "No remarks provided.")
                background_tasks.add_task(send_email, user_record.email, subject, body)
            except Exception as e:
                print(f"⚠️ OT Approval Email Error: {e}")

    # 🔴 STATE 3: Rejection (Employee Notification)
    elif status == "Rejected" and user_record and user_record.email:
        try:
            subject = f"❌ OT Claim REJECTED - {ot.ot_date}"
            body = template_ot_decision(ot.employee_name, display_approver, "Rejected", ot.ot_type, str(ot.ot_date), remarks or "No remarks provided.")
            background_tasks.add_task(send_email, user_record.email, subject, body)
        except Exception as e:
            print(f"⚠️ OT Rejection Email Error: {e}")

    # 🚀 Activity Log Sync
    if log_activity:
        try:
            act_type = "APPROVAL" if status == "Approved" else "REJECTION"
            msg_mgr = f"You {status.upper()} {ot.employee_name}'s OT Claim"
            actor_id = acting_user.id if is_superuser_override else (acting_mgr.id if acting_mgr else None)
            if actor_id:
                log_activity(db=db, user_id=actor_id, action_type=act_type, category="OT Claim", message=msg_mgr, reference_id=ot.id)
            if user_record:
                msg_emp = f"Your OT Claim was approved via administrative override" if is_superuser_override else f"Your OT Claim was {status.upper()}"
                log_activity(db=db, user_id=user_record.id, action_type=act_type, category="OT Claim", message=msg_emp, reference_id=ot.id, actor_id=actor_id)
            db.commit() 
        except Exception as e:
            print(f"⚠️ Activity Logging Failed: {e}")

    return {"message": "Action processed and OT bank updated.", "status": ot.status, "routed_to_l2": route_to_l2}


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

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    current_status = ot.status
    
    # Extract Reason safely
    reason_val = payload.reason if (payload and payload.reason) else "No reason provided"
    reason_text = f" (Reason: {reason_val})"

    # --- STATUS LOGIC ---

    # CASE A: WITHDRAWAL (Pending -> Withdrawn)
    if current_status in ["Pending", "Pending L2 Approval"]:
        ot.status = "Withdrawn"
        # 🚀 FIX: Handle None history safely
        ot.status_history = (ot.status_history or "") + f"\n > Withdrawn by Employee{reason_text} ({timestamp})"
        msg = "Overtime claim successfully withdrawn."
        
    # CASE B: CANCELLATION (Approved -> Pending Cancel)
    elif current_status == "Approved":
        ot.status = "Pending Cancel"
        ot.status_history = (ot.status_history or "") + f"\n > Cancellation Requested by Employee{reason_text} ({timestamp})"
        msg = "Cancellation request sent to manager."
        
        # Email Manager (Safely)
        try:
            manager = db.query(models.User).filter(models.User.full_name == ot.approver_name).first()
            # Ensure template exists before calling
            if manager and manager.email and 'template_cancellation_request' in globals():
                body = template_cancellation_request(
                    manager.full_name, 
                    ot.employee_name, 
                    f"Overtime ({ot.ot_type})", 
                    str(ot.ot_date), 
                    str(ot.ot_date), 
                    reason_val
                )
                background_tasks.add_task(send_email, manager.email, "Action Required: OT Cancellation", body)
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
            # 🚀 FIX: GENERATE LOCAL URL
            # If the path exists but doesn't start with 'http' or '/uploads', prepend local folder
            full_attachment_url = o.attachment_path
            if full_attachment_url and not full_attachment_url.startswith(("/uploads", "http")):
                full_attachment_url = f"/uploads/mcs/{o.attachment_path}"

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
                "attachment_path": full_attachment_url,
                "manager_remarks": o.manager_remarks or "",
                "status_history": o.status_history or "Pending"
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
        # 🚀 FIX: GENERATE LOCAL URL
        full_attachment_url = o.attachment_path
        if full_attachment_url and not full_attachment_url.startswith(("/uploads", "http")):
            full_attachment_url = f"/uploads/mcs/{o.attachment_path}"

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
            "status_history": o.status_history or "Pending"
        })
        
    return formatted_results