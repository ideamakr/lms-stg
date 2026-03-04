import sqlite3
import os
from dotenv import load_dotenv

# 1. Load the exact same .env file your app uses
load_dotenv()

def upgrade_database():
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url or not db_url.startswith("sqlite:///"):
        print("❌ ERROR: Could not find a valid SQLite DATABASE_URL in your .env file!")
        return

    # 2. Strip the 'sqlite:///' prefix to get the actual file path
    db_filename = db_url.replace("sqlite:///", "")
    
    print(f"🔗 Attempting to connect to the REAL database: {db_filename}")

    try:
        conn = sqlite3.connect(db_filename)
        cursor = conn.cursor()
        
        # 3. Verify we are in the right place
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("❌ ERROR: Connected, but 'users' table is missing! Check your .env DATABASE_URL path.")
            return

        # 4. Add overtime_bank
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN overtime_bank FLOAT DEFAULT 0.0;")
            print("✅ SUCCESS: Added 'overtime_bank' column.")
        except sqlite3.OperationalError as e:
            print(f"⏭️ SKIP: 'overtime_bank' - {e}")

        # 5. Add unpaid_taken
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN unpaid_taken FLOAT DEFAULT 0.0;")
            print("✅ SUCCESS: Added 'unpaid_taken' column.")
        except sqlite3.OperationalError as e:
            print(f"⏭️ SKIP: 'unpaid_taken' - {e}")

        conn.commit()
        conn.close()
        print("🎉 Database upgrade complete!")

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    upgrade_database()