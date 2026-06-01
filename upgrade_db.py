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

        # 4. Standard structural legacy safeguards
        legacy_cols = [
            ("overtime_bank", "FLOAT DEFAULT 0.0"),
            ("unpaid_taken", "FLOAT DEFAULT 0.0")
        ]

        # 5. Complete manifest of newly mapped enterprise & banking column pillars
        new_enterprise_cols = [
            ("employee_no_old", "TEXT"),
            ("common_name", "TEXT"),
            ("employee_status", "TEXT"),
            ("organization_o", "TEXT"),
            ("organization_ou1", "TEXT"),
            ("organization_ou2", "TEXT"),
            ("lotus_notes_id", "TEXT"),
            ("document_status", "TEXT"),
            ("company", "TEXT"),
            ("location", "TEXT"),
            ("position_grade", "TEXT"),
            ("contract_expiry_date", "TEXT"),
            ("expat_type", "TEXT"),
            ("category", "TEXT"),
            ("ranking", "TEXT"),
            ("highest_qualification", "TEXT"),
            ("level_0", "TEXT"),
            ("level_1", "TEXT"),
            ("level_2", "TEXT"),
            ("place_of_birth", "TEXT"),
            ("date_ict_removal", "TEXT"),
            ("date_resigned", "TEXT"),
            ("last_working_day", "TEXT"),
            ("last_day_of_service", "TEXT"),
            ("shift_employee", "TEXT"),
            ("compensation_leave_entitled", "TEXT"),
            ("commissioning_engineer", "TEXT"),
            ("scholar", "TEXT"),
            ("bank_holder_name", "TEXT"),
            ("bank_name", "TEXT"),
            ("bank_account_number", "TEXT"),
            ("bank_account_status", "TEXT DEFAULT 'Active'")
        ]

        # Execute safe sequential migrations
        for col_name, col_type in (legacy_cols + new_enterprise_cols):
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
                print(f"✅ SUCCESS: Added '{col_name}' column.")
            except sqlite3.OperationalError as e:
                print(f"⏭️ SKIP: '{col_name}' - Already matches structural rules.")

        conn.commit()
        conn.close()
        print("🎉 Database upgrade complete! Table schema is now aligned with models.py.")

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    upgrade_database()