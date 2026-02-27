import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Load the secrets from your .env file
# 1. Load the secrets
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in .env file!")

# 2. Check the environment
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # ✅ Local SQLite Settings
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False} 
    )
else:
    # ✅ Cloud PostgreSQL (Supabase) Settings
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# ... rest of file
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()