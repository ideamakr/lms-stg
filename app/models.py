from sqlalchemy import Column, Integer, String, Date, Float, DateTime, Enum as SqlEnum, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
import enum
from .database import Base
from datetime import datetime
from pydantic import BaseModel

# 1. Enums
class LeaveType(str, enum.Enum):
    ANNUAL = "Annual Leave"
    MEDICAL = "Medical Leave"
    EMERGENCY = "Emergency Leave"
    COMPASSIONATE = "Compassionate Leave"
    UNPAID = "Unpaid Leave"

class LeaveStatus(str, enum.Enum):  
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"
    PENDING_CANCEL = "Pending Cancel"
    WITHDRAWN = "Withdrawn"
    PENDING_L2 = "Pending L2 Approval"

class OTStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"
    WITHDRAWN = "Withdrawn"

# 2. Tables

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    employee_name = Column(String, index=True)
    year = Column(Integer)
    leave_type = Column(String)
    
    # 🟢 Entitlement Columns
    entitlement = Column(Float, default=0.0)
    remaining = Column(Float, default=0.0)          
    carry_forward_total = Column(Float, default=0.0) 

# 🚀 SINGLE, CORRECT LEAVE CLASS
class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True, index=True)
    employee_name = Column(String, index=True)
    
    # 🚀 LEGACY (Keep these for now so existing UI doesn't break)
    approver_name = Column(String, index=True)
    approver_l2 = Column(String, nullable=True)  
    
    # 🚀 NEW ID-BASED RELATIONSHIPS
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approver_l2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 🚀 ORM RELATIONSHIPS (Makes querying "leave.approver.full_name" easy)
    approver = relationship("User", foreign_keys=[approver_id])
    approver_l2_ref = relationship("User", foreign_keys=[approver_l2_id])
    
    # Standard Data
    leave_type = Column(String) 
    start_date = Column(Date)
    end_date = Column(Date)
    reason = Column(String)
    
    # Status & Logistics
    status = Column(String, default="Pending")
    days_taken = Column(Float, default=0.0) 
    attachment_path = Column(String, nullable=True)
    
    # Audit Trail
    status_history = Column(String, default="Pending")
    manager_remarks = Column(String, nullable=True)
    
    # Timestamps
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # 🚀 CF Merge Tracking
    is_cf_merged = Column(Boolean, default=False) 

class PublicHoliday(Base):
    __tablename__ = "public_holidays"
    # Added autoincrement=True to ensure the DB knows to generate the ID
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String)
    holiday_date = Column(Date, unique=True, index=True)
    
    # 🚀 FIX: Tell SQLAlchemy about the new column
    states = Column(String, default="All States")

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_name = Column(String)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    password = Column(String)
    role = Column(String, default="employee")
    is_active = Column(Boolean, default=True)
    
    # 🚀 Manager Power Column
    is_senior_manager = Column(Boolean, default=False) 
    current_session_id = Column(String, nullable=True)
    
    # 📋 EMPLOYMENT & IDENTITY (Step 1)
    employee_id = Column(String, unique=True, nullable=True) # Employee No (New)
    employee_no_old = Column(String, nullable=True)          
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    common_name = Column(String, nullable=True)              
    preferred_name = Column(String, nullable=True) 
    profile_pic_url = Column(String, nullable=True) 
    
    joined_date = Column(String, nullable=True) 
    job_title = Column(String, nullable=True)
    department = Column(String, nullable=True)
    business_unit = Column(String, nullable=True)
    line_manager = Column(JSON, nullable=True, default=list) 
    hod_name = Column(JSON, nullable=True, default=list)
    contract_type = Column(String, nullable=True) 
    work_location = Column(String, nullable=True) 

    # 🏢 NEW ENTERPRISE ORGANIZATIONAL STRUCTURE FIELDS
    employee_status = Column(String, nullable=True)               
    organization_o = Column(String, nullable=True)                
    organization_ou1 = Column(String, nullable=True)              
    organization_ou2 = Column(String, nullable=True)              
    lotus_notes_id = Column(String, nullable=True)                
    document_status = Column(String, nullable=True)               
    company = Column(String, nullable=True)                       
    location = Column(String, nullable=True)                      
    position_grade = Column(String, nullable=True)                
    contract_expiry_date = Column(String, nullable=True)          
    expat_type = Column(String, nullable=True)                    
    category = Column(String, nullable=True)                      
    ranking = Column(String, nullable=True)                       
    highest_qualification = Column(String, nullable=True)         
    
    # Structural Levels
    level_0 = Column(String, nullable=True)                        
    level_1 = Column(String, nullable=True)                        
    level_2 = Column(String, nullable=True)                        
    
    # 👤 PERSONAL INFO (Step 2)
    gender = Column(String, nullable=True)
    marital_status = Column(String, nullable=True)
    ic_number = Column(String, nullable=True)      
    nationality = Column(String, nullable=True)    
    dob = Column(String, nullable=True)            
    place_of_birth = Column(String, nullable=True)                
    race = Column(String, nullable=True)           
    religion = Column(String, nullable=True)       
    
    # 📅 EMPLOYEE LIFECYCLE & MILESTONES
    date_ict_removal = Column(String, nullable=True)              
    date_resigned = Column(String, nullable=True)                 
    last_working_day = Column(String, nullable=True)              
    last_day_of_service = Column(String, nullable=True)           
    
    # ⚙️ OPERATIONAL & POLICY FLAGS
    shift_employee = Column(String, nullable=True, default="No")                
    compensation_leave_entitled = Column(String, nullable=True, default="No")   
    commissioning_engineer = Column(String, nullable=True, default="No")        
    scholar = Column(String, nullable=True, default="No")                       

    # 📞 CONTACT & LOGISTICS (Step 3)
    email = Column(String, nullable=True) # Office Email
    personal_email = Column(String, nullable=True) 
    mobile = Column(String, nullable=True)         # Office/Primary Mobile
    home_address = Column(String, nullable=True)    
    current_address = Column(String, nullable=True) 
    
    # 🚨 EMERGENCY CONTACT (Step 3)
    emergency_contact_name = Column(String, nullable=True)   
    emergency_contact_rel = Column(String, nullable=True)    
    emergency_contact_mobile = Column(String, nullable=True) 
    
    # 🏦 NEW BANKING DETAILS SECTION
    bank_holder_name = Column(String, nullable=True)              
    bank_name = Column(String, nullable=True)                     
    bank_account_number = Column(String, nullable=True)           
    bank_account_status = Column(String, nullable=True, default="Active") 

    # 💰 THE WALLETS
    overtime_bank = Column(Float, default=0.0)
    unpaid_taken = Column(Float, default=0.0)
    
    assigned_roles = relationship("UserRole", backref="user", cascade="all, delete-orphan")
class GlobalPolicy(Base):
    __tablename__ = "global_policy"
    id = Column(Integer, primary_key=True, index=True)
    annual_days = Column(Integer, default=14)
    medical_days = Column(Integer, default=14)
    emergency_days = Column(Integer, default=2)
    compassionate_days = Column(Integer, default=3)
    
    # 🚀 Master Switch for L2 Workflow
    l2_approval_enabled = Column(Boolean, default=False)
    
    # 🔒 SYSTEM CAPACITY CONSTRAINTS
    max_seats = Column(Integer, default=0)
    registration_lock = Column(Boolean, default=False)

class Overtime(Base):
    __tablename__ = "overtime_claims"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_name = Column(String, index=True)
    
    # 🚀 LEGACY (Keep these for now)
    approver_name = Column(String, index=True)
    approver_l2 = Column(String, nullable=True) 
    
    # 🚀 NEW ID-BASED RELATIONSHIPS
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approver_l2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 🚀 ORM RELATIONSHIPS
    approver = relationship("User", foreign_keys=[approver_id])
    approver_l2_ref = relationship("User", foreign_keys=[approver_l2_id])
    
    # Data Fields
    ot_date = Column(Date)
    ot_type = Column(String)    
    ot_unit = Column(String)    
    start_time = Column(String, nullable=True)
    end_time = Column(String, nullable=True)
    total_value = Column(Float) 
    reason = Column(String)
    attachment_path = Column(String, nullable=True) 
    status = Column(String, default="Pending") 
    status_history = Column(String, default="Pending")
    manager_remarks = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True) 
    value = Column(String)

# Pydantic Models (Schemas) used in other parts of the app
class CarryForwardConfig(BaseModel):
    max_days: float
    expiry_date: str

class CFToggleRequest(BaseModel):
    enabled: bool
    confirm_cleanup: bool = False

# --- Pydantic Schemas ---

class HeadcountLimitsRequest(BaseModel):
    max_seats: int
    registration_lock: bool    

class Broadcast(Base):
    __tablename__ = "broadcasts"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String) # Stores "System Administrator"
    
# ============================================================
# 📜 ACTIVITY LOG MODEL
# ============================================================
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # The person whose dashboard this log appears on
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    
    # The person who actually clicked the button (Manager or Employee)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Types: 'SUBMISSION', 'APPROVAL', 'REJECTION', etc.
    action_type = Column(String)
    
    # Categories: 'Annual Leave', 'Medical Leave', 'OT', etc.
    category = Column(String)
    
    # The actual text (e.g., "You submitted Annual Leave")
    message = Column(String)
    
    # Link to the specific record in 'leaves' or 'overtime_claims'
    reference_id = Column(Integer, nullable=True)
    
    # The date it happened
    created_at = Column(DateTime, default=datetime.now) 


# ============================================================
# 📊 BULK ONBOARDING LOG MODEL (For Spreadsheet Status Grid)
# ============================================================
class BulkOnboardLog(Base):
    __tablename__ = "bulk_onboard_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Links rows from the same upload file session together
    batch_id = Column(String, index=True) 
    row_number = Column(Integer)
    
    # Identity details grabbed or generated from the CSV row
    employee_id = Column(String, nullable=True)
    username = Column(String, nullable=True)
    full_name = Column(String)
    email = Column(String)
    
    # State tracking metrics
    account_status = Column(String, default="Pending") # 'Created', 'Skipped', 'Pending'
    email_status = Column(String, default="N/A")       # 'Pending', 'Processing', 'Sent', 'Failed', 'N/A'
    
    # Explicit logging to tell HR exactly what broke
    failure_reason = Column(String, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.now)


# ============================================================
# 🎫 IT SERVICE DESK & INCIDENT TRIAGE MODELS
# ============================================================
class SystemIncident(Base):
    __tablename__ = "system_incidents"

    id = Column(Integer, primary_key=True, index=True)
    
    # Reporter Identity
    reporter_name = Column(String, index=True)
    reporter_role = Column(String, nullable=True)
    
    # Categorization
    issue_type = Column(String) # e.g., "Code Bug", "Environment", "Configuration"
    urgency = Column(String)    # e.g., "P1 - Critical", "P3 - Medium"
    
    # Context & Evidence
    screen_context = Column(String, nullable=True) # e.g., "/dashboard/add-user"
    description = Column(String)
    attachment_path = Column(String, nullable=True)
    
    # Resolution Tracking
    status = Column(String, default="OPEN") # OPEN, PROCESSING, RESOLVED, REJECTED
    admin_notes = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# --- Pydantic Schemas for the Service Desk ---
class IncidentCreateRequest(BaseModel):
    issue_type: str
    urgency: str
    screen_context: str = "Unknown"
    description: str

class IncidentUpdateRequest(BaseModel):
    status: str
    admin_notes: str = None