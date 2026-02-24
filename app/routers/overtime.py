import os
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Query, BackgroundTasks, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db
from app import models
from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel
import tempfile
import re

# ============================================================
# 🌍 GLOBAL CONFIGURATION
# ============================================================

if os.getenv("ENV") == "PROD":
    TARGET_DIR = "/var/www/uploads" 
else:
    TARGET_DIR = os.path.join(tempfile.gettempdir(), "leave_system_uploads")

if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR, exist_ok=True)

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

# ✅ Schema for Cancellation Reason (Required for JSON payload)
class CancelRequestSchema(BaseModel):
    reason: Optional[str] = None

# 1. APPLY FOR OVERTIME
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
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    employee_name = employee_name.strip()
    approver_name = approver_name.strip()
    ot_date_obj = date.fromisoformat(ot_date)

    # Check Duplicates
    existing_ot = db.query(models.Overtime).filter(
        models.Overtime.employee_name == employee_name,
        models.Overtime.ot_date == ot_date_obj,
        models.Overtime.ot_type == ot_type,
        models.Overtime.status.in_(["Pending", "Approved", "Pending L2 Approval", "Pending Cancel"])
    ).first()

    if existing_ot:
        raise HTTPException(status_code=400, detail=f"Duplicate Request: {existing_ot.status} claim exists.")

    # Save File
    saved_filename = None
    if file and file.filename:
        file_ext = os.path.splitext(file.filename)[1]
        date_stamp = ot_date.replace("-", "")
        time_stamp = datetime.now().strftime("%H%M%S")
        saved_filename = f"{employee_name}_OT_{date_stamp}_{time_stamp}{file_ext}"
        file_path = os.path.join(TARGET_DIR, saved_filename)
        try:
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        except Exception:
            raise HTTPException(status_code=500, detail="Could not save attachment.")

    # Calculate Value
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

    # Create Record
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

    # Email Manager
    manager = db.query(models.User).filter(models.User.full_name == approver_name).first()
    if manager and manager.email:
        body = template_new_ot_request(manager.full_name, employee_name, ot_type, ot_date, f"{total_val} {ot_unit}")
        background_tasks.add_task(send_email, manager.email, f"Action Required: OT Claim - {employee_name}", body)

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


# 3. GET MANAGER PENDING REQUESTS
@router.get("/manager-requests")
def get_manager_ot_requests(approver_name: str, db: Session = Depends(get_db)):
    # 🚀 ROBUST QUERY: Matches Leave Logic
    # Lane 1: L1 sees 'Pending' and 'Pending Cancel'
    # Lane 2: L2 sees 'Pending L2 Approval' ONLY
    results = db.query(models.Overtime).filter(
        or_(
            and_(
                models.Overtime.approver_name == approver_name, 
                models.Overtime.status.in_(["Pending", "Pending Cancel"])
            ),
            and_(
                models.Overtime.approver_l2 == approver_name, 
                models.Overtime.status == "Pending L2 Approval"
            )
        )
    ).all()
    
    return [{
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
        "attachment_path": o.attachment_path,
        "manager_remarks": o.manager_remarks or "",
        "status_history": o.status_history or "Pending"
    } for o in results]


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
    
    # 🚀 DETECT CANCELLATION JOURNEY (Deep Check)
    is_cancellation_journey = (
        current_status == "Pending Cancel" or 
        "Cancellation" in (ot.status_history or "")
    )

    # =========================================================
    # A. CANCELLATION LOGIC
    # =========================================================
    if is_cancellation_journey:
        if status == "Approved":
            # 1. Route to L2 if needed
            if current_status == "Pending Cancel" and l2_active and is_l1 and not is_senior and ot.approver_l2:
                ot.status = "Pending L2 Approval"
                ot.status_history += f" > L1 Approved Cancellation. Routed to {ot.approver_l2} ({timestamp})"
                db.commit()
                return {"message": "Cancellation approved by L1. Routed to L2."}
            
            # 2. Final Cancellation
            ot.status = "Cancelled"
            ot.status_history += f" > Cancellation FINALIZED by {approver_name} ({timestamp})"
            
            # Email Employee
            try:
                emp = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()
                if emp and emp.email and 'template_cancellation_approved' in globals():
                    body = template_cancellation_approved(ot.employee_name, approver_name, f"Overtime ({ot.ot_type})", str(ot.ot_date), str(ot.ot_date))
                    background_tasks.add_task(send_email, emp.email, "OT Cancellation Approved", body)
            except: pass

        else:
            # Rejection -> Revert to Approved
            ot.status = "Approved"
            ot.status_history += f" > Cancellation REJECTED by {approver_name} ({timestamp})"
            try:
                emp = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()
                if emp and emp.email and 'template_cancellation_rejected' in globals():
                    body = template_cancellation_rejected(ot.employee_name, approver_name, f"Overtime ({ot.ot_type})", str(ot.ot_date), str(ot.ot_date), remarks)
                    background_tasks.add_task(send_email, emp.email, "OT Cancellation Rejected", body)
            except: pass

    # =========================================================
    # B. NORMAL APPROVAL LOGIC
    # =========================================================
    else:
        if status == "Approved":
            # Route to L2
            if l2_active and current_status == "Pending" and not is_senior:
                if not l2_name:
                    raise HTTPException(status_code=400, detail="L2 Manager must be selected.")
                
                ot.status = "Pending L2 Approval"
                ot.approver_l2 = l2_name
                ot.status_history += f" > L1 Approved by {approver_name}. Routed to {l2_name} ({timestamp})"
                
                # Email L2
                l2_user = db.query(models.User).filter(models.User.full_name == l2_name).first()
                if l2_user and l2_user.email:
                    body = template_l2_ot_request(l2_name, approver_name, ot.employee_name, ot.ot_type, str(ot.ot_date), f"{ot.total_value} {ot.ot_unit}")
                    background_tasks.add_task(send_email, l2_user.email, f"Action Required: L2 OT Approval", body)

            else:
                # Final Approval
                ot.status = "Approved"
                ot.status_history += f" > Final Approval by {approver_name} ({timestamp})"
                
                # Email Employee
                try:
                    emp = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()
                    if emp and emp.email:
                        body = template_ot_decision(ot.employee_name, approver_name, ot.status, ot.ot_type, str(ot.ot_date), remarks or "No remarks.")
                        background_tasks.add_task(send_email, emp.email, f"✅ OT Claim Approved", body)
                except: pass

        elif status == "Rejected":
            ot.status = "Rejected"
            ot.status_history += f" > Rejected by {approver_name} ({timestamp})"
            
            # Email Employee
            try:
                emp = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()
                if emp and emp.email:
                    body = template_ot_decision(ot.employee_name, approver_name, ot.status, ot.ot_type, str(ot.ot_date), remarks or "No remarks.")
                    background_tasks.add_task(send_email, emp.email, f"❌ OT Claim Rejected", body)
            except: pass

    ot.manager_remarks = remarks
    db.commit()
    return {"message": "Action recorded successfully"}


# 5. CANCEL/WITHDRAW REQUEST
@router.put("/{ot_id}/cancel")
async def cancel_overtime_claim(
    ot_id: int, 
    background_tasks: BackgroundTasks,
    payload: CancelRequestSchema = Body(None), # 🚀 FIX: Accepts JSON Payload now
    db: Session = Depends(get_db)
):
    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT claim not found")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    current_status = ot.status
    
    # Extract Reason safely
    reason_val = payload.reason if (payload and payload.reason) else "No reason provided"
    reason_text = f" (Reason: {reason_val})"

    # 1. WITHDRAWAL (Pending)
    if current_status in ["Pending", "Pending L2 Approval"]:
        ot.status = "Withdrawn"
        ot.status_history += f" > Withdrawn by Employee{reason_text} ({timestamp})"
        db.commit()
        return {"message": "Overtime claim successfully withdrawn."}
    
    # 2. CANCELLATION REQUEST (Approved)
    # 🚀 FIX: Allows 'Approved' claims to be cancelled (Moves to Pending Cancel)
    elif current_status == "Approved":
        ot.status = "Pending Cancel"
        ot.status_history += f" > Cancellation Requested by Employee{reason_text} ({timestamp})"
        
        # Email Manager (Safely)
        try:
            manager = db.query(models.User).filter(models.User.full_name == ot.approver_name).first()
            if manager and manager.email and 'template_cancellation_request' in globals():
                body = template_cancellation_request(manager.full_name, ot.employee_name, f"Overtime ({ot.ot_type})", str(ot.ot_date), str(ot.ot_date), reason_val)
                background_tasks.add_task(send_email, manager.email, "OT Cancellation Request", body)
        except: pass
        
        db.commit()
        return {"message": "Cancellation request sent to manager."}
    
    raise HTTPException(status_code=400, detail="Cannot cancel this claim in its current state.")

@router.get("/my-requests")
def get_my_overtime_requests(employee_name: str, db: Session = Depends(get_db)):
    try:
        results = db.query(models.Overtime).filter(
            models.Overtime.employee_name == employee_name
        ).order_by(models.Overtime.ot_date.desc()).all()
        
        return [{
            "id": o.id,
            "employee_name": o.employee_name,
            "ot_date": o.ot_date.strftime("%Y-%m-%d"),
            "ot_type": o.ot_type,
            "ot_unit": o.ot_unit,
            "total_value": o.total_value,
            "status": o.status,
            "reason": o.reason,
            "approver_name": o.approver_name,
            "attachment_path": o.attachment_path, 
            "manager_remarks": o.manager_remarks or "",
            "status_history": o.status_history or "Pending"
        } for o in results]
    except Exception as e:
        print(f"Error fetching personal OT history: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not load overtime history")