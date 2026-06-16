import os
import json
import shutil
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from config import (
    CHUNKS_PATH, INDEX_PATH, POLICY_DIR, DEMO_POLICY_DIR
)
from core.logging import get_logger
from rag.ingest import ingest_policy_document
from services.rag_service import reload_retriever_data

logger = get_logger("services.policy")

def get_user_policy_paths(user_email: str) -> Dict[str, Path]:
    """Generates isolated filesystem paths for a specific user."""
    from utils.email_utils import normalize_email_address
    # Slugify the normalized email for filesystem safety
    slug = re.sub(r'[^a-z0-9]', '_', normalize_email_address(user_email).lower())
    
    user_dir = POLICY_DIR / slug
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # Isolate vector database index and chunk definitions in a dedicated subdirectory
    index_dir = user_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    
    return {
        "policy_dir": user_dir,
        "index_path": index_dir / "index.faiss",
        "chunks_path": index_dir / "chunks.json"
    }

def slugify_policy_id(raw_name: str) -> str:
    base = Path(raw_name).stem if raw_name else "policy"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return base or "policy"

def load_policy_chunks(user_email: str) -> List[Dict[str, Any]]:
    paths = get_user_policy_paths(user_email)
    chunks_path = paths["chunks_path"]
    if not chunks_path.exists():
        return []
    try:
        with open(chunks_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_policy_chunks(chunks: List[Dict[str, Any]], user_email: str):
    paths = get_user_policy_paths(user_email)
    chunks_path = paths["chunks_path"]
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

def rebuild_index_from_chunks(chunks: List[Dict[str, Any]], user_email: str):
    paths = get_user_policy_paths(user_email)
    index_path = paths["index_path"]
    
    texts = [c.get("text", "") for c in chunks if c.get("text")]
    if not texts:
        if index_path.exists():
            index_path.unlink()
        return

    from services.rag_service import get_embedder
    embedder = get_embedder()
    embeddings = embedder.encode(texts, normalize_embeddings=True)
    embeddings = np.asarray(embeddings).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss.write_index(index, str(index_path))

def remove_policy_chunks(policy_id: str, user_email: str) -> Tuple[List[Dict[str, Any]], int]:
    chunks = load_policy_chunks(user_email)
    retained = [c for c in chunks if str(c.get("policy_id", "")) != policy_id]
    removed = len(chunks) - len(retained)
    if removed:
        save_policy_chunks(retained, user_email)
        rebuild_index_from_chunks(retained, user_email)
    return retained, removed

def resolve_policy_file_path(policy_id: str, user_email: Optional[str] = None) -> Optional[Path]:
    """Resolves policy path (supporting PDF, DOCX, TXT, MD, Images), checking user directory first, then demo directory."""
    dirs = []
    if user_email:
        paths = get_user_policy_paths(user_email)
        dirs.append(paths["policy_dir"])
    
    dirs.append(DEMO_POLICY_DIR)
    
    for d in dirs:
        if d.exists():
            for ext in [
                ".pdf", ".PDF", ".docx", ".DOCX", ".txt", ".TXT", ".md", ".MD",
                ".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"
            ]:
                p = d / f"{policy_id}{ext}"
                if p.exists():
                    return p
    return None

def async_categorize_policy(policy_id: str, user_email: str):
    """Background task to asynchronously classify a policy document using the LLM and DB categories."""
    try:
        from db.repository import get_active_categories, get_system_role
        from services.ai_utils import generate_content_with_fallback, get_genai_client
        from config import ULTIMATE_FALLBACK_LIST
        
        chunks = load_policy_chunks(user_email)
        policy_chunks = [c for c in chunks if str(c.get("policy_id", "")) == policy_id]
        
        if not policy_chunks:
            logger.warning(f"No chunks found for policy {policy_id} to categorize.")
            return
            
        # Combine text up to ~4000 characters to give LLM enough context
        text_content = ""
        for c in policy_chunks:
            text_content += c.get("text", "") + "\n\n"
            if len(text_content) > 4000:
                break
        text_content = text_content[:4000]
        
        active_cats = get_active_categories(user_email)
        if not active_cats:
            return
            
        cat_names = [c["name"] for c in active_cats]
        cat_list_str = "\n".join(f"- {name}" for name in cat_names)
        
        custom_role = get_system_role(user_email)
        
        prompt = f"""You are a {custom_role}.
Read the following policy document extract and assign it to the most appropriate category from the list below.

AVAILABLE CATEGORIES:
{cat_list_str}

If the document does not clearly fit into ANY of these categories, reply exactly with: Miscellaneous

POLICY EXTRACT:
{text_content}

Reply with ONLY the exact name of the category from the list above. Do not add any extra text or quotes."""

        from config import GEMINI_API_KEY
        client = get_genai_client(api_key=GEMINI_API_KEY)
        
        assigned_category = "Miscellaneous"
        response = generate_content_with_fallback(
            client=client,
            contents=prompt,
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Policy-Categorizer"
        )
        if response:
            result = getattr(response, "text", str(response)).strip()
            # Clean up the result (remove quotes, etc)
            result = result.strip('"\'*.- \n')
            if result in cat_names:
                assigned_category = result
                
        # Save back to JSON
        updated = False
        for c in chunks:
            if str(c.get("policy_id", "")) == policy_id:
                c["category"] = assigned_category
                updated = True
                
        if updated:
            save_policy_chunks(chunks, user_email)
            logger.info(f"Policy {policy_id} categorized as: {assigned_category}")
            
    except Exception as e:
        logger.error(f"Failed to async categorize policy {policy_id}: {e}")
