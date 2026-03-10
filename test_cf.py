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
            # 💰 Step A: Set the CF Wallet strictly to 5.0
            # This wipes any previous testing values
            balance.carry_forward_total = 5.0
            
            # 🛡️ Step B: IDEMPOTENT RESET
            # We pull the base entitlement (contract days) and add the 5.0 CF.
            # This prevents the "stacking bug" where multiple runs keep adding 5 days.
            base_entitlement = float(balance.entitlement or 14.0)
            balance.remaining = base_entitlement + 5.0
            
            db.commit()
            print(f"✅ Success! Sarah has been reset to 5.0 Banked days.")
            print(f"📊 Base Entitlement: {base_entitlement}")
            print(f"📊 Total spendable (Annual + CF): {balance.remaining}")
        else:
            print(f"❌ Error: Could not find a 2026 Annual Leave record for {employee}.")

    except Exception as e:
        db.rollback()
        print(f"🔥 Critical Failure: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_sarah_cf()