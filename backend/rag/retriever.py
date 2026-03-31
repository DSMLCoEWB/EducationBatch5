import os
import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------- CONFIG ----------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

INDEX_PATH = os.path.join(DATA_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(DATA_DIR, "demo_policy_chunks.json")

TOP_K = 5
SIMILARITY_THRESHOLD = 0.50
MIN_SCORE = 0.55

# ---------- EMBEDDING ----------
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# ---------- LOAD DATA ----------
try:
    if os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH):
        index = faiss.read_index(INDEX_PATH)
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            policy_chunks = json.load(f)

        if index.ntotal != len(policy_chunks):
            print(f"[WARN]: FAISS mismatch: index={index.ntotal}, chunks={len(policy_chunks)}")
    else:
        index = None
        policy_chunks = []
except Exception as e:
    print(f"[ERROR]: Retriever failed to load: {e}")
    index = None
    policy_chunks = []


def retrieve_policy_chunks(query: str):
    """
    Retrieve relevant policy chunks using FAISS.
    Enforces Strict semantic re-ranking and consistency filtering.
    """
    if not index or not policy_chunks:
        print("[WARN]: Retriever not initialized or empty.")
        return []

    print("Query:", query)

    # Encode query
    query_emb = embedder.encode([query], normalize_embeddings=True)
    query_emb = np.asarray(query_emb).astype("float32")

    # Search FAISS
    scores, indices = index.search(query_emb, TOP_K)

    results = []
    
    # Track unique sections for consistency filter
    sections_seen = set()

    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        
        chunk = policy_chunks[idx]
        
        # TASK 1: Add semantic re-ranking
        chunk_text = chunk.get("text", "")
        chunk_emb = embedder.encode([chunk_text], normalize_embeddings=True)
        chunk_emb = np.asarray(chunk_emb).astype("float32")
        
        # Cosine similarity dot product
        semantics_score = float(np.dot(query_emb[0], chunk_emb[0]))
        
        if semantics_score >= MIN_SCORE:
            section = chunk.get("section_title", "General")
            
            res = {
                "text": chunk_text,
                "metadata": {
                    "policy_id": chunk.get("policy_id", "DEMO_POLICY"),
                    "section": section,
                    "clause_id": chunk.get("clause_id", str(idx))
                },
                "score": semantics_score
            }
            results.append(res)
            sections_seen.add(section)

    # LIMIT results to top 3 and Sort
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:3]
    
    # TASK 1: Add consistency filter
    unique_sections = set(res["metadata"]["section"] for res in results)
    if len(unique_sections) > 2 and results:
        highest_scoring_section = results[0]["metadata"]["section"]
        results = [res for res in results if res["metadata"]["section"] == highest_scoring_section]

    print("Retrieved:", len(results))
    print("Top clauses:", [c["metadata"]["clause_id"] for c in results])
    
    return results
