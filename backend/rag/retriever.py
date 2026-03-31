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
SIMILARITY_THRESHOLD = 0.30

# ---------- EMBEDDING ----------
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# ---------- LOAD DATA ----------
try:
    if os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH):
        index = faiss.read_index(INDEX_PATH)
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            policy_chunks = json.load(f)

        if index.ntotal != len(policy_chunks):
            print(f"⚠️ FAISS mismatch: index={index.ntotal}, chunks={len(policy_chunks)}")
    else:
        index = None
        policy_chunks = []
except Exception as e:
    print(f"❌ Retriever failed to load: {e}")
    index = None
    policy_chunks = []


def retrieve_policy_chunks(query: str):
    """
    Retrieve relevant policy chunks using FAISS.
    Uses keyword boosting for critical topics.
    """
    if not index or not policy_chunks:
        print("⚠️ Retriever not initialized or empty.")
        return []

    print("Query:", query)

    # Encode query
    query_emb = embedder.encode([query], normalize_embeddings=True)
    query_emb = np.asarray(query_emb).astype("float32")

    # Search FAISS
    scores, indices = index.search(query_emb, TOP_K)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        
        chunk = policy_chunks[idx]
        
        # Structure mapping
        res = {
            "text": chunk.get("text", ""),
            "metadata": {
                "policy_id": chunk.get("policy_id", "DEMO_POLICY"),
                "section": chunk.get("section_title", "General"),
                "clause_id": chunk.get("clause_id", str(idx))
            },
            "score": float(score)
        }
        
        # Keyword Boost Logic
        q_low = query.lower()
        t_low = res["text"].lower()
        
        boost = 0
        if "scholarship" in q_low and "scholarship" in t_low:
            boost += 0.15
        if ("exam" in q_low or "result" in q_low) and "examination" in t_low:
            boost += 0.15
        if "hostel" in q_low and "hostel" in t_low:
            boost += 0.15
            
        res["score"] += boost
        
        # Filter by threshold OR keep if it's the top relative match
        if res["score"] >= SIMILARITY_THRESHOLD:
            results.append(res)
            
    # Always return at least 1 result if available
    if not results and indices[0][0] != -1:
        idx = indices[0][0]
        chunk = policy_chunks[idx]
        results.append({
            "text": chunk.get("text", ""),
            "metadata": {
                "policy_id": chunk.get("policy_id", "DEMO_POLICY"),
                "section": chunk.get("section_title", "General"),
                "clause_id": chunk.get("clause_id", str(idx))
            },
            "score": float(scores[0][0])
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    
    print("Retrieved:", len(results))
    print("Top clauses:", [c["metadata"]["clause_id"] for c in results])
    
    return results
