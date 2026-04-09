import os
import json
import sys
import hashlib
from pathlib import Path

# Add parent dir to path to import main
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import _get_google_fernet, GOOGLE_OAUTH_TOKENS_DIR
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()
user_email = os.getenv("GMAIL_ADDRESS")

def get_creds(email):
    h = hashlib.sha256(email.encode()).hexdigest()
    token_path = GOOGLE_OAUTH_TOKENS_DIR / f"{h}.enc"
    if not token_path.exists():
        return None
    fernet = _get_google_fernet()
    with open(token_path, "rb") as f:
        creds_json = fernet.decrypt(f.read()).decode("utf-8")
    return Credentials.from_authorized_user_info(json.loads(creds_json))

print(f"DEBUG: Starting debug sync for {user_email}...")
creds = get_creds(user_email)
if not creds:
    print(f"ERROR: No credentials found for {user_email}.")
    exit(1)

service = build("gmail", "v1", credentials=creds)

# 1. Check Inbox via Query
print("\n--- Query: 'in:inbox' ---")
q_resp = service.users().messages().list(userId="me", q="in:inbox", maxResults=100).execute()
q_ids = [m['id'] for m in q_resp.get('messages', [])]
print(f"Total IDs found via query: {len(q_ids)}")

# 2. Check Inbox via Label
print("\n--- Label: 'INBOX' ---")
l_resp = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=100).execute()
l_ids = [m['id'] for m in l_resp.get('messages', [])]
print(f"Total IDs found via label: {len(l_ids)}")

if len(l_ids) != len(q_ids):
    print(f"⚠️ DISCREPANCY DETECTED: Label has {len(l_ids)}, Query has {len(q_ids)}")
else:
    print("✅ Label and Query match.")
