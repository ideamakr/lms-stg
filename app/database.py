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

# # ✅ Production Client Server Settings 
#     engine = create_engine(
#         DATABASE_URL, 
#         pool_pre_ping=True,    
        
#         pool_size=50,          # 🪑 50 permanent active connections ready 24/7
#         max_overflow=30,       # 📈 Allow up to 30 extra connections during morning peak hours
#         pool_timeout=30,       # ⏱️ Drop back down to 30s (because with 80 slots, nobody should be waiting)
#         pool_recycle=1800      # ♻️ Increase to 30 mins (production DBs don't drop idle channels aggressively)
#     )

else:
    # ✅ Cloud PostgreSQL (Supabase/Render) Settings - DATABASE-SAFE CONFIG
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,    # 🔄 Checks if connection is alive before using it
        
        # 🛡️ OPTIMIZED FOR MULTI-STAGE LOOPS:
        # pool_size + max_overflow = 15 max connections.
        # This maximizes your throughput while staying under the database's 16-connection limit!
        pool_size=10,          # 🪑 Safe permanent connection ceiling
        max_overflow=5,        # 📈 Headroom allowance increased slightly to 5 for multi-stage surges
        
        # ⏱️ THE MULTI-STAGE SAVIOR:
        # Increased from 60 to 90. Requests waiting on multi-tier approvals will now happily
        # wait in memory for a connection slot rather than timing out with a QueuePool error.
        pool_timeout=90,       
        
        pool_recycle=300       # ♻️ Recycles connections every 5 minutes to beat cloud idle limits
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