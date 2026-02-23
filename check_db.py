import sqlite3

conn = sqlite3.connect('leave.db')
cursor = conn.cursor()

print("Columns in leave_balances:")
cursor.execute("PRAGMA table_info(leave_balances)")
for col in cursor.fetchall():
    print(f"- {col[1]}") # This prints the actual column name

conn.close()