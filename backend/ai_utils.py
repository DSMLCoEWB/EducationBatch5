import os
import time
import json
from typing import List, Any, Optional

def generate_content_with_fallback(
    client, 
    contents: Any, 
    config: Optional[Any] = None, 
    model_list: List[str] = [], # Kept for API compatibility but ignored
    label: str = "AI Service"
):
    """
    Executes a generate_content call using OpenAI SDK for Ollama.
    """
    if not client:
        print(f"[{label}]: Error - No OpenAI client initialized for local Ollama.")
        return None

    model_name = os.getenv("LOCAL_LLM_MODEL", "llama3.2:3b")
    
    # Internal Retry Loop
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = (2 ** attempt) + 0.5 
                print(f"[{label}]: Wait {wait_time}s before retry {attempt} on {model_name}...")
                time.sleep(wait_time)

            print(f"[{label}]: Attempting generation with {model_name}...")
            
            # Parse contents
            prompt = ""
            if isinstance(contents, list):
                for part in contents:
                    if isinstance(part, str):
                        prompt += part + "\n"
                    # Ignore bytes (images/pdfs) for local text-only model
            elif hasattr(contents, "parts"):
                # Handle old google.genai.types.Content format if passed
                prompt = contents.parts[0].text
            else:
                prompt = str(contents)

            messages = [{"role": "user", "content": prompt}]
            
            # Parse config (duck typing old google.genai GenerateContentConfig)
            temp = 0.2
            if hasattr(config, 'temperature'):
                temp = config.temperature
            elif isinstance(config, dict) and 'temperature' in config:
                temp = config['temperature']

            sys_inst = ""
            if hasattr(config, 'system_instruction'):
                sys_inst = config.system_instruction
            elif isinstance(config, dict) and 'system_instruction' in config:
                sys_inst = config['system_instruction']
            
            if sys_inst:
                messages.insert(0, {"role": "system", "content": f"{sys_inst}\n\nIMPORTANT: Ensure valid output."})

            kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": temp
            }
            
            # Check for JSON request
            is_json = False
            if hasattr(config, 'response_mime_type') and config.response_mime_type == "application/json":
                is_json = True
            elif isinstance(config, dict) and config.get('response_mime_type') == "application/json":
                is_json = True
                
            if hasattr(config, 'response_schema') or (isinstance(config, dict) and config.get('response_schema')):
                is_json = True

            if is_json:
                kwargs["response_format"] = {"type": "json_object"}
                if sys_inst:
                    messages[0]["content"] += " MUST BE RAW JSON ONLY. DO NOT USE MARKDOWN ```json ``` BLOCKS."
                else:
                    messages.insert(0, {"role": "system", "content": "MUST BE RAW JSON ONLY. DO NOT USE MARKDOWN ```json ``` BLOCKS."})

            response = client.chat.completions.create(**kwargs)
            
            class MockResponse:
                def __init__(self, text):
                    self.text = text
            
            if response and response.choices:
                print(f"[{label}]: Success with {model_name}")
                text = response.choices[0].message.content
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                return MockResponse(text)
            
            print(f"[{label}]: Empty response from {model_name}, retrying...")
            
        except Exception as e:
            err_msg = str(e).lower()
            print(f"[{label}]: Unexpected error with {model_name}: {e}")
            if "429" in err_msg or "rate limit" in err_msg:
                continue
            else:
                break

    print(f"[{label}]: FATAL - Model failed after retries.")
    return None
