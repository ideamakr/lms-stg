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
    approver_name = Column(String, index=True)
    # 🚀 Workflow Columns (CRITICAL FOR L2)
    approver_l2 = Column(String, nullable=True)  
    
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
    id = Column(Integer, primary_key=True, index=True)
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
    employee_id = Column(String, unique=True, nullable=True)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    joined_date = Column(String, nullable=True) 
    job_title = Column(String, nullable=True)
    department = Column(String, nullable=True)
    business_unit = Column(String, nullable=True)

# EMPLOYMENT & IDENTITY
    line_manager = Column(JSON, nullable=True, default=list) # 🚀 Changed from String to JSON
    hod_name = Column(JSON, nullable=True, default=list)

    
    contract_type = Column(String, nullable=True) # 🆕 New
    work_location = Column(String, nullable=True) # 🆕 New
    
    # 👤 PERSONAL INFO (Step 2)
    preferred_name = Column(String, nullable=True) # 🆕 New
    profile_pic_url = Column(String, nullable=True) # 🆕 New
    gender = Column(String, nullable=True)
    marital_status = Column(String, nullable=True)
    ic_number = Column(String, nullable=True)      # 🆕 New
    nationality = Column(String, nullable=True)    # 🆕 New
    dob = Column(String, nullable=True)            # 🆕 New
    race = Column(String, nullable=True)           # 🆕 New
    religion = Column(String, nullable=True)       # 🆕 New
    
    # 📞 CONTACT & LOGISTICS (Step 3)
    email = Column(String, nullable=True) # Office Email
    personal_email = Column(String, nullable=True) # 🆕 New
    mobile = Column(String, nullable=True)         # Office/Primary Mobile
    home_address = Column(String, nullable=True)    # 🆕 New
    current_address = Column(String, nullable=True) # 🆕 New
    
    # 🚨 EMERGENCY CONTACT (Step 3)
    emergency_contact_name = Column(String, nullable=True)   # 🆕 New
    emergency_contact_rel = Column(String, nullable=True)    # 🆕 New
    emergency_contact_mobile = Column(String, nullable=True) # 🆕 New
    
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

class Overtime(Base):
    __tablename__ = "overtime_claims" # Changed table name to match consistency
    id = Column(Integer, primary_key=True, index=True)
    employee_name = Column(String, index=True)
    approver_name = Column(String, index=True)
    
    # 🚀 Workflow Columns (CRITICAL FOR L2)
    approver_l2 = Column(String, nullable=True) 
    
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