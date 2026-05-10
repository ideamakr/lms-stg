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
from supabase import create_client, Client # 👈 Added for Cloud Uploads

from app.database import get_db
from app import models

# ============================================================
# 🌍 GLOBAL CONFIGURATION
# ============================================================

# Initialize Supabase Client (Independent of main.py to avoid circular imports)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

    # B. Cloud Upload Logic
    saved_filename = None
    if file and file.filename:
        try:
            contents = await file.read()
            img = Image.open(io.BytesIO(contents))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=60, optimize=True)
            compressed_data = output.getvalue()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_filename = Path(file.filename).stem 
            clean_name = f"{timestamp}_{clean_filename.replace(' ', '_')}.jpg"
            storage_path = f"mcs/{clean_name}"

            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=storage_path,
                file=compressed_data,
                file_options={"content-type": "image/jpeg"}
            )
            saved_filename = clean_name
            
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            raise HTTPException(status_code=500, detail="Could not upload attachment.")

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
        "attachment_path": o.attachment_path,
        "manager_remarks": o.manager_remarks or "",
        "status_history": o.status_history or "Pending"
    } for o in results]

# 3. GET MANAGER PENDING & HISTORY REQUESTS (Unified)
@router.get("/manager-requests")
def get_manager_ot_requests(approver_name: str, db: Session = Depends(get_db)):
    # 🚀 THE FIX: Return ALL requests the manager has interacted with!
    # The frontend inbox will automatically filter out only the "Pending" ones,
    # while the Activity Log will use the full history to show past approvals.
    results = db.query(models.Overtime).filter(
        or_(
            models.Overtime.approver_name.ilike(approver_name.strip()),
            models.Overtime.approver_l2.ilike(approver_name.strip()),
            models.Overtime.status_history.ilike(f"%{approver_name.strip()}%") 
        )
    ).order_by(models.Overtime.id.desc()).all()
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

    formatted_results = []
    for o in results:
        # FIX: GENERATE FULL CLOUD URL
        full_attachment_url = o.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{o.attachment_path}"

        formatted_results.append({
            "id": o.id,
            "employee_name": o.employee_name,
            "approver_name": o.approver_name,
            "approver_l2": o.approver_l2,
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

# 4. PROCESS MANAGER ACTION
@router.post("/manager-action/{ot_id}")
async def process_ot_action( 
    ot_id: int, 
    background_tasks: BackgroundTasks, 
    status: str, 
    remarks: str = "", 
    approver_name: str = "", 
    l2_name: str = Query(None), 
    db: Session = Depends(get_db)
):
    try:
        from app.routers.leave import log_activity
    except ImportError:
        log_activity = None

    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT record not found")

    acting_mgr = db.query(models.User).filter(models.User.full_name == approver_name).first()
    is_senior = getattr(acting_mgr, 'is_senior_manager', False)
    is_l1 = (approver_name == ot.approver_name)

    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    l2_active = policy.l2_approval_enabled if policy else False
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    current_status = ot.status
    
    user_record = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()

    is_cancellation_journey = (
        current_status == "Pending Cancel" or 
        "Cancellation" in (ot.status_history or "")
    )

    # =========================================================
    # A. CANCELLATION LOGIC
    # =========================================================
    if is_cancellation_journey:
        if status == "Approved":
            if current_status == "Pending Cancel" and l2_active and is_l1 and not is_senior and ot.approver_l2:
                ot.status = "Pending L2 Approval"
                ot.status_history += f" > L1 Approved Cancellation. Routed to {ot.approver_l2} ({timestamp})"
                db.commit()
                # If you want L2 notification, it would go here
                return {"message": "Cancellation approved by L1. Routed to L2."}
            
            if user_record:
                current_bank = float(user_record.overtime_bank or 0.0)
                user_record.overtime_bank = max(0, current_bank - float(ot.total_value or 0.0))

            ot.status = "Cancelled"
            ot.status_history += f" > Cancellation FINALIZED by {approver_name} ({timestamp})"

        else:
            ot.status = "Approved"
            ot.status_history += f" > Cancellation REJECTED by {approver_name} ({timestamp})"

    # =========================================================
    # B. NORMAL APPROVAL LOGIC
    # =========================================================
    else:
        if status == "Approved":
            if l2_active and current_status == "Pending" and not is_senior:
                if not l2_name:
                    raise HTTPException(status_code=400, detail="L2 Manager must be selected.")
                ot.status = "Pending L2 Approval"
                ot.approver_l2 = l2_name
                ot.status_history += f" > L1 Approved by {approver_name}. Routed to {l2_name} ({timestamp})"
            else:
                if user_record:
                    current_bank = float(user_record.overtime_bank or 0.0)
                    user_record.overtime_bank = current_bank + float(ot.total_value or 0.0)

                ot.status = "Approved"
                ot.status_history += f" > Final Approval by {approver_name} ({timestamp})"

        elif status == "Rejected":
            ot.status = "Rejected"
            ot.status_history += f" > Rejected by {approver_name} ({timestamp})"

    ot.manager_remarks = remarks
    db.commit() # 💾 Commit changes to the OT record first

    # 📧 --- 🚀 NEW: NOTIFY EMPLOYEE OF THE DECISION (The Merged Fix) ---
    if user_record and user_record.email:
        try:
            status_icon = "✅" if status == "Approved" else "❌"
            display_status = status
            
            # Labeling for cancellations
            if is_cancellation_journey:
                display_status = f"Cancellation {status}"
                status_icon = "✅" if status == "Approved" else "⚠️"

            subject = f"{status_icon} OT Claim {display_status.upper()} - {ot.ot_date}"
            
            body = template_ot_decision(
                employee_name=ot.employee_name,
                manager_name=approver_name,
                status=display_status,
                ot_type=ot.ot_type,
                ot_date=str(ot.ot_date),
                remarks=remarks or "No remarks provided."
            )
            background_tasks.add_task(send_email, user_record.email, subject, body)
            print(f"📧 OT Decision email queued for employee: {user_record.email}")
        except Exception as e:
            print(f"⚠️ OT Decision Email Error: {e}")

    # 🚀 Activity Log Sync
    if log_activity and acting_mgr:
        try:
            act_type = "APPROVAL" if status == "Approved" else "REJECTION"
            msg_mgr = f"You {status.upper()} {ot.employee_name}'s OT Claim"
            log_activity(db=db, user_id=acting_mgr.id, action_type=act_type, category="OT Claim", message=msg_mgr, reference_id=ot.id)
            
            if user_record:
                msg_emp = f"Your OT Claim was {status.upper()}"
                log_activity(db=db, user_id=user_record.id, action_type=act_type, category="OT Claim", message=msg_emp, reference_id=ot.id, actor_id=acting_mgr.id)
            db.commit() # Save the logs
        except Exception as e:
            print(f"⚠️ Activity Logging Failed: {e}")

    return {"message": "Action processed and OT bank updated."}


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
        
        # 🛡️ PREPARE SUPABASE CONSTANTS
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

        formatted_results = []
        for o in results:
            # 🚀 FIX: GENERATE FULL CLOUD URL
            # If the path exists but doesn't start with 'http', we assume it's a filename in the 'mcs' folder
            full_attachment_url = o.attachment_path
            if full_attachment_url and not full_attachment_url.startswith("http"):
                full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{o.attachment_path}"

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
                "attachment_path": full_attachment_url, # 👈 Send the fixed URL
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
    db: Session = Depends(get_db)
):
    query = db.query(models.Overtime)
    
    # 1. RBAC: Managers only see what they touched. Admins see all.
    if "hr_admin" not in user_role.lower():
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
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

    formatted_results = []
    for o in results:
        full_attachment_url = o.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{o.attachment_path}"

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