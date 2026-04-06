import smtplib
import ssl
import time
import os
from email.message import EmailMessage
from dotenv import load_dotenv

# Load settings from .env to get the target email address
load_dotenv()

# ==========================================
# CONFIGURATION (Account B - Sender)
# ==========================================
# 1. Use a DIFFERENT Gmail account than the one connected to the app.
# 2. Generate an "App Password" (16 chars) for this second account.
SENDER_EMAIL = "your-second-email@gmail.com" 
SENDER_APP_PASSWORD = "xxxx xxxx xxxx xxxx" 

# Target email (The one connected to your AICOE app)
TARGET_EMAIL = os.getenv("GMAIL_USER") or "target-email@gmail.com"

# ==========================================
# DEMO GRIEVANCES
# ==========================================
GRIEVANCES = [
    {
        "subject": "Urgent: Scholarship Disbursement Issue - ID 5542",
        "body": "Dear Authority,\n\nI am writing to report that my scholarship for the current semester (Fall 2025) has not been disbursed yet. My student ID is 5542. Please look into this immediately.\n\nRegards,\nRajesh Kumar"
    },
    {
        "subject": "Request for Semester Extension - Medical Grounds",
        "body": "Sir/Madam,\n\nI am a student of Computer Science. Due to unfortunate medical reasons, I missed my final exams. I request you to allow a semester extension.\n\nThank you,\nSneha Sharma"
    },
    {
        "subject": "Hostel Facility Complaint: Water Shortage",
        "body": "To the Warden,\n\nThere has been a severe water shortage in Block C of the boys hostel for the last 3 days. We are facing extreme difficulty.\n\nSincerely,\nAmit Singh"
    }
]

def send_grievances():
    if not TARGET_EMAIL:
        print("❌ Error: TARGET_EMAIL not found in .env or script.")
        return

    print(f"🚀 Starting seeding process...")
    print(f"📤 From: {SENDER_EMAIL}")
    print(f"📥 To: {TARGET_EMAIL}")
    print("-" * 30)

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            
            for i, g in enumerate(GRIEVANCES):
                msg = EmailMessage()
                msg.set_content(g["body"])
                msg["Subject"] = g["subject"]
                msg["From"] = SENDER_EMAIL
                msg["To"] = TARGET_EMAIL

                server.send_message(msg)
                print(f"✅ Sent grievance {i+1}: {g['subject']}")
                
                # Sleep briefly to avoid bulk spam filters
                time.sleep(2)
                
        print("-" * 30)
        print("🎉 Seeding complete! Now go to your dashboard and click 'Refresh'.")
    except Exception as e:
        print(f"❌ Failed to send emails: {e}")
        print("\n💡 TIP: Make sure you use an 'App Password' (16 characters) for Account B, not your regular password.")

if __name__ == "__main__":
    if "xxxx" in SENDER_APP_PASSWORD:
        print("⚠️ ACTION REQUIRED: Open 'backend/seed_external.py' and enter your second account's App Password.")
    else:
        send_grievances()
