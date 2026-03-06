from app.database import SessionLocal
from app import models

def seed_sarah_cf():
    db = SessionLocal()
    try:
        # 1. Target Sarah Connor for the current year 2026
        target_year = 2026
        employee = "Sarah Connor"
        
        print(f"🚀 Seeding Carry Forward for {employee} ({target_year})...")

        # 2. Find her Annual Leave bucket for 2026
        balance = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == employee,
            models.LeaveBalance.year == target_year,
            models.LeaveBalance.leave_type == "Annual Leave"
        ).first()

        if balance:
            # 💰 Step A: Inject 5.0 days into the CF Wallet column
            balance.carry_forward_total = 5.0
            
            # 🛡️ Step B: Update the 'remaining' column
            # We add 5.0 to whatever her current remaining balance is.
            # (e.g., if she had 7.0, she now has 12.0)
            current_rem = float(balance.remaining or 0.0)
            balance.remaining = current_rem + 5.0
            
            db.commit()
            print(f"✅ Success! Sarah now has 5.0 days in her {target_year} CF Wallet.")
            print(f"📊 Previous Remaining: {current_rem}")
            print(f"📊 New Total Available for Sarah: {balance.remaining} Days")
        else:
            print(f"❌ Error: Could not find a 2026 Annual Leave record for {employee}.")

    except Exception as e:
        db.rollback()
        print(f"🔥 Critical Failure: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_sarah_cf()