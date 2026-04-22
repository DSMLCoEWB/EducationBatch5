import os
import pandas as pd
import base64
from email.mime.text import MIMEText
from typing import Dict, Any

from gmail.client import get_gmail_api_service
from core.logging import get_logger

logger = get_logger("utils.seeding")

DEMO_EMAILS = [
    {
        "subject": "[DEMO] Urgent: Examination Center Disruption",
        "body": "Highly urgent matter regarding Center 402. Room roof is leaking.",
        "sender": "center_head@edu.gov"
    },
    {
        "subject": "[DEMO] Scholarship Disbursement Query",
        "body": "I have not received my merit scholarship for the last two quarters.",
        "sender": "student1@univ.edu"
    }
]

def send_demo_emails_to_gmail_inbox(user_email: str) -> Dict[str, Any]:
    """Injects a set of hardcoded demo emails into the user's Gmail inbox."""
    service = get_gmail_api_service(user_email)
    if not service:
        return {"error": "Gmail service failed"}
        
    count = 0
    for email in DEMO_EMAILS:
        message = MIMEText(email['body'])
        message['to'] = user_email
        message['subject'] = email['subject']
        message['from'] = email['sender']
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        try:
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            count += 1
        except Exception as e:
            logger.error(f"Seeding failed for {email['subject']}: {e}")
            
    return {"sent_count": count}

def cleanup_seeded_emails(user_email: str) -> Dict[str, Any]:
    """Moves all emails with [DEMO] prefix to trash."""
    service = get_gmail_api_service(user_email)
    if not service: return {"error": "service_not_found"}
    
    results = service.users().messages().list(userId='me', q="subject:[DEMO]").execute()
    messages = results.get('messages', [])
    
    deleted = 0
    for m in messages:
        service.users().messages().trash(userId='me', id=m['id']).execute()
        deleted += 1
        
    return {"deleted": deleted}

def send_excel_emails_to_gmail_inbox(user_email: str) -> Dict[str, Any]:
    """Parses grievances.xlsx and injects them as real Gmail messages."""
    from config import DATA_DIR
    excel_path = os.path.join(DATA_DIR, "grievances.xlsx")
    if not os.path.exists(excel_path):
        return {"error": "Excel file not found at " + excel_path}
        
    service = get_gmail_api_service(user_email)
    if not service:
        return {"error": "Gmail service failed"}
        
    try:
        df = pd.read_excel(excel_path)
        count = 0
        for _, row in df.head(10).iterrows(): # Limit to 10 for safety
            subject = str(row.get("Subject", "[SEEDED] No Subject"))
            body = str(row.get("Body", "Empty body"))
            sender = str(row.get("Sender", "citizen@testing.edu"))
            
            message = MIMEText(body)
            message['to'] = user_email
            message['subject'] = f"[EXCEL] {subject}"
            message['from'] = sender
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            count += 1
            
        return {"sent_count": count}
    except Exception as e:
        logger.error(f"Excel seeding failed: {e}")
        return {"error": str(e)}
