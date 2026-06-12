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
        # --- RESOURCE LOCK ---
        # Claim the hardware for human interaction to prevent GPU collisions and CPU offloading slowdowns
        from core.resource_manager import AI_RESOURCE_MANAGER
        AI_RESOURCE_MANAGER.acquire_high_priority()

        reply_bundle = generate_suggested_reply_with_evidence(
            email_content=request.email_content,
            user_email=user_email,
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

