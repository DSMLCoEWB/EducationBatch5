import json
import hashlib
import threading
import httplib2
from pathlib import Path

def get_hardened_http(timeout: int = 60):
    """
    Creates an httplib2.Http instance with system proxy discovery disabled
    and a relaxed timeout for stable SSL handshakes on constrained networks.
    """
    # Explicitly set proxy_info=None to bypass the httplib2 'WRONG_VERSION_NUMBER' bug
    return httplib2.Http(proxy_info=None, timeout=timeout)
from typing import Any, Optional
from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
import google_auth_httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import (
    GOOGLE_OAUTH_TOKENS_DIR, GOOGLE_OAUTH_ENCRYPTION_KEY, 
    GOOGLE_OAUTH_SCOPES, SYNC_ENABLED
)
from core.gmail_context import GMAIL_SERVICE_MAP, GMAIL_SERVICE_LOCK

# Proactive Cache Reset: Wipe stale connections on reload to ensure hardened transport is used.
with GMAIL_SERVICE_LOCK:
    GMAIL_SERVICE_MAP.clear()
from utils.rate_limiter import GMAIL_RATE_LIMITER
from core.logging import get_logger

logger = get_logger("gmail.client")

def _get_google_fernet() -> Fernet:
    """Provides the encryption engine for local token storage."""
    return Fernet(GOOGLE_OAUTH_ENCRYPTION_KEY.encode("utf-8"))

def _gmail_token_filename(user_email: str) -> str:
    """Generates a secure, deterministic filename for storing user credentials."""
    hashed = hashlib.sha256(user_email.strip().lower().encode("utf-8")).hexdigest()
    return f"{hashed}.enc"

def _token_path_for_user(user_email: str) -> Path:
    """Resolves the absolute path to a user's encrypted Gmail token."""
    GOOGLE_OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return GOOGLE_OAUTH_TOKENS_DIR / _gmail_token_filename(user_email)

def save_google_credentials(user_email: str, creds: Credentials) -> None:
    """Encrypts and persists Google OAuth credentials to the local filesystem."""
    token_path = _token_path_for_user(user_email)
    encrypted_token = _get_google_fernet().encrypt(creds.to_json().encode("utf-8"))
    with open(token_path, "wb") as f:
        f.write(encrypted_token)

def load_google_credentials(user_email: str) -> Optional[Credentials]:
    """Retrieves and decrypts Google OAuth credentials, performing auto-refresh if needed."""
    token_path = _token_path_for_user(user_email)
    if not token_path.exists():
        return None

    try:
        encrypted_token = token_path.read_bytes()
        token_json = _get_google_fernet().decrypt(encrypted_token).decode("utf-8")
        token_data = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(token_data, scopes=GOOGLE_OAUTH_SCOPES)
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ [Auth] Failed to decrypt/load credentials for {user_email}: {e}")
        return None

    # Handle automatic token refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_google_credentials(user_email, creds)
        except Exception as e:
            logger.error(f"❌ [Auth] Failed to refresh credentials for {user_email}: {e}")
            return None

    return creds if creds and creds.valid else None

def get_gmail_api_service(user_email: str) -> Any:
    """
    Returns a thread-safe, rate-limited Gmail API service instance.
    Implements a Service Singleton Cache per user.
    """
    if not SYNC_ENABLED:
        logger.warning(f"🚫 Gmail sync is globally disabled. Blocking request for {user_email}")
        return None

    # 1. Atomic Check of Singleton Cache
    with GMAIL_SERVICE_LOCK:
        cached_service = GMAIL_SERVICE_MAP.get(user_email)
        if cached_service:
            return cached_service
    
    # 2. Load and Validate Credentials
    creds = load_google_credentials(user_email)
    if not creds or not creds.valid:
        with GMAIL_SERVICE_LOCK:
            GMAIL_SERVICE_MAP.pop(user_email, None)
        return None
    
    try:
        # Refresh logic is already handled in load_google_credentials, 
        # but we double check for safety before building service.
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            save_google_credentials(user_email, creds)
            with GMAIL_SERVICE_LOCK:
                GMAIL_SERVICE_MAP.pop(user_email, None)

        # 3. Double-check cache after credential validation to avoid redundant builds
        with GMAIL_SERVICE_LOCK:
            if user_email in GMAIL_SERVICE_MAP:
                return GMAIL_SERVICE_MAP[user_email]

        # 4. Built Service with Proactive Rate Limiting
        GMAIL_RATE_LIMITER.wait()
        auth_http = google_auth_httplib2.AuthorizedHttp(creds, http=get_hardened_http())
        service = build("gmail", "v1", http=auth_http, cache_discovery=False)
        
        with GMAIL_SERVICE_LOCK:
            GMAIL_SERVICE_MAP[user_email] = service
        return service

    except Exception as e:
        logger.error(f"❌ [Gmail API] Failed to initialize service for {user_email}: {e}")
        with GMAIL_SERVICE_LOCK:
            GMAIL_SERVICE_MAP.pop(user_email, None)
        return None

def get_user_display_name(user_email: str):
    """
    Retrieves the user's display name and official email.
    Only returns a display name if it is officially configured in Gmail 'Send As' settings
    to ensure recipients don't see 'unauthenticated' security warnings.
    """
    service = get_gmail_api_service(user_email)
    if not service:
        return "", user_email
    
    try:
        # 1. Get official profile email for consistency
        profile = service.users().getProfile(userId='me').execute()
        official_email = profile.get('emailAddress', user_email)
        
        # 2. Get Gmail 'Send As' settings (The only source for 'Authenticated' names)
        results = service.users().settings().sendAs().list(userId='me').execute()
        send_as = results.get('sendAs', [])
        official_email_lower = official_email.lower()
        
        # Priority 1: Match the specific email
        for alias in send_as:
            if alias.get('sendAsEmail', '').lower() == official_email_lower and alias.get('displayName'):
                return alias.get('displayName'), official_email
                
        # Priority 2: Use the primary alias name
        for alias in send_as:
            if alias.get('isPrimary') and alias.get('displayName'):
                return alias.get('displayName'), official_email

        # If no verified display name is found, return empty string for the name.
        # This prevents the 'unauthenticated' warning by letting Gmail use its own default.
        return "", official_email

    except Exception as e:
        logger.error(f"❌ [Gmail API] Error in get_user_display_name for {user_email}: {e}")
        return "", user_email
