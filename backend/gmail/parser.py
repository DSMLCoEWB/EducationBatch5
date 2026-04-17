import os
import base64
import hashlib
import json
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Dict, Any, List, Optional
from config import ATTACHMENTS_DIR
from core.logging import get_logger

logger = get_logger("gmail.parser")

def parse_gmail_message_raw(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parses raw RFC822 bytes into a structured dictionary.
    This is an optimized path that bypasses JSON decoding if we already have the raw payload.
    """
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    except Exception as e:
        logger.error(f"⚠️ Failed to parse raw EML bytes: {e}")
        return None

    sender = msg.get("From", "")
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    attachment_files = []

    raw_date = msg.get("Date")
    email_date = None
    try:
        if raw_date:
            email_date = parsedate_to_datetime(raw_date).date().isoformat()
    except Exception:
        email_date = None

    body = ""
    # MIME Walk for body and attachments
    try:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get_content_disposition()

                if content_type == "text/plain" and disposition != "attachment":
                    try:
                        content = part.get_content()
                        if isinstance(content, str):
                            body += content
                    except Exception:
                        pass

                if disposition == "attachment":
                    fname = part.get_filename()
                    payload = part.get_payload(decode=True)
                    if fname and payload:
                        unique_fname = _save_attachment(fname, payload)
                        if unique_fname:
                            attachment_files.append(unique_fname)
        else:
            try:
                content = msg.get_content()
                body = content if isinstance(content, str) else ""
            except Exception:
                body = ""
    except Exception as e:
        logger.error(f"⚠️ Error while processing MIME parts: {e}")

    return {
        "email_id": message_id,
        "parent_email_id": in_reply_to,
        "sender": sender,
        "subject": subject,
        "date": email_date,
        "content": f"{subject}\n{body}".strip(),
        "attachments": attachment_files
    }

def parse_gmail_message_json(msg_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses a Gmail 'full' format JSON response into our internal dictionary.
    Optimized to avoid re-fetching raw bytes if possible.
    """
    headers = {h["name"].lower(): h["value"] for h in msg_json.get("payload", {}).get("headers", [])}
    
    internal_id = msg_json.get("id")
    thread_id = msg_json.get("threadId")
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    raw_date = headers.get("date", "")
    message_id = headers.get("message-id", internal_id)
    in_reply_to = headers.get("in-reply-to", "")

    email_date = None
    if raw_date:
        try:
            email_date = parsedate_to_datetime(raw_date).date().isoformat()
        except Exception:
            pass

    # Basic content extraction from Parts
    body = _extract_body_from_payload(msg_json.get("payload", {}))
    
    # Attachment metadata (IDs, filenames)
    attachments = []
    _collect_attachments_metadata(msg_json.get("payload", {}), attachments)

    return {
        "email_id": message_id,
        "gmail_id": internal_id,
        "thread_id": thread_id,
        "parent_email_id": in_reply_to,
        "sender": sender,
        "subject": subject,
        "date": email_date,
        "content": f"{subject}\n{body}".strip(),
        "attachments_metadata": attachments, # Needs explicit download later
        "has_attachment": len(attachments) > 0
    }

def _save_attachment(filename: str, payload: bytes) -> Optional[str]:
    """Saves attachment bytes to disk and returns a unique safe filename."""
    try:
        if len(payload) > 5 * 1024 * 1024:
            logger.warning(f"⚠️ Skipping large attachment: {filename}")
            return None
        
        file_hash = hashlib.md5(payload).hexdigest()[:8]
        safe_fname = filename.replace(" ", "_").replace("/", "_")
        unique_fname = f"{file_hash}_{safe_fname}"
        path = os.path.join(ATTACHMENTS_DIR, unique_fname)
        
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(payload)
        return unique_fname
    except Exception as e:
        logger.error(f"⚠️ Failed to save attachment {filename}: {e}")
        return None

def _extract_body_from_payload(payload: Dict[str, Any]) -> str:
    """Recursively extracts text body from Gmail payload parts."""
    body = ""
    mime_type = payload.get("mimeType")
    data = payload.get("body", {}).get("data")

    if data and mime_type == "text/plain":
        try:
            body += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            pass
    
    if "parts" in payload:
        for part in payload["parts"]:
            body += _extract_body_from_payload(part)
    
    return body

def _collect_attachments_metadata(payload: Dict[str, Any], attachments: List[Dict[str, Any]]):
    """Recursively collects attachment information from Gmail payload parts."""
    if "parts" in payload:
        for part in payload["parts"]:
            _collect_attachments_metadata(part, attachments)
    
    filename = payload.get("filename")
    attachment_id = payload.get("body", {}).get("attachmentId")
    if filename and attachment_id:
        attachments.append({
            "filename": filename,
            "attachment_id": attachment_id,
            "mime_type": payload.get("mimeType"),
            "size": payload.get("body", {}).get("size")
        })
