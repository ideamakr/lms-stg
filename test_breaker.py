from app.database import SessionLocal
from app import models
import re

def create_blockers(start_id: str):
    db = SessionLocal()
    
    # Extract the prefix and the number (e.g., 'EMP-2026' and '0096')
    match = re.search(r'(.*?)-(\d+)$', start_id)
    if not match:
        print("❌ Invalid ID format! Make sure it looks like EMP-2026-0001")
        return
        
    prefix = match.group(1)
    num_str = match.group(2)
    start_num = int(num_str)
    
    print(f"\n🧱 Creating 4 blockers starting from {start_id}...")
    
    try:
        # Loop 4 times to block the original attempt + 3 retries
        for i in range(4):
            # Keep the exact same amount of padding (e.g., 0096)
            current_id = f"{prefix}-{start_num + i:0{len(num_str)}d}"
            
            # Check if it already exists to prevent script crash
            existing = db.query(models.User).filter(models.User.employee_id == current_id).first()
            if existing:
                print(f"  -> ⚠️ ID {current_id} is already blocked by {existing.username}")
                continue

            dummy_user = models.User(
                username=f"blocker_bot_{current_id.lower()}",
                full_name=f"Blocker Bot {i}",
                password="password123",
                email=f"blocker{i}_{current_id.lower()}@test.com",
                employee_id=current_id,
                role="employee",
                is_active=True,
                joined_date="2026-03-02"
            )
            db.add(dummy_user)
            print(f"  -> 🛑 Stole ID: {current_id}")
            
        db.commit()
        print("\n✅ All 4 IDs are now blocked in the database!")
        print("👉 NOW go click 'Save' on your frontend to watch the circuit breaker trip!\n")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    target_id = input("Enter the Employee ID currently shown on your form (e.g., EMP-2026-0096): ")
    create_blockers(target_id.strip())