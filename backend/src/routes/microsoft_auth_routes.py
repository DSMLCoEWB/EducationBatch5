import secrets
import urllib.parse
import requests
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

from config import (
    OAUTH_COOKIE_SECURE, OAUTH_SUCCESS_REDIRECT_URL,
    MICROSOFT_OAUTH_CLIENT_ID, MICROSOFT_OAUTH_CLIENT_SECRET,
    MICROSOFT_OAUTH_REDIRECT_URI, MICROSOFT_OAUTH_SCOPES
)
from core.auth import (
    save_microsoft_credentials,
    create_session_token, decode_session_token
)
from core.context import worker_manager
from core.coordination import run_background_sync_loop
from db.session import get_db_conn

router = APIRouter(prefix="/auth/microsoft", tags=["Authentication"])

class AuthStatus(BaseModel):
    connected: bool
    email: Optional[str] = None
    provider: Optional[str] = None

@router.get("/start")
def start_auth():
    state = secrets.token_urlsafe(16)
    
    # Construct Microsoft authorization URL
    params = {
        "client_id": MICROSOFT_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": MICROSOFT_OAUTH_REDIRECT_URI,
        "response_mode": "query",
        "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
        "state": state,
        "prompt": "select_account"
    }
    
    auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="microsoft_oauth_state",
        value=state,
        httponly=True,
        secure=OAUTH_COOKIE_SECURE,
        samesite="lax"
    )
    return response

@router.get("/callback")
def auth_callback(request: Request, code: str, state: str):
    stored_state = request.cookies.get("microsoft_oauth_state")
    
    if state != stored_state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch.")
        
    try:
        # Exchange code for token
        token_data = {
            "client_id": MICROSOFT_OAUTH_CLIENT_ID,
            "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
            "code": code,
            "redirect_uri": MICROSOFT_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
            "client_secret": MICROSOFT_OAUTH_CLIENT_SECRET,
        }
        
        token_res = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data=token_data
        , timeout=(5, 30))
        token_res.raise_for_status()
        tokens = token_res.json()
        
        import time
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 300
        
        # Get User Profile to get email
        user_res = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        , timeout=(5, 30))
        user_res.raise_for_status()
        user_info = user_res.json()
        
        raw_email = user_info.get('mail') or user_info.get('userPrincipalName')
        if not raw_email:
            raise HTTPException(status_code=400, detail="Could not retrieve email from Microsoft.")
        user_email = raw_email.lower()
        
        # Dynamic DNS Domain Enforcement
        from utils.dns_utils import detect_mail_provider
        provider = detect_mail_provider(user_email)
        
        if provider == "google":
            redirect_url = f"{OAUTH_SUCCESS_REDIRECT_URL or '/'}?error=invalid_provider_google"
            return RedirectResponse(url=redirect_url)
        
        # Save tokens
        save_microsoft_credentials(user_email, tokens)
        
        # Set auth provider to microsoft in DB
        with get_db_conn(tenant_email=user_email) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_sync_history (user_email, auth_provider)
                VALUES (?, 'microsoft')
                ON CONFLICT(user_email) DO UPDATE SET auth_provider = 'microsoft'
            """, (user_email,))
            conn.commit()
            
        # Start worker
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
            max_age=7 * 24 * 60 * 60
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth failed: {str(e)}")

@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request):
    """
    Returns the current authentication status for Microsoft.
    (Note: the frontend usually just calls /auth/google/status or a generic /auth/status. 
    We will update the frontend to use a unified status or we can just rely on the existing status endpoint since it just checks the session cookie).
    """
    token = request.cookies.get("session_token")
    user_email = decode_session_token(token)
    
    if user_email:
        # Check provider
        with get_db_conn(tenant_email=user_email) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT auth_provider FROM user_sync_history WHERE user_email = ?", (user_email,))
            row = cursor.fetchone()
            provider = row[0] if row else "google"
        return AuthStatus(connected=True, email=user_email, provider=provider)
        
    return AuthStatus(connected=False)
