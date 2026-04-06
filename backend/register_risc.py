import json
import time
import jwt
import requests
import sys
import os
from pathlib import Path

# This script helps you register your application's Webhook with Google RISC
# You need a Service Account JSON key with 'RISC Configuration Admin' role.

def make_bearer_token(credentials_file):
    """Generate a signed JWT to authorize RISC API calls."""
    with open(credentials_file) as service_json:
        service_account = json.load(service_json)
        issuer = service_account['client_email']
        subject = service_account['client_email']
        private_key_id = service_account['private_key_id']
        private_key = service_account['private_key']

    issued_at = int(time.time())
    expires_at = issued_at + 3600
    payload = {
        'iss': issuer,
        'sub': subject,
        'aud': 'https://risc.googleapis.com/google.identity.risc.v1beta.RiscManagementService',
        'iat': issued_at,
        'exp': expires_at
    }
    encoded = jwt.encode(payload, private_key, algorithm='RS256',
                         headers={'kid': private_key_id})
    return encoded

def configure_event_stream(auth_token, receiver_endpoint, events_requested):
    """Call Google RISC API to register the webhook URL."""
    stream_update_endpoint = 'https://risc.googleapis.com/v1beta/stream:update'
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    stream_cfg = {
        'delivery': {
            'delivery_method': 'https://schemas.openid.net/secevent/risc/delivery-method/push',
            'url': receiver_endpoint
        },
        'events_requested': events_requested
    }
    print(f"Registering endpoint: {receiver_endpoint}...")
    response = requests.post(stream_update_endpoint, json=stream_cfg, headers=headers)
    
    if response.status_code == 200:
        print("✅ SUCCESS: RISC Event Stream configured successfully.")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ ERROR {response.status_code}: {response.text}")

if __name__ == "__main__":
    # CONFIGURATION
    # Ensure we look in the same folder as this script for the credentials
    script_dir = Path(__file__).parent
    CREDENTIALS_PATH = script_dir / "service-account-credentials.json"
    # Replace this with your actual public HTTPS URL (e.g., https://your-app.com/risc/webhook)
    # Note: Google requires HTTPS for the receiver endpoint.
    WEBHOOK_URL = os.getenv("RISC_WEBHOOK_URL", "https://your-domain.com/risc/webhook")

    if not Path(CREDENTIALS_PATH).exists():
        print(f"⚠️ Error: {CREDENTIALS_PATH} not found.")
        print("Please place your Service Account JSON key in the 'backend' folder.")
        sys.exit(1)

    try:
        token = make_bearer_token(CREDENTIALS_PATH)
        
        # Subscribe to common security events
        events = [
            'https://schemas.openid.net/secevent/risc/event-type/account-disabled',
            'https://schemas.openid.net/secevent/risc/event-type/sessions-revoked',
            'https://schemas.openid.net/secevent/oauth/event-type/tokens-revoked'
        ]
        
        configure_event_stream(token, WEBHOOK_URL, events)
        
    except Exception as e:
        print(f"💥 An unexpected error occurred: {e}")
