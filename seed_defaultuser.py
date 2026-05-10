import sys
import json # 🚀 CRITICAL: We need this to convert lists to strings for SQLite

print("🚀 SCRIPT STARTED: Preparing to seed database for Phase 2...")

try:
    from app.database import SessionLocal, engine, Base
    from app import models
    print("✅ Imports successful!")
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    sys.exit(1)

DEFAULT_PASS_HASH = "123456" 

def seed_data():
    print("🏗️ Wiping old database and initializing fresh tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("🛠️ Setting up Core Team...")
        
        # 1. Natasha (HR Admin)
        natasha = models.User(
            username="natasha", full_name="Natasha Romanoff", employee_id="EMP-2026-0001",
            email="natasha@company.com", password=DEFAULT_PASS_HASH, role="hr_admin", 
            is_active=True, 
            # 🚀 FIX: Wrap lists in json.dumps() for SQLite compatibility
            line_manager=json.dumps([]), 
            hod_name=json.dumps([]) 
        )
        db.add(natasha)

        # 2. Sarah (Line Manager)
        sarah = models.User(
            username="sarah", full_name="Sarah Connor", employee_id="EMP-2026-0002",
            email="sarah@company.com", password=DEFAULT_PASS_HASH, role="manager", 
            is_active=True,
            line_manager=json.dumps([]), 
            hod_name=json.dumps([])
        )
        db.add(sarah)

        # 3. Tony (HOD / Senior Manager)
        tony = models.User(
            username="tony", full_name="Tony Stark", employee_id="EMP-2026-0003",
            email="tony@company.com", password=DEFAULT_PASS_HASH, role="manager", 
            is_senior_manager=True, is_active=True,
            line_manager=json.dumps([]), 
            hod_name=json.dumps([])
        )
        db.add(tony)

        # 4. Julian (The Test Employee)
        julian = models.User(
            username="julian", full_name="Julian Alfred", employee_id="EMP-2026-0004",
            email="julian@company.com", password=DEFAULT_PASS_HASH, role="employee", 
            is_active=True,
            # 🚀 FIX: Convert the list to a JSON string
            line_manager=json.dumps(["Sarah Connor"]), 
            hod_name=json.dumps(["Tony Stark"])
        )
        db.add(julian)
            
        # 5. Global Policy
        policy = models.GlobalPolicy(
            id=1, annual_days=14, medical_days=14, 
            emergency_days=2, compassionate_days=3, l2_approval_enabled=True
        )
        db.add(policy)

        db.commit()

        # 6. Initialize Balances & Roles
        print("💰 Initializing Balances and Roles...")
        users = db.query(models.User).all()
        for u in users:
            db.add(models.UserRole(user_id=u.id, role_name=u.role))
            
            for l_type in ["Annual Leave", "Medical Leave", "Emergency Leave", "Compassionate Leave"]:
                db.add(models.LeaveBalance(
                    employee_name=u.full_name,
                    year=2026,
                    leave_type=l_type,
                    entitlement=14.0 if "Annual" in l_type or "Medical" in l_type else 2.0,
                    remaining=14.0 if "Annual" in l_type or "Medical" in l_type else 2.0
                ))
        
        db.commit()
        print(f"✅ SUCCESS: Seeding complete!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()