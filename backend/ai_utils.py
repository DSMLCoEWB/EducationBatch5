import os
import time
from typing import List, Any, Optional
from google.genai import types

# --- ULTIMATE MODEL FALLBACK SEQUENCE (Best-to-Least Verified Free Tier) ---
# Ordered by Priority: 1. Latest Stable -> 2. Latest Previews -> 3. High Volume Fallbacks
ULTIMATE_FALLBACK_LIST = [
    # Primary: High Quota Free Model (500 RPD)
    "models/gemini-3.1-flash-lite-preview", 
    
    # Tier 1: Latest Stable Production Model
    "models/gemini-flash-latest",
    
    # Tier 2: Latest Previews & Reasoning
    "models/gemini-3-flash-preview", 
    "models/gemini-2.5-flash-lite",
    
    # Tier 3: Professional Design & Reasoning (Gemma 4 Family)
    "models/gemma-4-31b-it",
    "models/gemma-4-26b-a4b-it",
    
    # Tier 4: High Volume Safety Net (Gemma 3 Family)
    "models/gemma-3-27b-it",
    "models/gemma-3-12b-it",
    "models/gemma-3-4b-it",
    "models/gemma-3n-e2b-it",
    "models/gemma-3-1b-it",
    
    # Tier 5: Specialized Reasoning
    "models/gemini-robotics-er-1.6-preview",
    "models/gemini-robotics-er-1.5-preview"
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
        # Internal Retry Loop for the current model (Handle temporary congestion)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = (2 ** attempt) + 0.5 # Exponential backoff: 2.5s, 4.5s...
                    print(f"[{label}]: Rate limit backoff. Waiting {wait_time}s before retry {attempt} on {model_name}...")
                    time.sleep(wait_time)

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
                break # Exit retry loop and move to next model
                
            except Exception as e:
                last_error = e
                err_msg = str(e).lower()
                
                if "429" in err_msg or "rate limit" in err_msg:
                    if attempt < max_retries - 1:
                        continue # Retry same model
                    else:
                        print(f"[{label}]: Rate limit hit on {model_name} after {max_retries} attempts. Falling back to next model...")
                        break # Move to next model
                elif "404" in err_msg or "not found" in err_msg:
                    print(f"[{label}]: Model {model_name} not available or deprecated. Falling back...")
                    break # Move to next model
                else:
                    # For other errors (auth, network), we log and skip
                    print(f"[{label}]: Unexpected error with {model_name}: {e}")
                    break # Move to next model

    print(f"[{label}]: FATAL - All models failed in fallback loop. Last error: {last_error}")
    return None
