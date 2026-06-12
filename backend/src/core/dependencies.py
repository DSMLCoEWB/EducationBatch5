from fastapi import Request, HTTPException
from core.auth import decode_session_token
from config import OAUTH_TOKENS_DIR
from db.repository import is_user_revoked
import hashlib

def get_authenticated_user(request: Request) -> str:
    """Dependency to get the current user from session token."""
    token = request.cookies.get("session_token")
    user_email = decode_session_token(token)
    
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated.")
        
    if is_user_revoked(user_email):
        raise HTTPException(status_code=401, detail="Session revoked. Please log in again.")
        
    # Check if user has active credentials
    user_hash = hashlib.sha256(user_email.encode()).hexdigest()
    google_path = OAUTH_TOKENS_DIR / f"{user_hash}.enc"
    ms_path = OAUTH_TOKENS_DIR / f"ms_{user_hash}.enc"
    
    if not google_path.exists() and not ms_path.exists():
        raise HTTPException(status_code=401, detail="Account credentials missing. Please reconnect.")
        
    return user_email
