import sys
import random
from datetime import date

# 🚀 DEBUG: This will print immediately so we know the file is running
print("🚀 SCRIPT STARTED: Preparing to seed database...")

try:
    from app.database import SessionLocal, engine, Base
    from app import models
    print("✅ Imports successful!")
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    print("👉 Please run: pip install python-dotenv sqlalchemy")
    sys.exit(1)

# --- Configuration ---
TOTAL_USERS = 200
START_ID = 36
YEAR = 2026
DEFAULT_PASS_HASH = "123456" 

first_names = ["Ali", "Ahmad", "Siti", "Nur", "John", "Jane", "Michael", "Michelle", "David", "Sarah", "Wong", "Tan", "Lee", "Lim", "Raj", "Priya", "Kumar", "Devi", "Kevin", "Rachel"]
last_names = ["Abdullah", "Ismail", "Ibrahim", "Smith", "Doe", "Johnson", "Williams", "Brown", "Chong", "Ng", "Ong", "Goh", "Sharma", "Singh", "Patel", "Reddy", "Taylor", "Wilson", "Davis", "Chen"]
departments = ["Engineering", "Marketing", "HR", "Sales", "Finance", "Operations", "Support"]

def seed_data():
    print("🏗️ Initializing Database Tables (Creating leave.db)...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("🛠️ Setting up Core Management Team (Natasha, Sarah, Tony)...")
        
        # 1. Natasha (HR)
        natasha = db.query(models.User).filter(models.User.username == "natasha").first()
        if not natasha:
            natasha = models.User(
                username="natasha", full_name="Natasha Romanoff", employee_id="HR-001",
                email="natasha@company.com", password=DEFAULT_PASS_HASH, role="hr-admin", is_active=True
            )
            db.add(natasha)

        # 2. Sarah (Manager)
        sarah = db.query(models.User).filter(models.User.username == "sarah").first()
        if not sarah:
            sarah = models.User(
                username="sarah", full_name="Sarah Connor", employee_id="MGR-002",
                email="sarah@company.com", password=DEFAULT_PASS_HASH, role="manager", is_active=True
            )
            db.add(sarah)

        # 3. Tony (HOD)
        tony = db.query(models.User).filter(models.User.username == "tony").first()
        if not tony:
            tony = models.User(
                username="tony", full_name="Tony Stark", employee_id="MGR-001",
                email="tony@company.com", password=DEFAULT_PASS_HASH, role="manager", 
                is_senior_manager=True, is_active=True
            )
            db.add(tony)
            
        # 4. Global Policy
        policy = db.query(models.GlobalPolicy).filter(models.GlobalPolicy.id == 1).first()
        if not policy:
            policy = models.GlobalPolicy(
                id=1, annual_days=14, medical_days=14, 
                emergency_days=2, compassionate_days=3, l2_approval_enabled=False
            )
            db.add(policy)
        
        db.flush() 
        
        print(f"🌱 Seeding {TOTAL_USERS} employees...")

        for i in range(TOTAL_USERS):
            current_id = START_ID + i
            emp_id = f"EMP-{YEAR}-{current_id:04d}"
            
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            full_name = f"{fn} {ln} {i}" 
            username = f"{fn.lower()}{ln.lower()}{i}"
            
            new_user = models.User(
                employee_id=emp_id, username=username, full_name=full_name,
                first_name=fn, last_name=ln, email=f"{username}@company.com",
                password=DEFAULT_PASS_HASH, role="employee", is_active=True,
                department=random.choice(departments), business_unit="HQ",
                job_title="Staff", line_manager=sarah.full_name, hod_name=tony.full_name,     
                joined_date="2025-01-01", gender=random.choice(["Male", "Female"]),
                race=random.choice(["Malay", "Chinese", "Indian", "Other"]),
                religion=random.choice(["Islam", "Buddhism", "Christianity", "Hinduism", "Other"]),
                nationality="Malaysian", work_location="Main Office", contract_type="Full-Time"
            )
            db.add(new_user)
            
            for l_type, days in [
                ("Annual Leave", 14.0), ("Medical Leave", 14.0), 
                ("Emergency Leave", 2.0), ("Compassionate Leave", 3.0), ("Unpaid Leave", 0.0)
            ]:
                bal = models.LeaveBalance(
                    employee_name=full_name, year=YEAR, leave_type=l_type,
                    entitlement=days, remaining=days, carry_forward_total=0.0
                )
                db.add(bal)

        db.commit()
        print(f"✅ SUCCESS: Seeding complete! Database is now unified.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
    finally:
        db.close()

# 🛡️ THIS PART IS CRITICAL: It tells Python to actually run the function!
if __name__ == "__main__":
    seed_data()