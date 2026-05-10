import sqlite3
import sys

def check_employee_profile(emp_id):
    print(f"\n🕵️  SCANNING PROFILE DATA FOR: {emp_id}...")
    print("=" * 65)
    
    try:
        # Connect to the local database file in the current folder
        conn = sqlite3.connect("leave.db")
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Fetch the user based on Employee ID
        cursor.execute("SELECT * FROM users WHERE employee_id = ?", (emp_id,))
        user = cursor.fetchone()
        
        if not user:
            print(f"❌ ERROR: ID '{emp_id}' not found in leave.db.")
            print("👉 Check verify_emp.py to see the full list of IDs.")
            return

        # Category mapping to match your Onboarding Steps
        profile_map = {
            "🆔 IDENTITY": ["full_name", "first_name", "last_name", "preferred_name", "gender"],
            "🧬 PERSONAL": ["race", "religion", "nationality", "dob", "marital_status", "ic_number"],
            "💼 EMPLOYMENT": ["job_title", "department", "business_unit", "joined_date", "contract_type", "work_location"],
            "👥 MANAGEMENT": ["line_manager", "hod_name"],
            "📞 CONTACT": ["email", "personal_email", "mobile"],
            "🏠 ADDRESS": ["home_address", "current_address"],
            "🚨 EMERGENCY": ["emergency_contact_name", "emergency_contact_rel", "emergency_contact_mobile"],
            "🖼️ MEDIA": ["profile_pic_url"]
        }

        print(f"✅ RECORD FOUND: {user['full_name']}")
        print(f"{'SECTION / FIELD':<30} | {'STATUS':<10} | {'VALUE'}")
        print("-" * 65)

        for section, fields in profile_map.items():
            print(f"\n{section}")
            for field in fields:
                # Check if the column exists in the database first to avoid crashes
                if field not in user.keys():
                    print(f"{field:<30} | ⚠️ MISSING | (Column not in DB)")
                    continue
                    
                val = user[field]
                
                # Logic to detect empty or "Ghost" values
                is_empty = val is None or str(val).strip() == "" or str(val).lower() == "none"
                
                status = "❌ EMPTY" if is_empty else "✅ OK"
                display_val = "NULL" if val is None else f"{val}"
                
                print(f"{field:<30} | {status:<10} | {display_val}")

        conn.close()
        print("\n" + "=" * 65)
        print("💡 TIP: If '✅ OK' shows 'None', it means the literal string")
        print("   'None' was saved by the frontend instead of an actual value.")

    except sqlite3.OperationalError:
        print("❌ DATABASE ERROR: Could not find 'leave.db'.")
        print("👉 Make sure you are in the same folder as the database file.")
    except Exception as e:
        print(f"❌ SYSTEM ERROR: {e}")

if __name__ == "__main__":
    print("--- 🔍 Leave System Profile Integrity Scanner ---")
    
    # Prompt for ID with a clear instruction
    user_input = input("enter").strip()
    
    # Use Natasha as default if input is blank
    target_id = user_input if user_input else "HR-001"
    
    check_employee_profile(target_id)