from rag.retriever import get_embedder, index, policy_chunks, strip_html
import numpy as np
import faiss

def debug_retrieval(query):
    print(f"Original Query: {query}")
    clean_query = strip_html(query)
    print(f"Cleaned Query: {clean_query}")
    
    emb_model = get_embedder()
    query_emb = emb_model.encode([clean_query], normalize_embeddings=True)
    query_emb = np.asarray(query_emb).astype("float32")
    
    # Search FAISS
    scores, indices = index.search(query_emb, 10)
    print(f"FAISS Scores: {scores[0]}")
    print(f"FAISS Indices: {indices[0]}")
    
    candidate_idxs = [int(idx) for idx in indices[0] if idx != -1]
    candidate_chunks = [policy_chunks[idx] for idx in candidate_idxs]
    
    texts_to_score = [c.get("text", "") for c in candidate_chunks]
    
    chunk_embs = emb_model.encode(texts_to_score, normalize_embeddings=True)
    chunk_embs = np.asarray(chunk_embs).astype("float32")
    
    semantic_scores = np.dot(chunk_embs, query_emb[0])
    
    print("\nDetailed Analysis:")
    for i, score in enumerate(semantic_scores):
        print(f"Rank {i+1}: Score={score:.4f} | Clause={candidate_chunks[i].get('clause_id')} | Text={texts_to_score[i][:100]}...")

if __name__ == "__main__":
    query = "[AICOE-SEED] Legal complaint filed and no update I filed a legal complaint but have not received any update. Please inform the process."
    debug_retrieval(query)
