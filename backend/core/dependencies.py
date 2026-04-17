from fastapi import Request, HTTPException
from core.auth import decode_session_token
from config import GOOGLE_OAUTH_TOKENS_DIR
import hashlib

def get_authenticated_user(request: Request) -> str:
    """Dependency to get the current user from session token."""
    token = request.cookies.get("session_token")
    user_email = decode_session_token(token)
    
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated.")
        
    # Check if user has active credentials
    user_hash = hashlib.sha256(user_email.encode()).hexdigest()
    token_path = GOOGLE_OAUTH_TOKENS_DIR / f"{user_hash}.enc"
    if not token_path.exists():
        raise HTTPException(status_code=401, detail="Gmail credentials missing. Please reconnect.")
        
    return user_email
