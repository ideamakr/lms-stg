from app.database import engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

def add_missing_columns():
    print("🔌 Connecting to the database specified in your .env file...")
    
    try:
        # Connect using your app's exact database engine
        with engine.connect() as conn:
            
            # 1. Inject the max_seats column
            try:
                conn.execute(text("ALTER TABLE global_policy ADD COLUMN max_seats INTEGER DEFAULT 0"))
                print("✅ SUCCESS! The 'max_seats' column was safely added.")
            except OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print("⚠️ The column 'max_seats' already exists! Skipping.")
                else:
                    raise e
            
            # 2. Inject the registration_lock column
            try:
                conn.execute(text("ALTER TABLE global_policy ADD COLUMN registration_lock BOOLEAN DEFAULT 0"))
                print("✅ SUCCESS! The 'registration_lock' column was safely added.")
            except OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print("⚠️ The column 'registration_lock' already exists! Skipping.")
                else:
                    raise e

            # Commit changes
            conn.commit()
            print("🎉 Database patching complete! Your data is 100% intact. You can start your server now!")
            
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    add_missing_columns()