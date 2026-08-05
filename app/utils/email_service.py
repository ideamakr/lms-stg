import smtplib
import re
import os
import json
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------------------------------------
# ⚙️ CONFIGURATION (Synchronized with .env)
# ---------------------------------------------------------
USE_MOCK_EMAIL = False 

# 🔑 BREVO API V3 KEY 
# Updated to match the "BREVO_API_KEY" name found in your .env file
API_KEY = os.getenv("BREVO_API_KEY")

# 🚀 THE VERIFIED SENDER 
# Pulls from .env if available, otherwise defaults to your verified gmail
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "leavesystemnotif@gmail.com")


def send_email(to_email: str, subject: str, body: str):
    """
    Sends a professional HTML email using Brevo HTTP API.
    Bypasses cloud provider SMTP port restrictions (Port 587/465) for Staging/Production.
    """
    # 🛡️ Safety Guard
    if not to_email or to_email == "---" or "@" not in str(to_email):
        print(f"⚠️ Skipping email: Invalid recipient address '{to_email}'")
        return False

    # 🔑 CONFIGURATION SYNC WITH SMART FALLBACK
    # 🎯 FIX: Looks for BREVO_API_KEY first; if empty, automatically grabs BREVO_SMTP_PASS!
    current_api_key = os.getenv("BREVO_API_KEY") or os.getenv("BREVO_SMTP_PASS")
    current_sender = os.getenv("SENDER_EMAIL", "leavesystemnotif@gmail.com")

    # 🌐 System URL - Environment controlled
    # Production / Staging URL is supplied through .env
    SYSTEM_URL = os.getenv("CLIENT_DOMAIN", "http://127.0.0.1:8000").rstrip("/") + "/"

    # 🛑 Crash Prevention Guard
    if not current_api_key:
        print("❌ API ERROR: Could not find any Brevo Key in your .env file (Checked BREVO_API_KEY and BREVO_SMTP_PASS)")
        return False

    if USE_MOCK_EMAIL:
        print("\n" + "="*60)
        print(f"📧 [MOCK EMAIL SERVICE] 📧")
        print(f"To:      {to_email}")
        print(f"Subject: {subject}")
        print("-" * 60)
        print(body)
        print("="*60 + "\n")
        return True

    try:
        # 🎨 THE MAGIC WRAPPER (HTML & BUTTON)
        formatted_body = body.replace('\n', '<br>').replace('--------------------------------', '<hr style="border: none; border-top: 1px solid #cbd5e1; margin: 15px 0;">')
        
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; padding: 40px 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-top: 4px solid #3b82f6;">
                <div style="color: #334155; font-size: 15px; line-height: 1.6;">
                    {formatted_body}
                </div>
                
                <div style="margin-top: 25px; text-align: center;">
                    <a href="{SYSTEM_URL}" style="background-color: #3b82f6; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        Access System Dashboard
                    </a>
                </div>

                <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
                    Automated message from your Company Leave Management System<br>
                    <a href="{SYSTEM_URL}" style="color: #3b82f6; text-decoration: none;">{SYSTEM_URL}</a>
                </div>
            </div>
        </div>
        """
        
        payload = {
            "sender": {"name": "Leave System", "email": current_sender},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_content
        }

        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": str(current_api_key),  # Safeguarded string conversion
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req) as response:
            if response.getcode() in [200, 201, 202]:
                print(f"✅ Real Email sent successfully to {to_email} via HTTP API Web Request")
                return True
            
    except Exception as e:
        try:
            error_detail = e.read().decode('utf-8')
            print(f"❌ Brevo API Error: {error_detail}")
        except:
            print(f"❌ Failed to send real email via HTTP API: {e}")
        return False
    

# ---------------------------------------------------------
# 📝 TEMPLATE HELPERS (Keep your existing templates below)
# ---------------------------------------------------------

def template_new_user(name, username, password):
    return f"""
Hi {name},

Welcome to the team! Your account has been created.

Here are your login credentials:
--------------------------------
Username: {username}
Password: {password}
--------------------------------

Please log in immediately and change your password via the 'My Profile' section.

Best regards,
HR Team
"""

def template_new_request(manager_name, employee_name, type, start, end, days, admin_name=None):
    """
    🚀 FIXED: Added 'admin_name' as the 7th argument to prevent the error.
    """
    # Create a note only if Natasha/Admin applied on behalf of someone
    admin_note = f"\n(Submitted by {admin_name} on behalf of employee)\n" if admin_name else ""

    return f"""
Hi {manager_name},

Action Required: New Leave Request{admin_note}
--------------------------------
Employee:   {employee_name}
Leave Type: {type}
Duration:   {days} Day(s)
Dates:      {start} to {end}
--------------------------------

Please log in to the Dashboard to review and take action.

Best regards,
Leave Management System
"""

def template_request_approved(employee_name, manager_name, type, start, end):
    return f"""
Hi {employee_name},

Good news! Your leave request has been APPROVED.

--------------------------------
Approver:   {manager_name}
Type:       {type}
Dates:      {start} to {end}
Status:     ✅ APPROVED
--------------------------------

Your leave balance has been deducted accordingly.

Best regards,
Leave System
"""

def template_request_rejected(employee_name, manager_name, type, start, end, remarks):
    """
    🚀 UPDATED: Named 'remarks' to match leave.py and added a fallback for empty notes.
    """
    return f"""
Hi {employee_name},

Your leave request has been REJECTED.

--------------------------------
Approver:   {manager_name}
Type:       {type}
Dates:      {start} to {end}
Status:     ❌ REJECTED
Remarks:    {remarks if remarks else 'No specific remarks provided.'}
--------------------------------

The days have been returned to your balance.

Best regards,
Leave System
"""

def template_admin_password_reset(name, new_password):
    return f"""
Hi {name},

Security Alert: Your password has been reset by an Administrator.

Here are your new login credentials:
--------------------------------
New Password: {new_password}
--------------------------------

Please log in and change this password immediately.

Best regards,
Leave System
"""

def template_role_update(name, roles, is_senior):
    role_display = ", ".join([r.upper() for r in roles])
    l2_text = "enabled" if is_senior else "disabled"
    
    return f"""
Hi {name},

Your system permissions have been updated.

--------------------------------
New Roles:       {role_display}
L2 Approval:     {l2_text.upper()} (Senior Manager Status)
--------------------------------

You may need to log out and log back in for these changes to take effect.

Best regards,
HR Admin Team
"""

def template_account_status(name, is_active):
    status = "ACTIVATED" if is_active else "DEACTIVATED"
    action = "log in" if is_active else "no longer log in"
    
    return f"""
Hi {name},

Your account status has been updated.

--------------------------------
New Status:  {status}
Action:      You can {action} the system effective immediately.
--------------------------------

If you have any questions regarding this change, please contact the HR department.

Best regards,
HR Team
"""

def template_l2_request(l2_manager_name, l1_manager_name, employee_name, type, start, end):
    return f"""
Hi {l2_manager_name},

Action Required: Final Approval Needed (L2)

{l1_manager_name} has completed the first level approval for {employee_name}.
This request now requires your final sign-off as Department Head.

--------------------------------
Employee:   {employee_name}
Leave Type: {type}
Dates:      {start} to {end}
L1 Status:  ✅ Approved by {l1_manager_name}
--------------------------------

Please log in to the Manager Dashboard to finalize this request.

Best regards,
Leave System
"""

def template_new_ot_request(manager_name, employee_name, ot_type, ot_date, duration, admin_name=None):
    """
    🚀 FIXED: Added admin_name to support "Apply on Behalf" and prevent crashes.
    """
    # Create a note only if Natasha/Admin applied on behalf of someone
    admin_note = f"\n(Submitted by {admin_name} on behalf of employee)\n" if admin_name else ""

    return f"""
Hi {manager_name},

Action Required: New Overtime Claim{admin_note}
--------------------------------
Employee:   {employee_name}
Type:       {ot_type}
Date:       {ot_date}
Duration:   {duration}
--------------------------------

Please log in to the Manager Dashboard to review this claim.

Best regards,
Leave System
"""

def template_ot_decision(employee_name, manager_name, status, ot_type, ot_date, remarks):
    # 🚀 Use .upper() to ensure the icon works even if 'status' is lowercase
    icon = "✅" if status.upper() == "APPROVED" else "❌"
    
    return f"""
Hi {employee_name},

Your Overtime Claim has been {status.upper()}.

--------------------------------
Status:     {icon} {status.upper()}
Manager:    {manager_name}
Type:       {ot_type}
Date:       {ot_date}
Remarks:    {remarks if remarks else 'No specific remarks provided.'}
--------------------------------

Best regards,
Leave System
"""


def template_l2_ot_request(l2_manager_name, l1_manager_name, employee_name, ot_type, ot_date, duration):
    return f"""
Hi {l2_manager_name},

Action Required: Final Approval Needed (L2 Overtime)

{l1_manager_name} has completed the first level approval for an Overtime claim by {employee_name}.
This request now requires your final sign-off as Department Head.

--------------------------------
Employee:   {employee_name}
OT Type:    {ot_type}
Date:       {ot_date}
Duration:   {duration}
L1 Status:  ✅ Approved by {l1_manager_name}
--------------------------------

Please log in to the Manager Dashboard to finalize this request.

Best regards,
Leave System
"""

# ---------------------------------------------------------
# 🚀 CANCELLATION WORKFLOW TEMPLATES
# ---------------------------------------------------------

def template_cancellation_request(manager_name, employee_name, type, start, end, reason):
    return f"""
Hi {manager_name},

Action Required: Leave Cancellation Request

{employee_name} has requested to CANCEL an already approved leave.

--------------------------------
Employee:   {employee_name}
Leave Type: {type}
Dates:      {start} to {end}
Reason:     {reason if reason else 'No reason provided'}
--------------------------------

Please log in to the Manager Dashboard to Confirm or Deny this cancellation.

Best regards,
Leave System
"""

def template_l2_cancellation_request(l2_manager_name, l1_manager_name, employee_name, type, start, end):
    return f"""
Hi {l2_manager_name},

Action Required: Cancellation Approval (Level 2)

{l1_manager_name} has approved the CANCELLATION request for {employee_name}.
This now requires your final sign-off to restore the employee's balance.

--------------------------------
Employee:   {employee_name}
Type:       {type}
Dates:      {start} to {end}
Status:     Waiting for L2 Confirmation
--------------------------------

Please log in to the Manager Dashboard to finalize this cancellation.

Best regards,
Leave System
"""

def template_cancellation_approved(employee_name, manager_name, type, start, end):
    return f"""
Hi {employee_name},

Your request to CANCEL your leave has been APPROVED.

--------------------------------
Approved By: {manager_name}
Type:        {type}
Dates:       {start} to {end}
Status:      ✅ CANCELLED (Balance Restored)
--------------------------------

Best regards,
Leave System
"""

def template_cancellation_rejected(employee_name, manager_name, type, start, end, remarks):
    return f"""
Hi {employee_name},

Your request to CANCEL your leave was DENIED. The leave remains valid and active.

--------------------------------
Denied By:   {manager_name}
Type:        {type}
Dates:       {start} to {end}
Status:      ⚠️ CANCELLATION REJECTED
Remarks:     {remarks if remarks else 'No specific remarks provided.'}
--------------------------------

Best regards,
Leave System
"""

# ---------------------------------------------------------
# 🏥 MEDICAL & SECURITY TEMPLATES
# ---------------------------------------------------------

def template_medical_request(manager_name, employee_name, start, end, days, admin_name=None):
    """
    Specific template for Medical Leaves.
    🚀 FIXED: Added admin_name to support "Apply on Behalf" and prevent crashes.
    """
    # Create a note only if Natasha/Admin applied on behalf of someone
    admin_note = f"\n(Submitted by {admin_name} on behalf of employee)\n" if admin_name else ""

    return f"""
Hi {manager_name},

Action Required: Medical Leave Reported{admin_note}
--------------------------------
Employee:   {employee_name}
Type:       Medical Leave 🚑
Duration:   {days} Day(s)
Dates:      {start} to {end}
--------------------------------

Please log in to the Dashboard to review any supporting documents (MC) and take action.

Best regards,
Leave System
"""

def template_forgot_password(name, username, temp_password):
    return f"""
Hi {name},

We received a request to recover your account credentials.

--------------------------------
Account Recovery Details:
• Username:      {username}
• Temp Password: {temp_password}
--------------------------------

Please log in using the credentials above. We highly recommend that you immediately navigate to your profile and change this to a secure password of your choice.

If you did not request this recovery, please contact the HR department immediately.

Best regards,
System Admin
"""


def template_new_incident(ticket_id: str, reporter_name: str, issue_type: str, urgency: str, description: str):
    """
    Template for logging new IT service desk tickets.
    Integrates with the existing HTML formatting replacement pipeline.
    """
    return f"""
Hi there,

A new IT support incident has been registered in the system tracking index.

--------------------------------
Ticket ID:   {ticket_id}
Reporter:    {reporter_name}
Category:    {issue_type}
Urgency:     {urgency}
--------------------------------

Issue Details:
{description}

Please log in to the system workspace to track progress or add updates.
"""


def template_cf_request(manager_name, employee_name, days, reason):
    """
    Template for Carry Forward requests.
    """
    return f"""
Hi {manager_name},

Action Required: New Carry Forward Request
--------------------------------
Employee:       {employee_name}
Days Requested: {days} Days
Reason:         {reason}
--------------------------------

Please log in to the Dashboard to review and take action.

Best regards,
Leave System
"""

def template_cf_approved(employee_name, manager_name, days):
    return f"""
Hi {employee_name},

Good news! Your Carry Forward request has been APPROVED.

--------------------------------
Approver:   {manager_name}
Days Approved: {days} Days
Status:     ✅ APPROVED
--------------------------------

The requested days will be moved to your balance for the upcoming year.

Best regards,
Leave System
"""

def template_cf_rejected(employee_name, manager_name, remarks):
    return f"""
Hi {employee_name},

Your Carry Forward request has been REJECTED.

--------------------------------
Approver:   {manager_name}
Status:     ❌ REJECTED
Remarks:    {remarks if remarks else 'No specific remarks provided.'}
--------------------------------

Best regards,
Leave System
"""

def template_cf_cancellation_approved(employee_name, manager_name, days):
    return f"""
Hi {employee_name},

Your request to CANCEL your Carry Forward request has been APPROVED.

--------------------------------
Approved By: {manager_name}
Days:        {days} Days
Status:      ✅ CF CANCELLATION APPROVED
--------------------------------

Best regards,
Leave System
"""

def template_cf_cancellation_rejected(employee_name, manager_name, remarks):
    return f"""
Hi {employee_name},

Your request to CANCEL your Carry Forward request was DENIED.

--------------------------------
Denied By:   {manager_name}
Status:      ⚠️ CF CANCELLATION REJECTED
Remarks:     {remarks if remarks else 'No specific remarks provided.'}
--------------------------------

Best regards,
Leave System
"""

def template_l2_cf_cancellation_request(l2_manager_name, l1_manager_name, employee_name, days):
    return f"""
Hi {l2_manager_name},

Action Required: Carry Forward Cancellation Approval (Level 2)

{l1_manager_name} has approved the cancellation of a Carry Forward request for {employee_name}.
This requires your final sign-off.

--------------------------------
Employee:   {employee_name}
Days:       {days} Days
Status:     Waiting for L2 Confirmation
--------------------------------

Please log in to the Manager Dashboard to finalize.

Best regards,
Leave System
"""


def template_cf_cancellation_request(manager_name, employee_name, days, reason):
    return f"""
Hi {manager_name},

Action Required: Carry Forward Cancellation Request

{employee_name} has requested to CANCEL a Carry Forward request.

--------------------------------
Employee:   {employee_name}
Days:       {days} Days
Reason:     {reason if reason else 'No reason provided'}
--------------------------------

Please log in to the Manager Dashboard to Confirm or Deny this cancellation.

Best regards,
Leave System
"""