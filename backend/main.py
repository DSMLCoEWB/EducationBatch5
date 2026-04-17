import os
import uvicorn
from app import app
from db.session import init_db
from core.logging import get_logger

logger = get_logger("bridge")

# --- COMPATIBILITY BRIDGE ---
# This file is kept to ensure that existing deployment scripts and 
# environments referencing 'main:app' continue to function without modification.

if __name__ == "__main__":
    init_db()  # Ensure DB is initialized
    
    # Optional logic for reclassification/migration if needed on startup
    # (Move to dedicated migration scripts in production)
    
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🔗 Modularized bridge starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
