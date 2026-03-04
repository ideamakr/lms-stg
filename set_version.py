import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

def update_version():
    # 1. Get DB name from .env
    db_url = os.getenv("DATABASE_URL")
    db_filename = db_url.replace("sqlite:///", "")
    
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    # 2. Update the system_version key
    # If the key doesn't exist, this script will create it
    cursor.execute("""
        INSERT INTO system_settings (key, value) 
        VALUES ('system_version', 'V1.3.0')
        ON CONFLICT(key) DO UPDATE SET value='V1.3.0';
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Database version updated to V1.3.0 in {db_filename}")

if __name__ == "__main__":
    update_version()