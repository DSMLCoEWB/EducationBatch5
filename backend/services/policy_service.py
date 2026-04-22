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
from rag_pipeline.ingest import ingest_policy_document # Legacy integration
from services.rag_service import reload_retriever_data

logger = get_logger("services.policy")

def slugify_policy_id(raw_name: str) -> str:
    base = Path(raw_name).stem if raw_name else "policy"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return base or "policy"

def load_policy_chunks() -> List[Dict[str, Any]]:
    if not CHUNKS_PATH.exists():
        return []
    try:
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_policy_chunks(chunks: List[Dict[str, Any]]):
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

def rebuild_index_from_chunks(chunks: List[Dict[str, Any]]):
    texts = [c.get("text", "") for c in chunks if c.get("text")]
    if not texts:
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    embeddings = embedder.encode(texts, normalize_embeddings=True)
    embeddings = np.asarray(embeddings).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss.write_index(index, str(INDEX_PATH))

def remove_policy_chunks(policy_id: str) -> Tuple[List[Dict[str, Any]], int]:
    chunks = load_policy_chunks()
    retained = [c for c in chunks if str(c.get("policy_id", "")) != policy_id]
    removed = len(chunks) - len(retained)
    if removed:
        save_policy_chunks(retained)
        rebuild_index_from_chunks(retained)
    return retained, removed

def resolve_policy_file_path(policy_id: str) -> Optional[Path]:
    for d in [POLICY_DIR, DEMO_POLICY_DIR]:
        p = d / f"{policy_id}.pdf"
        if p.exists():
            return p
    return None
