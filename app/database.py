import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Load the secrets from your .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in .env file!")

# 🚀 PROTOCOL FIX: SQLAlchemy 1.4+ requires 'postgresql://' 
# but many providers still give 'postgres://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Check the environment
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # ✅ Local SQLite Settings - UPGRADED POOL HEADROOM
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,    # 🔄 Checks if connection is alive before using it
        pool_size=30,          # 🪑 Expanded base pool for simultaneous dashboard requests
        max_overflow=20,       # 📈 Extra temporary burst connections headroom
        pool_timeout=60,       # ⏱️ Wait 60s before timing out
        pool_recycle=1800      # ♻️ Refresh connections every 30 mins
    )
else:
    # ✅ Cloud PostgreSQL (Supabase/Render) Settings - RESILIENT CONFIG
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,    # 🔄 🔍 Pre-ping catches dropped connections before queries execute
        pool_size=30,          # 🪑 Base connection pool
        max_overflow=20,       # 📈 Extra connections during traffic spikes
        pool_timeout=60,       # ⏱️ Wait 60s before timing out
        pool_recycle=300       # ♻️ 🕒 Recycles connections every 5 minutes to beat cloud idle limits
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