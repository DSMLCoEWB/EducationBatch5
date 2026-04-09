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

# Directory to store extracted attachments
ATTACHMENTS_DIR = "./attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

# ---------------- ATTACHMENT TEXT EXTRACTION ----------------
def extract_text_from_attachment_ai(path: str) -> str:
    """Uses Gemini Vision to extract text from images and scanned PDFs."""
    try:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return ""

        client = Client(api_key=api_key)
        
        # Read file as bytes
        with open(path, "rb") as f:
            file_data = f.read()

        mime_type = "image/jpeg"
        if path.lower().endswith(".pdf"):
            mime_type = "application/pdf"
        elif path.lower().endswith(".png"):
            mime_type = "image/png"

        contents = [
            types.Part.from_bytes(data=file_data, mime_type=mime_type),
            "Extract all legible text from this document for archival purposes. If it is an official document (like a scholarship letter or grievance), preserve the core facts like names, dates, and decision status."
        ]

        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            label="OCR Service"
        )

        if response and response.text:
            return f"\n--- [Extracted from Attachment: {os.path.basename(path)}] ---\n{response.text}\n"
    except Exception as e:
        print(f"⚠️ AI OCR failed for {path}: {e}")
    return ""


def extract_attachment_text(path):
    try:
        if path.lower().endswith(".pdf"):
            try:
                with pdfplumber.open(path) as pdf:
                    text = " ".join(
                        (page.extract_text() or "")
                        for page in pdf.pages[:5]
                    ).strip()
                    if text:
                        return text
            except Exception:
                print(f"⚠️ Error reading PDF with pdfplumber: {path}")
            # If no text found or error occurred, proceed to AI OCR fallback

        if path.lower().endswith(".docx"):
            try:
                doc = Document(path)
                return " ".join(p.text for p in doc.paragraphs)
            except Exception:
                print(f"⚠️ Skipping unreadable DOCX: {path}")
                return ""

        if path.lower().endswith(".xlsx"):
            try:
                df = pd.read_excel(path)
                return df.astype(str).head(10).to_string()
            except Exception:
                print(f"⚠️ Skipping unreadable XLSX: {path}")
                return ""

        if path.lower().endswith(".txt"):
            try:
                return open(path, errors="ignore").read()
            except Exception:
                return ""

        # AI Fallback for Images and Scanned PDFs
        if path.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
            return extract_text_from_attachment_ai(path)

    except Exception:
        print(f"⚠️ Failed to extract attachment: {path}")

    return ""


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
                        attachment_files.append(unique_fname)
                    except Exception as e:
                        print(f"⚠️ Failed to save attachment {fname}: {e}")
                        continue

                    # Extract text from attachment for content indexing
                    tmp_path = os.path.join(ATTACHMENTS_DIR, unique_fname)
                    try:
                        attachment_text += extract_attachment_text(tmp_path)
                    except Exception:
                        print(f"⚠️ Attachment text extraction failed: {fname}")

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
