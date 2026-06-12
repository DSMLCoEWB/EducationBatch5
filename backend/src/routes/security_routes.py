from fastapi import APIRouter, Request, HTTPException, Response
import os
import json
import jwt
import requests
from db.repository import revoke_user_session

router = APIRouter(prefix="/security", tags=["Security"])

@router.post("/risc/webhook")
async def risc_webhook(request: Request):
    """
    Handle Google Cross-Account Protection (RISC) security event notifications.
    """
    try:
        body = await request.body()
        token = body.decode("utf-8")
        
        # 1. Get Google RISC configuration
        risc_config = requests.get('https://accounts.google.com/.well-known/risc-configuration', timeout=(5, 30)).json()
        google_certs = requests.get(risc_config['jwks_uri'], timeout=(5, 30)).json()
        
        # 2. Decode & Validate JWT
        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        public_key = None
        for key in google_certs['keys']:
            if key['kid'] == kid:
                from jwt.algorithms import RSAAlgorithm
                public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                break
        
        if not public_key:
            raise Exception("Public key missing")

        decoded = jwt.decode(
            token, public_key, algorithms=['RS256'],
            audience=client_id, issuer=risc_config['issuer'],
            options={"verify_exp": False}
        )
        
        events = decoded.get("events", {})
        for etype, edata in events.items():
            subj = edata.get("subject", {})
            email = subj.get("email") or subj.get("sub")
            if email and ("account-disabled" in etype or "sessions-revoked" in etype):
                revoke_user_session(email, f"RISC Event: {etype}")
        
        return Response(status_code=202)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid token")
