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

    device = "cuda" if torch.cuda.is_available() else "cpu"
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
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

def resolve_policy_file_path(policy_id: str, user_email: str = None) -> Optional[Path]:
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
