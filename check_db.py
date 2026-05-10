import sqlite3

def check_database():
    print("🔍 Scanning database structure...")
    
    try:
        # Connect to your SQLite database
        conn = sqlite3.connect("leave.db")
        cursor = conn.cursor()
        
        # 1. Check if the new columns physically exist in the table
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        expected_columns = [
            'first_name', 'gender', 'race', 'religion', 'dob', 
            'nationality', 'ic_number', 'business_unit', 'home_address'
        ]
        
        print("\n📋 Checking for new columns in 'users' table:")
        missing_columns = []
        for expected in expected_columns:
            if expected in columns:
                print(f"  ✅ {expected} exists!")
            else:
                print(f"  ❌ MISSING: {expected}")
                missing_columns.append(expected)
                
        # 2. Check the actual data of Michael Jackson (or the newest employee)
        print("\n👤 Checking the most recently registered user:")
        cursor.execute("SELECT full_name, first_name, gender, race, department, mobile FROM users ORDER BY id DESC LIMIT 1")
        last_user = cursor.fetchone()
        
        if last_user:
            print(f"  Full Name:  {last_user[0]}")
            print(f"  First Name: {last_user[1]}")
            print(f"  Gender:     {last_user[2]}")
            print(f"  Race:       {last_user[3]}")
            print(f"  Department: {last_user[4]}")
            print(f"  Mobile:     {last_user[5]}")
        else:
            print("  No users found in database.")
            
        conn.close()
        
        if missing_columns:
            print("\n⚠️ CONCLUSION: Your database is out of sync with models.py!")
        else:
            print("\n✅ CONCLUSION: Your database structure is perfect. The issue is in the frontend cache.")

    except Exception as e:
        print(f"Error checking database: {e}")

if __name__ == "__main__":
    check_database()