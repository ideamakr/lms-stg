import random
from datetime import date
from app.database import SessionLocal
from app import models

# --- Configuration ---
TOTAL_USERS = 200
START_ID = 36
YEAR = 2026
# Pre-hashed standard password for 'password123'
DEFAULT_PASS_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYq" 

first_names = ["Ali", "Ahmad", "Siti", "Nur", "John", "Jane", "Michael", "Michelle", "David", "Sarah", "Wong", "Tan", "Lee", "Lim", "Raj", "Priya", "Kumar", "Devi", "Kevin", "Rachel"]
last_names = ["Abdullah", "Ismail", "Ibrahim", "Smith", "Doe", "Johnson", "Williams", "Brown", "Chong", "Ng", "Ong", "Goh", "Sharma", "Singh", "Patel", "Reddy", "Taylor", "Wilson", "Davis", "Chen"]
departments = ["Engineering", "Marketing", "HR", "Sales", "Finance", "Operations", "Support"]

def seed_data():
    db = SessionLocal()
    try:
        print(f"🌱 Seeding {TOTAL_USERS} users starting from EMP-{YEAR}-{START_ID:04d}...")
        
        # Get a default Line Manager (Use your actual admin name if you want them assigned to you)
        manager_name = "System Administrator" 
        
        for i in range(TOTAL_USERS):
            current_id = START_ID + i
            emp_id = f"EMP-{YEAR}-{current_id:04d}"
            
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            # Add the index 'i' to ensure usernames/names are 100% unique
            full_name = f"{fn} {ln} {i}" 
            username = f"{fn.lower()}{ln.lower()}{i}"
            
            # 1. Create User
 # 1. Create User
            new_user = models.User(
                employee_id=emp_id,
                full_name=full_name,
                username=username,
                email=f"{username}@company.com",
                password=DEFAULT_PASS_HASH,  # <--- Change this line!
                role="employee",
                is_active=True,
                department=random.choice(departments),
                business_unit="HQ",
                job_title="Staff",
                line_manager=manager_name,
                joined_date=date(2025, 1, 1)
            )
            db.add(new_user)
            
            # 2. Create Leave Balances
            for l_type, days in [("Annual Leave", 14.0), ("Medical Leave", 14.0), ("Emergency Leave", 2.0), ("Compassionate Leave", 3.0), ("Unpaid Leave", 0.0)]:
                bal = models.LeaveBalance(
                    employee_name=full_name,
                    year=YEAR,
                    leave_type=l_type,
                    entitlement=days,
                    remaining=days,
                    carry_forward_total=0.0
                )
                db.add(bal)
            
            # 3. Create some dummy leaves for every 3rd person to test the math engine
            if i % 3 == 0:
                dummy_leave = models.Leave(
                    employee_name=full_name,
                    approver_name=manager_name,
                    leave_type="Annual Leave",
                    start_date=date(YEAR, 4, 1),
                    end_date=date(YEAR, 4, 2),
                    days_taken=2.0,
                    reason="Random generated leave",
                    status="Approved",
                    status_history=f"Approved ({YEAR}-04-01 10:00)"
                )
                db.add(dummy_leave)

        # Commit everything at once
        db.commit()
        print("✅ Seeding complete! 200 users and their balances have been added.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()