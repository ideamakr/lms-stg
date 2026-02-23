import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Database Connection
BASE_DIR = "/Users/ext.neil.jalos/Documents/leave-system/leave-system"
db_path = os.path.join(BASE_DIR, "leave.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    full_name = Column(String)
    email = Column(String)
    password = Column(String)
    role = Column(String)
    is_active = Column(Boolean, default=True) # 🚀 This is the fix

def finalize_superuser():
    db = SessionLocal()
    
    # Target the 'superuser' account
    admin = db.query(User).filter(User.username == "superuser").first()
    
    if admin:
        admin.email = "nieljalos+lms01@gmail.com"
        admin.password = "password123"
        admin.full_name = "System Administrator"
        admin.role = "superuser"
        admin.is_active = True # ✅ Force activation
        db.commit()
        print("✅ SUCCESS: 'superuser' is now ACTIVE and configured.")
    else:
        # Create it if it somehow got deleted
        new_admin = User(
            username="superuser",
            full_name="System Administrator",
            email="nieljalos+lms01@gmail.com",
            password="password123",
            role="superuser",
            is_active=True
        )
        db.add(new_admin)
        db.commit()
        print("✅ SUCCESS: New active 'superuser' account created.")
    
    db.close()

if __name__ == "__main__":
    finalize_superuser()