import os
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models
from app.models import Base

def seed_db():
    print("🚀 Starting Database Hard Reset...")
    
    # 1. DELETE PHYSICAL DB FILES
    db_files = ["leave.db", "sql_app.db", "leave_app.db"] 
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                print(f"🗑️  Deleted existing {db_file}")
            except Exception:
                pass

    # 2. CREATE NEW TABLES
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # --- 1. GLOBAL POLICY ---
        policy = models.GlobalPolicy(
            id=1, annual_days=14, medical_days=14, emergency_days=2, compassionate_days=3,
            l2_approval_enabled=True 
        )
        db.add(policy)

        # --- 2. THE CORE USERS ---
        core_users = [
            models.User(username="natasha", full_name="Natasha Romanoff", password="123", 
                        role="hr_admin", employee_id="HR-001", line_manager=None, job_title="HR Director"),
            models.User(username="tony", full_name="Tony Stark", password="123", 
                        role="manager", employee_id="MGR-001", is_senior_manager=True, line_manager="Natasha Romanoff", job_title="Engineering Director"),
            models.User(username="sarah", full_name="Sarah Connor", password="123", 
                        role="manager", employee_id="MGR-002", is_senior_manager=False, line_manager="Tony Stark", job_title="Team Lead"),
            models.User(username="neil", full_name="Neil J", password="123", 
                        role="employee", employee_id="EMP-001", line_manager="Sarah Connor", job_title="Junior Developer")
        ]
        db.add_all(core_users)
        db.commit()

        # --- 3. TEAM SARAH (Additional 5 Employees) ---
        team_sarah = []
        for i in range(1, 6):
            emp = models.User(
                username=f"sarah_staff_{i}", full_name=f"Staff Sarah {i}", password="123",
                role="employee", employee_id=f"S-00{i}", line_manager="Sarah Connor", job_title="Developer"
            )
            team_sarah.append(emp)
        
        # --- 4. TEAM TONY (Additional 5 Employees) ---
        team_tony = []
        for i in range(1, 6):
            emp = models.User(
                username=f"tony_staff_{i}", full_name=f"Staff Tony {i}", password="123",
                role="employee", employee_id=f"T-00{i}", line_manager="Tony Stark", job_title="Sr. Engineer"
            )
            team_tony.append(emp)

        all_users = core_users + team_sarah + team_tony
        db.add_all(team_sarah + team_tony)
        db.commit()

        # --- 5. INITIALIZE BALANCES ---
        print("🛡️  Provisioning Wallets for 2026...")
        for u in all_users:
            # Assign roles in UserRole table
            db.add(models.UserRole(user_id=u.id, role_name="employee"))
            if u.role != "employee":
                db.add(models.UserRole(user_id=u.id, role_name=u.role))

            # Create standard balance rows
            balances = [
                ("Annual Leave", 14.0), ("Medical Leave", 14.0), 
                ("Emergency Leave", 2.0), ("Compassionate Leave", 3.0), ("Unpaid Leave", 0.0)
            ]
            for l_type, days in balances:
                db.add(models.LeaveBalance(
                    employee_name=u.full_name, year=2026, leave_type=l_type,
                    entitlement=days, remaining=days, carry_forward_total=0.0
                ))
        
        db.commit()
        print(f"✅ Reset Successful! {len(all_users)} users created.")
        print("--------------------------------------------------")
        print("Neil J added successfully reporting to Sarah Connor.")

    except Exception as e:
        db.rollback()
        print(f"❌ Seed Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()