import sqlite3

def find_employee_by_name(name_query):
    print(f"🔍 Searching database for Name: '{name_query}'...\n")
    
    try:
        conn = sqlite3.connect("leave.db")
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Search using LIKE to be flexible with middle names
        cursor.execute("SELECT * FROM users WHERE full_name LIKE ?", (f"%{name_query}%",))
        row = cursor.fetchone()
        
        if not row:
            print(f"❌ ERROR: No employee found containing the name '{name_query}'.")
            print("\nCheck the list below for everyone currently in your DB:")
            cursor.execute("SELECT employee_id, full_name FROM users")
            all_users = cursor.fetchall()
            for u in all_users:
                print(f" - {u['employee_id']}: {u['full_name']}")
            return

        print(f"✅ Record Found! Actual ID in DB: {row['employee_id']}")
        print("-" * 50)
        print(f"{'COLUMN NAME':<30} | {'VALUE':<20}")
        print("-" * 50)

        for key in row.keys():
            val = row[key]
            is_missing = val is None or str(val).strip() == ""
            status_icon = "❌ MISSING" if is_missing else "✅"
            display_val = "NULL" if val is None else f"'{val}'"
            print(f"{key:<30} | {status_icon:<10} {display_val}")

        conn.close()

    except Exception as e:
        print(f"System Error: {e}")

if __name__ == "__main__":
    # Searching for Michael now
    find_employee_by_name("Michael Jackson")