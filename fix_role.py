import sqlite3

# 🚀 Updated to match your exact database name
DB_FILE = "leave.db" 

def fix_natasha():
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Update her role to the correct 'hr_admin'
        cursor.execute("""
            UPDATE users 
            SET role = 'hr_admin' 
            WHERE full_name = 'Natasha Middies Romanoff'
        """)
        
        # Save the changes
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"✅ Success! Updated {cursor.rowcount} record(s). Natasha is now an HR Admin.")
        else:
            print("⚠️ No records were updated. Make sure her full_name is exactly 'Natasha Romanoff'.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_natasha()