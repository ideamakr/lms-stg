import sqlite3

def find_user_239():
    print("🕵️ Investigating User ID 239 and the end of the table...")
    
    try:
        conn = sqlite3.connect("leave.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Look for Michael Jackson by name (Case insensitive)
        print("\n🔍 Searching for any name like 'Michael'...")
        cursor.execute("SELECT id, employee_id, full_name FROM users WHERE full_name LIKE '%Michael%'")
        michaels = cursor.fetchall()
        for m in michaels:
            print(f"   Found: ID {m['id']} | EmpID: {m['employee_id']} | Name: {m['full_name']}")

        # 2. Look specifically for ID 239
        print(f"\n🔍 Searching specifically for Primary Key ID: 239...")
        cursor.execute("SELECT * FROM users WHERE id = 239")
        user_239 = cursor.fetchone()
        
        if user_239:
            print(f"✅ User 239 EXISTS!")
            print(f"   Full Name: {user_239['full_name']}")
            print(f"   Emp ID:    {user_239['employee_id']}")
        else:
            print("❌ User 239 DOES NOT EXIST in this database.")

        # 3. Check the very last 5 users added to the system
        print("\n📋 Last 5 users added to the database:")
        cursor.execute("SELECT id, employee_id, full_name FROM users ORDER BY id DESC LIMIT 5")
        last_five = cursor.fetchall()
        for u in last_five:
            print(f"   ID: {u['id']} | EmpID: {u['employee_id']} | Name: {u['full_name']}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_user_239()