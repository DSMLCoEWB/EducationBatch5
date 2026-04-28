from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Dict, Any
import base64
from core.dependencies import get_authenticated_user
from gmail.client import get_gmail_api_service, get_hardened_http, load_google_credentials
from core.logging import get_logger
import google_auth_httplib2
from googleapiclient.discovery import build

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
    from gmail.client import get_gmail_api_service, get_user_display_name
    from email.mime.text import MIMEText
    from email.utils import formataddr
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    display_name, official_email = get_user_display_name(user_email)
    message = MIMEText(payload.body)
    message['to'] = payload.to_email
    if display_name:
        message['From'] = formataddr((display_name, official_email))
    message['subject'] = payload.subject
    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        sent_msg = service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
        return {"id": sent_msg['id'], "status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profile")
def get_profile_info(user_email: str = Depends(get_authenticated_user)):
    """Returns Gmail sendAs name vs Google Profile name for account setup."""
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    try:
        # 1. Fetch Gmail 'Send As' name
        results = service.users().settings().sendAs().list(userId='me').execute()
        send_as = results.get('sendAs', [])
        primary_name = next((a.get('displayName', "") for a in send_as if a.get('isPrimary')), "")
        
        # 2. Fetch Google Account Profile name
        creds = load_google_credentials(user_email)
        profile_name = ""
        if creds:
            auth_http = google_auth_httplib2.AuthorizedHttp(creds, http=get_hardened_http())
            oauth2_service = build("oauth2", "v2", http=auth_http, cache_discovery=False)
            user_info = oauth2_service.userinfo().get().execute()
            profile_name = user_info.get("name", "")
            
        return {
            "email": user_email,
            "displayName": primary_name,
            "profileName": profile_name,
            "needsSetup": not primary_name and bool(profile_name)
        }
    except Exception as e:
        logger.error(f"Error fetching profile info: {e}")
        return {"email": user_email, "displayName": "", "profileName": "", "needsSetup": False}

@router.post("/update-display-name")
def update_display_name(payload: Dict[str, str], user_email: str = Depends(get_authenticated_user)):
    """Updates the Gmail 'Send As' name to match the requested name."""
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    new_name = payload.get("name")
    if not new_name:
        raise HTTPException(status_code=400, detail="Name is required")
        
    try:
        results = service.users().settings().sendAs().list(userId='me').execute()
        send_as = results.get('sendAs', [])
        primary_email = next((a.get('sendAsEmail') for a in send_as if a.get('isPrimary')), user_email)
        
        service.users().settings().sendAs().patch(
            userId='me', 
            sendAsEmail=primary_email, 
            body={'displayName': new_name}
        ).execute()
        
        return {"success": True, "updatedName": new_name}
    except Exception as e:
        logger.error(f"Error updating display name: {e}")
        raise HTTPException(status_code=500, detail=str(e))

