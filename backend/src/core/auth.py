import os
import json
import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from cryptography.fernet import Fernet

from config import (
    GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI, GOOGLE_OAUTH_SCOPES,
    OAUTH_TOKENS_DIR, OAUTH_ENCRYPTION_KEY,
    APP_SESSION_SECRET
)
from core.logging import get_logger

logger = get_logger("core.auth")

# --- OAUTH HELPERS ---

def get_fernet() -> Fernet:
    if not OAUTH_ENCRYPTION_KEY:
         raise ValueError("OAUTH_ENCRYPTION_KEY not set in environment.")
    return Fernet(OAUTH_ENCRYPTION_KEY.encode("utf-8"))

def build_google_flow(state: Optional[str] = None) -> Flow:
    client_config = {
        "web": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_OAUTH_REDIRECT_URI],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_OAUTH_SCOPES,
        state=state
    )
    flow.redirect_uri = GOOGLE_OAUTH_REDIRECT_URI
    return flow

def save_google_credentials(user_email: str, creds: Credentials):
    OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    user_hash = hashlib.sha256(user_email.lower().encode("utf-8")).hexdigest()
    token_path = OAUTH_TOKENS_DIR / f"{user_hash}.enc"
    
    creds_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    
    encrypted = get_fernet().encrypt(json.dumps(creds_data).encode("utf-8"))
    with open(token_path, "wb") as f:
        f.write(encrypted)
    logger.info(f"💾 Credentials saved for {user_email[:12]}...")

def load_google_credentials(user_email: str) -> Optional[Credentials]:
    user_hash = hashlib.sha256(user_email.lower().encode("utf-8")).hexdigest()
    token_path = OAUTH_TOKENS_DIR / f"{user_hash}.enc"
    if not token_path.exists():
        return None
        
    try:
        with open(token_path, "rb") as f:
            encrypted = f.read()
        decrypted = get_fernet().decrypt(encrypted).decode("utf-8")
        return Credentials.from_authorized_user_info(json.loads(decrypted))
    except Exception as e:
        logger.error(f"❌ Failed to load credentials for {user_email}: {e}")
        return None

def save_microsoft_credentials(user_email: str, token_data: dict):
    OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    user_hash = hashlib.sha256(user_email.lower().encode("utf-8")).hexdigest()
    # We prefix with ms_ to distinguish
    token_path = OAUTH_TOKENS_DIR / f"ms_{user_hash}.enc"
    
    encrypted = get_fernet().encrypt(json.dumps(token_data).encode("utf-8"))
    with open(token_path, "wb") as f:
        f.write(encrypted)
    logger.info(f"💾 Microsoft credentials saved for {user_email[:12]}...")

def load_microsoft_credentials(user_email: str) -> Optional[dict]:
    user_hash = hashlib.sha256(user_email.lower().encode("utf-8")).hexdigest()
    token_path = OAUTH_TOKENS_DIR / f"ms_{user_hash}.enc"
    if not token_path.exists():
        return None
        
    try:
        with open(token_path, "rb") as f:
            encrypted = f.read()
        decrypted = get_fernet().decrypt(encrypted).decode("utf-8")
        return json.loads(decrypted)
    except Exception as e:
        logger.error(f"❌ Failed to load Microsoft credentials for {user_email}: {e}")
        return None

def refresh_microsoft_token(user_email: str, tokens: dict) -> Optional[dict]:
    import requests
    import time
    from config import MICROSOFT_OAUTH_CLIENT_ID, MICROSOFT_OAUTH_CLIENT_SECRET
    
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
        
    data = {
        "client_id": MICROSOFT_OAUTH_CLIENT_ID,
        "client_secret": MICROSOFT_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    
    try:
        res = requests.post("https://login.microsoftonline.com/common/oauth2/v2.0/token", data=data, timeout=(5, 30))
        res.raise_for_status()
        new_tokens = res.json()
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600) - 300
        save_microsoft_credentials(user_email, new_tokens)
        return new_tokens
    except Exception as e:
        logger.error(f"❌ Failed to refresh MS token for {user_email}: {e}")
        return None

def get_valid_microsoft_token(user_email: str) -> Optional[str]:
    import time
    tokens = load_microsoft_credentials(user_email)
    if not tokens:
        return None
        
    expires_at = tokens.get("expires_at")
    
    # If expired or missing expiration (legacy), try refreshing
    if not expires_at or time.time() >= expires_at:
        tokens = refresh_microsoft_token(user_email, tokens)
        if not tokens:
            return None
            
    return tokens.get("access_token")

# --- SESSION HELPERS ---

def create_session_token(user_email: str) -> str:
    payload = {
        "sub": user_email,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, APP_SESSION_SECRET, algorithm="HS256")

def decode_session_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, APP_SESSION_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        logger.warning("🕒 Session token expired.")
        return None
    except Exception:
        return None
