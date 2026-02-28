from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import database, models
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["System Settings"])

# --- SCHEMAS ---
class CFSettingUpdate(BaseModel):
    enabled: bool
    confirm_cleanup: bool = False

# New Schema for Rules
class CFRulesUpdate(BaseModel):
    max_days: float
    expiry_date: str

class BrandingConfig(BaseModel):
    company_name: str
    company_sub_info: str  
    company_logo: str
    broadcast_enabled: bool = False
    broadcast_message: str = ""
    broadcast_start: str = ""
    broadcast_end: str = ""
    maintenance_mode: bool = False

# 👇 ADD YOUR VERSION VARIABLE HERE
# APP_VERSION = "v1.0.0"    

# --- 🚀 HELPER: SMART USER LOOKUP ---
def get_current_user(
    employee_name: str = Query(..., alias="employee_name", description="Name of the requester"), 
    db: Session = Depends(database.get_db)
):
    # Try finding by Full Name first
    user = db.query(models.User).filter(models.User.full_name == employee_name).first()
    
    # Fallback: Try finding by Username
    if not user:
        user = db.query(models.User).filter(models.User.username == employee_name).first()

    if not user:
        raise HTTPException(status_code=401, detail=f"User '{employee_name}' not found")
    return user

# --- HELPER: UPDATE DB SETTING ---
def _update_setting(db: Session, key: str, value: str):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if not setting:
        setting = models.SystemSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    # Note: Commit is handled by the caller usually, but adding it here is safe for single updates
    db.commit()

# --- ROUTES ---

# 1. GET ALL SETTINGS (Toggle Status + Config Rules)
@router.get("/carry-forward")
def get_cf_status(db: Session = Depends(database.get_db)):
    # ✅ ALIGNED: Uses 'carry_forward_enabled' to match your main.py/DB
    setting_enabled = db.query(models.SystemSetting).filter(models.SystemSetting.key == "carry_forward_enabled").first()
    is_enabled = setting_enabled.value == "true" if setting_enabled else False

    # B. Fetch Configuration Rules
    max_days_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "cf_max_days").first()
    expiry_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "cf_expiry_date").first()

    # C. Process Values
    max_days_val = 365.0 
    if max_days_setting and max_days_setting.value:
        try:
            max_days_val = float(max_days_setting.value)
        except ValueError:
            max_days_val = 365.0
            
    expiry_val = expiry_setting.value if expiry_setting else None

    return {
        "enabled": is_enabled,
        "max_days": max_days_val,
        "expiry_date": expiry_val
    }

# 2. TOGGLE FEATURE (ON/OFF)
@router.post("/carry-forward")
def toggle_cf_status(
    data: CFSettingUpdate, 
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(database.get_db)
):
    # Authorization Check (Added 'superuser' to match your main.py guard logic)
    if current_user.role not in ["admin", "hr_admin", "superuser"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Case: Turning ON
    if data.enabled:
        # ✅ ALIGNED: Uses 'carry_forward_enabled'
        _update_setting(db, "carry_forward_enabled", "true")
        return {"status": "success", "message": "Carry Forward feature enabled."}

    # Case: Turning OFF - Check for Active Data
    active_cf_requests = db.query(models.Leave).filter(
        models.Leave.leave_type == "Annual Leave",
        models.Leave.reason.contains("[CARRY FORWARD"),
        ~models.Leave.status.in_(["Cancelled", "Rejected", "Withdrawn"]) 
    ).all()
    
    count = len(active_cf_requests)

    if count > 0 and not data.confirm_cleanup:
        return {
            "status": "warning_required",
            "message": f"There are {count} active Carry Forward requests.",
            "count": count
        }

    if count > 0 and data.confirm_cleanup:
        for req in active_cf_requests:
            req.status = "Cancelled"
            req.manager_comments = "System: Feature disabled by Admin. Auto-cancelled."
    
    # ✅ ALIGNED: Uses 'carry_forward_enabled'    
    _update_setting(db, "carry_forward_enabled", "false")
    
    return {"status": "success", "message": f"Carry Forward disabled. {count} requests cancelled.", "action": "disabled"}

# 3. SAVE CONFIG RULES (Max Days & Date)
@router.post("/carry-forward-rules")
def save_cf_rules(
    config: CFRulesUpdate,
    db: Session = Depends(database.get_db)
    # Note: You can add current_user dependency here if you want admin check
):
    try:
        # Save Max Days
        _update_setting(db, "cf_max_days", str(config.max_days))

        # Save Expiry Date
        _update_setting(db, "cf_expiry_date", config.expiry_date)

        print(f"✅ Rules Saved: Max {config.max_days} days, Expires {config.expiry_date}")
        return {"message": "Configuration saved successfully"}

    except Exception as e:
        print(f"❌ Error saving rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

    # 4. GET BRANDING & BROADCAST SETTINGS (Includes Versioning)
@router.get("/branding")
def get_branding(db: Session = Depends(database.get_db)):
    """
    Fetches Company Identity, Broadcast details, and the System Version.
    """
    name_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "company_name").first()
    sub_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "company_sub_info").first() 
    logo_setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "company_logo").first()
    
    def get_val(key, default=""):
        setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
        return setting.value if setting else default

    return {
        # 🚀 THE FIX: Now fetches dynamically from the database!
        "system_version": get_val("system_version", "v1.0.0"), 
        
        "company_name": name_setting.value if name_setting else "IdeaMakr",
        "company_sub_info": sub_setting.value if sub_setting else "Software Studio", 
        "company_logo": logo_setting.value if logo_setting else "",
        
        "broadcast_enabled": get_val("broadcast_enabled", "false").lower() == "true",
        "broadcast_message": get_val("broadcast_message", ""),
        "broadcast_start": get_val("broadcast_start", ""),
        "broadcast_end": get_val("broadcast_end", ""),
        "maintenance_mode": get_val("maintenance_mode", "false").lower() == "true"
    }

# 5. SAVE BRANDING SETTINGS
@router.post("/branding")
def save_branding(config: BrandingConfig, db: Session = Depends(database.get_db)):
    """
    Saves Branding and Broadcast config.
    """
    try:
        def update_setting(key: str, value: str):
            setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
            if setting:
                setting.value = str(value) 
            else:
                new_setting = models.SystemSetting(key=key, value=str(value))
                db.add(new_setting)

        update_setting("company_name", config.company_name[:20])
        update_setting("company_sub_info", config.company_sub_info[:35])
        update_setting("company_logo", config.company_logo)
        
        update_setting("broadcast_enabled", str(config.broadcast_enabled).lower())
        update_setting("broadcast_message", config.broadcast_message)
        update_setting("broadcast_start", config.broadcast_start)
        update_setting("broadcast_end", config.broadcast_end)
        update_setting("maintenance_mode", str(config.maintenance_mode).lower())
        
        db.commit()
        return {"message": "System settings updated successfully"}

    except Exception as e:
        db.rollback()
        print(f"❌ Error saving branding: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    