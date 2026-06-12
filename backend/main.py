import os
import sys
from pathlib import Path

# Inject src directory into PYTHONPATH
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import uvicorn
from app import app
from core.logging import get_logger

logger = get_logger("bridge")

# --- COMPATIBILITY BRIDGE ---
# This file is kept to ensure that existing deployment scripts and 
# environments referencing 'main:app' continue to function without modification.

if __name__ == "__main__":
    
    # Optional logic for reclassification/migration if needed on startup
    # (Move to dedicated migration scripts in production)
    
    port = int(os.getenv("PORT", "8000"))
    app_env = os.getenv("APP_ENV", "development").lower()
    is_dev = app_env in ["dev", "development"]
    
    logger.info(f"🔗 Modularized bridge starting on port {port} (Dev-Reload: {is_dev})...")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=is_dev)
