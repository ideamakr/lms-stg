import sqlite3

# Connect to your database
conn = sqlite3.connect('leave.db')
cursor = conn.cursor()

# Get the most recent leave request submitted
cursor.execute("SELECT id, employee_name, applied_by, reason FROM leaves ORDER BY id DESC LIMIT 1;")
row = cursor.fetchone()

print("\n--- 🔍 DATABASE CHECK ---")
if row:
    print(f"Leave ID      : {row[0]}")
    print(f"Employee      : {row[1]}")
    print(f"Applied By    : {row[2]}  <--- THIS IS THE MAGIC FIELD!")
    print(f"Reason        : {row[3]}")
else:
    print("No leaves found.")
print("-------------------------\n")

conn.close()