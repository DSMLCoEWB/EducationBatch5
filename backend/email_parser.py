import os
import pdfplumber
import pandas as pd
from docx import Document
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
import hashlib
import base64
from google.genai import Client, types
from ai_utils import generate_content_with_fallback

from config import ATTACHMENTS_DIR
from services.ocr_service import extract_attachment_text

# Ensure directory exists
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------- EML PARSER ----------------
def parse_eml(file_path):
    try:
        with open(file_path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
    except Exception:
        print(f"⚠️ Failed to parse EML file: {file_path}")
        return None

    sender = msg.get("From", "")
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    attachment_files = []  # Track actual attachment filenames

    raw_date = msg.get("Date")
    email_date = None

    try:
        if raw_date:
            email_date = parsedate_to_datetime(raw_date).date().isoformat()
    except Exception:
        email_date = None

    # ---------------- BODY EXTRACTION ----------------
    body = ""
    attachment_text = ""
    
    try:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get_content_disposition()

                if content_type == "text/plain" and disposition != "attachment":
                    try:
                        body += part.get_content()
                    except Exception:
                        pass

                if disposition == "attachment":
                    fname = part.get_filename()
                    payload = part.get_payload(decode=True)

                    if not fname or not payload:
                        continue
                    
                    # Skip very large attachments (>5 MB) for extraction
                    if len(payload) > 5 * 1024 * 1024:
                        print(f"⚠️ Skipping large attachment: {fname}")
                        continue
                    
                    # Generate unique filename using hash to avoid conflicts
                    file_hash = hashlib.md5(payload).hexdigest()[:8]
                    safe_fname = fname.replace(" ", "_").replace("/", "_")
                    unique_fname = f"{file_hash}_{safe_fname}"
                    attachment_path = os.path.join(ATTACHMENTS_DIR, unique_fname)
                    
                    # Save the actual attachment file
                    try:
                        with open(attachment_path, "wb") as f:
                            f.write(payload)
                        attachment_files.append({
                            "filename": unique_fname,
                            "original_name": fname,
                            "size": len(payload)
                        })
                    except Exception as e:
                        print(f"⚠️ Failed to save attachment {fname}: {e}")
                        continue
                    
                    # NOTE: OCR is now handled by the background worker in coordination.py
                    # to prevent blocking the sync engine.

        else:
            try:
                body = msg.get_content()
            except Exception:
                body = ""

    except Exception:
        print(f"⚠️ Error while processing email body: {file_path}")

    return {
        "email_id": message_id,
        "parent_email_id": in_reply_to,
        "sender": sender,
        "subject": subject,
        "date": email_date,
        "content": f"{subject}\n{body}\n{attachment_text}",
        "attachments": attachment_files,
        "eml_file": os.path.basename(file_path)
    }
