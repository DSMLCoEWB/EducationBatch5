from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

from config import (
    GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI, GOOGLE_OAUTH_SCOPES,
    OAUTH_COOKIE_SECURE, OAUTH_SUCCESS_REDIRECT_URL
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
        secure=OAUTH_COOKIE_SECURE,
        samesite="lax"
    )
    if hasattr(flow, "code_verifier"):
        response.set_cookie(
            key="google_oauth_verifier",
            value=flow.code_verifier,
            httponly=True,
            secure=OAUTH_COOKIE_SECURE,
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
        raw_email = user_info['email']
        user_email = raw_email.lower()
        
        # Dynamic DNS Domain Enforcement
        from utils.dns_utils import detect_mail_provider
        provider = detect_mail_provider(user_email)
        
        if provider == "microsoft":
            redirect_url = f"{OAUTH_SUCCESS_REDIRECT_URL or '/'}?error=invalid_provider_microsoft"
            return RedirectResponse(url=redirect_url)
        
        save_google_credentials(user_email, flow.credentials)
        
        # Set auth provider to google in DB
        from db.session import get_db_conn
        with get_db_conn(tenant_email=user_email) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_sync_history (user_email, auth_provider)
                VALUES (?, 'google')
                ON CONFLICT(user_email) DO UPDATE SET auth_provider = 'google'
            """, (user_email,))
            conn.commit()
        
        # BOOTSTRAP: Start the Stealth Sync worker for the user
        if not worker_manager.is_sync_running(user_email):
            worker_manager.start_sync_worker(user_email, run_background_sync_loop)
        
        from db.repository import unrevoke_user_session
        unrevoke_user_session(user_email)
        
        token = create_session_token(user_email)
        # Redirect the user back to the frontend application
        redirect_url = OAUTH_SUCCESS_REDIRECT_URL or "/"
        response = RedirectResponse(url=redirect_url)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=OAUTH_COOKIE_SECURE,
            samesite="lax",
            max_age=7 * 24 * 60 * 60 # 7 Days memory
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
        from db.repository import revoke_user_session
        revoke_user_session(user_email, "User Logged Out")
        
    response.delete_cookie("session_token")
    return {"status": "logged_out"}
