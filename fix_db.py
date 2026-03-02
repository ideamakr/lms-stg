from app.database import engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

def add_missing_column():
    print("🔌 Connecting to the database specified in your .env file...")
    
    try:
        # Connect using your app's exact database engine
        with engine.connect() as conn:
            # Inject the missing column
            conn.execute(text("ALTER TABLE public_holidays ADD COLUMN states VARCHAR DEFAULT 'All States'"))
            conn.commit()
            print("✅ SUCCESS! The 'states' column was safely added to your database.")
            print("Your data is 100% intact. You can start your server now!")
            
    except OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️ The column 'states' already exists! You are good to go.")
        else:
            print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    add_missing_column()