import os
import time
from typing import List, Any, Optional
from google.genai import types

# --- ULTIMATE MODEL FALLBACK SEQUENCE (Best-to-Least Verified Free Tier) ---
# Ordered by Priority: 1. Latest Stable -> 2. Latest Previews -> 3. High Volume Fallbacks
ULTIMATE_FALLBACK_LIST = [
    # Primary: Latest Stable Production Model
    "gemini-flash-latest",           # Recommended for stability
    
    # Tier 1: Latest Reasoning (Gemini 3.x Family)
    "gemini-3.1-flash-lite-preview", # Most advanced small model (500 RPD)
    "gemini-3-flash-preview",        # Frontier performance (20 RPD)
    "gemini-2.5-flash-lite",         # High efficiency
    
    # Tier 3: Professional Design & Reasoning (Gemma 4 Family)
    "gemma-4-31b",                  # Professional design core (1,500 RPD)
    "gemma-4-26b",                  # 1,500 RPD
    
    # Tier 4: High Volume Safety Net (Gemma 3 Family)
    "gemma-3-27b",                  # 14,400 RPD (Extreme volume)
    "gemma-3-12b",                  # 14,400 RPD
    "gemma-3-4b",                   # 14,400 RPD
    "gemma-3-2b",                   # 14,400 RPD
    "gemma-3-1b",                   # 14,400 RPD
    
    # Tier 5: Specialized Reasoning
    "gemini-robotics-er-1.5-preview" # Specialized (20 RPD)
]

def generate_content_with_fallback(
    client, 
    contents: Any, 
    config: Optional[types.GenerateContentConfig] = None, 
    model_list: List[str] = ULTIMATE_FALLBACK_LIST,
    label: str = "AI Service"
):
    """
    Executes a generate_content call with automated fallback through a list of models.
    Handles 429 (Rate Limit) and 404 (Not Found/Deprecated) errors.
    """
    if not client:
        print(f"[{label}]: Error - No Gemini client initialized.")
        return None

    last_error = None
    for model_name in model_list:
        try:
            print(f"[{label}]: Attempting generation with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
            
            # If we got here, it succeeded
            if response and (response.text or (hasattr(response, 'candidates') and response.candidates)):
                print(f"[{label}]: Success with {model_name}")
                return response
            
            print(f"[{label}]: Empty response from {model_name}, moving to next...")
            
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            
            if "429" in err_msg or "rate limit" in err_msg:
                print(f"[{label}]: Rate limit hit on {model_name}. Falling back...")
                continue
            elif "404" in err_msg or "not found" in err_msg:
                print(f"[{label}]: Model {model_name} not available or deprecated. Falling back...")
                continue
            else:
                # For other errors (auth, network), we log but try one more just in case
                print(f"[{label}]: Unexpected error with {model_name}: {e}")
                continue

    print(f"[{label}]: FATAL - All models failed in fallback loop. Last error: {last_error}")
    return None
