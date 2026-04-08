import os
import json
import faiss
import numpy as np
import re
from sentence_transformers import SentenceTransformer

# ---------- CONFIG ----------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

INDEX_PATH = os.path.join(DATA_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(DATA_DIR, "policy_chunks.json")

TOP_K = 5
SIMILARITY_THRESHOLD = 0.50
MIN_SCORE = 0.55

# ---------- EMBEDDING ----------
_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        print("[INFO]: Loading SentenceTransformer model for retrieval...")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder

index = None
policy_chunks = []
_last_index_mtime = None
_last_chunks_mtime = None


def strip_html(text: str) -> str:
    """Removes HTML tags and normalizes whitespace for cleaner semantic embeddings."""
    if not text:
        return ""
    # Remove script and style tags and their contents
    clean = re.sub(r"<(style|script)[^>]*>[\s\S]*?<\/\1>", " ", text, flags=re.IGNORECASE)
    # Remove all other tags
    clean = re.sub(r"<[^>]*>", " ", clean)
    # Decode some common HTML entities
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Normalize whitespace
    return " ".join(clean.split()).strip()


def _choose_chunks_path() -> str:
    """Use the active policy chunks generated from demo PDFs or uploaded PDFs."""
    return CHUNKS_PATH


def _mtime(path: str):
    return os.path.getmtime(path) if os.path.exists(path) else None


def reload_retriever_data(force: bool = False) -> None:
    """Reload FAISS/chunks when source files changed on disk."""
    global index, policy_chunks, _last_index_mtime, _last_chunks_mtime

    chunks_path = _choose_chunks_path()
    index_mtime = _mtime(INDEX_PATH)
    chunks_mtime = _mtime(chunks_path)

    if not force and index_mtime == _last_index_mtime and chunks_mtime == _last_chunks_mtime:
        return

    try:
        if index_mtime is None or chunks_mtime is None:
            index = None
            policy_chunks = []
            _last_index_mtime = index_mtime
            _last_chunks_mtime = chunks_mtime
            return

        index = faiss.read_index(INDEX_PATH)
        with open(chunks_path, "r", encoding="utf-8") as f:
            policy_chunks = json.load(f)

        if index.ntotal != len(policy_chunks):
            print(f"[WARN]: FAISS mismatch: index={index.ntotal}, chunks={len(policy_chunks)}")

        _last_index_mtime = index_mtime
        _last_chunks_mtime = chunks_mtime
    except Exception as e:
        print(f"[ERROR]: Retriever failed to load: {e}")
        index = None
        policy_chunks = []


# Initial load at import time.
reload_retriever_data(force=True)


def retrieve_policy_chunks(query: str):
    """
    Retrieve relevant policy chunks using FAISS.
    Enforces Strict semantic re-ranking and consistency filtering.
    """
    reload_retriever_data()

    if not index or not policy_chunks:
        print("[WARN]: Retriever not initialized or empty.")
        return []

    # Clean query: Remove HTML pollution which ruins semantic embedding
    clean_query = strip_html(query)
    print("Cleaned Query:", clean_query[:300] + ("..." if len(clean_query) > 300 else ""))

    # Encode query
    emb_model = get_embedder()
    query_emb = emb_model.encode([clean_query], normalize_embeddings=True)
    query_emb = np.asarray(query_emb).astype("float32")

    # Search FAISS
    scores, indices = index.search(query_emb, TOP_K)

    # Filter and collect candidate indexes
    candidate_idxs = [int(idx) for idx in indices[0] if idx != -1]
    if not candidate_idxs:
        return []
        
    # Map back to chunks
    candidate_chunks = [policy_chunks[idx] for idx in candidate_idxs]
    
    # Optimized Batch Encoding for semantic re-ranking
    texts_to_score = [c.get("text", "") for c in candidate_chunks]
    
    print(f"Re-ranking {len(texts_to_score)} candidates using batch encoding...")
    chunk_embs = emb_model.encode(texts_to_score, normalize_embeddings=True)
    chunk_embs = np.asarray(chunk_embs).astype("float32") # Matrix: (len(batch), dim)
    
    # Batch calculate cosine similarities
    # (n, dim) dot (dim,) -> (n,)
    semantic_scores = np.dot(chunk_embs, query_emb[0])

    results = []
    for i, chunk in enumerate(candidate_chunks):
        score = float(semantic_scores[i])
        
        if score >= MIN_SCORE:
            section = chunk.get("section_title", "General")
            res = {
                "text": chunk.get("text", ""),
                "metadata": {
                    "policy_id": chunk.get("policy_id", "DEMO_POLICY"),
                    "section": section,
                    "clause_id": chunk.get("clause_id", "N/A")
                },
                "score": score
            }
            results.append(res)

    # LIMIT results to top 3 and Sort
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:3]
    
    # Consistency filter: if results come from 3 different sections, prefer the absolute top section
    unique_sections = set(res["metadata"]["section"] for res in results)
    if len(unique_sections) > 2 and results:
        highest_scoring_section = results[0]["metadata"]["section"]
        results = [res for res in results if res["metadata"]["section"] == highest_scoring_section]

    print("Retrieved:", len(results))
    print("Top clauses:", [c["metadata"]["clause_id"] for c in results])
    
    return results
