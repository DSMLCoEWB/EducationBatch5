from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from core.dependencies import get_authenticated_user
from services.rag_service import generate_suggested_reply_with_evidence
from services.ocr_service import extract_text_from_attachment_ai
from services.agent_service import get_chatbot_response
from db.repository import update_email_attachment_content

router = APIRouter(tags=["Intelligence"])

# --- MODELS ---

class GenerateReplyRequest(BaseModel):
    email_content: str
    email_subject: str = ""
    sender: str = ""
    category: str = ""
    attachment_content: str = ""
    history: List[Dict[str, Any]] = []
    email_id: str = ""

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    reply: str

# --- ENDPOINTS ---

@router.post("/generate-reply")
def get_suggested_reply(
    request: GenerateReplyRequest,
    user_email: str = Depends(get_authenticated_user)
):
    """Generates an AI-powered suggested reply based on policy context."""
    try:
        reply_bundle = generate_suggested_reply_with_evidence(
            email_content=request.email_content,
            email_subject=request.email_subject,
            sender=request.sender,
            category=request.category,
            attachment_content=request.attachment_content,
            history=request.history,
            email_id=request.email_id
        )
        return reply_bundle
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat", response_model=ChatResponse)
def chatbot_chat(
    request: ChatRequest,
    user_email: str = Depends(get_authenticated_user)
):
    """Conversational AI agent for executive analytics and policy queries."""
    try:
        reply = get_chatbot_response(
            user_message=request.message,
            user_email=user_email,
            session_id=request.session_id
        )
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reprocess-attachment")
def reprocess_attachment(
    email_id: str,
    filename: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Manually triggers OCR re-processing for a specific attachment."""
    from config import ATTACHMENTS_DIR
    import os
    path = os.path.join(ATTACHMENTS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Attachment file not found.")
        
    text = extract_text_from_attachment_ai(path)
    if text:
        update_email_attachment_content(user_email, email_id, text, filename)
        return {"status": "success", "extracted_text": text}
    return {"status": "failed"}
