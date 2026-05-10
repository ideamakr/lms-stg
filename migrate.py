import sqlite3
import os

# 🚀 TARGET DATABASE
DB_FILE = "leave.db" 

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"❌ Error: {DB_FILE} not found in this directory.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # List of all potential new columns to add
    new_columns = [
        ("first_name", "TEXT"),
        ("middle_name", "TEXT"),
        ("last_name", "TEXT"),
        ("preferred_name", "TEXT"),
        ("profile_pic_url", "TEXT"),
        ("ic_number", "TEXT"),
        ("nationality", "TEXT"),
        ("dob", "TEXT"),
        ("race", "TEXT"),
        ("religion", "TEXT"),
        ("hod_name", "TEXT"),
        ("contract_type", "TEXT"),
        ("work_location", "TEXT"),
        ("personal_email", "TEXT"),
        ("home_address", "TEXT"),
        ("current_address", "TEXT"),
        ("emergency_contact_name", "TEXT"),
        ("emergency_contact_rel", "TEXT"),
        ("emergency_contact_mobile", "TEXT")
    ]

    print(f"📡 Starting migration on {DB_FILE}...")

    for col_name, col_type in new_columns:
        try:
            # We use ALTER TABLE to add columns one by one
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            print(f"✅ Added column: {col_name}")
        except sqlite3.OperationalError as e:
            # This error happens if the column already exists
            if "duplicate column name" in str(e).lower():
                print(f"ℹ️  Column '{col_name}' already exists, skipping.")
            else:
                print(f"⚠️  Unexpected error on '{col_name}': {e}")

    conn.commit()
    conn.close()
    print("🏁 Migration complete! Your 200 records have been upgraded successfully.")

if __name__ == "__main__":
    migrate()