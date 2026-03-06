import sqlite3
import os
from dotenv import load_dotenv

# 1. Load DB Path from .env
load_dotenv()
db_url = os.getenv("DATABASE_URL")
# SQLite URLs usually look like 'sqlite:///./leave.db', we need just the path
db_path = db_url.replace("sqlite:///", "") if db_url else "./leave.db"

def run_migration():
    print(f"🚀 Starting V1.4.0 Migration on: {db_path}")
    
    if not os.path.exists(db_path):
        print("❌ Error: Database file not found. Check your .env path.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # The columns we need to add to 'global_policy'
    new_columns = [
        ("cf_enabled", "BOOLEAN DEFAULT 0"),
        ("cf_max_days", "FLOAT DEFAULT 5.0"),
        ("cf_expiry_date", "DATE")
    ]

    for col_name, col_type in new_columns:
        try:
            # Check if column already exists to prevent 'duplicate column' error
            cursor.execute(f"SELECT {col_name} FROM global_policy LIMIT 1")
            print(f"✅ Column '{col_name}' already exists. Skipping.")
        except sqlite3.OperationalError:
            # Column missing? Let's add it!
            print(f"➕ Adding column: {col_name}...")
            cursor.execute(f"ALTER TABLE global_policy ADD COLUMN {col_name} {col_type}")
            conn.commit()

    print("\n✨ Migration Complete. Existing data preserved.")
    conn.close()

if __name__ == "__main__":
    run_migration()