import sqlite3
import os

def main():
    # 🔍 Automatically locate your database file path location
    db_path = "leave.db"
    if not os.path.exists(db_path) and os.path.exists("app/leave.db"):
        db_path = "app/leave.db"
        
    if not os.path.exists(db_path):
        print("❌ Could not locate leave.db in your project root or app folder!")
        return

    print(f"📦 Connecting directly to database file at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 📋 Dynamically extract table columns to keep this completely schema-safe
    cursor.execute("PRAGMA table_info(leaves)")
    columns = [col[1] for col in cursor.fetchall()]
    
    print("⚡ Injecting 50 cosmetic testing rows into 'leaves' table...")
    
    for i in range(1, 51):
        # Base dataset mapped to your UI table columns
        row_data = {
            "employee_name": f"Test Scroll Employee {i:02d}",
            "approver_name": "Sarah Connor",
            "leave_type": "Annual Leave",
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
            "reason": f"📜 Layout Overflow Verification Row {i:02d}"
        }
        
        # Automatically account for framework state columns if they are present
        if "status" in columns:
            row_data["status"] = "Pending"
        if "leave_status" in columns:
            row_data["leave_status"] = "Pending"
        if "is_half_day" in columns:
            row_data["is_half_day"] = "false"
            
        # Filter insertion data to match only existing database columns
        final_fields = {k: v for k, v in row_data.items() if k in columns}
        
        placeholders = ", ".join(["?"] * len(final_fields))
        field_names = ", ".join(final_fields.keys())
        query = f"INSERT INTO leaves ({field_names}) VALUES ({placeholders})"
        
        cursor.execute(query, list(final_fields.values()))

    conn.commit()
    conn.close()
    print("✅ Success! 50 test rows have been written directly to your local database.")

if __name__ == "__main__":
    main()