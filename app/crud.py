from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas

def get_leave_balance(db: Session, employee_name: str, leave_type: models.LeaveType, year: int):
    # 1. Get Limit
    balance = db.query(models.LeaveBalance).filter(
        models.LeaveBalance.employee_name == employee_name,
        models.LeaveBalance.leave_type == leave_type,
        models.LeaveBalance.year == year
    ).first()
    
    if not balance: return {"entitlement": 0, "remaining": 0}

    # 2. Calculate Used
    used = db.query(func.sum(models.Leave.days_taken)).filter(
        models.Leave.employee_name == employee_name,
        models.Leave.leave_type == leave_type,
        models.Leave.status.in_([models.LeaveStatus.APPROVED, models.LeaveStatus.PENDING]),
        func.extract('year', models.Leave.start_date) == year
    ).scalar() or 0.0

    return {"entitlement": balance.entitlement, "remaining": balance.entitlement - used}

def create_leave(db: Session, leave_data: dict):
    db_leave = models.Leave(**leave_data)
    db.add(db_leave)
    db.commit()
    db.refresh(db_leave)
    return db_leave
