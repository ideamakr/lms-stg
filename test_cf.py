from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models
import os
from datetime import date

def seed_db():
    print("🚀 Starting Clean Slate & Population...")
    
    db_file = "leave.db"  
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            print(f"🗑️  Deleted existing {db_file}")
        except PermissionError:
            print(f"⚠️  ERROR: Could not delete {db_file}. Close the server terminal first!")
            return

    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ⚙️ 1. POLICY (Standard 14 days)
        policy = models.GlobalPolicy(id=1, annual_days=14, medical_days=14, emergency_days=2, compassionate_days=3, l2_approval_enabled=False)
        db.add(policy)

        # 👥 2. CORE USERS
        superuser = models.User(username="superuser", full_name="System Administrator", password="password123", role="superuser", is_active=True)
        tony = models.User(username="tony", full_name="Tony Stark", password="123", role="manager", employee_id="MGR-01", is_senior_manager=True)
        db.add_all([superuser, tony])
        db.commit()

        # 💰 3. WALLETS (2026 & 2027)
        # We initialize Tony with the standard 14 days for 2026.
        db.add(models.UserRole(user_id=tony.id, role_name="manager"))
        db.add(models.UserRole(user_id=tony.id, role_name="employee"))
        
        for year in [2026, 2027]:
            db.add(models.LeaveBalance(
                employee_name="Tony Stark", year=year, leave_type="Annual Leave", 
                entitlement=14.0, remaining=14.0, carry_forward_total=0.0
            ))
        db.commit()

        # ==========================================
        # 👑 4. TONY STARK "READY TO MERGE" (2025 -> 2026)
        # ==========================================
        print("🔧 Creating Tony Stark 2025 -> 2026 Request (Status: Approved)...")
        
        # We create a request dated in 2025. 
        # Status "Approved" means it is waiting for HR to click MERGE.
        tony_cf = models.Leave(
            employee_name="Tony Stark",
            approver_name="System Administrator",
            leave_type="Annual Leave",
            start_date=date(2025, 12, 31),
            end_date=date(2025, 12, 31),
            reason="[CARRY FORWARD: 5.0 DAYS] Unused balance from 2025",
            status="Approved", 
            days_taken=5.0,
            status_history="Submitted > Approved by Manager"
        )
        db.add(tony_cf)
        db.commit()

        print(f"✅ SUCCESS! Tony Stark's 5-day request is now PENDING HR MERGE.")
        print(f"👉 Tony's current 2026 balance is 14.0 days.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()