from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

from config import (
    GOOGLE_OAUTH_COOKIE_SECURE, GOOGLE_OAUTH_SUCCESS_REDIRECT_URL
)
from core.auth import (
    build_google_flow, save_google_credentials, 
    create_session_token, decode_session_token
)
from core.context import worker_manager
from core.coordination import run_background_sync_loop

router = APIRouter(prefix="/auth/google", tags=["Authentication"])

class AuthStatus(BaseModel):
    connected: bool
    email: Optional[str] = None

@router.get("/start")
def start_auth():
    flow = build_google_flow()
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="google_oauth_state",
        value=state,
        httponly=True,
        secure=GOOGLE_OAUTH_COOKIE_SECURE,
        samesite="lax"
    )
    if hasattr(flow, "code_verifier"):
        response.set_cookie(
            key="google_oauth_verifier",
            value=flow.code_verifier,
            httponly=True,
            secure=GOOGLE_OAUTH_COOKIE_SECURE,
            samesite="lax"
        )
    return response

@router.get("/callback")
def auth_callback(request: Request, code: str, state: str):
    stored_state = request.cookies.get("google_oauth_state")
    code_verifier = request.cookies.get("google_oauth_verifier")
    
    if state != stored_state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch.")
        
    try:
        flow = build_google_flow(state=state)
        flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=flow.credentials)
        user_info = service.userinfo().get().execute()
        user_email = user_info['email']
        
        save_google_credentials(user_email, flow.credentials)
        
        # BOOTSTRAP: Start the Stealth Sync worker for the user
        if not worker_manager.is_sync_running(user_email):
            worker_manager.start_sync_worker(user_email, run_background_sync_loop)
        
        token = create_session_token(user_email)
        # Production Handshake: Redirect back to the React app, not the backend root
        redirect_url = GOOGLE_OAUTH_SUCCESS_REDIRECT_URL or "http://localhost:3000"
        response = RedirectResponse(url=redirect_url)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=GOOGLE_OAUTH_COOKIE_SECURE,
            samesite="lax"
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth failed: {str(e)}")

@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request):
    """
    Returns the current authentication status.
    [SAFETY]: Auto-restart of sync worker is REMOVED to prevent bot-like heartbeats.
    The worker now only starts during explicit login or manual trigger.
    """
    token = request.cookies.get("session_token")
    user_email = decode_session_token(token)
    return AuthStatus(connected=bool(user_email), email=user_email)

@router.post("/logout")
def auth_logout(response: Response, request: Request):
    token = request.cookies.get("session_token")
    user_email = decode_session_token(token)
    if user_email:
        worker_manager.stop_sync_worker(user_email)
        
    response.delete_cookie("session_token")
    return {"status": "logged_out"}
