import os
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Query, BackgroundTasks # 🚀 Added BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db
from app import models
from datetime import date, datetime
from typing import Any
import tempfile

# ============================================================
# 🌍 GLOBAL CONFIGURATION (Environment Aware)
# ============================================================

if os.getenv("ENV") == "PROD":
    TARGET_DIR = "/var/www/uploads" 
else:
    TARGET_DIR = os.path.join(tempfile.gettempdir(), "leave_system_uploads")

if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR, exist_ok=True)

from app.utils.email_service import (
    send_email, 
    template_new_ot_request, 
    template_ot_decision,
    template_l2_ot_request
)

router = APIRouter(prefix="/overtime", tags=["Overtime"])


# 1. APPLY FOR OVERTIME
@router.post("/apply")
async def apply_overtime(
    background_tasks: BackgroundTasks, # 🚀 INJECTED: Background worker
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
    # --- 1. SANITIZE & PARSE ---
    employee_name = employee_name.strip()
    approver_name = approver_name.strip()
    ot_date_obj = date.fromisoformat(ot_date)

    # --- 2. DUPLICATE CHECK ---
    existing_ot = db.query(models.Overtime).filter(
        models.Overtime.employee_name == employee_name,
        models.Overtime.ot_date == ot_date_obj,
        models.Overtime.ot_type == ot_type,
        models.Overtime.status.in_(["Pending", "Approved", "Pending L2 Approval", "Pending Cancel"])
    ).first()

    if existing_ot:
        raise HTTPException(
            status_code=400, 
            detail=f"Duplicate Request: You already have a {existing_ot.status} claim for this date and type."
        )

    # --- 3. FILE HANDLING ---
    saved_filename = None
    if file and file.filename:
        file_ext = os.path.splitext(file.filename)[1]
        date_stamp = ot_date.replace("-", "")
        time_stamp = datetime.now().strftime("%H%M%S")
        saved_filename = f"{employee_name}_OT_{date_stamp}_{time_stamp}{file_ext}"
        
        file_path = os.path.join(TARGET_DIR, saved_filename)
        
        try:
            if not os.path.exists(TARGET_DIR):
                os.makedirs(TARGET_DIR, exist_ok=True)
                
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Could not save OT attachment.")

    # --- 4. DURATION CALCULATION ---
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
            raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    # --- 5. SAVE RECORD ---
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

    # --- 6. EMAIL TRIGGER (Background Queue) ---
    manager = db.query(models.User).filter(models.User.full_name == approver_name).first()
    if manager and manager.email:
        duration_str = f"{total_val} {ot_unit}"
        body = template_new_ot_request(
            manager_name=manager.full_name, 
            employee_name=employee_name, 
            ot_type=ot_type, 
            ot_date=ot_date, 
            duration=duration_str
        )
        # 🚀 Send via background task instantly
        background_tasks.add_task(send_email, manager.email, f"Action Required: OT Claim from {employee_name}", body)

    return {"message": "Overtime request submitted successfully", "id": new_ot.id}


# 2. GET ALL OT REQUESTS (Audit Log)
@router.get("/all-requests")
def get_all_overtime_requests(db: Session = Depends(get_db)):
    try:
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
    except Exception as e:
        print(f"Audit Log Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# 3. GET MANAGER'S PENDING TASKS
@router.get("/manager-requests")
def get_manager_ot_requests(approver_name: str, db: Session = Depends(get_db)):
    # Shows L1 tasks (Pending) AND L2 tasks (Pending L2 Approval)
    results = db.query(models.Overtime).filter(
        or_(
            and_(models.Overtime.approver_name == approver_name, models.Overtime.status == "Pending"),
            and_(models.Overtime.approver_l2 == approver_name, models.Overtime.status == "Pending L2 Approval")
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


# 4. PROCESS MANAGER ACTION (Approve/Reject)
@router.post("/manager-action/{ot_id}")
async def process_ot_action( # 🚀 Changed to async
    ot_id: int, 
    background_tasks: BackgroundTasks, # 🚀 INJECTED: Background worker
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

    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    l2_active = policy.l2_approval_enabled if policy else False
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    current_status = ot.status
    send_employee_email = False 

    # --- 2. HANDLE APPROVALS ---
    if status == "Approved":
        # Route to L2
        if l2_active and current_status == "Pending" and not is_senior:
            if not l2_name:
                raise HTTPException(status_code=400, detail="L2 Manager must be selected.")
            
            ot.status = "Pending L2 Approval"
            ot.approver_l2 = l2_name
            ot.status_history += f" > L1 Approved by {approver_name}. Routed to {l2_name} ({timestamp})"
            
            # 🚀 EMAIL TO L2 MANAGER (Background Task)
            l2_user = db.query(models.User).filter(models.User.full_name == l2_name).first()
            if l2_user and l2_user.email:
                duration_str = f"{ot.total_value} {ot.ot_unit}"
                body = template_l2_ot_request(
                    l2_manager_name=l2_name,
                    l1_manager_name=approver_name,
                    employee_name=ot.employee_name,
                    ot_type=ot.ot_type,
                    ot_date=str(ot.ot_date),
                    duration=duration_str
                )
                background_tasks.add_task(send_email, l2_user.email, f"Action Required: L2 OT Approval for {ot.employee_name}", body)

        else:
            # Final Approval
            ot.status = "Approved"
            ot.status_history += f" > Final Approval by {approver_name} ({timestamp})"
            send_employee_email = True 
            
    # --- 3. HANDLE REJECTIONS ---
    elif status == "Rejected":
        ot.status = "Rejected"
        ot.status_history += f" > Rejected by {approver_name} ({timestamp})"
        send_employee_email = True 

    ot.manager_remarks = remarks
    db.commit()

    # 🚀 EMAIL TO EMPLOYEE (Background Task)
    if send_employee_email:
        employee = db.query(models.User).filter(models.User.full_name == ot.employee_name).first()
        if employee and employee.email:
            body = template_ot_decision(
                ot.employee_name,
                approver_name,
                ot.status,
                ot.ot_type,
                str(ot.ot_date),
                remarks or "No remarks provided."
            )
            subject_icon = "✅" if ot.status == "Approved" else "❌"
            background_tasks.add_task(send_email, employee.email, f"{subject_icon} OT Claim {ot.status}", body)

    return {"message": f"Action recorded successfully"}


@router.put("/{ot_id}/cancel")
def cancel_overtime_claim(ot_id: int, db: Session = Depends(get_db)):
    ot = db.query(models.Overtime).filter(models.Overtime.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT claim not found")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Withdrawal from Employee (No email needed as it just deletes a pending request)
    if ot.status in ["Pending", "Pending L2 Approval"]:
        ot.status = "Withdrawn"
        ot.status_history += f" > Withdrawn by Employee ({timestamp})"
        db.commit()
        return {"message": "Overtime claim successfully withdrawn."}
    
    raise HTTPException(status_code=400, detail="Only pending or partially approved claims can be withdrawn.")

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