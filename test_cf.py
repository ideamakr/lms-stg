from app.database import SessionLocal
from app import models

def seed_last_year_cf():
    db = SessionLocal()
    try:
        employee = "Sarah Connor"
        last_year = 2025
        current_year = 2026
        cf_days_to_carry = 5.0
        
        print(f"🚀 Simulating End-of-Year Carry Forward for {employee}...")

        # --- Step 1: Simulate Last Year's Leftover Balance (2025) ---
        balance_2025 = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == employee,
            models.LeaveBalance.year == last_year,
            models.LeaveBalance.leave_type == "Annual Leave"
        ).first()

        if not balance_2025:
            print(f"⚠️ No 2025 record found for {employee}. Creating dummy record...")
            balance_2025 = models.LeaveBalance(
                employee_name=employee,
                year=last_year,
                leave_type="Annual Leave",
                entitlement=14.0,
                remaining=cf_days_to_carry, # Simulating 5 days left at end of 2025
                carry_forward_total=0.0
            )
            db.add(balance_2025)
        else:
            balance_2025.remaining = cf_days_to_carry
            print(f"✅ 2025 Annual Leave updated to show {cf_days_to_carry} days unspent.")

        # --- Step 2: Bank the CF into Current Year (2026) ---
        balance_2026 = db.query(models.LeaveBalance).filter(
            models.LeaveBalance.employee_name == employee,
            models.LeaveBalance.year == current_year,
            models.LeaveBalance.leave_type == "Annual Leave"
        ).first()

        if balance_2026:
            # 💰 Set the CF Wallet strictly to the carried over days
            balance_2026.carry_forward_total = cf_days_to_carry
            
            # 🛡️ IDEMPOTENT RESET: Base entitlement + CF
            base_entitlement = float(balance_2026.entitlement or 14.0)
            balance_2026.remaining = base_entitlement + cf_days_to_carry
            
            print(f"✅ 2026 Annual Leave updated! {cf_days_to_carry} days banked from {last_year}.")
            print(f"📊 Base 2026 Entitlement: {base_entitlement}")
            print(f"📊 Total spendable now (Annual + CF): {balance_2026.remaining}")
        else:
            print(f"❌ Error: Could not find a {current_year} Annual Leave record for {employee}. Please register the user first.")

        db.commit()
        print("🎉 Regression seed completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"🔥 Critical Failure: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_last_year_cf()