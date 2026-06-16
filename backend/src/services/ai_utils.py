"""
AI Utilities for the AICOE Education System.

This module provides a hardware-aware interface for AI content generation,
supporting both local inference via Ollama and cloud-based fallback via Google Gemini.

DESIGN PRINCIPLES:
1. Resource Coordination: Integrates with AI_RESOURCE_MANAGER to ensure 
   human-interactive tasks (Chatbot, Reply Generation) take precedence over 
   background tasks (OCR, Triage) on shared VRAM hardware.
2. Environment Portability: Automatically detects Docker vs Native host environments
   to route local inference requests correctly (localhost vs host.docker.internal).
3. Fallback Resilience: Sequentially attempts models from a configurable fallback
   list to guarantee system availability if local resources are offline.
"""
import os
import time
from core.logging import get_logger
from config import ULTIMATE_FALLBACK_LIST, VISION_FALLBACK_LIST, AI_PREFER_LOCAL, PRIMARY_LOCAL_MODEL, VERTEX_AI_PROJECT, VERTEX_AI_LOCATION
from google import genai

import ollama
from ollama import Client
from core.resource_manager import AI_RESOURCE_MANAGER

logger = get_logger("ai_utils")

from typing import Optional

def get_genai_client(api_key: Optional[str] = None):
    """
    Returns a configured google.genai Client.
    If VERTEX_AI_PROJECT is configured, it forces Enterprise Vertex AI routing
    (zero-data-training). Otherwise, it falls back to the standard developer API key.
    """
    if VERTEX_AI_PROJECT:
        logger.info(f"🔒 Initializing Enterprise Vertex AI Client (Project: {VERTEX_AI_PROJECT})")
        return genai.Client(vertexai=True, project=VERTEX_AI_PROJECT, location=VERTEX_AI_LOCATION)
    elif api_key:
        return genai.Client(api_key=api_key)
    return None

# Connect to Ollama (Docker-aware host detection)
IN_DOCKER = os.path.exists('/.dockerenv')
DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434" if IN_DOCKER else "http://localhost:11434"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
ollama_client = Client(host=OLLAMA_HOST)

def generate_content_with_fallback(client, contents, model_list=ULTIMATE_FALLBACK_LIST, label="AI-Task", **kwargs):
    """
    Robust wrapper that tries multiple models in sequence.
    Now respects the AI_RESOURCE_MANAGER lock for background tasks.
    """
    if not model_list:
        return None
        
    for model_name in model_list:
        try:
            # 1. Local Ollama Integration
            if model_name.startswith("ollama/"):
                # Resource Coordination: Only gate on the GPU lock when
                # actually about to use local hardware.  Cloud (Gemini)
                # calls skip this entirely so they are never stalled.
                if label not in ["Chatbot", "RAG-Generator"]:
                    AI_RESOURCE_MANAGER.wait_for_gpu(label)
                if not AI_PREFER_LOCAL:
                    logger.info(f"⏭️ [{label}] Skipping local model {model_name} (AI_PREFER_LOCAL is False)")
                    continue
                
                # Use the specialist model from the list (e.g. moondream) 
                # unless it's a general reasoning task
                actual_model = model_name.replace("ollama/", "")
                if label not in ["OCR Service", "Vision-Task"]:
                    actual_model = PRIMARY_LOCAL_MODEL or actual_model
                
                # Only log for interactive tasks or first attempt
                logger.info(f"🏎️ [{label}] Using Local Ollama: {actual_model}")
                
                # 🖼️ Improved Image/OCR Support
                prompt_text = ""
                images = []
                
                if isinstance(contents, list):
                    for part in contents:
                        # Extract text
                        if hasattr(part, "text") and part.text:
                            prompt_text += part.text
                        elif isinstance(part, str):
                            prompt_text += part
                        # Extract images (for OCR/Vision)
                        if hasattr(part, "inline_data"):
                            images.append(part.inline_data.data)
                else:
                    prompt_text = str(contents)
                
                # Respect the high context window we enabled on the server
                context_size = int(os.getenv("OLLAMA_CONTEXT_LENGTH", 4096))
                
                response = ollama_client.generate(
                    model=actual_model, 
                    prompt=prompt_text,
                    images=images,
                    options={"num_ctx": context_size}
                )
                
                # Wrap response to match Gemini client interface (duck typing)
                class OllamaResponse:
                    def __init__(self, text): self.text = text
                return OllamaResponse(response['response'])

            # 2. Cloud Gemini Integration
            # When local-only mode is active, never fall through to cloud models.
            if AI_PREFER_LOCAL:
                logger.info(f"⏭️ [{label}] Skipping cloud model {model_name} (AI_PREFER_LOCAL is True)")
                continue

            if not client: 
                continue

            from config import VERTEX_AI_PROJECT
            # Vertex AI prefers the raw model name, Developer API can keep the user's exact string
            cloud_model = model_name.replace("models/", "") if (VERTEX_AI_PROJECT and model_name.startswith("models/")) else model_name
            
            response = client.models.generate_content(
                model=cloud_model,
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
