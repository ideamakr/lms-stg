from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional, List
from .models import LeaveType, LeaveStatus

# --- USER SCHEMAS ---

class UserBase(BaseModel):
    username: str
    full_name: str
    role: str = "employee"
    is_active: bool = True
    is_senior_manager: bool = False

class UserCreate(UserBase):
    password: str
    employee_id: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    business_unit: Optional[str] = None
    department: Optional[str] = None
    line_manager: Optional[str] = None
    joined_date: Optional[str] = None

class UserDisplay(UserBase):
    id: int
    employee_id: Optional[str] = None
    # This helps Pydantic read the SQLAlchemy relationship for roles if needed
    roles_list: Optional[List[str]] = [] 
    
    model_config = ConfigDict(from_attributes=True)

# --- LEAVE SCHEMAS ---

class LeaveCreate(BaseModel):
    employee_name: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str

class LeaveResponse(LeaveCreate):
    id: int
    status: LeaveStatus
    days_taken: float
    model_config = ConfigDict(from_attributes=True)

# 🚀 NEW: LEAVE BALANCE SCHEMA (Add this to fix the empty tiles)
class LeaveBalanceResponse(BaseModel):
    employee_name: str
    year: int
    leave_type: str
    entitlement: float
    remaining: float           # 🟢 Critical for Dashboard
    carry_forward_total: float = 0.0 # 🟢 Critical for CF Logic
    taken: float = 0.0         # Optional helpful stat

    model_config = ConfigDict(from_attributes=True)


    # --- SYSTEM SETTINGS / BRANDING SCHEMAS ---

class BrandingConfig(BaseModel):
    # Original Required Fields
    company_name: str
    company_sub_info: str  
    company_logo: str
    
    # New Optional Fields (Defaults ensure old frontend requests don't crash)
    broadcast_enabled: bool = False
    broadcast_message: str = ""
    broadcast_start: str = ""
    broadcast_end: str = ""
    maintenance_mode: bool = False