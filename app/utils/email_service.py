import smtplib
import re
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------------------------------------------------
# ⚙️ CONFIGURATION
# ---------------------------------------------------------
USE_MOCK_EMAIL = False 

SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 587

# The system login Brevo gave you
SMTP_LOGIN = "a2ebdf001@smtp-brevo.com" 

# Your password (API/SMTP Key)
SMTP_PASSWORD = "xsmtpsib-c746ebe28cd18fe158d1b8521e7632500138d07f9f2f9492ecef3b098c0f74f2-9ExGRZxcjZ8qJFLv"

# 🚀 The Verified Sender Email
SENDER_EMAIL = "leavesystemnotif@gmail.com"

def send_email(to_email: str, subject: str, body: str):
    """
    Sends an email using Brevo SMTP or prints to console if in Mock Mode.
    Supports basic HTML for icons and formatting.
    """
    # 🛡️ Safety Guard
    if not to_email or to_email == "---" or "@" not in str(to_email):
        print(f"⚠️ Skipping email: Invalid recipient address '{to_email}'")
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
        msg = MIMEMultipart()
        msg['From'] = f"Leave System <{SENDER_EMAIL}>" # What the user sees
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # 🎨 THE MAGIC WRAPPER
        # Converts Python newlines to HTML breaks, and turns your "---" into a clean divider line
        formatted_body = body.replace('\n', '<br>').replace('--------------------------------', '<hr style="border: none; border-top: 1px solid #cbd5e1; margin: 15px 0;">')
        
        # Wraps the text in a modern, centered card design matching your dashboard
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; padding: 40px 20px; margin: 0;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-top: 4px solid #3b82f6;">
                <div style="color: #334155; font-size: 15px; line-height: 1.6;">
                    {formatted_body}
                </div>
                <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
                    Automated message from your Company Leave Management System
                </div>
            </div>
        </div>
        """
        
        # 🚀 Attach the styled HTML content instead of the raw body
        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() 
            # 🚀 Authenticate using the system login, send using the verified sender
            server.login(SMTP_LOGIN, SMTP_PASSWORD) 
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        
        print(f"✅ Real Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send real email via Brevo: {str(e)}")
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

def template_new_request(manager_name, employee_name, type, start, end, days):
    return f"""
Hi {manager_name},

Action Required: New Leave Request

--------------------------------
Employee:   {employee_name}
Leave Type: {type}
Duration:   {days} Days
Dates:      {start} to {end}
--------------------------------

Please log in to the Dashboard to Approve or Reject this request.

Best regards,
Leave System
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

def template_request_rejected(employee_name, manager_name, type, start, end, reason):
    return f"""
Hi {employee_name},

Your leave request has been REJECTED.

--------------------------------
Approver:   {manager_name}
Type:       {type}
Dates:      {start} to {end}
Status:     ❌ REJECTED
Reason:     {reason}
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

def template_new_ot_request(manager_name, employee_name, ot_type, ot_date, duration):
    return f"""
Hi {manager_name},

Action Required: New Overtime Claim

{employee_name} has submitted a new overtime claim.

--------------------------------
Type:       {ot_type}
Date:       {ot_date}
Duration:   {duration}
--------------------------------

Please log in to the Manager Dashboard to review this claim.

Best regards,
Overtime System
"""

def template_ot_decision(employee_name, manager_name, status, ot_type, ot_date, remarks):
    icon = "✅" if status == "Approved" else "❌"
    return f"""
Hi {employee_name},

Your Overtime Claim has been {status.upper()}.

--------------------------------
Status:     {icon} {status}
Manager:    {manager_name}
Type:       {ot_type}
Date:       {ot_date}
Remarks:    {remarks}
--------------------------------

Best regards,
Overtime System
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
Overtime System
"""

# ---------------------------------------------------------
# 🚀 CANCELLATION WORKFLOW TEMPLATES
# ---------------------------------------------------------

# 1. Notification to L1 (When Employee clicks "Cancel")
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

# 2. Notification to L2 (When L1 Approves a Cancellation, but L2 is ON)
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

# 3. Final Confirmation to Employee (Cancellation Approved)
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

# 4. Rejection Notification to Employee (Cancellation Denied)
def template_cancellation_rejected(employee_name, manager_name, type, start, end, remarks):
    return f"""
Hi {employee_name},

Your request to CANCEL your leave was DENIED. The leave remains valid and active.

--------------------------------
Denied By:   {manager_name}
Type:        {type}
Dates:       {start} to {end}
Status:      ⚠️ CANCELLATION REJECTED
Remarks:     {remarks}
--------------------------------

Best regards,
Leave System
"""

def send_system_email(recipient_email: str, subject: str, body: str):
    """
    Universal Email Helper
    MOCK MODE: Prints to terminal.
    PROD MODE: Plug in SendGrid/SMTP here.
    """
    print("\n" + "="*50)
    print(f"📧 SYSTEM EMAIL QUEUED")
    print(f"To: {recipient_email}")
    print(f"Subject: {subject}")
    print(f"Body: {body}")
    print("="*50 + "\n")
    
    # FUTURE TODO: 
    # sg = SendGridAPIClient('YOUR_API_KEY')
    # response = sg.send(message)
    return True

def template_medical_request(manager_name, employee_name, start, end, days):
    """
    Specific template for Medical Leaves.
    🚀 UPDATED: Removed 'Evidence' line to force Manager login for details.
    """
    return f"""
Hi {manager_name},

Action Required: Medical Leave Reported

{employee_name} has submitted a Medical Leave request.

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