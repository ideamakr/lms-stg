from fastapi import APIRouter, Depends, HTTPException, Form, Body, Header, BackgroundTasks # 🚀 Added BackgroundTasks
from sqlalchemy.orm import Session
from app import models, database  
import json
from datetime import datetime
import secrets
from pydantic import BaseModel
from typing import Optional 

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
def get_all_users(search: str = "", role: str = "", db: Session = Depends(get_db)):
    # 🚀 THE GHOST FILTER:
    # We start the query by excluding the 'superuser' role.
    # This ensures 'usersuper' never appears in employee lists or counts.
    query = db.query(models.User).filter(models.User.role != "superuser")
    
    # Existing Search Logic
    if search:
        query = query.filter(models.User.full_name.ilike(f"%{search}%"))
        
    # Existing Role Logic
    if role:
        query = query.filter(models.User.role == role)

    users = query.all()
    result = []
    
    for u in users:
        # Initial roles list
        roles_list = ["employee"]
        
        # Check assigned_roles relationship
        for r in u.assigned_roles:
            if r.role_name.lower() != "employee" and r.role_name not in roles_list:
                roles_list.append(r.role_name)
        
        # Check master role column
        if u.role and u.role not in roles_list:
            roles_list.append(u.role)
            
        result.append({
            "id": u.id,
            "full_name": u.full_name or "Unknown",
            "username": u.username,
            "role": u.role or "employee",
            "is_active": getattr(u, 'is_active', True),
            "is_senior_manager": getattr(u, 'is_senior_manager', False), 
            "roles_list": roles_list,
            "employee_id": u.employee_id or "",
            "gender": u.gender or "",
            "marital_status": u.marital_status or "",
            "email": u.email or "",
            "mobile": u.mobile or "",
            "job_title": u.job_title or "",
            "business_unit": u.business_unit or "",
            "department": u.department or "",
            "line_manager": u.line_manager or "",
            "joined_date": str(u.joined_date) if u.joined_date else ""
        })
        
    return result

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

@router.post("/register")
async def register_user(
    background_tasks: BackgroundTasks, 
    username: str = Form(...), 
    full_name: str = Form(...), 
    password: str = Form(...),
    employee_id: str = Form(...),
    gender: str = Form(...),
    marital_status: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    job_title: str = Form(...),
    business_unit: str = Form(...),
    department: str = Form(...),
    line_manager: str = Form(None), # Default to None if not provided
    joined_date: str = Form(...),
    db: Session = Depends(get_db)
):
    # --- 1. STRICT DATA NORMALIZATION ---
    # We clean these BEFORE any database checks to ensure 100% matching
    clean_username = username.strip().lower()
    clean_full_name = full_name.strip()
    clean_email = email.strip().lower()
    clean_line_manager = line_manager.strip() if line_manager else ""
    clean_employee_id = employee_id.strip()

    # --- 2. DUPLICATION GUARD ---
    # Check existence using the normalized data
    existing_user = db.query(models.User).filter(
        (models.User.username == clean_username) | 
        (models.User.email == clean_email)
    ).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this username or email already exists.")

    # --- 3. CREATE USER OBJECT (Clean Data Phase) ---
    new_user = models.User(
        username=clean_username, 
        full_name=clean_full_name, 
        password=password, 
        role="employee",
        employee_id=clean_employee_id,
        gender=gender,
        marital_status=marital_status,
        email=clean_email,
        mobile=mobile.strip(),
        job_title=job_title.strip(),
        business_unit=business_unit.strip(),
        department=department.strip(),
        line_manager=clean_line_manager, 
        joined_date=joined_date,
        is_active=True # Ensure new users are active by default
    )
    db.add(new_user)
    db.flush() # Generate new_user.id for the role table

    # --- 4. ADD DEFAULT ROLE ---
    db.add(models.UserRole(user_id=new_user.id, role_name="employee"))

    # --- 5. FETCH GLOBAL POLICY ---
    policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
    annual = policy.annual_days if policy else 14
    medical = policy.medical_days if policy else 14
    emergency = policy.emergency_days if policy else 2
    compassionate = policy.compassionate_days if policy else 3

    # --- 6. INITIALIZE LEAVE BALANCES (Normalization Sync) ---
    # 🚀 FIX: employee_name must match clean_full_name for dashboard mapping
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
            employee_name=clean_full_name, # 🚀 Linked to the clean name
            leave_type=l_type,
            year=current_year,
            entitlement=float(days),
            remaining=float(days), # Dashboard will show the full balance immediately
            carry_forward_total=0.0
        ))

    try:
        db.commit()
        
        # --- 7. 📧 EMAIL NOTIFICATION TRIGGER (Clean Data Phase) ---
        if clean_email and "@" in clean_email:
            try:
                from app.utils.email_service import send_email, template_new_user
                
                subject = "🎉 Welcome to the Team"
                body = template_new_user(
                    name=clean_full_name, 
                    username=clean_username, 
                    password=password 
                )
                
                # Async hand-off to Brevo
                background_tasks.add_task(send_email, clean_email, subject, body)
            except Exception as mail_err:
                print(f"⚠️ Email Queue Warning: {mail_err}")
                
        return {"message": f"User {clean_full_name} registered successfully."}
    
    except Exception as e:
        db.rollback()
        print(f"❌ Critical Registration Failure: {e}")
        raise HTTPException(status_code=500, detail="Registration failed due to a database error.")

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
def update_user_profile(
    user_id: int,
    full_name: str = Form(...),
    employee_id: str = Form(...),
    gender: str = Form(...),
    marital_status: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    job_title: str = Form(...),
    business_unit: str = Form(...),
    department: str = Form(...),
    line_manager: str = Form(...),
    joined_date: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_name = user.full_name
    new_name = full_name.strip()

    # 🚀 CASCADING NAME SYNC
    if old_name != new_name:
        # 1. Sync Leave Balances (Prevents wallet reset)
        db.query(models.LeaveBalance).filter(models.LeaveBalance.employee_name == old_name).update({"employee_name": new_name})
        
        # 2. Sync Leave History
        db.query(models.Leave).filter(models.Leave.employee_name == old_name).update({"employee_name": new_name})
        
        # 3. Sync Overtime History
        db.query(models.Overtime).filter(models.Overtime.employee_name == old_name).update({"employee_name": new_name})

        # 4. Sync Approver Logs (L1 & L2)
        # If this user was an L1 Approver:
        db.query(models.Leave).filter(models.Leave.approver_name == old_name).update({"approver_name": new_name})
        db.query(models.Overtime).filter(models.Overtime.approver_name == old_name).update({"approver_name": new_name})
        
        # 🚀 NEW: If this user was an L2 Approver (Department Head):
        # We check if the column exists first to be safe, or just run the update if you know it exists.
        db.query(models.Leave).filter(models.Leave.approver_l2 == old_name).update({"approver_l2": new_name})

    # 5. Update the Primary User Record
    user.full_name = new_name
    user.employee_id = employee_id
    user.gender = gender
    user.marital_status = marital_status
    user.email = email
    user.mobile = mobile
    user.job_title = job_title
    user.business_unit = business_unit
    user.department = department
    user.line_manager = line_manager
    user.joined_date = joined_date

    db.commit()
    return {"message": "Profile and related history synced successfully"}

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