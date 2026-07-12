import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Load the secrets from your .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # 🎛️ The environment toggle

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in .env file!")

# 🚀 PROTOCOL FIX: SQLAlchemy 1.4+ requires 'postgresql://' 
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Check the environment type
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # ✅ Local SQLite Settings - Removed Postgres-specific pool arguments
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )

elif ENVIRONMENT == "production":
    # ✅ Production Client Server Settings (PostgreSQL 17 On-Premise)
    # This unlocks high performance since you control the physical hardware!
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,    
        pool_size=50,          # 🪑 50 permanent active connections ready 24/7
        max_overflow=30,       # 📈 Allow up to 30 extra connections during morning peaks
        pool_timeout=30,       # ⏱️ Drop timeout to 30s since slots are abundant
        pool_recycle=1800      # ♻️ Refresh channels every 30 minutes
    )

else:
    # ✅ Cloud PostgreSQL (Staging Supabase/Render) Settings - DATABASE-SAFE CONFIG
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,    
        pool_size=10,          
        max_overflow=5,        
        pool_timeout=90,       
        pool_recycle=300       
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Utility to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()