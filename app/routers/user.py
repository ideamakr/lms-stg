from fastapi import APIRouter, Depends, HTTPException, Form, Body, Header, BackgroundTasks, File, UploadFile, Query # 🚀 Added Query
from sqlalchemy.orm import Session
from app import models, database  
import json
from datetime import datetime
import secrets
from pydantic import BaseModel
from typing import Optional, List
import re
from sqlalchemy.exc import IntegrityError

# 🚀 Added these 3 imports for saving files locally!
import os      
import shutil  
import time
from sqlalchemy import func

# 🚀 ADDED: Email Service Imports for Admin Actions
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

# 🚀 NEW: Schema for the "Change Password" tab
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

router = APIRouter(prefix="/users", tags=["Users"])

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
    
    result = []
    
    # Safely map every user to a dictionary
    for u in users:
        # --- Existing Roles Logic ---
        roles_list = ["employee"]
        for r in u.assigned_roles:
            if r.role_name.lower() != "employee" and r.role_name not in roles_list:
                roles_list.append(r.role_name)
        if u.role and u.role not in roles_list:
            roles_list.append(u.role)

        # 🚀 PHASE 3: NEW STATUS LOGIC
        # Check if this specific user has an 'Approved' leave overlapping today
        current_leave = db.query(models.Leave).filter(
            models.Leave.employee_name == u.full_name,
            models.Leave.status == 'Approved',
            models.Leave.start_date <= today,
            models.Leave.end_date >= today
        ).first()
        
        # Format the date for the frontend (e.g., "2026-05-10") or return None
        leave_end_str = str(current_leave.end_date) if current_leave else None
            
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

        except IntegrityError:
            db.rollback() 
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

from fastapi import Header

@router.put("/{user_id}/profile-update")
async def update_user_profile(
    user_id: int,
    
    # 📋 STEP 1
    full_name: str = Form(...), 
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...), 
    joined_date: str = Form(...),
    mobile: str = Form(...), 

    # 📋 OPTIONALS
    middle_name: Optional[str] = Form(None),
    job_title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    line_manager: Optional[str] = Form(None),
    hod_name: Optional[str] = Form(None),
    contract_type: Optional[str] = Form(None),
    business_unit: Optional[str] = Form(None),
    work_location: Optional[str] = Form(None),

    # 👤 STEP 2
    preferred_name: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    marital_status: Optional[str] = Form(None),
    ic_no: Optional[str] = Form(None),
    nationality: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    race: Optional[str] = Form(None),
    religion: Optional[str] = Form(None),

    # 📞 STEP 3
    personal_email: Optional[str] = Form(None),
    home_address: Optional[str] = Form(None),
    current_address: Optional[str] = Form(None),
    emergency_contact_name: Optional[str] = Form(None),
    emergency_contact_rel: Optional[str] = Form(None),
    emergency_contact_mobile: Optional[str] = Form(None),
    
    profile_pic: Optional[UploadFile] = File(None),
    x_username: Optional[str] = Header(None), # 🔒 SECURITY BADGE INJECTED HERE
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🚀 PHASE 2 UPDATE: Helper logic to parse multiple manager lists
    def parse_manager_list(data):
        if not data: return []
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, list) else [str(data)]
        except:
            return [str(data)] if data else []

    final_line_managers = parse_manager_list(line_manager)
    final_hod_names = parse_manager_list(hod_name)

    old_name = user.full_name
    new_name = full_name.strip()

    # 🚀 CASCADING NAME SYNC
    if old_name != new_name:
        db.query(models.LeaveBalance).filter(models.LeaveBalance.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Leave).filter(models.Leave.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Overtime).filter(models.Overtime.employee_name == old_name).update({"employee_name": new_name})
        db.query(models.Leave).filter(models.Leave.approver_name == old_name).update({"approver_name": new_name})
        db.query(models.Overtime).filter(models.Overtime.approver_name == old_name).update({"approver_name": new_name})
        db.query(models.Leave).filter(models.Leave.approver_l2 == old_name).update({"approver_l2": new_name})

    # Update Profile Picture if uploaded
    if profile_pic:
        try:
            from app.main import compress_and_upload
            user.profile_pic_url = compress_and_upload(profile_pic, folder="avatars")
        except Exception as e:
            print(f"Avatar Upload Warning: {e}")

    # ============================================================
    # 🛡️ THE BACKEND SECURITY LOCKDOWN
    # ============================================================
    is_admin = False
    is_self_edit = False
    
    # 1. Check who is making this request via the header
    if x_username:
        requester = db.query(models.User).filter(models.User.username == x_username).first()
        if requester:
            if requester.id == user.id:
                is_self_edit = True
            
            roles_list = [r.role_name for r in requester.assigned_roles] if hasattr(requester, 'assigned_roles') else []
            if requester.role in ["hr_admin", "admin", "superuser"] or "hr_admin" in roles_list:
                is_admin = True

    # 2. ALWAYS ALLOWED: Map Personal & Contact Fields
    user.full_name = new_name
    user.first_name = first_name.strip() if first_name else None
    user.middle_name = middle_name.strip() if middle_name else None
    user.last_name = last_name.strip() if last_name else None
    user.preferred_name = preferred_name.strip() if preferred_name else None
    user.email = email.strip().lower()
    user.mobile = mobile.strip()
    user.gender = gender
    user.marital_status = marital_status
    user.ic_number = ic_no.strip() if ic_no else None
    user.nationality = nationality.strip() if nationality else None
    user.dob = dob
    user.race = race.strip() if race else None
    user.religion = religion.strip() if religion else None
    user.personal_email = personal_email.strip() if personal_email else None
    user.home_address = home_address.strip() if home_address else None
    user.current_address = current_address.strip() if current_address else None
    user.emergency_contact_name = emergency_contact_name.strip() if emergency_contact_name else None
    user.emergency_contact_rel = emergency_contact_rel.strip() if emergency_contact_rel else None
    user.emergency_contact_mobile = emergency_contact_mobile.strip() if emergency_contact_mobile else None

# 3. LOCKDOWN ZONE: Admins can update employment fields for ANYONE (including themselves)
    if is_admin:
        print(f"🔓 [SECURITY] Admin {x_username} updated official employment fields.")
        user.job_title = job_title.strip() if job_title else None
        user.department = department.strip() if department else None
        user.line_manager = final_line_managers
        user.hod_name = final_hod_names
        user.joined_date = joined_date
        user.contract_type = contract_type.strip() if contract_type else None
        user.business_unit = business_unit.strip() if business_unit else None
        user.work_location = work_location.strip() if work_location else None
    else:
        print(f"🔒 [SECURITY] Ignored employment fields. Requester is self-editing and is not an admin.")

    db.commit()
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

    # 2. Verify Current Password
    if user.password != payload.current_password:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    # 3. Update Password
    user.password = payload.new_password
    
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
    
    # 2. Find the highest existing ID to prevent duplicates
    # We look for the user with the largest primary key ID
    last_user = db.query(models.User).order_by(models.User.id.desc()).first()
    
    next_num = 1
    if last_user:
        next_num = last_user.id + 1
    
    # 3. Format: EMP-2026-0001
    next_id = f"EMP-{current_year}-{next_num:04d}"
    
    return {"next_id": next_id}

# --- SYSTEM POLICY ENDPOINTS ---

@router.get("/policy/current")
def get_global_policy(db: Session = Depends(get_db)):
    # Fetch the master policy (ID=1)
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    if not policy:
        # Fallback if seed hasn't run
        return {"l2_approval_enabled": False}
    return {"l2_approval_enabled": policy.l2_approval_enabled}

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
        
        # We will hardcode 200 for now, later we'll pull this from System Settings
        max_seats = 200 

        # 2. Global Leave & OT Bottlenecks (Total Pending across company)
        # Note: Replace 'LeaveRequest' and 'OTRequest' with your actual model names
        pending_leaves = db.query(models.LeaveRequest).filter(models.LeaveRequest.status == "Pending").count()
        pending_ot = db.query(models.OTRequest).filter(models.OTRequest.status == "Pending").count()

        # 3. Incident Triage (Coming soon in next step)
        # For now, we return 0 until we build the Incident table
        open_incidents = 0 

        # 4. System Health
        # Check if any global broadcast is currently active
        active_broadcast = db.query(models.SystemSettings).first().is_broadcast_active if db.query(models.SystemSettings).first() else False

        return {
            "headcount": {
                "total": total_users,
                "active": active_users,
                "max_seats": max_seats,
                "percent_used": (total_users / max_seats) * 100
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