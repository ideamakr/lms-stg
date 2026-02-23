import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Form, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles 
from sqlalchemy.orm import Session
import shutil
import tempfile
from datetime import datetime
# 👇 IMPORT SYSTEM SETTINGS
from app.routers import leave, user, overtime, system_settings 
from app.schemas import BrandingConfig # 🚀 ADD THIS TO PREVENT THE CRASH


# 👇 IMPORT get_db FROM DATABASE
from .database import engine, Base, SessionLocal, get_db
from . import models

# Create Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Leave System API")


# ============================================================
# 🧭 PATH CONFIGURATION (ALIGNED WITH SAFE ZONE)
# ============================================================

# 1. Get the folder where main.py lives (which is 'app/')
BASE_APP_DIR = Path(__file__).resolve().parent 

# 2. Define standard Static Folder (for CSS/JS)
STATIC_DIR = BASE_APP_DIR / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

# 3. 🚀 THE "SAFE ZONE" ALIGNMENT
# We point to the System Temp folder so Uvicorn cannot see file changes
UPLOADS_DIR = Path(tempfile.gettempdir()) / "leave_system_uploads"

# 📂 Ensure the external folder exists
if not UPLOADS_DIR.exists():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 🚀 Mount standard static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 📂 Mount the EXTERNAL Safe Zone to the /uploads URL
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

print(f"✅ Server mapping /uploads to Safe Zone: {UPLOADS_DIR}")
print(f"✅ Uploads Path: {UPLOADS_DIR}")

# 🔒 4. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🛡️ THE GUARD: PLACED AT THE TOP SO ALL ROUTES CAN SEE IT!
# ============================================================
def get_current_superuser(
    db: Session = Depends(get_db), 
    x_username: str = Header(None) 
): 
    if not x_username:
        raise HTTPException(status_code=401, detail="Missing user identity in headers.")
        
    # Search by Username OR Full Name to catch "System Administrator"
    user = db.query(models.User).filter(
        (models.User.username == x_username) | 
        (models.User.full_name == x_username)
    ).first()
    
    if not user:
        print(f"❌ GUARD BLOCKED: User '{x_username}' not found in database.")
        raise HTTPException(status_code=403, detail="Access denied: User not found.")
        
    # 🔍 DEBUG: Print exactly what role the database has for this user
    print(f"🔍 GUARD CHECK: User '{user.full_name}' has the role '{user.role}'")
    
    # 🚀 THE FIX: Accept 'superuser', 'hr_admin', or 'admin'
    if user.role not in ["superuser", "hr_admin", "admin"]:
        print(f"❌ GUARD BLOCKED: Role '{user.role}' is not allowed to change system settings.")
        raise HTTPException(status_code=403, detail="Access denied: Insufficient privileges.")
    
    return user

# ============================================================
# 🚀 ROUTERS & ENDPOINTS
# ============================================================

# Login Route
@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # 1. Identify User
    user_record = db.query(models.User).filter(models.User.username == username).first()
    
    # 2. Verify Credentials (Existing logic)
    if not user_record or user_record.password != password:
        raise HTTPException(status_code=400, detail="Access Denied: Invalid credentials.")

    # 🚀 3. MAINTENANCE GATEKEEPER
    # We check if system is locked. If yes, only 'superuser' role can pass.
    if is_system_locked(db):
        if user_record.role != "superuser":
            # 503 is the standard HTTP code for "Service Unavailable/Maintenance"
            raise HTTPException(
                status_code=503, 
                detail="System is currently under maintenance. Please try again later."
            )
    
    # 4. Success Path (Existing logic)
    roles_list = [r.role_name for r in user_record.assigned_roles]
    if not roles_list:
        roles_list = [user_record.role] if user_record.role else ["employee"]
    
    return {"full_name": user_record.full_name, "roles": roles_list}


# ============================================================
# 🚀 SYSTEM LOCKED GATEKEEPER
# ============================================================
def is_system_locked(db: Session):
    """Checks if maintenance is enabled and if the current time is within the window."""
    m_enabled = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_enabled").first()
    m_mode = db.query(models.SystemSetting).filter(models.SystemSetting.key == "maintenance_mode").first()
    
    # If the master toggle is OFF or Maintenance Lock is OFF, system is NOT locked
    if not m_enabled or m_enabled.value != "true": return False
    if not m_mode or m_mode.value != "true": return False

    # Get the window times
    start_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_start").first()
    end_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_end").first()

    if not start_setting or not end_setting or not start_setting.value or not end_setting.value: 
        return False

    try:
        now = datetime.now()
        
        # 🛡️ DEFENSIVE FIX: Slice the string to the first 16 characters (YYYY-MM-DDTHH:MM)
        # This safely strips away any seconds or milliseconds a browser might append.
        clean_start = start_setting.value[:16]
        clean_end = end_setting.value[:16]
        
        start_dt = datetime.strptime(clean_start, "%Y-%m-%dT%H:%M")
        end_dt = datetime.strptime(clean_end, "%Y-%m-%dT%H:%M")
        
        return start_dt <= now <= end_dt
    except Exception as e:
        print(f"🕒 Time Check Error: {e}")
        return False
    

@app.post("/settings/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    """
    Saves the uploaded logo to the server's Safe Zone and returns the URL.
    """
    try:
        extension = Path(file.filename).suffix
        if extension.lower() not in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        filename = f"company_logo{extension}"
        file_path = UPLOADS_DIR / filename
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {"logo_url": f"/uploads/{filename}"}
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload logo")
    
    # ✅ REGISTER ALL ROUTERS
app.include_router(leave.router)
app.include_router(user.router)
app.include_router(overtime.router)
app.include_router(system_settings.router)