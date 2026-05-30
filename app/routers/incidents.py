from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import os
import time
import shutil

from .. import models
from ..database import get_db

# 📧 ROBUST EMAIL UTILITIES IMPORT STRATEGY (Mirrors your leaves.py setup)
try:
    from app.email_service import send_email, template_new_incident
except ImportError:
    try:
        from app.utils.email_service import send_email, template_new_incident
    except ImportError:
        try:
            from email_service import send_email, template_new_incident
        except ImportError:
            from utils.email_service import send_email, template_new_incident

router = APIRouter(prefix="/incidents", tags=["IT Service Desk"])

# --- Pydantic Schemas ---
class IncidentCreate(BaseModel):
    issue_type: str
    urgency: str
    screen_context: str = "Unknown"
    description: str
    attachment_path: str = None

class IncidentUpdate(BaseModel):
    status: str
    admin_notes: str = None

# --- Routes ---

# 🚀 NEW: Dual-Layer File Storage Upload Engine
@router.post("/upload")
async def upload_incident_attachment(file: UploadFile = File(...)):
    """
    Saves attachments with a robust dual-layer strategy:
    1️⃣ Attempts to upload to Supabase Cloud Storage bucket.
    2️⃣ Gracefully falls back to local storage if cloud is unreachable/unconfigured.
    """
    try:
        # Generate a unique timestamped file token to prevent filename collisions
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        clean_name = f"{timestamp}_{file.filename.replace(' ', '_')}"
        
        # 1️⃣ FIRST LAYER: Attempt Supabase Cloud Storage Upload
        try:
            # Inline runtime import to fully prevent circular dependencies with main.py
            from app.main import supabase, SUPABASE_BUCKET
            
            if supabase and SUPABASE_BUCKET:
                # Read file content stream
                file_contents = await file.read()
                storage_path = f"incidents/{clean_name}"
                
                # Push binary stream directly to your Supabase bucket
                supabase.storage.from_(SUPABASE_BUCKET).upload(
                    path=storage_path,
                    file=file_contents,
                    file_options={"content-type": file.content_type}
                )
                
                # Fetch public asset URL link
                public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
                print(f"☁️ Cloud Target Hit: Attachment saved to Supabase -> {public_url}")
                return {"attachment_url": public_url}
                
        except Exception as cloud_err:
            # Cloud failed or is unconfigured; log warning and seek stream back to 0 for local reader
            print(f"⚠️ Cloud upload bypassed. Executing local storage fallback handler. Error: {cloud_err}")
            await file.seek(0)

        # 2️⃣ SECOND LAYER: Local Storage Fallback Strategy
        UPLOAD_DIR = "uploads"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(UPLOAD_DIR, clean_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        local_url = f"/uploads/{clean_name}"
        print(f"📁 Fallback Target Hit: Attachment written locally to disk -> {local_url}")
        return {"attachment_url": local_url}

    except Exception as err:
        print(f"❌ Storage Core Failure: Both upload layers rejected file. {str(err)}")
        raise HTTPException(status_code=500, detail="Unable to process and store file attachment.")


@router.post("/new")
def create_incident(
    request: IncidentCreate, 
    employee_name: str, 
    db: Session = Depends(get_db)
):
    """Creates a new IT Service Desk Ticket and dispatches automatic Brevo notifications."""
    # Find the user to automatically log their role and target their verified email address
    user = db.query(models.User).filter(models.User.full_name == employee_name).first()
    reporter_role = user.job_title if user and user.job_title else "Employee"

    new_incident = models.SystemIncident(
        reporter_name=employee_name,
        reporter_role=reporter_role,
        issue_type=request.issue_type,
        urgency=request.urgency,
        screen_context=request.screen_context,
        description=request.description,
        attachment_path=request.attachment_path,
        status="OPEN"
    )
    
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)
    
    # Generate the formatted tracking reference token tag
    ticket_id = f"#INC-{str(new_incident.id).zfill(4)}"
    
    # 📧 BREVO NOTIFICATION GATEWAY
    try:
        # Pulls the custom template seamlessly through whichever import layer succeeded above
        email_body = template_new_incident(
            ticket_id=ticket_id,
            reporter_name=employee_name,
            issue_type=request.issue_type,
            urgency=request.urgency,
            description=request.description
        )

        # 1️⃣ Ticket Confirmation Copy for the reporting Employee
        if user and hasattr(user, 'email') and user.email:
            send_email(
                to_email=user.email,
                subject=f"🎟️ IT Support Ticket Logged: {ticket_id}",
                body=email_body
            )
        else:
            print(f"⚠️ User Notification Skipped: No email property found on employee account metadata for '{employee_name}'")

        # 2️⃣ Ticket Alert Triage Notification for the System Administrator
        # Dynamically pulls ADMIN_EMAIL from settings, defaulting to SENDER_EMAIL as a fallback
        admin_recipient = os.getenv("ADMIN_EMAIL") or os.getenv("SENDER_EMAIL", "leavesystemnotif@gmail.com")
        
        send_email(
            to_email=admin_recipient,
            subject=f"🚨 [NEW TICKET - {request.urgency}] {request.issue_type} from {employee_name}",
            body=email_body
        )

    except Exception as email_err:
        # Kept inside a safe block to guarantee successful database lifecycle commits 
        # even if an external API handshake slow-down or throttle threshold occurs
        print(f"⚠️ Non-critical email routing anomaly captured safely: {email_err}")
    
    return {
        "message": "Incident reported successfully", 
        "ticket_id": ticket_id
    }

@router.get("/all")
def get_all_incidents(db: Session = Depends(get_db)):
    """Fetches all tickets for the Superadmin Triage Board, newest first."""
    incidents = db.query(models.SystemIncident).order_by(models.SystemIncident.id.desc()).all()
    return incidents

@router.put("/{incident_id}/status")
def update_incident(
    incident_id: int, 
    request: IncidentUpdate, 
    db: Session = Depends(get_db)
):
    """Allows Superadmin to update the status, add resolution notes, and notify the user via email."""
    incident = db.query(models.SystemIncident).filter(models.SystemIncident.id == incident_id).first()
    
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # 💾 Capture current status before updating to display in the email comparison
    old_status = incident.status
    
    # Sync incoming tracking properties
    incident.status = request.status
    if request.admin_notes is not None:
        incident.admin_notes = request.admin_notes
        
    db.commit()
    db.refresh(incident)
    
    # 📧 LIFECYCLE TRANSITION NOTIFICATION PIPELINE
    try:
        # Locate the original ticket creator inside the system identity registries
        user = db.query(models.User).filter(models.User.full_name == incident.reporter_name).first()
        
        if user and hasattr(user, 'email') and user.email:
            ticket_id = f"#INC-{str(incident.id).zfill(4)}"
            subject = f"🔄 IT Ticket Status Updated: {ticket_id} [{incident.status}]"
            
            # Cleanly isolate the single latest entry line added to the notes stack
            latest_note = request.admin_notes.split('\n')[-1].strip() if request.admin_notes else None
            if latest_note and ("]:" in latest_note or "•" in latest_note):
                latest_note = latest_note.split(']:')[-1].strip() if ']:' in latest_note else latest_note

            email_body = f"""
            <div style="font-family: Arial, sans-serif; color: #334155; max-width: 600px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02);">
                <h2 style="color: #2563eb; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-top: 0;">IT Support Desk Update</h2>
                <p>Hello <strong>{incident.reporter_name}</strong>,</p>
                <p>The status of your support request <strong>{ticket_id}</strong> has been updated by the System Administrator.</p>
                
                <div style="background: #f8fafc; padding: 15px 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #cbd5e1;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: bold; width: 35%;">Issue Category:</td>
                            <td style="padding: 6px 0; font-weight: 700; color: #1e293b;">{incident.issue_type}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: bold;">Previous Status:</td>
                            <td style="padding: 6px 0; color: #64748b; font-weight: 700; text-transform: uppercase;">{old_status}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; color: #64748b; font-weight: bold;">Current Status:</td>
                            <td style="padding: 6px 0; color: #2563eb; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">{incident.status}</td>
                        </tr>
                    </table>
                </div>
                
                {f'''<div style="margin-top: 20px;">
                    <h4 style="margin-bottom: 6px; color: #475569; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Administrator Resolution Notes:</h4>
                    <div style="margin: 0; background: #f1f5f9; padding: 12px 15px; border-left: 4px solid #2563eb; font-style: italic; border-radius: 0 8px 8px 0; font-size: 14px; color: #334155;">
                        "{latest_note if latest_note else request.admin_notes}"
                    </div>
                </div>''' if request.admin_notes else ""}
                
                <p style="margin-top: 35px; font-size: 0.75rem; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px; font-style: italic;">
                    This is an automated transaction confirmation tracking message. Please do not reply directly to this mailbox system.
                </p>
            </div>
            """
            
            send_email(to_email=user.email, subject=subject, body=email_body)
            print(f"📧 Status update notification email dispatched successfully to: {user.email}")
            
    except Exception as email_err:
        # Kept inside a defensive warning block so database commits survive if an SMTP handshake issues happen
        print(f"⚠️ Non-critical status email transmission anomaly caught safely: {email_err}")

    return {"message": "Ticket updated successfully"}