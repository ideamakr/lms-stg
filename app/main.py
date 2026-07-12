import os
import io
import uuid
import pytz
import logging
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# 1. Force environment encoding
os.environ["PYTHONIOENCODING"] = "utf-8"

# 2. Reconfigure standard output/error
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 3. Configure Timezone-aware Logging
def custom_time(*args):
    # Renamed to my_dt for clarity
    my_dt = datetime.now(pytz.timezone('Asia/Kuala_Lumpur'))
    return my_dt.timetuple()

# Apply the custom time to the standard logging formatter
logging.Formatter.converter = custom_time

# 4. Add the Uvicorn Logging Config
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(asctime)s - %(levelname)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO"},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}

# 👇 ADD THESE TWO LINES HERE TO APPLY THE CONFIG IMMEDIATELY
import logging.config
logging.config.dictConfig(LOGGING_CONFIG)

# Now proceed with your app initialization...

# 👇 THIRD PARTY IMPORTS
from fastapi import FastAPI, Depends, HTTPException, Form, File, UploadFile, Header
from fastapi.staticfiles import StaticFiles 
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from PIL import Image
from dotenv import load_dotenv

# 👇 LOCAL APPLICATION IMPORTS
from app.database import engine, Base, get_db
from app import models, schemas
from app.utils.security import verify_password
# 🚀 ADDED 'incidents' to the router imports below:
from app.routers import leave, user, overtime, system_settings, incidents 
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import text

# 👇 INITIALIZE ENVIRONMENT
load_dotenv()


# 🏢 MULTI-TENANT CONFIGURATION
CLIENT_NAME = os.getenv("CLIENT_NAME", "psyap & co")


# 🚀 2. SET GLOBAL TIMEZONE
LOCAL_TZ = pytz.timezone('Asia/Kuala_Lumpur')

# Create Database Tables (Note: Only creates NEW tables, won't update existing ones)
Base.metadata.create_all(bind=engine)

# ============================================================
# 📦 SCHEMAS
# ============================================================
class LoginRequest(BaseModel):
    username: str
    password: str

# ============================================================
# 🛠️ APP INITIALIZATION
# ============================================================
# 🚀 Dynamic Title Fixed (Removed the duplicate row that was overwriting it)
app = FastAPI(title=f"{CLIENT_NAME} Leave System API")

# 🚀 MOUNT THE UPLOADS FOLDER
# serving local fallback images for profiles
if not os.path.exists("uploads"):
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("uploads/avatars", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 🔒 CORS Configuration
allowed_origins = [
    "http://127.0.0.1:5500", 
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://leave.psyap.com:8080"
]

# 🚀 Dynamically whitelist the production/Cloudflare domain and its variants
CLIENT_DOMAIN = os.getenv("CLIENT_DOMAIN")
if CLIENT_DOMAIN:
    # Add the base domain
    allowed_origins.append(CLIENT_DOMAIN)
    
    # If the domain doesn't already end with a port, add the 8081 variant
    if ":" not in CLIENT_DOMAIN.split("//")[-1]:
        # Construct the port 8081 variant
        port_8081_domain = f"{CLIENT_DOMAIN}:8081"
        allowed_origins.append(port_8081_domain)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)
# ============================================================
# 📸 UTILITIES
# ============================================================
def compress_and_upload(file: UploadFile, folder: str = "mcs") -> str:
    """Shrinks images to < 500KB and saves them locally on the server."""
    try:
        # Read the bytes
        contents = file.file.read()
        
        # 🛡️ SAFETY CHECK: Is the file actually empty?
        if not contents:
            raise ValueError("File content is empty.")

        img = Image.open(io.BytesIO(contents))

        # Convert to standard RGB to drop alpha channels for JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Generate the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_filename = Path(file.filename).stem 
        clean_name = f"{timestamp}_{clean_filename.replace(' ', '_')}.jpg"
        
        # Define the exact path
        target_dir = f"uploads/{folder}"
        os.makedirs(target_dir, exist_ok=True)
        file_path = f"{target_dir}/{clean_name}"
        
        # Save with compression
        img.save(file_path, format="JPEG", quality=60, optimize=True)

        return f"/uploads/{folder}/{clean_name}"

    except Exception as e:
        print(f"❌ Local Upload Error: {e}")
        raise ValueError(f"Failed to process image: {e}")

def is_system_locked(db: Session):
    """Checks if maintenance mode is active within the scheduled window."""
    m_enabled = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_enabled").first()
    m_mode = db.query(models.SystemSetting).filter(models.SystemSetting.key == "maintenance_mode").first()
    
    if not m_enabled or m_enabled.value != "true": return False
    if not m_mode or m_mode.value != "true": return False

    start_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_start").first()
    end_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "broadcast_end").first()

    if not start_setting or not end_setting or not start_setting.value or not end_setting.value: 
        return False

    try:
        now = datetime.now()
        start_dt = datetime.strptime(start_setting.value[:16], "%Y-%m-%dT%H:%M")
        end_dt = datetime.strptime(end_setting.value[:16], "%Y-%m-%dT%H:%M")
        return start_dt <= now <= end_dt
    except Exception as e:
        print(f"🕒 Time Check Error: {e}")
        return False

# ============================================================
# 🛡️ SECURITY DEPENDENCIES
# ============================================================
def get_current_superuser(db: Session = Depends(get_db), x_username: str = Header(None)): 
    if not x_username:
        raise HTTPException(status_code=401, detail="Missing user identity in headers.")
        
    user = db.query(models.User).filter(
        (models.User.username == x_username) | (models.User.full_name == x_username)
    ).first()
    
    if not user:
        raise HTTPException(status_code=403, detail="Access denied: User not found.")
        
    if user.role not in ["superuser", "hr_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied: Insufficient privileges.")
    
    return user

# ============================================================
# 🚀 SYSTEM ROUTES
# ============================================================
@app.get("/system/today")
def get_system_today():
    now = datetime.now(LOCAL_TZ)
    return {
        "today": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "Asia/Kuala_Lumpur"
    }

@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user_record = db.query(models.User).filter(models.User.username == data.username).first()
    
    if not user_record or not verify_password(data.password, user_record.password):
        raise HTTPException(status_code=400, detail="Access Denied: Invalid credentials.")

    if is_system_locked(db):
        if user_record.role != "superuser":
            raise HTTPException(
                status_code=503, 
                detail="System is currently under maintenance. Please try again later."
            )
    
    new_session_id = f"session-{uuid.uuid4()}" 
    user_record.current_session_id = new_session_id 
    db.commit()

    # Success Path - Map assigned roles
    roles_list = [r.role_name for r in user_record.assigned_roles]
    if not roles_list:
        roles_list = [user_record.role] if user_record.role else ["employee"]
    
    return {
        "full_name": user_record.full_name, 
        "roles": roles_list,
        "session_id": new_session_id,
        "username": user_record.username
    }

@app.post("/settings/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    extension = Path(file.filename).suffix.lower()
    if extension not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Invalid image format")
    
    public_url = compress_and_upload(file, folder="system")
    return {"logo_url": public_url}

# ============================================================
# 🏁 REGISTER ROUTERS
# ============================================================
app.include_router(leave.router)
app.include_router(user.router)
app.include_router(overtime.router)
app.include_router(system_settings.router)
app.include_router(incidents.router)  # 🚀 ADDED THIS LINE PROPERLY

@app.get("/")
def read_root():
    return {"status": "Leave System API is Online", "docs": "/docs"}

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return RedirectResponse(url="https://cdn-icons-png.flaticon.com/512/1063/1063376.png")

@app.get("/api/system/version")
async def get_version(db: Session = Depends(get_db)):
    try:
        # Wrap the raw SQL string inside text()
        query = text("SELECT value FROM system_settings WHERE key = 'system_version'")
        version_setting = db.execute(query).fetchone()
        
        if version_setting:
            return {"version": version_setting[0]}
        
        return {"version": "v1.0.0-fallback"}
        
    except Exception as e:
        # Catch any DB errors (like missing tables) so it doesn't cause a 500 crash
        print(f"⚠️ Version Sync Error: {e}")
        return {"version": "v1.0.0-fallback"}
    
    # --- LOGGING SETUP ---
LOG_DIR = r"C:\leave-system\leave-system\logs"
LOG_FILE = os.path.join(LOG_DIR, "server_logs.txt")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)