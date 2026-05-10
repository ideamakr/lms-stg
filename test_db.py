import psycopg2

try:
    # Use your EXACT URL details here
    conn = psycopg2.connect(
        dbname="leave_system_db",
        user="postgres",
        password="Linkinpark8*",
        host="localhost",
        port="5433"
    )
    print("✅ Connection Successful! Your URL is correct.")
    conn.close()
except Exception as e:
    print(f"❌ Connection Failed: {e}")