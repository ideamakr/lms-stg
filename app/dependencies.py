# app/dependencies.py
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import SessionLocal
from . import models

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 🛡️ THE SECURITY GUARD FUNCTION
async def validate_session(
    x_session_id: str = Header(None, alias="X-Session-ID"),
    x_requester_name: str = Header(None, alias="X-Requester-Name"),
    db: Session = Depends(get_db)
):
    # 1. 🛑 GUARD: Check if headers are physically missing (The "EMPTY ID" fix)
    if not x_session_id or x_session_id == "null":
        print(f"🛑 401 Block: {x_requester_name} sent an EMPTY ID. Header was missing.")
        raise HTTPException(status_code=401, detail="Session ID missing")

    # 2. Look up the user in the database
    user = db.query(models.User).filter(models.User.full_name == x_requester_name).first()

    # 3. 🛑 GUARD: Check if the session matches the latest login
    if not user or user.current_session_id != x_session_id:
        print(f"⚠️ Session Conflict: {x_requester_name} kicked out (New login detected elsewhere).")
        raise HTTPException(status_code=401, detail="Session expired or logged in elsewhere")

    return user # Session is valid!