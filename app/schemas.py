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
    # 🚀 Step 1: Employment
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    office_email: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    business_unit: Optional[str] = None
    line_manager: Optional[str] = None
    hod_name: Optional[str] = None
    joined_date: Optional[str] = None
    contract_type: Optional[str] = None
    work_location: Optional[str] = None

class UserDisplay(UserBase):
    id: int
    employee_id: Optional[str] = None
    roles_list: Optional[List[str]] = [] 
    
    # 📋 Step 1: Employment & Identity
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    preferred_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    joined_date: Optional[str] = None 
    job_title: Optional[str] = None
    department: Optional[str] = None
    business_unit: Optional[str] = None
    line_manager: Optional[str] = None
    hod_name: Optional[str] = None
    contract_type: Optional[str] = None
    work_location: Optional[str] = None
    
    # 👤 Step 2: Personal Info
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    ic_number: Optional[str] = None
    nationality: Optional[str] = None
    dob: Optional[str] = None
    race: Optional[str] = None
    religion: Optional[str] = None
    
    # 📞 Step 3: Contact & Logistics
    email: Optional[str] = None # Mapping to Office Email
    personal_email: Optional[str] = None
    mobile: Optional[str] = None
    home_address: Optional[str] = None
    current_address: Optional[str] = None
    
    # 🚨 Emergency Contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_rel: Optional[str] = None
    emergency_contact_mobile: Optional[str] = None
    
    # 💰 Wallets
    overtime_bank: float = 0.0
    unpaid_taken: float = 0.0

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

# 🚀 NEW: LEAVE BALANCE SCHEMA
class LeaveBalanceResponse(BaseModel):
    employee_name: str
    year: int
    leave_type: str
    entitlement: float
    remaining: float           
    carry_forward_total: float = 0.0 
    taken: float = 0.0         

    model_config = ConfigDict(from_attributes=True)

# --- SYSTEM SETTINGS / BRANDING SCHEMAS ---

class BrandingConfig(BaseModel):
    company_name: str
    company_sub_info: str  
    company_logo: str
    broadcast_enabled: bool = False
    broadcast_message: str = ""
    broadcast_start: str = ""
    broadcast_end: str = ""
    maintenance_mode: bool = False