import csv
import io
import json
import os
import re
import shutil
import time
import secrets
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Form, Body, Header, BackgroundTasks, File, UploadFile, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import models, database  
from app.database import get_db
from app.utils.security import hash_password, verify_password

# 🚀 THE ONLY ROUTER DECLARATION WE NEED
# Using "/users" ensures your existing frontend user & profile features keep working perfectly!
router = APIRouter(prefix="/users", tags=["Users"])

# 🚀 Email Service Imports for Admin Actions
try:
    from app.utils.email_service import (
        send_email, 
        template_admin_password_reset,
        template_role_update,
        template_account_status
    )
except ImportError:
    from utils.email_service import (
        send_email, 
        template_admin_password_reset,
        template_role_update,
        template_account_status
    )

# --- SCHEMAS ---

class AdminResetRequest(BaseModel):
    new_password: str

# 🚀 Schema for the "Change Password" tab
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/all")
def get_all_users(
    search: str = "", 
    role: str = "", 
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db)
):
    # 🚀 PHASE 3: Capture current date for the status check
    today = datetime.now().date()

    # THE GHOST FILTER: Hide superusers from the UI
    query = db.query(models.User).filter(models.User.role != "superuser")
    
    # Existing Search Logic
    if search:
        query = query.filter(models.User.full_name.ilike(f"%{search}%"))
        
    # Existing Role Logic
    if role:
        query = query.filter(models.User.role == role)

    # THE PERFORMANCE ENGINE: Count and Slice
    total_count = query.count()
    offset = (page - 1) * page_size
    users = query.offset(offset).limit(page_size).all()
    
    # ==============================================================
    # 🚀 ANTI N+1 BOTTLENECK FIX: BULK LEAVE & ROLE LOOKUP
    # ==============================================================
    user_full_names = [u.full_name for u in users if u.full_name]
    user_ids = [u.id for u in users]
    
    leave_dict = {}
    roles_dict = {}

    if user_full_names:
        # Ask the database ONCE for all active leaves
        active_leaves = db.query(models.Leave).filter(
            models.Leave.employee_name.in_(user_full_names),
            models.Leave.status == 'Approved',
            models.Leave.start_date <= today,
            models.Leave.end_date >= today
        ).all()
        for leave in active_leaves:
            leave_dict[leave.employee_name] = str(leave.end_date)

    if user_ids:
        # Ask the database ONCE for all assigned roles for this entire batch
        bulk_roles = db.query(models.UserRole).filter(
            models.UserRole.user_id.in_(user_ids)
        ).all()
        for r in bulk_roles:
            if r.user_id not in roles_dict:
                roles_dict[r.user_id] = []
            roles_dict[r.user_id].append(r.role_name)
    # ==============================================================

    result = []
    
    # Safely map every user to a dictionary
    for u in users:
        # --- 🚀 THE SPEED UPGRADE: Instant memory lookup for roles! ---
        roles_list = ["employee"]
        user_specific_roles = roles_dict.get(u.id, [])
        
        for r_name in user_specific_roles:
            if r_name.lower() != "employee" and r_name not in roles_list:
                roles_list.append(r_name)
                
        if u.role and u.role not in roles_list:
            roles_list.append(u.role)

        # 🚀 PHASE 3: NEW STATUS LOGIC (Optimized)
        # Instantly check the dictionary instead of pausing to query the database
        leave_end_str = leave_dict.get(u.full_name)
            
        result.append({
            "id": u.id,
            "full_name": u.full_name or "Unknown",
            "first_name": u.first_name or "",
            "middle_name": u.middle_name or "",
            "last_name": u.last_name or "",
            "preferred_name": u.preferred_name or "",
            "username": u.username,
            "role": u.role or "employee",
            "is_active": getattr(u, 'is_active', True),
            "is_senior_manager": getattr(u, 'is_senior_manager', False), 
            "roles_list": roles_list,
            "employee_id": getattr(u, 'employee_id', ""),
            "gender": getattr(u, 'gender', ""),
            "marital_status": getattr(u, 'marital_status', ""),
            "email": getattr(u, 'email', ""),
            "personal_email": getattr(u, 'personal_email', ""),
            "mobile": getattr(u, 'mobile', ""),
            "job_title": getattr(u, 'job_title', ""),
            "business_unit": getattr(u, 'business_unit', ""),
            "department": getattr(u, 'department', ""),
            
            # ============================================================
            # 🚀 NEW FIELD SERIALIZATION ADDITIONS (Item 3 Mapping Loop)
            # ============================================================
            "employee_no_old": getattr(u, 'employee_no_old', ""),
            "common_name": getattr(u, 'common_name', ""),
            "employee_status": getattr(u, 'employee_status', ""),
            "organization_o": getattr(u, 'organization_o', ""),
            "organization_ou1": getattr(u, 'organization_ou1', ""),
            "organization_ou2": getattr(u, 'organization_ou2', ""),
            "lotus_notes_id": getattr(u, 'lotus_notes_id', ""),
            "document_status": getattr(u, 'document_status', ""),
            "company": getattr(u, 'company', ""),
            "location": getattr(u, 'location', ""),
            "position_grade": getattr(u, 'position_grade', ""),
            "contract_expiry_date": str(u.contract_expiry_date) if getattr(u, 'contract_expiry_date', None) else "",
            "expat_type": getattr(u, 'expat_type', ""),
            "category": getattr(u, 'category', ""),
            "ranking": getattr(u, 'ranking', ""),
            "highest_qualification": getattr(u, 'highest_qualification', ""),
            "level_0": getattr(u, 'level_0', ""),
            "level_1": getattr(u, 'level_1', ""),
            "level_2": getattr(u, 'level_2', ""),
            "place_of_birth": getattr(u, 'place_of_birth', ""),
            "date_ict_removal": str(u.date_ict_removal) if getattr(u, 'date_ict_removal', None) else "",
            "date_resigned": str(u.date_resigned) if getattr(u, 'date_resigned', None) else "",
            "last_working_day": str(u.last_working_day) if getattr(u, 'last_working_day', None) else "",
            "last_day_of_service": str(u.last_day_of_service) if getattr(u, 'last_day_of_service', None) else "",
            "shift_employee": getattr(u, 'shift_employee', "No"),
            "compensation_leave_entitled": getattr(u, 'compensation_leave_entitled', "No"),
            "commissioning_engineer": getattr(u, 'commissioning_engineer', "No"),
            "scholar": getattr(u, 'scholar', "No"),
            "bank_holder_name": getattr(u, 'bank_holder_name', ""),
            "bank_name": getattr(u, 'bank_name', ""),
            "bank_account_number": getattr(u, 'bank_account_number', ""),
            "bank_account_status": getattr(u, 'bank_account_status', "Active"),
            # ============================================================
            
            # PHASE 2 UPDATE: Preserved
            "line_manager": u.line_manager if isinstance(u.line_manager, list) else [],
            "hod_name": u.hod_name if isinstance(u.hod_name, list) else [],
            
            "contract_type": getattr(u, 'contract_type', ""),
            "work_location": getattr(u, 'work_location', ""),
            "joined_date": str(u.joined_date) if getattr(u, 'joined_date', None) else "",
            "ic_no": getattr(u, 'ic_number', ""),
            "nationality": getattr(u, 'nationality', ""),
            "dob": str(u.dob) if getattr(u, 'dob', None) else "",
            "race": getattr(u, 'race', ""),
            "religion": getattr(u, 'religion', ""),
            "home_address": getattr(u, 'home_address', ""),
            "current_address": getattr(u, 'current_address', ""),
            "emergency_contact_name": getattr(u, 'emergency_contact_name', ""),
            "emergency_contact_rel": getattr(u, 'emergency_contact_rel', ""),
            "emergency_contact_mobile": getattr(u, 'emergency_contact_mobile', ""),
            "profile_pic_url": getattr(u, 'profile_pic_url', ""),

            # 🚀 PHASE 3 NEW FIELD:
            "current_leave_end": leave_end_str
        })
        
    return {
        "users": result,
        "total": total_count,
        "page": page,
        "page_size": page_size
    }


# 🚀 NEW HELPER: Fetch a user's name by their ID for frontend caching
@router.get("/get-by-id/{user_id}")
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # We only return the ID and Name to keep the payload tiny
    return {"id": user.id, "full_name": user.full_name}


@router.put("/{user_id}/roles-update")
async def update_user_roles_multiple( # 🚀 Changed to async
    user_id: int, 
    background_tasks: BackgroundTasks, # 🚀 INJECTED: Background worker
    roles: str = Form(...), 
    is_senior_manager: bool = Form(False),
    x_requester_name: str = Header(None, alias="X-Requester-Name"),
    db: Session = Depends(get_db)
):
    try:
        role_list = json.loads(roles)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid role data format")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Block role changes for Inactive employees
    if not user.is_active:
        raise HTTPException(
            status_code=400, 
            detail=f"Modification Denied: {user.full_name} is currently Inactive."
        )

    # 🛡️ Security Lock for HR Admin
    if user.role == "hr_admin" and "hr_admin" not in role_list:
        other_active_admins = db.query(models.User).filter(
            models.User.role == "hr_admin",
            models.User.is_active == True,
            models.User.id != user_id
        ).count()
        
        if other_active_admins < 1:
            raise HTTPException(
                status_code=400, 
                detail="Security Lock: Cannot remove the last active HR Admin."
            )

    # ==============================================================
    # 🚀 AUTO-ESCALATE ORPHANED TASKS (Safety Net logic preserved)
    # ==============================================================
    was_manager = any(r.role_name == "manager" for r in user.assigned_roles) or user.role == "manager"
    is_now_manager = "manager" in role_list
    was_senior = user.is_senior_manager
    is_now_senior = is_senior_manager

    acting_admin = x_requester_name if x_requester_name else "HR Admin"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    reassigned_count = 0

    if was_manager and not is_now_manager:
        l1_leaves = db.query(models.Leave).filter(models.Leave.approver_name == user.full_name, models.Leave.status.in_(["Pending", "Pending Cancel"])).all()
        for l in l1_leaves:
            l.approver_name = acting_admin
            l.status_history += f" > Auto-Escalated to {acting_admin} {{Note: Manager Role Revoked}} ({timestamp})"
            reassigned_count += 1

        l1_ots = db.query(models.Overtime).filter(models.Overtime.approver_name == user.full_name, models.Overtime.status.in_(["Pending", "Pending Cancel"])).all()
        for ot in l1_ots:
            ot.approver_name = acting_admin
            ot.status_history += f" > Auto-Escalated to {acting_admin} {{Note: Manager Role Revoked}} ({timestamp})"
            reassigned_count += 1

    if was_senior and not is_now_senior:
        l2_leaves = db.query(models.Leave).filter(models.Leave.approver_l2 == user.full_name, models.Leave.status.in_(["Pending L2 Approval", "Pending Cancel"])).all()
        for l in l2_leaves:
            l.approver_l2 = acting_admin
            l.status_history += f" > Auto-Escalated to {acting_admin} {{Note: L2 Role Revoked}} ({timestamp})"
            reassigned_count += 1

        l2_ots = db.query(models.Overtime).filter(models.Overtime.approver_l2 == user.full_name, models.Overtime.status.in_(["Pending L2 Approval", "Pending Cancel"])).all()
        for ot in l2_ots:
            ot.approver_l2 = acting_admin
            ot.status_history += f" > Auto-Escalated to {acting_admin} {{Note: L2 Role Revoked}} ({timestamp})"
            reassigned_count += 1

    # ==============================================================
    # 🚀 UPDATE ROLES IN DATABASE
    # ==============================================================
    user.is_senior_manager = is_senior_manager
    db.query(models.UserRole).filter(models.UserRole.user_id == user_id).delete()
    
    if not role_list:
        role_list = ["employee"]

    for r_name in role_list:
        db.add(models.UserRole(user_id=user_id, role_name=r_name))
    
    if "hr_admin" in role_list:
        user.role = "hr_admin"
    elif "manager" in role_list:
        user.role = "manager"
    else:
        user.role = "employee"

    try:
        db.commit()

        # 🚀 EMAIL NOTIFICATION TRIGGER (Background Task)
        if user.email and "@" in str(user.email):
            subject = "🛡️ System Permissions Updated"
            body = template_role_update(
                name=user.full_name,
                roles=role_list,
                is_senior=is_senior_manager
            )
            background_tasks.add_task(send_email, user.email, subject, body)

        msg = f"User account updated successfully for {user.full_name}."
        if reassigned_count > 0:
            msg += f"<br><br>⚠️ <b>{reassigned_count} pending request(s)</b> were automatically transferred to your queue."

        return {"message": msg, "reassigned": reassigned_count}

    except Exception as e:
        db.rollback()
        print(f"❌ DB Error during role update: {e}")
        raise HTTPException(status_code=500, detail="Database error during permission update.")

@router.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    clean_username = username.strip().lower()
    user = db.query(models.User).filter(models.User.username == clean_username).first()

    # 1. Verify Credentials (Existing)
    if not user or user.password != password:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    # 🛑 2. SECURITY FIX: Block Inactive Users
    # This prevents the system from generating a session for deactivated staff.
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive. Contact HR.")

    # 🚀 3. THE SESSION FIX: Create a unique ID for this specific login session
    # (Rest of the function remains untouched to preserve stability)
    new_session_id = secrets.token_hex(16) 
    user.current_session_id = new_session_id
    db.commit() 

    # 4. Get roles from the roles table
    roles_list = [r.role_name for r in user.assigned_roles]

    # 5. Use the 'role' column fallback if roles table is empty
    if not roles_list:
        roles_list = [user.role] if user.role else ["employee"]

    # 6. Return EVERYTHING to the frontend
    return {
        "username": user.username,
        "full_name": user.full_name,
        "is_senior_manager": user.is_senior_manager,
        "roles": roles_list,
        "session_id": new_session_id
    }

def get_current_active_user(
    session_id: str = Header(..., alias="X-Session-ID"), 
    db: Session = Depends(get_db)
):
    # 1. Fetch user by the session_id provided in the frontend header
    user = db.query(models.User).filter(models.User.current_session_id == session_id).first()
    
    # 2. If no user matches or the session_id is None, they are "kicked out"
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="Session expired or replaced by another login."
        )
    return user

@router.get("/my-profile")
def get_my_profile(
    current_user: models.User = Depends(get_current_active_user)
):
    # This logic only runs if the session is valid
    return {
        "username": current_user.username,
        "full_name": current_user.full_name
    }


# # 🚀 Change this from .post to .get
# @router.get("/setup-superuser")
# def setup_superuser(db: Session = Depends(get_db)):
#     # 1. Check if superuser already exists to prevent duplicates
#     existing_super = db.query(models.User).filter(models.User.username == "superuser").first()
#     if existing_super:
#         return {"message": "Superuser already exists!"}

#     # 2. Create the Superuser
#     try:
#         super_user = models.User(
#             username="superuser",
#             password="SuperPassword123!",  # Change this to whatever you want
#             full_name="System Administrator",
#             email="admin@yourcompany.com",
#             role="superuser",
#             is_active=True,
#             # Add placeholders for other required fields
#             joined_date="2024-01-01" 
#         )
        
#         db.add(super_user)
#         db.commit()
#         return {"message": "✅ Superuser created successfully! You can now log in."}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Failed to create superuser: {str(e)}")
    
#     INSERT INTO users (username, password, full_name, role, is_active) 
# VALUES ('superuser', 'SuperPassword123!', 'System Administrator', 'superuser', true);


@router.post("/register")
async def register_user(
    background_tasks: BackgroundTasks, 
    
    # 📋 STEP 1: STRICTLY REQUIRED
    username: str = Form(...), 
    password: str = Form(...),
    full_name: str = Form(...), 
    employee_id: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...), 
    joined_date: str = Form(...),
    mobile: str = Form(...), 

    # 📋 STEP 1: OPTIONAL
    middle_name: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    line_manager: Optional[str] = Form(None),
    hod_name: Optional[str] = Form(None),
    contract_type: Optional[str] = Form(None),
    business_unit: Optional[str] = Form(None),
    work_location: Optional[str] = Form(None),

    # 👤 STEP 2: PERSONAL INFO
    preferred_name: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    ic_no: Optional[str] = Form(None),
    nationality: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    race: Optional[str] = Form(None),
    religion: Optional[str] = Form(None),

    # 📞 STEP 3: CONTACT & LOGISTICS
    personal_email: Optional[str] = Form(None),
    home_address: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    emergency_contact_name: Optional[str] = Form(None),
    emergency_contact_rel: Optional[str] = Form(None),
    emergency_contact_mobile: Optional[str] = Form(None),

    # 🖼️ FILE UPLOAD
    profile_pic: Optional[UploadFile] = File(None),
    
    db: Session = Depends(get_db)
):
    # --- 1. STRICT DATA NORMALIZATION ---
    clean_username = username.strip().lower()
    clean_full_name = full_name.strip()
    clean_email = email.strip().lower()
    clean_employee_id = employee_id.strip()

    # 🚀 PHASE 2 UPDATE: Parse incoming managers as JSON lists
    # This prevents the "UndefinedVariable" error and handles multi-select data
    def parse_manager_list(data):
        if not data: return []
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, list) else [str(data)]
        except:
            return [str(data)] if data else []

    final_line_managers = parse_manager_list(line_manager)
    final_hod_names = parse_manager_list(hod_name)

    # --- 2. DUPLICATION GUARD ---
    if db.query(models.User).filter(models.User.email == clean_email).first():
        raise HTTPException(status_code=400, detail="Duplicate Email: This email address is already registered.")
        
    if db.query(models.User).filter(models.User.username == clean_username).first():
        raise HTTPException(status_code=400, detail="Duplicate Username: This username is already taken.")

    # --- 📸 3. HANDLE PROFILE PICTURE ---
    avatar_url = None
    if profile_pic:
        try:
            upload_dir = "uploads/avatars"
            os.makedirs(upload_dir, exist_ok=True)
            file_extension = profile_pic.filename.split(".")[-1]
            unique_filename = f"user_reg_{int(time.time())}.{file_extension}"
            file_location = os.path.join(upload_dir, unique_filename)
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(profile_pic.file, buffer)
            avatar_url = f"/{file_location}"
        except Exception as e:
            print(f"⚠️ Avatar Upload Warning: {e}")

# --- 🚀 4. THE 3-RETRY AUTO-INCREMENT LOOP ---
    max_attempts = 4  
    current_emp_id = clean_employee_id
    success = False

    for attempt in range(max_attempts):
        try:
            new_user = models.User(
                username=clean_username, 
                full_name=clean_full_name, 
                password=password, 
                role="employee",
                employee_id=current_emp_id,
                profile_pic_url=avatar_url, 
                
                # Employment
                email=clean_email,
                first_name=first_name.strip() if first_name else None,
                middle_name=middle_name.strip() if middle_name else None,
                last_name=last_name.strip() if last_name else None,
                preferred_name=preferred_name.strip() if preferred_name else None,
                job_title=job_title.strip() if job_title else None,
                department=department.strip() if department else None,

                # 🚀 PHASE 2 FIX: Using the parsed lists instead of clean_line_manager
                line_manager=final_line_managers,
                hod_name=final_hod_names,

                joined_date=joined_date,
                contract_type=contract_type.strip() if contract_type else None,
                business_unit=business_unit.strip() if business_unit else None,
                work_location=work_location.strip() if work_location else None,

                # Personal
                gender=gender,
                marital_status=marital_status,
                ic_number=ic_no.strip() if ic_no else None,
                nationality=nationality.strip() if nationality else None,
                dob=dob,
                race=race.strip() if race else None,
                religion=religion.strip() if religion else None,

                # Contact & Emergency
                mobile=mobile.strip() if mobile else None,
                personal_email=personal_email.strip() if personal_email else None,
                home_address=home_address.strip() if home_address else None,
                current_address=current_address.strip() if current_address else None,
                emergency_contact_name=emergency_contact_name.strip() if emergency_contact_name else None,
                emergency_contact_rel=emergency_contact_rel.strip() if emergency_contact_rel else None,
                emergency_contact_mobile=emergency_contact_mobile.strip() if emergency_contact_mobile else None,
                
                is_active=True 
            )
            db.add(new_user)
            db.flush()

            # --- 5. ADD DEFAULT ROLE ---
            db.add(models.UserRole(user_id=new_user.id, role_name="employee"))

            # --- 6. INITIALIZE BALANCES ---
            policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
            annual = policy.annual_days if policy else 14
            medical = policy.medical_days if policy else 14
            emergency = policy.emergency_days if policy else 2
            compassionate = policy.compassionate_days if policy else 3

            current_year = datetime.now().year
            leave_setups = [
                (models.LeaveType.ANNUAL, annual),
                (models.LeaveType.MEDICAL, medical),
                (models.LeaveType.EMERGENCY, emergency),
                (models.LeaveType.COMPASSIONATE, compassionate),
                (models.LeaveType.UNPAID, 0.0) 
            ]

            for l_type, days in leave_setups:
                db.add(models.LeaveBalance(
                    employee_name=clean_full_name, 
                    leave_type=l_type,
                    year=current_year,
                    entitlement=float(days),
                    remaining=float(days), 
                    carry_forward_total=0.0
                ))

            db.commit()
            success = True
            break

        except IntegrityError as e:
            db.rollback() 
            print(f"DEBUG: IntegrityError details: {str(e.orig)}")
            if attempt < max_attempts - 1:
                match = re.search(r'(.*?)-(\d+)$', current_emp_id)
                if match:
                    prefix = match.group(1); num_str = match.group(2)
                    current_emp_id = f"{prefix}-{int(num_str) + 1:0{len(num_str)}d}"
                else:
                    raise HTTPException(status_code=400, detail="Employee ID format unrecognized.")
            else:
                raise HTTPException(status_code=400, detail="Duplicate ID conflict detected.")
        except Exception as e:
            db.rollback()
            print(f"❌ Critical Failure: {e}")
            raise HTTPException(status_code=500, detail="Registration failed due to server error.")

    # --- 7. 📧 EMAIL NOTIFICATION ---
    if success and clean_email and "@" in clean_email:
        try:
            from app.utils.email_service import send_email, template_new_user
            subject = "🎉 Welcome to the Team"
            body = template_new_user(name=clean_full_name, username=clean_username, password=password)
            background_tasks.add_task(send_email, clean_email, subject, body)
        except Exception as mail_err:
            print(f"⚠️ Email Queue Warning: {mail_err}")
            
    return {
        "message": f"User {clean_full_name} registered successfully.",
        "assigned_emp_id": current_emp_id 
    }



@router.put("/{user_id}/toggle-status")
async def toggle_user_status( # 🚀 Async execution for background tasks
    user_id: int, 
    background_tasks: BackgroundTasks, # 🚀 Background worker injected safely
    db: Session = Depends(get_db)
):
    # 1. Fetch user securely
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 2. 🛡️ SECURITY CHECK: Prevent deactivating the last active HR Admin
    # Only applies if the user is currently active and is an HR Admin
    if user.is_active and user.role == "hr_admin":
        active_admin_count = db.query(models.User).filter(
            models.User.role == "hr_admin",
            models.User.is_active == True
        ).count()
        
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=400, 
                detail="Security Lock: Cannot deactivate the last active HR Admin. "
                       "Please assign another user as HR Admin first."
            )
    
    # 3. Safely toggle the boolean status
    user.is_active = not user.is_active
    
    # 4. 🚀 Kick-out logic: Destroy active session tokens immediately if deactivated
    if not user.is_active:
        user.current_session_id = None
        
    try:
        # 5. Commit changes to the database FIRST
        db.commit()

        # 6. 📧 EMAIL NOTIFICATION TRIGGER (Only fires if DB commit succeeds)
        if user.email and "@" in str(user.email):
            status_label = "ACTIVATED" if user.is_active else "DEACTIVATED"
            subject = f"⚠️ Account Security Alert: Status {status_label}"
            
            body = template_account_status(
                name=user.full_name or "Employee", # Fallback added for maximum safety
                is_active=user.is_active
            )
            
            # Hand off to Brevo instantly without blocking the frontend
            background_tasks.add_task(send_email, user.email, subject, body)

        status_text = "Activated" if user.is_active else "Deactivated"
        return {"message": f"User {user.full_name} has been {status_text}"}

    except Exception as e:
        # 7. Safe Rollback: If anything fails, revert DB state and alert frontend
        db.rollback()
        print(f"❌ Status Toggle Error: {e}")
        raise HTTPException(status_code=500, detail="Database error toggling user status.")


@router.put("/{user_id}/profile-update")
async def update_user_profile(
    user_id: int,
    # 📋 STEP 1 (Required Core Basics)
    full_name: str = Form(...), 
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...), 
    joined_date: str = Form(...),
    mobile: str = Form(...), 

    # 📋 OPTIONALS / ADMIN MANAGEMENT LOGS (Extended Corporate Structural Layers)
    middle_name: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    line_manager: Optional[str] = Form(None),
    hod_name: Optional[str] = Form(None),
    contract_type: Optional[str] = Form(None),
    business_unit: Optional[str] = Form(None),
    work_location: Optional[str] = Form(None),
    
    # New Corporate/Enterprise Fields Parameters
    common_name: Optional[str] = Form(None),
    employee_no_old: Optional[str] = Form(None),
    lotus_notes_id: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    position_grade: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    ranking: Optional[str] = Form(None),
    expat_type: Optional[str] = Form(None),
    employee_status: Optional[str] = Form(None),
    document_status: Optional[str] = Form(None),
    highest_qualification: Optional[str] = Form(None),
    
    # Hierarchy Structural Routing Mappings
    organization_o: Optional[str] = Form(None),
    organization_ou1: Optional[str] = Form(None),
    organization_ou2: Optional[str] = Form(None),
    level_0: Optional[str] = Form(None),
    level_1: Optional[str] = Form(None),
    level_2: Optional[str] = Form(None),
    
    # Milestone Lifecycle Offboarding Dates 
    contract_expiry_date: Optional[str] = Form(None),
    date_resigned: Optional[str] = Form(None),
    last_working_day: Optional[str] = Form(None),
    last_day_of_service: Optional[str] = Form(None),
    date_ict_removal: Optional[str] = Form(None),
    
    # Operational Dropdown Options Flags
    shift_employee: Optional[str] = Form(None),
    compensation_leave_entitled: Optional[str] = Form(None),
    commissioning_engineer: Optional[str] = Form(None),
    scholar: Optional[str] = Form(None),

    # 👤 STEP 2 (Personal Specifications Node)
    preferred_name: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    ic_no: Optional[str] = Form(None),
    nationality: Optional[str] = Form(None),
    place_of_birth: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    race: Optional[str] = Form(None),
    religion: Optional[str] = Form(None),

    # 📞 STEP 3 (Contact Registry & Salary Bank Nodes)
    personal_email: Optional[str] = Form(None),
    home_address: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    emergency_contact_name: Optional[str] = Form(None),
    emergency_contact_rel: Optional[str] = Form(None),
    emergency_contact_mobile: Optional[str] = Form(None),
    
    # Salary Disbursal Parameters
    bank_name: Optional[str] = Form(None),
    bank_account_number: Optional[str] = Form(None),
    bank_holder_name: Optional[str] = Form(None),
    bank_account_status: Optional[str] = Form(None),
    
    profile_pic: Optional[UploadFile] = File(None),
    x_username: Optional[str] = Header(None), 
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. 🛡️ MANAGER LIST PARSER
    def parse_manager_list(data):
        if not data: return []
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, list) else [str(data)]
        except:
            return [str(data)] if data else []

    final_line_managers = parse_manager_list(line_manager)
    final_hod_names = parse_manager_list(hod_name)

# 2. 🚀 CASCADING NAME SYNC (Identity Protection)
    old_name = user.full_name
    new_name = full_name.strip()

    if old_name != new_name:
        # 🚀 PRE-FLIGHT PATCH: Sanitize the lists BEFORE they touch the user object.
        # This ensures that even if the UI sends the "old" name in the form, 
        # we correct it to the "new" name in memory before assigning it to the database.
        if isinstance(final_line_managers, list):
            final_line_managers = [new_name if n == old_name else n for n in final_line_managers]
        if isinstance(final_hod_names, list):
            final_hod_names = [new_name if n == old_name else n for n in final_hod_names]
        
        # Now assign the cleaned/patched variables to the user object
        user.line_manager = final_line_managers
        user.hod_name = final_hod_names

        # 🚀 TABLE UPDATES: Update every table that uses employee_name or approver_name
        # This keeps your leave and overtime history perfectly in sync with the new name
        db.query(models.LeaveBalance).filter(models.LeaveBalance.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Leave).filter(models.Leave.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Overtime).filter(models.Overtime.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Leave).filter(models.Leave.approver_name == old_name).update({"approver_name": new_name})
        db.query(models.Overtime).filter(models.Overtime.approver_name == old_name).update({"approver_name": new_name})
        db.query(models.Leave).filter(models.Leave.approver_l2 == old_name).update({"approver_l2": new_name})

        # 🚀 ROBUST CASCADE: Update all other users
        # We perform this after the user object is patched to ensure consistency
        all_users = db.query(models.User).all()
        for u in all_users:
            if u.id == user.id: continue # Skip the user we just patched
            
            updated_any = False
            
            # Update Line Manager List
            if isinstance(u.line_manager, list) and old_name in u.line_manager:
                u.line_manager = [new_name if n == old_name else n for n in u.line_manager]
                updated_any = True
            
            # Update HOD List
            if isinstance(u.hod_name, list) and old_name in u.hod_name:
                u.hod_name = [new_name if n == old_name else n for n in u.hod_name]
                updated_any = True
            
            # Only add to the session if changes were made
            if updated_any:
                db.add(u)
                print(f"🔄 Syncing manager reference for: {u.full_name}")

    # 3. 📸 AVATAR UPDATE
    if profile_pic:
        try:
            from app.main import compress_and_upload
            user.profile_pic_url = compress_and_upload(profile_pic, folder="avatars")
        except Exception as e:
            print(f"Avatar Upload Warning: {e}")

# ============================================================
    # 👑 THE PERMANENT BACKEND FIX: CASE & LAYER INSENSITIVE GATING
    # ============================================================
    is_admin = False
    if x_username:
        # 1. Clean and normalize the incoming header token string safely
        clean_requester_token = str(x_username).strip()
        
        # 2. Look up the requester checking BOTH username handles and display strings
        requester_account = db.query(models.User).filter(
            (models.User.username == clean_requester_token.lower()) | 
            (models.User.full_name.ilike(clean_requester_token))
        ).first()
        
        if requester_account:
            # 3. Fetch ALL roles assigned to this user from your junction roles table
            user_role_rows = db.query(models.UserRole).filter(
                models.UserRole.user_id == requester_account.id
            ).all()
            
            # 4. Extract them into a normalized list array
            assigned_roles_array = [str(r.role_name).strip().lower() for r in user_role_rows]
            
            # 5. Extract the base column role string fallback
            fallback_role = str(requester_account.role).strip().lower() if requester_account.role else "employee"
            
            # 6. Secure verification evaluation gate corridor
            if (
                fallback_role in ["hr_admin", "admin", "superuser"] or 
                "hr_admin" in assigned_roles_array or 
                "admin" in assigned_roles_array or 
                "superuser" in assigned_roles_array
            ) or (clean_requester_token.lower() == "superuser"):
                is_admin = True
    # ============================================================

    # 5. ✅ SELF-EDITABLE FIELDS (Always Mapped and Updated)
    user.full_name = new_name
    user.first_name = first_name.strip()
    user.middle_name = middle_name.strip() if middle_name else None
    user.last_name = last_name.strip()
    user.preferred_name = preferred_name.strip() if preferred_name else None
    user.email = email.strip().lower()
    user.mobile = mobile.strip()
    
    # Step 2 & 3 Identity Metrics Data Overwrites
    user.gender = gender
    user.marital_status = marital_status
    user.ic_number = ic_no.strip() if ic_no else None 
    user.nationality = nationality.strip() if nationality else None
    user.place_of_birth = place_of_birth.strip() if place_of_birth else None
    user.dob = dob
    user.race = race.strip() if race else None
    user.religion = religion.strip() if religion else None
    user.highest_qualification = highest_qualification.strip() if highest_qualification else None
    
    # Logistics Coordinates
    user.personal_email = personal_email.strip() if personal_email else None
    user.home_address = home_address.strip() if home_address else None
    user.current_address = current_address.strip() if current_address else None
    user.emergency_contact_name = emergency_contact_name.strip() if emergency_contact_name else None
    user.emergency_contact_rel = emergency_contact_rel.strip() if emergency_contact_rel else None
    user.emergency_contact_mobile = emergency_contact_mobile.strip() if emergency_contact_mobile else None

    # 💸 Disbursal Salary Bank Parameters Row Assignments
    user.bank_name = bank_name.strip() if bank_name else None
    user.bank_account_number = bank_account_number.strip() if bank_account_number else None
    user.bank_holder_name = bank_holder_name.strip() if bank_holder_name else None
    user.bank_account_status = bank_account_status if bank_account_status else "Active"

    # 6. 🔓 ADMIN LOCKDOWN ZONE (Safe Update Protected Tier)
    if is_admin:
        print(f"[SECURITY] Admin {x_username} updating official employment fields.")
        
        # Guarded String Blocks
        if job_title and job_title.strip(): 
            user.job_title = job_title.strip()
        if department and department.strip(): 
            user.department = department.strip()
        if joined_date: 
            user.joined_date = joined_date
        if contract_type and contract_type.strip(): 
            user.contract_type = contract_type.strip()
        if business_unit and business_unit.strip(): 
            user.business_unit = business_unit.strip()
        if work_location and work_location.strip(): 
            user.work_location = work_location.strip()

        # Extended Employment Field Configurations
        user.common_name = common_name.strip() if common_name else None
        user.employee_no_old = employee_no_old.strip() if employee_no_old else None
        user.lotus_notes_id = lotus_notes_id.strip() if lotus_notes_id else None
        user.company = company.strip() if company else None
        user.location = location.strip() if location else None
        user.position_grade = position_grade.strip() if position_grade else None
        user.category = category.strip() if category else None
        user.ranking = ranking.strip() if ranking else None
        user.expat_type = expat_type.strip() if expat_type else None
        user.employee_status = employee_status.strip() if employee_status else None
        user.document_status = document_status.strip() if document_status else None
        
        # Enterprise Organizational Routing Hierarchy Structures
        user.organization_o = organization_o.strip() if organization_o else None
        user.organization_ou1 = organization_ou1.strip() if organization_ou1 else None
        user.organization_ou2 = organization_ou2.strip() if organization_ou2 else None
        user.level_0 = level_0.strip() if level_0 else None
        user.level_1 = level_1.strip() if level_1 else None
        user.level_2 = level_2.strip() if level_2 else None
        
        # Offboarding Lifecycle Date Milestones
        user.contract_expiry_date = contract_expiry_date if contract_expiry_date else None
        user.date_resigned = date_resigned if date_resigned else None
        user.last_working_day = last_working_day if last_working_day else None
        user.last_day_of_service = last_day_of_service if last_day_of_service else None
        user.date_ict_removal = date_ict_removal if date_ict_removal else None
        
        # Operational Indicators Flags
        user.shift_employee = shift_employee if shift_employee else "No"
        user.compensation_leave_entitled = compensation_leave_entitled if compensation_leave_entitled else "No"
        user.commissioning_engineer = commissioning_engineer if commissioning_engineer else "No"
        user.scholar = scholar if scholar else "No"

        # 🚀 PROTECT MANAGERS: Corrected logic to ensure empty selections clear properly
        if line_manager is not None:
            user.line_manager = final_line_managers
        if hod_name is not None:
            user.hod_name = final_hod_names
    else:
        print(f"🔒 [SECURITY] Ignored employment fields for {user.username}. Requester is not an admin.")

    db.commit()
    db.refresh(user)
    return {"message": "Profile updated successfully"}

@router.put("/{user_id}/reset-password")
async def admin_reset_password( # 🚀 Changed to async
    user_id: int, 
    payload: AdminResetRequest,
    background_tasks: BackgroundTasks, # 🚀 INJECTED: Background worker
    db: Session = Depends(get_db)
):
    """
    Allows HR Admin to force-reset a user's password.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # In production, hash this password!
    user.password = payload.new_password
    
    try:
        db.commit()

        # 🚀 EMAIL NOTIFICATION TRIGGER (Background Task)
        if user.email and "@" in str(user.email):
            subject = "🔒 Security Alert: Administrator Password Reset"
            body = template_admin_password_reset(user.full_name, payload.new_password)
            background_tasks.add_task(send_email, user.email, subject, body)

        return {"message": f"Password for {user.full_name} has been reset."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during reset.")
    


# ==========================================
# 1. HELPER FUNCTIONS (Define these FIRST)
# ==========================================

# 📧 UNIVERSAL EMAIL HELPER (MOCK MODE)
def send_system_email(recipient_email: str, subject: str, body: str):
    """
    Centralized email handler. 
    Currently prints to terminal for verification.
    Ready to be swapped for SendGrid/SMTP later.
    """
    try:
        print("\n" + "🚀" + "="*60)
        print(f" OUTGOING NOTIFICATION")
        print(f" To:      {recipient_email}")
        print(f" Subject: {subject}")
        print(f" Content: {body}")
        print("="*60 + "\n")
        return True
    except Exception as e:
        print(f"❌ Mock Email Error: {e}")
        return False

# ==========================================
# 2. API ROUTES (Define these AFTER)
# ==========================================

# 🚀 User Self-Service Change Password
@router.put("/{username}/change-password")
async def change_user_password( # 🚀 Changed to async
    username: str, 
    payload: ChangePasswordRequest, 
    background_tasks: BackgroundTasks, # 🚀 INJECTED: Background worker
    db: Session = Depends(get_db)
):
    # 1. Find User (Case-insensitive match)
    user = db.query(models.User).filter(models.User.username == username.strip().lower()).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")

    if not payload.current_password or not payload.new_password:
        raise HTTPException(status_code=400, detail="Current password and new password are required.")

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters long.")

    # 2. Verify Current Password
    if not verify_password(payload.current_password, user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    # 3. Update Password
    user.password = hash_password(payload.new_password)
    
    try:
        db.commit()
        
        # 🚀 4. TRIGGER NOTIFICATION (Background Task)
        if user.email and "@" in str(user.email):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Formatted to trigger the "Magic Wrapper" styling in your email service
            email_body = (
                f"Hi {user.full_name},\n\n"
                f"This is an automated security alert to confirm that your account password "
                f"was successfully changed on {timestamp}.\n"
                f"--------------------------------\n"
                f"Security Check:\n"
                f"• If you performed this change, you can safely ignore this email.\n"
                f"• If you DID NOT perform this change, please contact HR immediately.\n"
                f"--------------------------------\n"
            )
            
            # Send using the global Brevo engine via background worker
            background_tasks.add_task(send_email, user.email, "🔒 Security Alert: Password Changed", email_body)
            
        return {"message": "Password updated. Notification sent."}
        
    except Exception as e:
        db.rollback()
        print(f"❌ DB Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error saving password.")

# 🚀 Check Username Availability
@router.get("/check-username")
def check_username(username: str, db: Session = Depends(get_db)):
    """
    Checks if a username is available. 
    Uses strict equality (==) to prevent partial match bugs.
    """
    if not username:
        return {"available": True}

    # 1. Clean the input (lowercase and strip spaces)
    search_name = username.strip().lower()
    
    # 2. Strict Equality Check
    user = db.query(models.User).filter(models.User.username == search_name).first()
    
    if user:
        # Exact match found - Username is taken
        return {"available": False}
    
    # No exact match - Username is free to use
    return {"available": True}


# 🚀 Check Email Availability
@router.get("/check-email")
def check_email(email: str, db: Session = Depends(get_db)):
    """
    Real-time check to see if an email address is already registered.
    """
    if not email:
        return {"available": True}

    clean_email = email.strip().lower()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    
    if user:
        return {"available": False}
    
    return {"available": True}


@router.post("/forgot-password")
async def forgot_password(
    background_tasks: BackgroundTasks, 
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_email = email.strip().lower()
    print(f"\n🔍 [DEBUG] Searching DB for email: '{clean_email}'")
    
    # 🚀 Case-insensitive database matching
    user = db.query(models.User).filter(models.User.email.ilike(clean_email)).first()
    
    # 🚀 Python Fallback for hidden spaces in old data
    if not user:
        print("⚠️ [DEBUG] Strict match failed. Checking for hidden spaces in DB...")
        all_users = db.query(models.User).all()
        user = next((u for u in all_users if u.email and u.email.strip().lower() == clean_email), None)
    
    # Standard security message
    generic_msg = {"message": "If an account with that email exists, an email has been sent."}

    if not user:
        print(f"⛔ [DEBUG] Failed: Absolutely no user found with email '{clean_email}'.")
        return generic_msg
        
    if not user.is_active:
        print(f"⛔ [DEBUG] Failed: User '{user.full_name}' found, but account is marked as INACTIVE.")
        return generic_msg

    print(f"✅ [DEBUG] User found: {user.full_name}. Generating recovery info...")

    # 1. Generate new temporary password
    temp_password = secrets.token_urlsafe(8)
    user.password = temp_password
    
    try:
        db.commit()

        # 2. Prepare the email with BOTH Username and Temp Password
        subject = "🔒 Account Recovery: Credentials Reset"
        
        try:
            from app.utils.email_service import template_forgot_password, send_email
        except ImportError:
            from utils.email_service import template_forgot_password, send_email

        # 🚀 PASSING BOTH: We now pass user.username to the template
        body = template_forgot_password(
            name=user.full_name, 
            username=user.username, 
            temp_password=temp_password
        )
        
        background_tasks.add_task(send_email, user.email, subject, body)
        
        print(f"📧 [DEBUG] Success! Credentials sent to: {user.email}\n")
        return generic_msg

    except Exception as e:
        db.rollback()
        print(f"❌ [DEBUG] DB or Email Error: {e}")
        raise HTTPException(status_code=500, detail="Database error processing recovery.")


@router.get("/next-id")
def get_next_employee_id(db: Session = Depends(get_db)):
    # 1. Get current year
    current_year = datetime.now().year
    
    # 2. Find the highest existing Employee ID pattern (Ignoring technical Row IDs)
    # We look specifically for the highest string starting with "EMP-[Year]"
    last_user = db.query(models.User)\
        .filter(models.User.employee_id.like(f"EMP-{current_year}-%"))\
        .order_by(models.User.employee_id.desc())\
        .first()
    
    next_num = 1
    if last_user and last_user.employee_id:
        try:
            # We extract the number from the string "EMP-2026-008" -> 8
            # This ensures that even if Row ID is 15, we only care that the last Emp is 008
            last_id_number = int(last_user.employee_id.split("-")[-1])
            next_num = last_id_number + 1
        except (ValueError, IndexError):
            # Safe fallback: if we can't parse the text, count the total employees instead
            next_num = db.query(models.User).filter(models.User.role == "employee").count() + 1
    else:
        # If no employees exist yet, check the total employee count as a baseline
        next_num = db.query(models.User).filter(models.User.role == "employee").count() + 1
    
    # 3. Format: EMP-2026-009 (Strict 3-digit padding)
    # This turns 9 into 009 and 10 into 010 (Correcting the 0010 issue)
    next_id = f"EMP-{current_year}-{next_num:03d}"
    
    return {"next_id": next_id}

# --- SYSTEM POLICY ENDPOINTS ---

@router.get("/policy/current")
def get_global_policy(db: Session = Depends(get_db)):
    # Fetch the master policy (ID=1)
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    if not policy:
        # Fallback if seed hasn't run
        return {"l2_approval_enabled": False, "max_seats": 0, "registration_lock": False}
    
    return {
        "l2_approval_enabled": policy.l2_approval_enabled,
        "max_seats": policy.max_seats if policy.max_seats else 0,
        "registration_lock": policy.registration_lock if policy.registration_lock else False
    }

@router.put("/policy/update-l2")
def update_l2_toggle(enabled: bool = Form(...), db: Session = Depends(get_db)):
    # Look for the master policy (ID=1)
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    
    if not policy:
        # Create it if it doesn't exist for some reason
        policy = models.GlobalPolicy(id=1, l2_approval_enabled=enabled)
        db.add(policy)
    else:
        # Update existing
        policy.l2_approval_enabled = enabled
    
    db.commit()
    return {"message": "Policy Updated", "l2_approval_enabled": policy.l2_approval_enabled}

@router.put("/{user_id}/upload-avatar")
async def upload_user_avatar(
    user_id: int,
    profile_pic: UploadFile = File(...),
    employee_name: Optional[str] = Query(None), # 🚀 Explicitly absorbs the URL parameter
    db: Session = Depends(get_db)
):
    """
    Dedicated endpoint for LOCAL profile picture updates.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    try:
        # 🚀 1. CREATE LOCAL FOLDER IF IT DOESN'T EXIST
        upload_dir = "uploads/avatars"
        os.makedirs(upload_dir, exist_ok=True)
        
        # 🚀 2. CREATE A UNIQUE FILENAME (Prevents overwriting)
        file_extension = profile_pic.filename.split(".")[-1]
        unique_filename = f"user_{user_id}_{int(time.time())}.{file_extension}"
        file_location = os.path.join(upload_dir, unique_filename)
        
        # 🚀 3. SAVE TO YOUR COMPUTER'S HARD DRIVE
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(profile_pic.file, buffer)
        
        # 4. Save the local path to the database
        avatar_url = f"/{file_location}" # e.g. /uploads/avatars/user_239_123456.jpg
        user.profile_pic_url = avatar_url
        db.commit()
        
        return {"message": "Avatar saved locally", "avatar_url": avatar_url}
    except Exception as e:
        print(f"Local Avatar Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save image locally.")
    

@router.delete("/{user_id}/remove-avatar")
async def remove_user_avatar(
    user_id: int, 
    employee_name: Optional[str] = Query(None), # 🚀 Absorbs the incoming URL parameter
    db: Session = Depends(get_db)
):
    """
    Clears the profile picture from the database and deletes the file from the server.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 1. 🗑️ Physical File Cleanup (Optional but Recommended)
    # This deletes the actual .jpg file from your 'uploads/avatars' folder
    if user.profile_pic_url:
        try:
            # Converts "/uploads/avatars/pic.jpg" to "uploads/avatars/pic.jpg"
            file_path = user.profile_pic_url.lstrip("/") 
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Deleted local file: {file_path}")
        except Exception as e:
            print(f"⚠️ Physical file removal warning: {e}")

    # 2. 🧹 Database Update
    # Sets the column back to NULL so the frontend knows to show initials again
    user.profile_pic_url = None
    db.commit()
    
    return {"message": "Profile photo removed and reverted to default."}


@router.get("/global-stats")
def get_global_stats(db: Session = Depends(get_db), current_user_role: str = Header(None)):
    # 🛡️ SECURITY CHECK: Only allow Superusers
    # In a real setup, we'd verify the token, but for now we check the role header
    if current_user_role != "superuser":
        raise HTTPException(status_code=403, detail="Access Denied: Superuser only.")

    try:
        # 1. User Capacity Stats
        total_users = db.query(models.User).count()
        active_users = db.query(models.User).filter(models.User.is_active == True).count()
        
        # 🚀 NEW: Fetch actual max_seats and registration_lock from GlobalPolicy
        policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
        max_seats = policy.max_seats if policy and policy.max_seats else 0
        registration_lock = policy.registration_lock if policy else False

        # Calculate percentage safely to avoid division by zero errors
        percent_used = (total_users / max_seats * 100) if max_seats > 0 else 0

        # 2. Global Leave & OT Bottlenecks (Total Pending across company)
        # 🚀 FIX: Updated to use your actual database models (Leave and Overtime)
        pending_leaves = db.query(models.Leave).filter(models.Leave.status == "Pending").count()
        pending_ot = db.query(models.Overtime).filter(models.Overtime.status == "Pending").count()

        # 3. Incident Triage (Coming soon in next step)
        # For now, we return 0 until we build the Incident table
        open_incidents = 0 

        # 4. System Health
        # 🚀 FIX: Safely checks the SystemSetting key/value structure
        active_broadcast = False
        broadcast_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_enabled").first()
        if broadcast_setting and broadcast_setting.value == "true":
            active_broadcast = True

        return {
            "headcount": {
                "total": total_users,
                "active": active_users,
                "max_seats": max_seats,
                "percent_used": min(100, percent_used), # Cap at 100% for the UI gauge
                "registration_lock": registration_lock
            },
            "bottlenecks": {
                "leaves": pending_leaves,
                "ot": pending_ot,
                "total_stuck": pending_leaves + pending_ot
            },
            "incidents": {
                "open": open_incidents,
                "critical_p1": 0
            },
            "system_health": {
                "broadcast_active": active_broadcast,
                "db_status": "Healthy"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch global stats: {str(e)}")
    
# 🎯 Ensure this regex rule is defined above the endpoint in user.py
USERNAME_REGEX = re.compile(r"^[a-z0-9-]{1,10}$")

# ============================================================
# 🔍 PHASE 1: IN-MEMORY DATA INTEGRITY DIAGNOSTICS
# ============================================================
@router.post("/bulk-onboard/validate")
async def bulk_onboard_validate(
    file: UploadFile = File(...),
    x_username: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication missing.")
    requester = db.query(models.User).filter(models.User.username == x_username).first()
    if not requester or requester.role != "superuser":
        raise HTTPException(status_code=403, detail="Access denied. Superuser only.")

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid format. Must be a CSV.")

    contents = await file.read()
    try:
        decoded_text = contents.decode('utf-8-sig')
    except UnicodeDecodeError:
        decoded_text = contents.decode('latin-1')
        
    buffer = io.StringIO(decoded_text)
    reader = csv.DictReader(buffer)

    mandatory_fields = {'full_name', 'first_name', 'last_name', 'email', 'joined_date', 'mobile'}
    if not mandatory_fields.issubset(set(reader.fieldnames or [])):
        missing = mandatory_fields - set(reader.fieldnames or [])
        raise HTTPException(status_code=400, detail=f"Missing columns: {list(missing)}")

    validation_results = []
    is_entire_file_valid = True
    existing_usernames = {u.username for u in db.query(models.User.username).all()}
    existing_emp_ids = {u.employee_id for u in db.query(models.User.employee_id).filter(models.User.employee_id != None).all()}

    # 🛡️ SAFE UPGRADE: Build look-up cache for existing full names (handles soft-warnings)
    existing_full_names = {u.full_name.strip().lower() for u in db.query(models.User.full_name).filter(models.User.full_name != None).all()}

    # ⚡ PRESERVED EXACTLY: Your active sequencing numbers to keep '009' alignment
    next_sim_num = 1001 
    last_user = db.query(models.User).filter(models.User.employee_id.like("EMP-%")).order_by(models.User.id.desc()).first()
    if last_user and last_user.employee_id:
        try:
            next_sim_num = int(last_user.employee_id.split("-")[-1]) + 1
        except: pass

    for idx, row in enumerate(reader, start=2):
        row_errors = []
        f_name, first_n, last_n = row.get('full_name','').strip(), row.get('first_name','').strip(), row.get('last_name','').strip()
        email_addr, emp_id, uname = row.get('email','').strip().lower(), row.get('employee_id','').strip(), row.get('username','').strip().lower()

        if not f_name or not email_addr: row_errors.append("Missing mandatory fields.")
        
        sim_id = emp_id if emp_id else f"EMP-2026-{next_sim_num:03d}"
        if not emp_id: next_sim_num += 1
        elif sim_id in existing_emp_ids: row_errors.append(f"ID Conflict: {sim_id}")

        if not uname:
            base = first_n.lower().replace(" ", "")[:10] or "emp"
            sim_uname = base
            count = 1
            while sim_uname in existing_usernames:
                suffix = str(count)
                sim_uname = f"{base[:10-len(suffix)]}{suffix}"
                count += 1
        else:
            sim_uname = uname
            if not USERNAME_REGEX.match(sim_uname): row_errors.append("Invalid username format.")
            elif sim_uname in existing_usernames: row_errors.append(f"Username taken: {sim_uname}")

        # 🛡️ SAFE UPGRADE: Flag same-name records without throwing a blocking validation error
        is_name_duplicate = f_name.lower().strip() in existing_full_names if f_name else False

        status = "Valid" if not row_errors else "Error"
        if status == "Error": is_entire_file_valid = False
        
        validation_results.append({
            "row": idx, 
            "employee_id": sim_id, 
            "username": sim_uname,
            "full_name": f_name or "Unknown", 
            "email": email_addr or "Unknown",
            "status": status, 
            "is_name_duplicate": is_name_duplicate,  # Added safely
            "notes": "Ready" if status == "Valid" else " | ".join(row_errors)
        })

    # 🛡️ ROLE FILTER UPGRADE: Fetch only qualified Line Managers (Managers + Senior Managers)
    db_managers = db.query(models.User.id, models.User.full_name, models.User.employee_id).filter(
        (models.User.role == "manager") | (models.User.is_senior_manager == True)
    ).all()
    
    # 🛡️ ROLE FILTER UPGRADE: Fetch only qualified HODs (Senior Managers)
    db_hods = db.query(models.User.id, models.User.full_name, models.User.employee_id).filter(
        models.User.is_senior_manager == True
    ).all()

    managers_list = [
        {"id": m.id, "full_name": m.full_name or "Unknown", "employee_id": m.employee_id or ""}
        for m in db_managers
    ]
    
    hods_list = [
        {"id": h.id, "full_name": h.full_name or "Unknown", "employee_id": h.employee_id or ""}
        for h in db_hods
    ]

    return {
        "can_proceed": is_entire_file_valid, 
        "total_rows": len(validation_results), 
        "rows": validation_results,
        "available_managers": managers_list,  # Segregated Line Managers list
        "available_hods": hods_list           # Segregated HODs list
    }

# ============================================================
# 📧 BACKGROUND WORKER: EMAIL DISPATCH
# ============================================================
def bulk_onboard_email_worker(log_id, raw_password, session_factory):
    db = session_factory()
    try:
        log = db.query(models.BulkOnboardLog).filter(models.BulkOnboardLog.id == log_id).first()
        if not log: return
        log.email_status = "Processing"
        db.commit()

        from app.utils.email_service import template_new_user, send_email
        body = template_new_user(name=log.full_name, username=log.username, password=raw_password)
        send_email(log.email, "🎉 Welcome to the Team", body)
        
        log.email_status = "Sent"
        db.commit()
    except Exception as e:
        db.rollback()
        log = db.query(models.BulkOnboardLog).filter(models.BulkOnboardLog.id == log_id).first()
        if log:
            log.email_status = "Failed"
            log.failure_reason = str(e)
            db.commit()
    finally: db.close()


# ============================================================
# 🚀 PHASE 2: ATOMIC DATABASE COMMIT (ALL PROFILE FIELDS MERGED)
# ============================================================
@router.post("/bulk-onboard/commit")
async def bulk_onboard_commit(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    hierarchy_mappings: Optional[str] = Form(None), # 🛡️ UPGRADE: Safely capture browser mapping collection strings
    x_username: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not x_username: 
        raise HTTPException(status_code=401, detail="Authentication missing.")
    req = db.query(models.User).filter(models.User.username == x_username).first()
    if not req or req.role != "superuser": 
        raise HTTPException(status_code=403, detail="Access denied. Superuser only.")

    contents = await file.read()
    try:
        decoded = contents.decode('utf-8-sig')
    except:
        decoded = contents.decode('latin-1')
    reader = csv.DictReader(io.StringIO(decoded))

    batch_token = f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    policy = db.query(models.GlobalPolicy).first()
    
    # 🛡️ UPGRADE: Decode string stream parameter array dictionary safely
    mappings_dict = {}
    if hierarchy_mappings:
        try:
            mappings_dict = json.loads(hierarchy_mappings)
        except Exception:
            pass # Keep dict empty if parsing fails to avoid dropping the batch execution

    # Auto-numbering logic (Preserved exactly to match your tracking codes)
    next_num = 1001
    last = db.query(models.User).filter(models.User.employee_id.like("EMP-%")).order_by(models.User.id.desc()).first()
    if last:
        try: 
            next_num = int(last.employee_id.split("-")[-1]) + 1
        except: 
            pass

    existing_usernames = {u.username for u in db.query(models.User.username).all()}
    committed_logs = []

    for idx, row in enumerate(reader, start=2):
        f_name, first_n, last_n = row.get('full_name','').strip(), row.get('first_name','').strip(), row.get('last_name','').strip()
        email, emp_id, uname = row.get('email','').strip().lower(), row.get('employee_id','').strip(), row.get('username','').strip().lower()

        final_id = emp_id if emp_id else f"EMP-2026-{next_num:03d}"
        if not emp_id: next_num += 1

        if not uname:
            base = first_n.lower().replace(" ", "")[:10] or "emp"
            final_uname = base
            c = 1
            while final_uname in existing_usernames:
                s = str(c)
                final_uname = f"{base[:10-len(s)]}{s}"
                c += 1
        else: 
            final_uname = uname
        existing_usernames.add(final_uname)

        # 🛡️ UPGRADE: Match current spreadsheet index against browser hierarchy allocations
        row_key = str(idx)
        chosen_manager = []
        chosen_hod = []
        
        if row_key in mappings_dict:
            mgr_val = mappings_dict[row_key].get("line_manager", "").strip()
            hod_val = mappings_dict[row_key].get("hod_name", "").strip()
            if mgr_val: 
                chosen_manager = [mgr_val]  # Encapsulated cleanly as JSON list arrays
            if hod_val: 
                chosen_hod = [hod_val]     # Encapsulated cleanly as JSON list arrays

        try:
            pw = "Welcome@2026"
            
            # 🎯 INTERNAL CLEANING UTILITY: Trims whitespace and converts empty values to None
            def get_optional(key: str, default_val=None):
                val = row.get(key)
                if val is None:
                    return default_val
                return val.strip() if val.strip() else default_val

            new_user = models.User(
                # Core Account Data (Preserved Existing Attributes)
                username=final_uname, 
                full_name=f_name, 
                first_name=first_n, 
                last_name=last_n,
                email=email, 
                employee_id=final_id, 
                role="employee", 
                password=pw, 
                is_active=True,
                
                # Core Employment Details (Preserved Existing Attributes)
                joined_date=row.get('joined_date','').strip(), 
                job_title=row.get('job_title','Admin').strip(),
                department=row.get('department','HR').strip(), 
                line_manager=chosen_manager, # 🛡️ Saved safely from manual frontend selection dropdowns
                hod_name=chosen_hod,         # 🛡️ Saved safely from manual frontend selection dropdowns
                
                # 🏢 Corporate Identity & Contract Spec Variables
                middle_name=get_optional('middle_name'),
                preferred_name=get_optional('preferred_name'),
                contract_type=get_optional('contract_type'),
                business_unit=get_optional('business_unit'),
                work_location=get_optional('work_location'),
                
                # 🏷️ Extended Enterprise Profile Identifiers 
                common_name=get_optional('common_name'),
                employee_no_old=get_optional('employee_no_old'),
                lotus_notes_id=get_optional('lotus_notes_id'),
                company=get_optional('company'),
                location=get_optional('location'),
                position_grade=get_optional('position_grade'),
                category=get_optional('category'),
                ranking=get_optional('ranking'),
                expat_type=get_optional('expat_type'),
                employee_status=get_optional('employee_status'),
                document_status=get_optional('document_status'),
                highest_qualification=get_optional('highest_qualification'),
                
                # 🗂️ Department Hierarchy Structural Matrix
                organization_o=get_optional('organization_o'),
                organization_ou1=get_optional('organization_ou1'),
                organization_ou2=get_optional('organization_ou2'),
                level_0=get_optional('level_0'),
                level_1=get_optional('level_1'),
                level_2=get_optional('level_2'),
                
                # 📅 Account Milestones & Departure Date Safeties
                contract_expiry_date=get_optional('contract_expiry_date'),
                date_resigned=get_optional('date_resigned'),
                last_working_day=get_optional('last_working_day'),
                last_day_of_service=get_optional('last_day_of_service'),
                date_ict_removal=get_optional('date_ict_removal'),
                
                # ⚙️ Operational Workflow Configurations (Fallbacks cleanly to 'No')
                shift_employee=get_optional('shift_employee', 'No'),
                compensation_leave_entitled=get_optional('compensation_leave_entitled', 'No'),
                commissioning_engineer=get_optional('commissioning_engineer', 'No'),
                scholar=get_optional('scholar', 'No'),
                
                # 👤 Personal Information Identity Specifications
                gender=get_optional('gender'),
                marital_status=get_optional('marital_status'),
                ic_number=get_optional('ic_no') or get_optional('ic_number'), # Securely catches either common spreadsheet header name variant
                nationality=get_optional('nationality'),
                place_of_birth=get_optional('place_of_birth'),
                dob=get_optional('dob'),
                race=get_optional('race'),
                religion=get_optional('religion'),
                
                # 📞 Emergency Contact & Communication Registries
                mobile=row.get('mobile','').strip() or None,
                personal_email=get_optional('personal_email'),
                home_address=get_optional('home_address'),
                current_address=get_optional('current_address'),
                emergency_contact_name=get_optional('emergency_contact_name'),
                emergency_contact_rel=get_optional('emergency_contact_rel'),
                emergency_contact_mobile=get_optional('emergency_contact_mobile'),
                
                # 💳 Salary Disbursal Financial Mappings
                bank_name=get_optional('bank_name'),
                bank_account_number=get_optional('bank_account_number'),
                bank_holder_name=get_optional('bank_holder_name'),
                bank_account_status=get_optional('bank_account_status', 'Active')
            )
            db.add(new_user)
            db.flush()
            db.add(models.UserRole(user_id=new_user.id, role_name="employee"))

            # Seed Balances
            balances = [("Annual Leave", policy.annual_days if policy else 14), 
                        ("Medical Leave", policy.medical_days if policy else 14),
                        ("Emergency Leave", 2), ("Compassionate Leave", 3)]
            for lt, val in balances:
                db.add(models.LeaveBalance(employee_name=f_name, year=datetime.now().year, leave_type=lt, entitlement=val, remaining=val))

            log = models.BulkOnboardLog(batch_id=batch_token, row_number=idx, employee_id=final_id, username=final_uname, full_name=f_name, email=email, account_status="Created", email_status="Pending")
            db.add(log)
            db.flush()
            committed_logs.append((log.id, pw))
        except Exception as e:
            db.rollback()
            db.add(models.BulkOnboardLog(batch_id=batch_token, row_number=idx, full_name=f_name, account_status="Skipped", email_status="N/A", failure_reason=str(e)))
            db.commit()
        db.commit() # Final commit block for individual record assurance updates

    # 🛫 DISPATCH BACKGROUND WORKERS (Sends the emails while you watch the progress)
    from app.database import SessionLocal
    for log_id, raw_pw in committed_logs:
        background_tasks.add_task(bulk_onboard_email_worker, log_id, raw_pw, SessionLocal)

    return {"message": "Batch processed successfully.", "batch_id": batch_token}

# ============================================================
# 🔄 EXTRA STEP: INDIVIDUAL EMAIL RETRY CIRCUIT FOR FAILED ROWS
# ============================================================
@router.post("/bulk-onboard/retry/{log_id}")
async def bulk_onboard_retry_email(
    log_id: int,
    background_tasks: BackgroundTasks,
    x_username: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # 🔒 1. SUPERUSER SECURITY GUARD
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication credentials missing.")
    requester = db.query(models.User).filter(models.User.username == x_username).first()
    if not requester or requester.role != "superuser":
        raise HTTPException(status_code=403, detail="Access denied. Superuser only.")

    # 🔍 2. LOOKUP TARGET LOG RECORD
    log_row = db.query(models.BulkOnboardLog).filter(models.BulkOnboardLog.id == log_id).first()
    if not log_row:
        raise HTTPException(status_code=404, detail="Onboarding transaction log row not found.")

    if log_row.email_status == "Sent":
        return {"status": "info", "message": f"Email for {log_row.full_name} has already been sent successfully."}

    # ⚙️ 3. RE-ARM QUEUE STATE
    log_row.email_status = "Pending"
    log_row.failure_reason = None
    db.commit()

    # Re-dispatch execution back into the out-of-band background task thread
    from app.database import SessionLocal
    background_tasks.add_task(
        bulk_onboard_email_worker,
        log_row.id,
        "Welcome@2026",  # Dispatched with default account baseline access keys
        SessionLocal
    )

    return {
        "status": "success",
        "message": f"Welcome email delivery re-queued for {log_row.full_name}."
    }


# ============================================================
# 📊 PROGRESS ENGINE: FETCH LIVE PROGRESS METRICS FOR A BATCH
# ============================================================
@router.get("/bulk-onboard/batch/{batch_id}")
def bulk_onboard_get_batch_status(
    batch_id: str,
    x_username: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    # 🔒 Superuser Gatekeeper Check
    if not x_username:
        raise HTTPException(status_code=401, detail="Authentication missing.")
    requester = db.query(models.User).filter(models.User.username == x_username).first()
    if not requester or requester.role != "superuser":
        raise HTTPException(status_code=403, detail="Access denied. Superuser only.")

    # 🔍 Pull matching log rows for this specific batch transaction window
    logs = db.query(models.BulkOnboardLog)\
             .filter(models.BulkOnboardLog.batch_id == batch_id)\
             .order_by(models.BulkOnboardLog.row_number.asc())\
             .all()

    serialized_rows = []
    for log in logs:
        # 🕵️‍♂️ DYNAMIC LOOKUP: Fetch successfully mapped supervisors from user profiles
        user_rec = db.query(models.User).filter(models.User.employee_id == log.employee_id).first()
        mgr_str = ", ".join(user_rec.line_manager) if user_rec and user_rec.line_manager else "—"
        hod_str = ", ".join(user_rec.hod_name) if user_rec and user_rec.hod_name else "—"

        serialized_rows.append({
            "id": log.id,
            "row": log.row_number,
            "employee_id": log.employee_id,
            "username": log.username,
            "full_name": log.full_name,
            "email": log.email,
            "line_manager": mgr_str,  # 🚀 FIXED: Added to serialization payload
            "hod_name": hod_str,      # 🚀 FIXED: Added to serialization payload
            "account_status": log.account_status,
            "email_status": log.email_status,
            "notes": log.failure_reason or ("Delivered successfully" if log.email_status == "Sent" else "Processing pipeline...")
        })

    return {
        "batch_id": batch_id,
        "rows": serialized_rows
    }


# ============================================================
# 🔒 SYSTEM COMMAND CENTER: HEADCOUNT LIMITS
# ============================================================
@router.post("/headcount-limits")
def update_headcount_limits(
    payload: models.HeadcountLimitsRequest,
    db: Session = Depends(get_db)
):
    """
    Saves the Max Capacity and Registration Lock constraints to the master policy.
    """
    try:
        # Fetch the master policy record (ID=1)
        policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
        
        if not policy:
            # If it doesn't exist for some reason, create it
            policy = models.GlobalPolicy(
                id=1, 
                max_seats=payload.max_seats, 
                registration_lock=payload.registration_lock
            )
            db.add(policy)
        else:
            # Update the existing record safely
            policy.max_seats = payload.max_seats
            policy.registration_lock = payload.registration_lock
            
        db.commit()
        return {"message": "Provisioning constraints updated successfully."}
    
    except Exception as e:
        db.rollback()
        print(f"❌ Limits Save Error: {e}")
        raise HTTPException(status_code=500, detail="Database transaction failed while saving limits.")