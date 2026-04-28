import os
import time
from core.logging import get_logger
from config import ULTIMATE_FALLBACK_LIST, VISION_FALLBACK_LIST

logger = get_logger("ai_utils")

def generate_content_with_fallback(client, contents, model_list, label="AI-Task", **kwargs):
    """
    Robust wrapper that tries multiple models in sequence to handle rate limits or failures.
    """
    if not client or not model_list:
        return None
        
    for model_name in model_list:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                **kwargs
            )
            if response:
                return response
        except Exception as e:
            # Check for common rate limit or service errors
            err_msg = str(e).lower()
            if "429" in err_msg or "quota" in err_msg:
                logger.warning(f"🕒 [{label}] Model {model_name} rate limited. Trying next...")
            else:
                logger.warning(f"⚠️ [{label}] Model {model_name} failed: {e}")
            continue
            
    logger.error(f"❌ [{label}] All models in fallback list failed.")
    return None
