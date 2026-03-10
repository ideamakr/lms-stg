import os
import math
import pandas as pd
import re
import tempfile
from typing import Union, Optional, List
from datetime import date, datetime 

# 🚀 FastAPI, Security & Background Tasks
from fastapi import APIRouter, Depends, HTTPException, Form, Query, Body, UploadFile, File, BackgroundTasks, Header
from sqlalchemy import func, or_, and_, desc, text, extract
from sqlalchemy.orm import Session
from pydantic import BaseModel 

# 📦 Local App Modules
from app import models
from app.database import SessionLocal
from app.dependencies import validate_session

# 📧 Email Utilities
# Robust import strategy to handle different environment paths
try:
    from app.utils.email_service import (
        send_email, 
        template_new_request,
        template_medical_request,
        template_request_approved,
        template_request_rejected,
        template_l2_request,
        template_cancellation_request,
        template_l2_cancellation_request,
        template_cancellation_approved,
        template_cancellation_rejected
    )
except ImportError:
    # Fallback for local testing
    from utils.email_service import (
        send_email, 
        template_new_request,
        template_medical_request,
        template_request_approved,
        template_request_rejected,
        template_l2_request,
        template_cancellation_request,
        template_l2_cancellation_request,
        template_cancellation_approved,
        template_cancellation_rejected
    )

# ============================================================
# 🏗️ ROUTER & SCHEMAS
# ============================================================
class CancelRequestSchema(BaseModel):
    reason: Optional[str] = None

router = APIRouter(prefix="/leaves", tags=["Leaves"])

# 🛠️ Database Dependency (Ensures a fresh session for every request)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 🚀 V1.5.1: THE ULTIMATE SPLIT-WALLET ENGINE (UNIFIED SYNC)
def _calculate_shared_balance(db: Session, employee_name: str, year: int, leave_type: str, include_pending: bool = False):
    import re
    from sqlalchemy import extract
    from datetime import date, datetime
    
    # 1. Bucket Mapping
    shared_annual_bucket = ["Annual Leave", "Emergency Leave", "Claim Carry Forward"]
    
    if leave_type in shared_annual_bucket:
        target_entitlement_type = "Annual Leave"
        types_to_scan = shared_annual_bucket
    else:
        target_entitlement_type = leave_type
        types_to_scan = [leave_type]

    balance_entry = db.query(models.LeaveBalance).filter(
        models.LeaveBalance.employee_name == employee_name,
        models.LeaveBalance.year == year,
        models.LeaveBalance.leave_type == target_entitlement_type
    ).first()

    if not balance_entry: return None

    # Fetch all active records
    active_statuses = ["Approved", "Pending", "Pending Cancel", "Pending L2 Approval"]
    used_leaves = db.query(models.Leave).filter(
        models.Leave.employee_name == employee_name,
        models.Leave.leave_type.in_(types_to_scan),
        models.Leave.status.in_(active_statuses),
        extract('year', models.Leave.start_date) == year
    ).all()

    # 📊 INDEPENDENT WALLET COUNTERS
    spent_annual = 0.0  
    spent_cf = 0.0      
    approved_taken_total = 0.0
    pending_total = 0.0

    for l in used_leaves:
        days = float(l.days_taken or 0.0)
        l_type = str(l.leave_type.value if hasattr(l.leave_type, 'value') else l.leave_type)
        status_str = str(l.status.value if hasattr(l.status, 'value') else l.status)
        
        if l_type == "Claim Carry Forward":
            spent_cf += days
        elif l_type in ["Annual Leave", "Emergency Leave"]:
            if "[CARRY FORWARD" in (l.reason or ""):
                match = re.search(r"\[CARRY FORWARD:\s*([\d\.]+)\s*DAYS\]", l.reason)
                cf_part = float(match.group(1)) if match else days
                spent_cf += cf_part
                spent_annual += max(0, days - cf_part)
            else:
                spent_annual += days
        else:
            spent_annual += days

        if status_str in ["Pending", "Pending L2 Approval"]:
            pending_total += days
        elif status_str in ["Approved", "Pending Cancel"]:
            approved_taken_total += days

    # --- 4. 🛡️ EXPIRY SYNC (Unified with Cleanup Script) ---
    base_entitlement = float(balance_entry.entitlement or 0.0)
    cf_banked = float(balance_entry.carry_forward_total or 0.0)
    today = datetime.now().date()
    
    # 🚀 The Fix: Read from the main 'carry_forward' settings JSON
    settings = db.query(models.SystemSetting).filter(models.SystemSetting.key == "carry_forward").first()
    
    expiry_date = None
    if settings and settings.value.get("expiry_date"):
        try:
            # Use the date from your Admin Settings toggle
            expiry_date = date.fromisoformat(settings.value["expiry_date"])
        except:
            expiry_date = date(year, 3, 23) # Fallback
    else:
        expiry_date = date(year, 3, 23)

    # 🛑 If today is past the deadline, unrequested days "vanish" from the display
    if today > expiry_date:
        cf_banked = spent_cf

    # 5. FINAL CALCULATION
    annual_remaining = base_entitlement - spent_annual
    cf_remaining = cf_banked - spent_cf

    return {
        "employee_name": employee_name,
        "year": year,
        "leave_type": target_entitlement_type,
        "entitlement": base_entitlement, 
        "carry_forward_total": max(0, cf_remaining), 
        "remaining": annual_remaining,                
        "taken": approved_taken_total,
        "pending_total": pending_total
    }

@router.get("/balance")
def get_leave_balance(
    employee_name: str, 
    year: int, 
    leave_type: str, 
    db: Session = Depends(get_db),
    user: models.User = Depends(validate_session) 
):
    # 🚀 AUTOMATIC TRIGGER: Run cleanup check every time a balance is requested.
    # This ensures that as soon as the clock strikes midnight on the expiry day,
    # the very next person to view a dashboard triggers the cleanup for everyone.
    check_and_wipe_expired_cf(db)

    # 1. First, ensure the year is initialized (2026 fix)
    ensure_leave_balance(db, employee_name, year)
    
    # 2. Then calculate the math
    balance = _calculate_shared_balance(db, employee_name, year, leave_type)
    
    if not balance:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    
    return balance

# --- 2. UPDATED CREATE LEAVE: STRICT VALIDATION (V1.4.9 FINAL) ---
@router.post("/")
async def create_leave(
    background_tasks: BackgroundTasks, 
    employee_name: str = Form(...), 
    approver_name: str = Form(...),
    leave_type: str = Form(...),
    start_date: str = Form(...), 
    end_date: str = Form(...),
    reason: str = Form(...), 
    is_half_day: Union[bool, str] = Form(False),
    file: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    # 1. SANITIZE & PARSE
    employee_name = employee_name.strip()
    approver_name = approver_name.strip()
    leave_type = leave_type.strip()
    start_obj = date.fromisoformat(start_date)
    end_obj = date.fromisoformat(end_date)
    is_half_day_bool = is_half_day in (True, "true")

    # 2. DUPLICATE / OVERLAP CHECK
    collision = db.query(models.Leave).filter(
        models.Leave.employee_name == employee_name,
        models.Leave.status.in_(["Pending", "Pending L2 Approval", "Approved", "Pending Cancel"]),
        models.Leave.start_date <= end_obj,
        models.Leave.end_date >= start_obj
    ).first()

    if collision:
        is_cf = "[CARRY FORWARD" in (collision.reason or "")
        type_label = "Carry Forward" if is_cf else "Leave"
        raise HTTPException(
            status_code=400, 
            detail=f"Duplicate Request: You already have a {type_label} request ({collision.status}) from {collision.start_date} to {collision.end_date}."
        )

    # 3. CALENDAR & HOLIDAY VALIDATION
    holidays = db.query(models.PublicHoliday).all()
    holiday_dates = [h.holiday_date for h in holidays]
    for check_date in [start_obj, end_obj]:
        if check_date.weekday() >= 5:
            raise HTTPException(status_code=400, detail=f"Selection Error: {check_date} is a weekend.")
        if check_date in holiday_dates:
            raise HTTPException(status_code=400, detail=f"Conflict: {check_date} is a Public Holiday.")

    # 4. CALCULATE DURATION
    if is_half_day_bool:
        days_requested = 0.5
        end_obj = start_obj
    else:
        all_dates = pd.date_range(start=start_obj, end=end_obj)
        working_days = [d for d in all_dates if d.weekday() < 5 and d.date() not in holiday_dates]
        days_requested = float(len(working_days))

    # --- 5. 🛡️ HARD WALLET LOCKDOWN (THE FIX) ---
    current_year = start_obj.year
    balance = _calculate_shared_balance(db, employee_name, current_year, leave_type, include_pending=True)
    
    if not balance:
        raise HTTPException(status_code=404, detail="Balance record not found.")

    # 🎯 ROUTING: Determine which specific bucket we are emptying
    if leave_type == "Claim Carry Forward":
        wallet_available = float(balance.get("carry_forward_total", 0))
        wallet_name = "Carry Forward"
    elif leave_type == "Unpaid Leave":
        wallet_available = 999.0  # Unpaid is infinite
        wallet_name = "Unpaid"
    else:
        wallet_available = float(balance.get("remaining", 0))
        wallet_name = "Annual/Medical"

    # 🛑 THE BLOCK: Prevent overspending the specific wallet
    if days_requested > wallet_available:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient {wallet_name} Balance: You requested {days_requested} days, but only {wallet_available} days are available."
        )

    # 🛡️ Special Case: Stop Annual Leave from "bleeding" into Carry Forward
    if leave_type == "Annual Leave" and days_requested > float(balance.get("remaining", 0)):
         raise HTTPException(
            status_code=400, 
            detail=f"Insufficient Annual Leave: You only have {balance.get('remaining')} days left. Please use 'Claim Carry Forward' to spend banked days."
        )

    # --- 6. FILE HANDLING (Safe Cloud Upload) ---
    attachment_url = None 
    if file and file.filename:
        try:
            from app.main import compress_and_upload
            attachment_url = compress_and_upload(file, folder="mcs")
        except Exception as e:
            raise HTTPException(status_code=500, detail="System Error: Failed to upload attachment.")

    # --- 7. SAVE RECORD ---
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    is_cf_request = (leave_type == "Claim Carry Forward")
    
    new_leave = models.Leave(
        employee_name=employee_name, 
        approver_name=approver_name, 
        leave_type=leave_type,
        start_date=start_obj, 
        end_date=end_obj, 
        reason=reason, 
        days_taken=days_requested,
        attachment_path=attachment_url,
        status="Pending", 
        status_history=f"Submitted ({now_str})"
    )
    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)

    # --- 8. EMAIL NOTIFICATION ---
    manager = db.query(models.User).filter(models.User.full_name == approver_name).first()
    if manager and manager.email:
        display_type = "Carry Forward" if is_cf_request else leave_type
        subject = f"ACTION REQUIRED: New {display_type} Request - {employee_name}"
        # (Using standard template for both to keep it clean)
        body = template_new_request(manager.full_name, employee_name, display_type, start_date, end_date, days_requested)
        background_tasks.add_task(send_email, manager.email, subject, body)

    return new_leave

# --- 3. MISSING ENDPOINT: BALANCE HISTORY ---
@router.get("/manager/balance-history")
def get_balance_history(db: Session = Depends(get_db), name: str = ""):
    current_year = datetime.now().year
    
    # 1. Fetch Balances
    balances = db.query(models.LeaveBalance).filter(
        models.LeaveBalance.employee_name == name,
        models.LeaveBalance.year == current_year
    ).all()
    
    entitlements = [{"type": b.leave_type.value if hasattr(b.leave_type, 'value') else str(b.leave_type), 
                     "days": b.entitlement} for b in balances]

    # 2. Fetch Leave History
    # 🚀 FIX: Changed to 'desc()' so latest leaves appear at the top
    leaves = db.query(models.Leave).filter(
        models.Leave.employee_name == name,
        models.Leave.start_date.cast(models.String).contains(str(current_year))
    ).order_by(models.Leave.start_date.desc()).all()

    # 3. Calculate Unpaid Total
    unpaid_sum = db.query(func.sum(models.Leave.days_taken)).filter(
        models.Leave.employee_name == name,
        models.Leave.leave_type == "Unpaid Leave",
        models.Leave.status == "Approved",
        models.Leave.start_date.cast(models.String).contains(str(current_year))
    ).scalar() or 0.0

    # 4. Process Logs & Calculate CF Total
    cf_total = 0.0
    history = []
    
    for l in leaves:
        raw_status = l.status.value if hasattr(l.status, 'value') else str(l.status)
        history_str = l.status_history or ""
        reason_str = l.reason or ""
        
        # Default Action Type & Days
        action_type = "Leave Request"
        is_cf = False
        display_days = l.days_taken or 0.0 

        # 🅰️ Check if this is a Carry Forward Request
        if "[CARRY FORWARD" in reason_str:
            action_type = "Carry Forward Request"
            is_cf = True
            
            # Extract the REAL amount
            match = re.search(r"\[CARRY FORWARD:\s*([\d\.]+)\s*DAYS\]", reason_str)
            if match:
                real_cf_val = float(match.group(1))
                display_days = real_cf_val 
                
                if raw_status == "Approved":
                    cf_total += real_cf_val

        # 🅱️ Check for Cancellations
        if "Cancellation Approved" in history_str or "Cancellation Rejected" in history_str:
            action_type = "Cancellation Request"
        elif "Pending Cancel" in history_str:
            action_type = "Cancellation Request"
        elif raw_status == "Cancelled" and "Approved" not in history_str:
            action_type = "Withdrawn Request"

        # Determine Display Status
        display_status = raw_status
        if raw_status == "Cancelled" and "Approved" not in history_str:
            display_status = "Withdrawn"
        elif "Cancellation Rejected" in history_str and raw_status == "Approved":
            display_status = "Cancel Rejected"

        history.append({
            "date": l.start_date.strftime("%Y-%m-%d"),
            "action": action_type, 
            "leave_id": f"{l.id:03d}",
            "leave_type": l.leave_type.value if hasattr(l.leave_type, 'value') else str(l.leave_type),
            "days": display_days,
            "status": display_status,
            "reason": l.reason,
            "is_cf": is_cf 
        })

    return {
        "entitlements": entitlements,
        "logs": history,
        "unpaid_total": unpaid_sum,
        "cf_total": cf_total
    }

import os # 👈 Make sure this is imported at the top

@router.get("/history")
def get_leave_history(
    employee_name: str, 
    db: Session = Depends(get_db), 
    page: int = 1, 
    page_size: int = 10,
    start_date: str = Query(None),
    end_date: str = Query(None),
    leave_type: str = Query(None),
    status: str = Query(None),
    duration: str = Query(None)
):
    skip = (page - 1) * page_size
    
    # 1. Base query
    query = db.query(models.Leave).filter(models.Leave.employee_name == employee_name)
    
    # 2. Precise Date Filtering
    if start_date and start_date.strip():
        try:
            target_start = datetime.strptime(start_date, "%Y-%m-%d").date() # Safer parsing
            query = query.filter(models.Leave.start_date == target_start)
        except ValueError:
            pass 

    if end_date and end_date.strip():
        try:
            target_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(models.Leave.end_date == target_end)
        except ValueError:
            pass
        
    # 3. Apply other dynamic filters
    if leave_type and leave_type.strip() not in ["Any", ""]:
        query = query.filter(models.Leave.leave_type == leave_type)
        
    if status and status.strip() not in ["All Status", "All", ""]:
        query = query.filter(models.Leave.status == status)
        
    if duration and duration.strip():
        try:
            query = query.filter(models.Leave.days_taken == float(duration))
        except ValueError:
            pass 

    # 4. Pagination Totals
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    
    # 5. Fetch records (Sorted Newest First)
    leaves = query.order_by(
        models.Leave.start_date.desc(), 
        models.Leave.id.desc()
    ).offset(skip).limit(page_size).all()
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    # We grab these once to build the URL efficiently
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")
    
    # 6. Formatted response
    formatted = []
    for l in leaves:
        l_type = l.leave_type.value if hasattr(l.leave_type, 'value') else str(l.leave_type)
        l_status = l.status.value if hasattr(l.status, 'value') else str(l.status)
        
        # 🚀 FIX: GENERATE FULL CLOUD URL
        # If the path exists but doesn't start with 'http', we assume it's a filename in the 'mcs' folder
        full_attachment_url = l.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{l.attachment_path}"

        formatted.append({
            "id": l.id, 
            "employee_name": l.employee_name,
            "approver_name": l.approver_name,
            "days_taken": l.days_taken, 
            "reason": l.reason or "No reason provided",
            "leave_type": l_type,
            "status": l_status,
            "start_date": l.start_date.strftime("%Y-%m-%d") if l.start_date else "N/A",
            "end_date": l.end_date.strftime("%Y-%m-%d") if l.end_date else "N/A",
            "attachment_path": full_attachment_url, # 👈 Send the fixed URL
            "status_history": l.status_history or "Pending",
            "approved_at": l.approved_at.strftime("%Y-%m-%d %H:%M") if l.approved_at else None,
            "rejected_at": l.rejected_at.strftime("%Y-%m-%d %H:%M") if l.rejected_at else None,
            "cancelled_at": l.cancelled_at.strftime("%Y-%m-%d %H:%M") if l.cancelled_at else None
        })

    return {
        "total_records": total, 
        "total_pages": total_pages, 
        "leaves": formatted
    }

# --- 5. CANCELLATION LOGIC (SECURED) ---
@router.put("/{leave_id}/cancel")
async def cancel_leave_request(
    leave_id: int, 
    background_tasks: BackgroundTasks, 
    payload: CancelRequestSchema = Body(None),
    db: Session = Depends(get_db),
    x_username: str = Header(None) # 🔒 SECURITY BADGE
):
    # 1. Security Check
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    leave = db.query(models.Leave).filter(models.Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    # 2. Ownership Verification
    current_user = db.query(models.User).filter(models.User.username == x_username).first()
    
    # Block if not owner AND not superuser
    if not current_user or (leave.employee_name != current_user.full_name and current_user.role != "superuser"):
        raise HTTPException(status_code=403, detail="You do not have permission to cancel this leave.")

    current_status = leave.status
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Format reason
    reason_val = payload.reason if (payload and payload.reason) else "No reason provided"
    reason_text = f" (Reason: {reason_val})"

    # --- STATUS LOGIC ---
    
    # CASE A: WITHDRAWAL (Pending -> Withdrawn)
    if current_status == "Pending":
        leave.status = "Withdrawn"
        leave.status_history = (leave.status_history or "") + f"\n > Withdrawn by Employee ({timestamp})"
        msg = "Request has been successfully withdrawn."
        
    # CASE B: CANCELLATION (Approved -> Pending Cancel)
    elif current_status in ["Approved", "Pending L2 Approval"]:
        leave.status = "Pending Cancel"
        leave.status_history = (leave.status_history or "") + f"\n > Cancellation Requested by Employee{reason_text} ({timestamp})"
        msg = "Cancellation request sent to manager for review."

        # 🚀 EMAIL NOTIFICATION
        manager = db.query(models.User).filter(models.User.full_name == leave.approver_name).first()
        
        if manager and manager.email:
            # Safe enum conversion
            l_type = leave.leave_type.value if hasattr(leave.leave_type, 'value') else str(leave.leave_type)
            
            subject = f"ACTION REQUIRED: Cancellation Request - {leave.employee_name}"
            body = template_cancellation_request(
                manager.full_name,
                leave.employee_name,
                l_type,
                leave.start_date.strftime("%Y-%m-%d"),
                leave.end_date.strftime("%Y-%m-%d"),
                reason_val
            )
            background_tasks.add_task(send_email, manager.email, subject, body)

    else:
        raise HTTPException(status_code=400, detail="Request state cannot be modified.")
    
    try:
        db.commit()
        return {"message": msg}
    except Exception as e:
        db.rollback()
        print(f"Error cancelling leave: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
# app/routers/leave.py

# 🚀 Ensure these are imported at the top

# ============================================================
# 7. MANAGER & ADMIN VIEWS
# ============================================================

@router.get("/manager/pending")
def get_manager_pending(
    approver_name: str, 
    db: Session = Depends(get_db), 
    page: int = 1, 
    page_size: int = 10,
    name: str = "",         
    date_str: str = "",     
    end_date: str = "",     
    leave_type: str = "",   
    status: str = "",
):
    # 1. Base Query: Matches Lane 1 (L1) and Lane 2 (L2) logic
    query = db.query(models.Leave).filter(
        or_(
            and_(models.Leave.approver_name == approver_name, models.Leave.status.in_(["Pending", "Pending Cancel"])),
            and_(models.Leave.approver_l2 == approver_name, models.Leave.status == "Pending L2 Approval")
        )
    )

    # 2. Filters
    if name: query = query.filter(models.Leave.employee_name.ilike(f"%{name}%"))
    if date_str: query = query.filter(models.Leave.start_date.cast(models.String).ilike(f"%{date_str}%"))
    if end_date: query = query.filter(models.Leave.end_date.cast(models.String).ilike(f"%{end_date}%"))
    if leave_type: query = query.filter(models.Leave.leave_type == leave_type)
    if status: query = query.filter(models.Leave.status == status)
    
    total_count = query.count()
    results = query.order_by(models.Leave.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

    formatted_results = []
    for r in results:
        # 🚀 FIX: GENERATE FULL CLOUD URL
        full_attachment_url = r.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{r.attachment_path}"

        formatted_results.append({
            "id": r.id,
            "employee_name": r.employee_name,
            "approver_name": r.approver_name,
            "approver_l2": r.approver_l2, # Critical for UI to show "Routed to..."
            "leave_type": str(r.leave_type.value) if hasattr(r.leave_type, 'value') else str(r.leave_type),
            "status": str(r.status.value) if hasattr(r.status, 'value') else str(r.status),
            "days_taken": r.days_taken,
            "start_date": r.start_date.strftime("%Y-%m-%d"),
            "end_date": r.end_date.strftime("%Y-%m-%d"),
            "reason": r.reason,
            "attachment_path": full_attachment_url, # 👈 Send the fixed URL
            "status_history": r.status_history or "Pending"
        })
    
    return {
        "total": total_count,
        "requests": formatted_results
    }



@router.get("/admin/fix-db-schema")
def fix_db_schema(db: Session = Depends(get_db)):
    messages = []
    # 1. Fix Leaves Table
    try:
        db.execute(text("ALTER TABLE leaves ADD COLUMN approver_l2 VARCHAR"))
        messages.append("✅ Leaves table updated.")
    except Exception:
        messages.append("ℹ️ Leaves table already updated.")

    # 2. Fix Overtime Table
    try:
        db.execute(text("ALTER TABLE overtime_claims ADD COLUMN approver_l2 VARCHAR"))
        messages.append("✅ Overtime table updated.")
    except Exception:
        messages.append("ℹ️ Overtime table already updated.")

    try:
        db.commit()
        return {"status": "success", "log": messages}
    except Exception as e:
        db.rollback()
        return {"status": "error", "detail": str(e)}




# app/routers/leave.py

@router.post("/manager/action/{leave_id}")
async def approve_leave( 
    leave_id: int, 
    background_tasks: BackgroundTasks, 
    status: str = Query(...),       
    remarks: str = Query(""),       
    approver_name: str = Query(""), 
    l2_name: str = Query(None), 
    db: Session = Depends(get_db)
):
    leave = db.query(models.Leave).filter(models.Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")

    # 1. Manager Identity & Permissions
    acting_mgr = db.query(models.User).filter(models.User.full_name == approver_name).first()
    is_senior = acting_mgr.is_senior_manager if acting_mgr else False
    is_l1 = (approver_name == leave.approver_name)
    
    # 2. Get Global Policy for L2 Toggle
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    l2_active = policy.l2_approval_enabled if policy else False

    # 3. 📝 PREPARE VARIABLES
    current_status = leave.status
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_str = f" | Note: {remarks}" if remarks else ""
    l_type_str = str(leave.leave_type.value) if hasattr(leave.leave_type, 'value') else str(leave.leave_type)

    # 🕵️ CRITICAL FIX: DETECT CANCELLATION JOURNEY
    # We check if this is a cancellation flow by looking at status OR history.
    # This ensures that even if status is "Pending L2 Approval", we know it's a cancellation.
    history_log = leave.status_history or ""
    is_cancellation_journey = (
        current_status == "Pending Cancel" or 
        "Cancellation" in history_log or
        "Request Cancellation" in history_log
    )

    # =========================================================================
    # 4. HANDLE CANCELLATION LOGIC (For BOTH L1 and L2 Stages)
    # =========================================================================
    if is_cancellation_journey:
        if status == "Approved":
            # 🚀 SUPER-ADMIN OVERRIDE
            is_hr_admin = acting_mgr and (acting_mgr.role == "hr_admin" or any(r.role_name == "hr_admin" for r in acting_mgr.assigned_roles))

            # 🔶 SCENARIO A: L1 Approves Cancellation -> Route to L2 (Only if L2 is active & required)
            # Logic: If we are strictly at L1 stage ("Pending Cancel") AND L2 is required
            if current_status == "Pending Cancel" and not is_hr_admin and l2_active and is_l1 and not is_senior and leave.approver_l2:
                l2_user = db.query(models.User).filter(models.User.full_name == leave.approver_l2).first()
                l2_still_valid = l2_user and l2_user.is_active and l2_user.is_senior_manager

                if l2_still_valid:
                    # Log History and Route
                    leave.status = "Pending L2 Approval"
                    leave.status_history += f" > L1 Approved Cancellation. Routed to {leave.approver_l2} ({timestamp}){note_str}"
                    
                    # 📧 Notify L2 Manager
                    try:
                        if l2_user.email:
                            body = template_l2_cancellation_request(
                                l2_manager_name=l2_user.full_name, 
                                l1_manager_name=approver_name, 
                                employee_name=leave.employee_name, 
                                type=l_type_str, 
                                start=str(leave.start_date), 
                                end=str(leave.end_date)
                            )
                            background_tasks.add_task(send_email, l2_user.email, f"ACTION REQUIRED: L2 Cancellation - {leave.employee_name}", body)
                    except Exception as e:
                        print(f"⚠️ Email Error (L2 Route): {e}")

                    db.commit()
                    return {"message": "Cancellation approved by L1. Routed to L2."}
                
            # 🟢 SCENARIO B: Final Cancellation 
            # This executes if:
            # 1. It is L1 but L2 is OFF
            # 2. It is L1 but User is Senior
            # 3. It is already at L2 ("Pending L2 Approval") <-- THIS FIXES YOUR BUG
            leave.status = "Cancelled"
            admin_note = " by HR Admin" if is_hr_admin else ""
            leave.status_history += f" > Cancellation FINALIZED{admin_note} by {approver_name} ({timestamp}){note_str}"
            
            # 📧 Notify Employee
            try:
                emp = db.query(models.User).filter(models.User.full_name == leave.employee_name).first()
                if emp and emp.email:
                    body = template_cancellation_approved(leave.employee_name, approver_name, l_type_str, str(leave.start_date), str(leave.end_date))
                    background_tasks.add_task(send_email, emp.email, f"Leave Cancelled: {l_type_str}", body)
            except Exception as e:
                print(f"⚠️ Email Error (Final Cancel): {e}")

        else:
            # 🔴 SCENARIO C: Cancellation Rejected (Revert to Approved)
            # If ANYONE rejects the cancellation, it goes back to being an Active Approved Leave
            leave.status = "Approved" 
            leave.status_history += f" > Cancellation REJECTED by {approver_name} ({timestamp}){note_str}"
            
            # 📧 Notify Employee
            try:
                emp = db.query(models.User).filter(models.User.full_name == leave.employee_name).first()
                if emp and emp.email:
                    body = template_cancellation_rejected(leave.employee_name, approver_name, l_type_str, str(leave.start_date), str(leave.end_date), remarks)
                    background_tasks.add_task(send_email, emp.email, f"Cancellation Denied: {l_type_str}", body)
            except Exception as e:
                print(f"⚠️ Email Error (Cancel Reject): {e}")

    # =========================================================================
    # 5. HANDLE NORMAL LEAVE REQUESTS (Pending -> Approved/Rejected)
    # =========================================================================
    else:
        if status == "Approved":
            # 🔶 L1 Approval -> Route to L2
            if l2_name: 
                leave.status = "Pending L2 Approval"
                leave.approver_l2 = l2_name
                leave.status_history += f" > L1 Approved. Routed to {l2_name} ({timestamp}){note_str}"
                
                # Notify L2
                try:
                    l2_user = db.query(models.User).filter(models.User.full_name == l2_name).first()
                    if l2_user and l2_user.email:
                        body = template_l2_request(l2_name, approver_name, leave.employee_name, l_type_str, str(leave.start_date), str(leave.end_date))
                        background_tasks.add_task(send_email, l2_user.email, f"ACTION REQUIRED: L2 Approval - {leave.employee_name}", body)
                except Exception as e:
                    print(f"⚠️ Email Error (Normal L2): {e}")

            # 🟢 Final Approval
            else: 
                leave.status = "Approved"
                leave.approved_at = datetime.now()
                leave.status_history += f" > Fully Approved by {approver_name} ({timestamp}){note_str}"
                
                # Notify Employee
                try:
                    emp = db.query(models.User).filter(models.User.full_name == leave.employee_name).first()
                    if emp and emp.email:
                        body = template_request_approved(leave.employee_name, approver_name, l_type_str, str(leave.start_date), str(leave.end_date))
                        background_tasks.add_task(send_email, emp.email, f"Leave Approved: {l_type_str}", body)
                except Exception as e:
                    print(f"⚠️ Email Error (Normal Approve): {e}")

        else: 
            # 🔴 Rejection
            leave.status = "Rejected"
            leave.rejected_at = datetime.now()
            leave.status_history += f" > Rejected by {approver_name} ({timestamp}){note_str}"

            # Notify Employee
            try:
                emp = db.query(models.User).filter(models.User.full_name == leave.employee_name).first()
                if emp and emp.email:
                    body = template_request_rejected(leave.employee_name, approver_name, l_type_str, str(leave.start_date), str(leave.end_date), remarks)
                    background_tasks.add_task(send_email, emp.email, f"Leave Rejected: {l_type_str}", body)
            except Exception as e:
                print(f"⚠️ Email Error (Normal Reject): {e}")

    db.commit()
    return {"message": "Request processed successfully"}


@router.get("/manager/all")
def get_all_manager_leaves(
    user_role: str,         
    approver_name: str = None, 
    name: str = "", 
    status: str = Query("", alias="status"), 
    date_str: str = Query(None), 
    db: Session = Depends(get_db)
):
    query = db.query(models.Leave)
    
    # 1. RBAC: Managers only see what they touched. Admins see all.
    if "hr_admin" not in user_role.lower():
        if approver_name:
            query = query.filter(
                or_(
                    models.Leave.approver_name.ilike(approver_name.strip()),
                    models.Leave.approver_l2.ilike(approver_name.strip()),
                    models.Leave.status_history.ilike(f"%{approver_name.strip()}%") 
                )
            )
        else:
            return {"requests": []}
    
    if name: query = query.filter(models.Leave.employee_name.ilike(f"%{name.strip()}%"))
    if date_str:
        try: query = query.filter(models.Leave.start_date == date.fromisoformat(date_str))
        except: pass
    if status and status not in ["All", "All Decisions", ""]:
        query = query.filter(models.Leave.status == status)
        
    results = query.order_by(models.Leave.id.desc()).all()
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

    formatted = []
    for r in results:
        # 🚀 FIX: GENERATE FULL CLOUD URL
        full_attachment_url = r.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{r.attachment_path}"

        formatted.append({
            "id": r.id,
            "employee_name": r.employee_name,
            "approver_name": r.approver_name,
            "approver_l2": r.approver_l2,
            "leave_type": str(r.leave_type.value) if hasattr(r.leave_type, 'value') else str(r.leave_type),
            "days_taken": r.days_taken,
            "start_date": r.start_date.strftime("%Y-%m-%d"),
            "end_date": r.end_date.strftime("%Y-%m-%d"),
            "status": str(r.status.value) if hasattr(r.status, 'value') else str(r.status),
            "attachment_path": full_attachment_url, # 👈 Send the fixed URL
            "status_history": r.status_history or "Pending"
        })

    return {"requests": formatted}

# Admin Query table
@router.get("/admin/query/{table_name}")
def admin_table_query(table_name: str, db: Session = Depends(get_db)):
    """
    A maintenance endpoint to perform 'SELECT *' on various tables.
    Usage: /leaves/admin/query/leaves
    """
    # Mapping the URL string to your SQLAlchemy models
    table_mapper = {
        "leaves": models.Leave,
        "balances": models.LeaveBalance,
        "holidays": models.PublicHoliday
    }

    model = table_mapper.get(table_name.lower())
    
    if not model:
        raise HTTPException(
            status_code=404, 
            detail=f"Table '{table_name}' not found. Available: leaves, balances, holidays"
        )

    # Performs the equivalent of SELECT * FROM table ORDER BY id DESC
    try:
        # Check if the model has an 'id' attribute for ordering
        if hasattr(model, 'id'):
            results = db.query(model).order_by(model.id.desc()).all()
        else:
            results = db.query(model).all()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/admin/entitlements-bulk")
def get_all_entitlements(db: Session = Depends(get_db)):
    # This single query joins Users, Leave Types, and Entitlements
    # It calculates everything in the database, not in Python loops.
    sql = text("""
        SELECT 
            u.id as employee_id,
            u.full_name,
            u.status,
            lt.name as leave_type,
            e.total_days,
            e.carried_forward,
            COALESCE(SUM(CASE WHEN l.status = 'approved' THEN l.total_days ELSE 0 END), 0) as used_days
        FROM users u
        CROSS JOIN leave_types lt
        LEFT JOIN entitlements e ON u.id = e.user_id AND lt.id = e.leave_type_id
        LEFT JOIN leaves l ON u.id = l.user_id AND lt.id = l.leave_type_id AND l.year = 2026
        WHERE u.status = 'active'
        GROUP BY u.id, lt.id, e.id
    """)
    result = db.execute(sql).mappings().all()
    return result
    
    
@router.get("/manager/entitlements")
@router.get("/admin/entitlements")
def get_team_entitlements(
    user_role: str,          
    approver_name: str,      
    db: Session = Depends(get_db), 
    name: str = ""
):
    current_year = datetime.now().year
    
    # 1. Standardize Inputs
    role_clean = user_role.lower().strip()
    approver_clean = approver_name.strip()

    # 2. 🔍 DATABASE OVERRIDE: Check if user is actually an Admin
    requester = db.query(models.User).filter(models.User.full_name == approver_clean).first()
    if requester:
        user_roles_list = [r.role_name for r in requester.assigned_roles] if hasattr(requester, 'assigned_roles') else []
        if requester.role == "hr_admin" or "hr_admin" in user_roles_list:
            role_clean = "hr_admin"

    # 3. RBAC Check
    allowed_roles = ["hr_admin", "manager", "payroll", "payroll_approver"]
    if role_clean not in allowed_roles:
        return []

    # 4. Define Query Scope
    users_query = db.query(models.User)
    if role_clean != "hr_admin":
        managed_by_profile = db.query(models.User.full_name).filter(models.User.line_manager == approver_clean).all()
        staff_list = [s[0] for s in managed_by_profile]
        submitted_to_mgr = db.query(models.Leave.employee_name).filter(models.Leave.approver_name == approver_clean).distinct().all()
        for s in submitted_to_mgr:
            if s[0] not in staff_list: staff_list.append(s[0])
        
        if not staff_list: return [] 
        users_query = users_query.filter(models.User.full_name.in_(staff_list))

    if name:
        users_query = users_query.filter(models.User.full_name.ilike(f"%{name}%"))
    
    try:
        users = users_query.all()
        if not users: return []
            
        user_names = [u.full_name for u in users]

        # 🚀 Bulk Fetch Balances and Leaves for Performance
        all_balances = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name.in_(user_names),
            models.LeaveBalance.year == current_year
        ).all()
        
        active_statuses = ["Approved", "Pending", "Pending Cancel", "Pending L2 Approval"]
        all_leaves = db.query(models.Leave).filter(
            models.Leave.employee_name.in_(user_names),
            models.Leave.status.in_(active_statuses),
            extract('year', models.Leave.start_date) == current_year
        ).all()

        policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
        defaults = {
            "Annual Leave": policy.annual_days if policy else 14.0,
            "Medical Leave": policy.medical_days if policy else 14.0,
            "Emergency Leave": policy.emergency_days if policy else 2.0,
            "Compassionate Leave": policy.compassionate_days if policy else 3.0
        }
        
        # 🗺️ Map data for quick O(1) lookup
        bal_map = {uname: [] for uname in user_names}
        for b in all_balances: bal_map[b.employee_name].append(b)
            
        leave_map = {uname: [] for uname in user_names}
        for l in all_leaves: leave_map[l.employee_name].append(l)

        results = []

        # 🚀 START LOOP (Indented inside try block)
        for u in users:
            emp_name = u.full_name
            u_bals = bal_map.get(emp_name, [])
            u_leaves = leave_map.get(emp_name, [])

            # 🛠️ INTERNAL CALCULATOR
            def get_bucket(l_type):
                b = next((x for x in u_bals if str(getattr(x.leave_type, 'value', x.leave_type)) == l_type), None)
                ent = float(b.entitlement or 0.0) if b else defaults.get(l_type, 0.0)
                cf_banked = float(b.carry_forward_total or 0.0) if b else 0.0
                
                shared_annual_bucket = ["Annual Leave", "Emergency Leave", "Claim Carry Forward"]
                types_to_count = shared_annual_bucket if l_type == "Annual Leave" else [l_type]
                
                spent_annual = 0.0
                spent_cf = 0.0
                
                for l in u_leaves:
                    l_type_str = str(getattr(l.leave_type, 'value', l.leave_type))
                    if l_type_str in types_to_count:
                        days = float(l.days_taken or 0.0)
                        
                        if l_type_str == "Claim Carry Forward":
                            spent_cf += days
                        elif l_type_str in ["Annual Leave", "Emergency Leave"]:
                            if "[CARRY FORWARD" in (l.reason or ""):
                                match = re.search(r"\[CARRY FORWARD:\s*([\d\.]+)\s*DAYS\]", l.reason)
                                cf_p = float(match.group(1)) if match else days
                                spent_cf += cf_p
                                spent_annual += max(0, days - cf_p)
                            else:
                                spent_annual += days
                        else:
                            spent_annual += days
                            
                return {
                    "ent": ent, 
                    "cf_rem": max(0, cf_banked - spent_cf), 
                    "rem": ent - spent_annual
                }

            ann = get_bucket("Annual Leave")
            med = get_bucket("Medical Leave")
            
            unpaid_taken = sum(float(l.days_taken or 0.0) for l in u_leaves 
                               if str(getattr(l.leave_type, 'value', l.leave_type)) == "Unpaid Leave" 
                               and str(getattr(l.status, 'value', l.status)) == "Approved")

            results.append({
                "name": emp_name,
                "status": "Active" if u.is_active else "Inactive",
                "is_active": u.is_active,
                "annual_remaining": ann["rem"],
                "annual_entitlement": ann["ent"],
                "medical_remaining": med["rem"],
                "medical_entitlement": med["ent"],
                "unpaid_taken": unpaid_taken,
                "carry_forward_total": ann["cf_rem"],
                "overtime_bank": float(getattr(u, 'overtime_bank', 0) or 0)
            })
            
        return results

    except Exception as e:
        print(f"❌ Database Query Error: {e}")
        import traceback
        traceback.print_exc() # This will help you see the exact line if it fails again
        raise HTTPException(status_code=500, detail="Failed to fetch balances")


@router.get("/approvers")
def get_approvers(db: Session = Depends(get_db)):
    """
    Fetches all active users with 'manager' or 'hr_admin' roles.
    This populates the 'Select Approver' dropdown on the frontend.
    """
    # 🚀 HIGH-FIDELITY FILTER: Using ILIKE ensures 'Manager' and 'manager' both work.
    approvers = db.query(models.User).filter(
        or_(
            models.User.role.ilike("manager"),
            models.User.role.ilike("hr_admin")
        ),
        models.User.is_active == True
    ).all()
    
    # Safety Fallback: if no specific roles found, show the first 10 users to prevent empty UI
    if not approvers:
        approvers = db.query(models.User).limit(10).all()
        
    return [{"full_name": a.full_name} for a in approvers]


# =========================================================================
# ⚙️ PUBLIC HOLIDAYS (Fixed 405 Method Not Allowed)
# =========================================================================

# 1. 🚀 ADDED GET: Fetch the list (This resolves the 405 error)
@router.get("/public-holidays")
def get_public_holidays(db: Session = Depends(get_db)):
    return db.query(models.PublicHoliday).order_by(models.PublicHoliday.holiday_date).all()

# 1. 🚀 BUG-FREE ADD ROUTE
@router.post("/public-holidays")
def add_public_holiday(
    holiday_date: str = Form(...), 
    name: str = Form(...), 
    states: str = Form("All States"), # 🟢 Catches the state!
    db: Session = Depends(get_db)     # 🟢 CORRECT DEPENDENCY: Connects to database!
):
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="Holiday name cannot exceed 50 characters.")
    try:
        date_obj = date.fromisoformat(holiday_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    new_holiday = models.PublicHoliday(
        holiday_date=date_obj, 
        name=name,
        states=states 
    )
    db.add(new_holiday)
    db.commit()
    return {"message": f"Holiday '{name}' added successfully."}

@router.delete("/public-holidays/{holiday_id}")
def delete_public_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.query(models.PublicHoliday).filter(models.PublicHoliday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    db.delete(holiday)
    db.commit()
    return {"message": "Holiday deleted"}

@router.get("/public-calendar")
def get_public_calendar(db: Session = Depends(get_db)):
    # 🚀 FIX: Use string comparison "Approved" to match saved data
    leaves = db.query(models.Leave).filter(models.Leave.status == "Approved").all()
    public_data = []
    for l in leaves:
        public_data.append({
            "employee_name": l.employee_name,
            "start_date": str(l.start_date),
            "end_date": str(l.end_date),
            "leave_type": l.leave_type.value if hasattr(l.leave_type, 'value') else str(l.leave_type)
        })
    return public_data

@router.get("/admin/audit-logs")
def get_global_audit_logs(db: Session = Depends(get_db)):
    """Fetches all leave requests for the System Audit Log (HR Admin only)."""
    results = db.query(models.Leave).order_by(models.Leave.id.desc()).all()
    
    # 🛡️ PREPARE SUPABASE CONSTANTS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET")

    formatted = []
    for l in results:
        # 🚀 FIX: GENERATE FULL CLOUD URL
        full_attachment_url = l.attachment_path
        if full_attachment_url and not full_attachment_url.startswith("http"):
            full_attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/mcs/{l.attachment_path}"

        formatted.append({
            "id": l.id,
            "employee_name": l.employee_name,
            "approver_name": l.approver_name,
            "leave_type": l.leave_type.value if hasattr(l.leave_type, 'value') else str(l.leave_type),
            "days_taken": l.days_taken,
            "start_date": l.start_date.strftime("%Y-%m-%d"),
            "end_date": l.end_date.strftime("%Y-%m-%d"),
            "status": l.status.value if hasattr(l.status, 'value') else str(l.status),
            "attachment_path": full_attachment_url, # 👈 Sends the valid link now
            "status_history": l.status_history or "Pending"
        })
    
    return formatted

# 2. 🚀 BUG-FREE EDIT ROUTE
@router.put("/public-holidays/{holiday_id}")
def update_public_holiday(
    holiday_id: int,
    name: str = Form(...),
    holiday_date: str = Form(...),
    states: Optional[str] = Form(None), # 🟢 Catches edits safely!
    db: Session = Depends(get_db)       # 🟢 CORRECT DEPENDENCY!
):
    holiday = db.query(models.PublicHoliday).filter(models.PublicHoliday.id == holiday_id).first()
    
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday record not found")

    try:
        holiday.name = name
        holiday.holiday_date = date.fromisoformat(holiday_date)
        
        if states is not None:
            holiday.states = states 
        
        db.commit()
        return {"message": "Holiday updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Update failed: {str(e)}")
    
    # --- NEW: GLOBAL POLICY ENDPOINTS ---

@router.get("/admin/policy")
def get_policy(db: Session = Depends(get_db)):
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    if not policy:
        return {"annual": 14, "medical": 14, "emergency": 2, "compassionate": 3, "l2_enabled": False}
    return {
        "annual": policy.annual_days,
        "medical": policy.medical_days,
        "emergency": policy.emergency_days,
        "compassionate": policy.compassionate_days,
        "l2_enabled": policy.l2_approval_enabled
    }

@router.post("/admin/policy")
def update_policy(settings: dict = Body(...), db: Session = Depends(get_db)):
    # 1. Fetch or create the master policy record
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    if not policy:
        # Initialize with hardcoded defaults if DB is empty
        policy = models.GlobalPolicy(
            id=1, 
            annual_days=14.0, 
            medical_days=14.0, 
            emergency_days=2.0, 
            compassionate_days=3.0,
            l2_approval_enabled=False
        )
        db.add(policy)
    
    # 2. Update Standard Days (Safely handle settings vs current DB values)
    policy.annual_days = settings.get("annual", policy.annual_days)
    policy.medical_days = settings.get("medical", policy.medical_days)
    policy.emergency_days = settings.get("emergency", policy.emergency_days)
    policy.compassionate_days = settings.get("compassionate", policy.compassionate_days)

    # 3. Save L2 Switch State
    if "l2_enabled" in settings:
        policy.l2_approval_enabled = settings["l2_enabled"]
    
    # Commit policy changes first to ensure values are saved
    db.commit()
    db.refresh(policy)

    # 4. 🚀 SYNC LOGIC with None-Safety
    current_year = datetime.now().year
    sync_map = [
        ("Annual Leave", policy.annual_days),
        ("Medical Leave", policy.medical_days),
        ("Emergency Leave", policy.emergency_days),
        ("Compassionate Leave", policy.compassionate_days)
    ]

    for l_type_str, new_val in sync_map:
        # 🛡️ THE FIX: Only attempt float conversion if new_val is not None
        if new_val is not None:
            try:
                db.query(models.LeaveBalance).filter(
                    models.LeaveBalance.year == current_year,
                    models.LeaveBalance.leave_type == l_type_str
                ).update({"entitlement": float(new_val)}, synchronize_session=False)
            except (ValueError, TypeError) as e:
                print(f"⚠️ Sync skipped for {l_type_str}: Invalid value {new_val}")
    
    db.commit()
    return {"message": "Global policy updated and synced for all employees."}

@router.post("/admin/adjust-individual")
def adjust_individual_balance(data: dict = Body(...), db: Session = Depends(get_db)):
    name = data.get("employee_name")
    year = data.get("year")
    
    types_mapping = {
        "Annual Leave": data.get("annual"),
        "Medical Leave": data.get("medical"),
        "Emergency Leave": data.get("emergency"),
        "Compassionate Leave": data.get("compassionate")
    }
    
    for leave_type, days in types_mapping.items():
        if days is None: continue 
        
        balance = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == name,
            models.LeaveBalance.year == year,
            models.LeaveBalance.leave_type == leave_type
        ).first()
        
        if balance:
            balance.entitlement = float(days)
        else:
            # Create if missing
            new_bal = models.LeaveBalance(
                employee_name=name,
                year=year,
                leave_type=leave_type,
                entitlement=float(days),
                remaining=float(days),
                carry_forward_total=0.0
            )
            db.add(new_bal)
            
    db.commit()
    return {"message": f"Successfully updated balances for {name}"}

# ============================================================
# 📊 HR ADMIN: REPORTING & AUDIT
# ============================================================

def ensure_leave_balance(db: Session, employee_name: str, year: int):
    """
    Ensures a complete set of leave buckets exists for the employee.
    If any specific bucket is missing, it creates it with the correct initial remaining days.
    """
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    
    defaults = [
        ("Annual Leave", policy.annual_days if policy else 14.0),
        ("Medical Leave", policy.medical_days if policy else 14.0),
        ("Emergency Leave", policy.emergency_days if policy else 2.0),
        ("Compassionate Leave", policy.compassionate_days if policy else 3.0),
        ("Unpaid Leave", 0.0) 
    ]

    for l_type, days in defaults:
        type_exists = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == employee_name,
            models.LeaveBalance.year == year,
            or_(
                models.LeaveBalance.leave_type == l_type,
                models.LeaveBalance.leave_type == models.LeaveType[l_type.upper().split()[0]] if hasattr(models, 'LeaveType') else False
            )
        ).first()

        if not type_exists:
            # 🚀 Refinement: Explicitly set remaining = days so user starts with a full wallet
            db.add(models.LeaveBalance(
                employee_name=employee_name,
                leave_type=l_type, 
                year=year,
                entitlement=float(days),
                remaining=float(days), # 👈 Ensure this matches entitlement
                carry_forward_total=0.0
            ))
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ ensure_leave_balance error: {e}")

# 2. Update your existing get_leave_balance endpoint

# --- HR ADMIN: USER ONBOARDING SYNC ---

@router.post("/admin/sync-new-user")
def sync_new_user(full_name: str, db: Session = Depends(get_db)):
    """
    Called immediately after a new user is registered.
    Ensures their leave 'wallet' is initialized with the current Global Policy.
    """
    # 1. Normalize the name to prevent trailing space mismatches
    clean_name = full_name.strip()
    current_year = datetime.now().year

    # 2. Use your existing helper to check/create the balances
    # This helper already looks at GlobalPolicy and sets up Annual, Medical, etc.
    try:
        ensure_leave_balance(db, clean_name, current_year)
        return {"status": "success", "message": f"Balances initialized for {clean_name}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Sync Logic Error: {str(e)}")
    
# --- HR ADMIN: L2 WORKFLOW PRE-FLIGHT CHECK ---

@router.get("/admin/l2-check")
def check_pending_l2(db: Session = Depends(get_db)):
    """
    Finds all requests currently at the L2 stage. 
    Used by Admin to prevent 'orphaning' requests when turning L2 OFF.
    """
    # 🚀 FIX: Query using the explicit string to match saved data
    pending = db.query(models.Leave).filter(
        models.Leave.status == "Pending L2 Approval"
    ).all()
    
    return [{
        "id": p.id,
        "employee_name": p.employee_name,
        # Safe handling of Enum or String for leave_type
        "leave_type": str(p.leave_type.value) if hasattr(p.leave_type, 'value') else str(p.leave_type),
        "start_date": p.start_date.strftime("%Y-%m-%d") if p.start_date else "N/A",
        "status": str(p.status)
    } for p in pending]



# =========================================================================
# 🚀 HR ADMIN: CARRY FORWARD (CF) PROCESSING ENGINE
# =========================================================================

@router.get("/cf-processing-list")
def get_cf_processing_list(
    name: str = "",
    year: str = "",
    status: str = "Pending",
    db: Session = Depends(get_db)
):
    import re
    # 1. Fetch all requests with the CF tag
    query = db.query(models.Leave).filter(models.Leave.reason.like("%[CARRY FORWARD:%"))
    
    if name:
        query = query.filter(models.Leave.employee_name.ilike(f"%{name}%"))
        
    cf_requests = query.all()
    result = []
    
    for req in cf_requests:
        # Filter out invalid states
        if req.status in ["Pending", "Rejected", "Cancelled", "Withdrawn"]:
            continue
            
        match = re.search(r"\[CARRY FORWARD:\s*([\d\.]+)\s*DAYS\]", req.reason or "")
        cf_days = float(match.group(1)) if match else 0.0
        
        origin_year = req.start_date.strftime("%Y") if req.start_date else str(datetime.now().year)
        target_year = str(int(origin_year) + 1)
        
        is_merged = (req.status == "Merged")
        
        # UI Filtering logic
        if status == "Pending" and is_merged: continue
        if status == "Merged" and not is_merged: continue
        if year and year != "All" and origin_year != year: continue
        
        target_balance = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == req.employee_name,
            models.LeaveBalance.year == int(target_year),
            models.LeaveBalance.leave_type == "Annual Leave"
        ).first()
        
        result.append({
            "id": req.id,
            "employee_name": req.employee_name,
            "origin_year": origin_year,
            "target_year": target_year,
            "cf_days": cf_days,
            "is_merged": is_merged,
            "current_balance_target_year": target_balance.remaining if target_balance else 0
        })
        
    return sorted(result, key=lambda x: x["id"], reverse=True)


@router.post("/cf-merge-bulk")
def merge_cf_bulk(payload: dict = Body(...), db: Session = Depends(get_db)):
    import re
    leave_ids = payload.get("leave_ids", [])
    if not leave_ids:
        raise HTTPException(status_code=400, detail="No requests selected for merge.")
        
    merged_count = 0
    for req_id in leave_ids:
        req = db.query(models.Leave).filter(models.Leave.id == req_id).first()
        
        if req and req.status == "Approved" and "[CARRY FORWARD:" in (req.reason or ""):
            match = re.search(r"\[CARRY FORWARD:\s*([\d\.]+)\s*DAYS\]", req.reason)
            cf_days = float(match.group(1)) if match else 0.0
            
            origin_year = int(req.start_date.strftime("%Y") if req.start_date else datetime.now().year)
            target_year = origin_year + 1
            
            # 🚀 FIX: Corrected attribute name 'year'
            target_balance = db.query(models.LeaveBalance).filter(
                models.LeaveBalance.employee_name == req.employee_name,
                models.LeaveBalance.year == target_year,
                models.LeaveBalance.leave_type == "Annual Leave"
            ).first()
            
            if target_balance:
                target_balance.carry_forward_total = float(target_balance.carry_forward_total or 0) + cf_days
                target_balance.remaining = float(target_balance.remaining or 0) + cf_days
            else:
                db.add(models.LeaveBalance(
                    employee_name=req.employee_name,
                    leave_type="Annual Leave",
                    year=target_year,
                    entitlement=14.0, 
                    remaining=14.0 + cf_days,
                    carry_forward_total=cf_days
                ))
            
            req.status = "Merged"
            req.status_history = (req.status_history or "") + f" > Merged to {target_year} Wallet"
            merged_count += 1
            
    db.commit()
    return {"message": f"Successfully merged {merged_count} requests to next year's balance."}
# 🧹 V1.5.0: The Carry-Forward "Grim Reaper" with Audit Trail
def check_and_wipe_expired_cf(db: Session):
    today = date.today()
    
    # 1. Fetch the Expiry Date from your Settings table
    settings = db.query(models.SystemSetting).filter(models.SystemSetting.key == "carry_forward").first()
    
    if not settings or not settings.value.get("expiry_date"):
        return

    try:
        expiry_date = date.fromisoformat(settings.value["expiry_date"])
    except:
        return 

    # 2. 🛑 THE KILL SWITCH: If today is AFTER the deadline
    if today > expiry_date:
        # Find all balances for the current year that still have CF days > 0
        expired_records = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.carry_forward_total > 0,
            models.LeaveBalance.year == today.year
        ).all()

        if expired_records:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            for record in expired_records:
                old_val = record.carry_forward_total
                
                # A. Create an Audit Record in the Leave table
                # We tag it as 'System Action' so Natasha knows it wasn't a manual deletion
                expiry_log = models.Leave(
                    employee_name=record.employee_name,
                    leave_type="Claim Carry Forward",
                    start_date=today,
                    end_date=today,
                    days_taken=old_val,
                    status="Cancelled", # Or create a new status like "Expired"
                    reason=f"[SYSTEM AUTO-CLEANUP] {old_val} banked days expired on {expiry_date}.",
                    status_history=f"Expired ({now_str})",
                    approver_name="System Administrator"
                )
                db.add(expiry_log)

                # B. Wipe the balance
                record.carry_forward_total = 0.0
            
            db.commit()
            print(f"🕒 {today}: Cleanup complete. {len(expired_records)} wallets emptied.")