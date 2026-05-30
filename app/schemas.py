from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional, List
from .models import LeaveType, LeaveStatus

# ============================================================
# 👤 USER SCHEMAS (Exposing and Handling All Corporate Fields)
# ============================================================

class UserBase(BaseModel):
    username: str
    full_name: str
    role: str = "employee"
    is_active: bool = True
    is_senior_manager: bool = False

class UserCreate(UserBase):
    password: str
    employee_id: Optional[str] = None
    
    # 📋 Step 1: Employment Core
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    common_name: Optional[str] = None
    email: Optional[str] = None  # Aligned directly with models.py Column name
    lotus_notes_id: Optional[str] = None
    employee_no_old: Optional[str] = None
    company: Optional[str] = None
    business_unit: Optional[str] = None
    department: Optional[str] = None
    work_location: Optional[str] = None
    position_grade: Optional[str] = None
    category: Optional[str] = None
    ranking: Optional[str] = None
    expat_type: Optional[str] = None
    
    # Enterprise Hierarchy Structures
    organization_o: Optional[str] = None
    organization_ou1: Optional[str] = None
    organization_ou2: Optional[str] = None
    level_0: Optional[str] = None
    level_1: Optional[str] = None
    level_2: Optional[str] = None
    
    # Assignments & Milestones
    line_manager: Optional[List[str]] = []
    hod_name: Optional[List[str]] = []
    job_title: Optional[str] = None
    contract_type: Optional[str] = None
    document_status: Optional[str] = None
    joined_date: Optional[str] = None
    contract_expiry_date: Optional[str] = None
    
    # Operational Flag Indicators Dropdowns
    shift_employee: Optional[str] = "No"
    compensation_leave_entitled: Optional[str] = "No"
    commissioning_engineer: Optional[str] = "No"
    scholar: Optional[str] = "No"

class UserDisplay(UserBase):
    id: int
    employee_id: Optional[str] = None
    roles_list: Optional[List[str]] = [] 
    
    # 📋 Step 1: Employment Identity Matrix
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    common_name: Optional[str] = None
    preferred_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    lotus_notes_id: Optional[str] = None
    employee_no_old: Optional[str] = None
    company: Optional[str] = None
    business_unit: Optional[str] = None
    department: Optional[str] = None
    work_location: Optional[str] = None
    location: Optional[str] = None
    position_grade: Optional[str] = None
    category: Optional[str] = None
    ranking: Optional[str] = None
    expat_type: Optional[str] = None
    employee_status: Optional[str] = None
    document_status: Optional[str] = None
    highest_qualification: Optional[str] = None
    
    # Enterprise Hierarchy Routing Layers
    organization_o: Optional[str] = None
    organization_ou1: Optional[str] = None
    organization_ou2: Optional[str] = None
    level_0: Optional[str] = None
    level_1: Optional[str] = None
    level_2: Optional[str] = None
    
    # 🚀 FIXED: Upgraded to list mappings to perfectly align with SQLAlchemy JSON serialization
    line_manager: Optional[List[str]] = []
    hod_name: Optional[List[str]] = []
    job_title: Optional[str] = None
    contract_type: Optional[str] = None
    joined_date: Optional[str] = None 
    contract_expiry_date: Optional[str] = None
    
    # Offboarding Lifecycle Milestones
    date_resigned: Optional[str] = None
    last_working_day: Optional[str] = None
    last_day_of_service: Optional[str] = None
    date_ict_removal: Optional[str] = None
    
    # Operational Dropdowns Flag Indicators
    shift_employee: Optional[str] = "No"
    compensation_leave_entitled: Optional[str] = "No"
    commissioning_engineer: Optional[str] = "No"
    scholar: Optional[str] = "No"
    
    # 👤 Step 2: Personal Details Parameters
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    ic_number: Optional[str] = None
    nationality: Optional[str] = None
    place_of_birth: Optional[str] = None
    dob: Optional[str] = None
    race: Optional[str] = None
    religion: Optional[str] = None
    
    # 📞 Step 3: Contact Logs & Logistics
    email: Optional[str] = None 
    personal_email: Optional[str] = None
    mobile: Optional[str] = None
    home_address: Optional[str] = None
    current_address: Optional[str] = None
    
    # 🚨 Emergency Contact Node
    emergency_contact_name: Optional[str] = None
    emergency_contact_rel: Optional[str] = None
    emergency_contact_mobile: Optional[str] = None
    
    # 💸 Disbursal Salary Bank Node
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_holder_name: Optional[str] = None
    bank_account_status: Optional[str] = "Active"
    
    # 💰 Balance Wallets
    overtime_bank: float = 0.0
    unpaid_taken: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    # Identity & Account Basics
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_senior_manager: Optional[bool] = None
    
    # 📋 Step 1: Corporate Employment Metrics
    employee_id: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    common_name: Optional[str] = None
    lotus_notes_id: Optional[str] = None
    employee_no_old: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    business_unit: Optional[str] = None
    work_location: Optional[str] = None
    location: Optional[str] = None
    position_grade: Optional[str] = None
    category: Optional[str] = None
    ranking: Optional[str] = None
    expat_type: Optional[str] = None
    employee_status: Optional[str] = None
    organization_o: Optional[str] = None
    organization_ou1: Optional[str] = None
    organization_ou2: Optional[str] = None
    level_0: Optional[str] = None
    level_1: Optional[str] = None
    level_2: Optional[str] = None
    line_manager: Optional[List[str]] = None
    hod_name: Optional[List[str]] = None
    contract_type: Optional[str] = None
    document_status: Optional[str] = None
    joined_date: Optional[str] = None
    contract_expiry_date: Optional[str] = None
    
    # Offboarding Milestones Dates
    date_resigned: Optional[str] = None
    last_working_day: Optional[str] = None
    last_day_of_service: Optional[str] = None
    date_ict_removal: Optional[str] = None
    
    # Operational Dropdowns
    shift_employee: Optional[str] = None
    compensation_leave_entitled: Optional[str] = None
    commissioning_engineer: Optional[str] = None
    scholar: Optional[str] = None
    
    # 👤 Step 2: Personal Data Profile
    preferred_name: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    ic_number: Optional[str] = None
    nationality: Optional[str] = None
    place_of_birth: Optional[str] = None
    dob: Optional[str] = None
    race: Optional[str] = None
    religion: Optional[str] = None
    highest_qualification: Optional[str] = None
    
    # 📞 Step 3: Contact Mappings
    email: Optional[str] = None
    personal_email: Optional[str] = None
    mobile: Optional[str] = None
    home_address: Optional[str] = None
    current_address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_rel: Optional[str] = None
    emergency_contact_mobile: Optional[str] = None
    
    # 💸 Disbursal Salary Bank Parameters
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_holder_name: Optional[str] = None
    bank_account_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# ============================================================
# 📅 LEAVE SCHEMAS
# ============================================================

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

class LeaveBalanceResponse(BaseModel):
    employee_name: str
    year: int
    leave_type: str
    entitlement: float
    remaining: float           
    carry_forward_total: float = 0.0 
    taken: float = 0.0         

    model_config = ConfigDict(from_attributes=True)

# ============================================================
# ⚙️ SYSTEM SETTINGS / BRANDING SCHEMAS
# ============================================================

class BrandingConfig(BaseModel):
    company_name: str
    company_sub_info: str  
    company_logo: str
    company_favicon: Optional[str] = None  # ✨ Added to match your frontend input variable name
    broadcast_enabled: bool = False
    broadcast_message: str = ""
    broadcast_start: str = ""
    broadcast_end: str = ""
    maintenance_mode: bool = False