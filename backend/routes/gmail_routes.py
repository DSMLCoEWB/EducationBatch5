from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
import base64
from core.dependencies import get_authenticated_user
from gmail.client import get_gmail_api_service
from core.logging import get_logger

logger = get_logger("routes.gmail")
router = APIRouter(prefix="/api/gmail", tags=["Gmail"])

@router.get("/inline/{gmail_id}/{cid}")
def get_inline_attachment(gmail_id: str, cid: str, user_email: str = Depends(get_authenticated_user)):
    """Proxy inline images securely through our backend to avoid CORS/Auth issues."""
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401, detail="Gmail login required")
        
    try:
        msg = service.users().messages().get(userId='me', id=gmail_id).execute()
        
        def find_part_by_cid(parts, target_cid):
            for part in parts:
                if part.get("headers"):
                    headers = {h["name"].lower(): h["value"] for h in part["headers"]}
                    if "content-id" in headers and (target_cid in headers["content-id"]):
                        return part
                if "parts" in part:
                    found = find_part_by_cid(part["parts"], target_cid)
                    if found: return found
            return None
            
        target_part = None
        if "payload" in msg:
            if "parts" in msg["payload"]:
                target_part = find_part_by_cid(msg["payload"]["parts"], cid)
                
        if not target_part:
            raise HTTPException(status_code=404, detail="Attachment not found")
            
        attachment_id = target_part.get("body", {}).get("attachmentId")
        if not attachment_id:
             if target_part.get("body", {}).get("data"):
                 data = base64.urlsafe_b64decode(target_part["body"]["data"])
                 return Response(content=data, media_type=target_part.get("mimeType", "image/jpeg"))
             raise HTTPException(status_code=404, detail="Content data not found")
             
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=gmail_id, id=attachment_id
        ).execute()
        
        data = base64.urlsafe_b64decode(attachment["data"])
        return Response(content=data, media_type=target_part.get("mimeType", "image/jpeg"))
        
    except Exception as e:
        logger.error(f"Error serving inline image {cid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ComposeRequest(BaseModel):
    to_email: str
    subject: str
    body: str

@router.post("/compose")
def compose_email(payload: ComposeRequest, user_email: str = Depends(get_authenticated_user)):
    """Composes and sends a new Gmail message."""
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    from email.mime.text import MIMEText
    message = MIMEText(payload.body)
    message['to'] = payload.to_email
    message['subject'] = payload.subject
    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        sent_msg = service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
        return {"id": sent_msg['id'], "status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
