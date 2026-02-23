from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite is easier for local testing than Postgres
DATABASE_URL = "sqlite:///./leave.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 🚀 MOVED HERE: This is the correct home for get_db
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()