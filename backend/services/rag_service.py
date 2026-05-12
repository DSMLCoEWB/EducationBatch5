import os
import json
import hashlib
import faiss
import numpy as np
import re
from typing import List, Dict, Any, Optional
import torch
from sentence_transformers import SentenceTransformer
from google import genai

from config import (
    INDEX_PATH, CHUNKS_PATH, RAG_TOP_K, 
    RAG_MIN_SCORE, RAG_FINAL_LIMIT, ULTIMATE_FALLBACK_LIST,
    RAG_UNREPLIED_MAX, RAG_ANCHOR_DEPTH
)
from core.logging import get_logger
from ai_utils import generate_content_with_fallback

logger = get_logger("services.rag")

# --- EMBEDDING SINGLETON ---
_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        # STRATEGY: We force CPU for small embeddings (80MB) to:
        # 1. Prevent Segfaults on AMD/WSL2
        # 2. Save 100% of VRAM for the Local LLM (Qwen 3.5)
        # 3. Ensure instant startup (no driver warm-up needed)
        device = "cpu"
        
        # Minimal hardware detection for logging
        try:
            if torch.cuda.is_available():
                logger.info("ℹ️ NVIDIA detected. Using CPU for Embeddings (VRAM Saving Mode)")
            else:
                import torch_directml
                logger.info("ℹ️ AMD/DirectML detected. Using CPU for Embeddings (Stability Mode)")
        except:
            logger.info("ℹ️ Using CPU for Embeddings (Standard Mode)")

        # Note: SentenceTransformer handles the device string or object automatically
        _embedder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    return _embedder

def strip_html(text: str) -> str:
    """Removes HTML tags and normalizes whitespace for cleaner semantic embeddings."""
    if not text: return ""
    clean = re.sub(r"<(style|script)[^>]*>[\s\S]*?<\/\1>", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]*>", " ", clean)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(clean.split()).strip()

# --- RETRIEVER (Multi-Tenant Cache) ---
_user_indices: Dict[str, Any] = {} # user_email -> faiss_index
_user_chunks: Dict[str, List[Dict[str, Any]]] = {} # user_email -> chunks_list

def reload_retriever_data(user_email: str):
    global _user_indices, _user_chunks
    
    from services.policy_service import get_user_policy_paths
    paths = get_user_policy_paths(user_email)
    index_path = paths["index_path"]
    chunks_path = paths["chunks_path"]

    if not os.path.exists(index_path) or not os.path.exists(chunks_path):
        logger.warning(f"⚠️ RAG Index or Chunks missing for {user_email}.")
        _user_indices[user_email] = None
        _user_chunks[user_email] = []
        return
        
    try:
        _user_indices[user_email] = faiss.read_index(str(index_path))
        with open(chunks_path, "r", encoding="utf-8") as f:
            _user_chunks[user_email] = json.load(f)
        logger.info(f"📚 RAG Index Loaded for {user_email}: {_user_indices[user_email].ntotal} chunks.")
    except Exception as e:
        logger.error(f"❌ Failed to load RAG index for {user_email}: {e}")

def retrieve_policy_chunks(query: str, user_email: str) -> List[Dict[str, Any]]:
    """Performs semantic search against user-specific policy documents via FAISS."""
    if user_email not in _user_indices or _user_indices[user_email] is None:
        reload_retriever_data(user_email)
    
    index = _user_indices.get(user_email)
    chunks = _user_chunks.get(user_email, [])
    
    if index is None or not chunks:
        return []

    model = get_embedder()
    clean_query = strip_html(query)
    
    query_emb = model.encode([clean_query], normalize_embeddings=True)
    query_emb = np.asarray(query_emb).astype("float32")

    # 1. Search FAISS for candidates
    scores_faiss, indices = index.search(query_emb, RAG_TOP_K)
    
    candidate_idxs = [int(idx) for idx in indices[0] if idx != -1]
    if not candidate_idxs:
        return []
        
    candidate_chunks = [chunks[idx] for idx in candidate_idxs]
    
    # 2. Batch Re-ranking (Surgical Parity)
    # Manual Cosine Similarity overrides raw FAISS distances for better precision
    texts_to_score = [c.get("text", "") for c in candidate_chunks]
    chunk_embs = model.encode(texts_to_score, normalize_embeddings=True)
    chunk_embs = np.asarray(chunk_embs).astype("float32")
    
    semantic_scores = np.dot(chunk_embs, query_emb[0])
    
    results = []
    for i, chunk in enumerate(candidate_chunks):
        score = float(semantic_scores[i])
        if score >= RAG_MIN_SCORE:
            results.append({
                "text": chunk.get("text", ""),
                "metadata": {
                    "clause_id": chunk.get("clause_id", "N/A"),
                    "section": chunk.get("section_title", "General")
                },
                "score": score
            })

    # 3. Sort and Apply Limit
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:RAG_FINAL_LIMIT]
    
    # 4. Consistency Filtering (Prefer dominant section)
    unique_sections = set(res["metadata"]["section"] for res in results)
    if len(unique_sections) > 2 and results:
        highest_scoring_section = results[0]["metadata"]["section"]
        results = [res for res in results if res["metadata"]["section"] == highest_scoring_section]

    return results

# --- GENERATION CONFIG ---

SYSTEM_PROMPT = """
You are a senior professional grievance redressal officer for an educational institution.
Primary Goal: Generate a formal, helpful, and policy-grounded email reply.

Rules:
1. Strict Grounding: Use ONLY the provided policy context.
2. Complete Response: Output a FULL email body (Salutation, Body, Signature).
3. NO REDUNDANT SUBJECT: DO NOT include a "Subject:" line in your response.
4. NO HARD WRAPPING: Do NOT insert line breaks within paragraphs. Use double newlines between paragraphs.
5. Minimum Length: The body must be 3-5 sentences minimum.
6. Policy Citation: You MUST explicitly mention specific clause IDs (e.g., "As per MSC-06...") to support your statements.
7. Delay Handling: If the query is about a delay, mention the specific escalation path (e.g., nodal officer) or response timelines.
8. Tone: Professional, authoritative yet respectful.
9. Language: Formal English.

If context is insufficient, state that no relevant policy clause is available.
"""

# --- REPLY GENERATOR ---

def generate_suggested_reply_with_evidence(
    email_content: str,
    user_email: str,
    email_subject: str = "",
    sender: str = "",
    category: str = "",
    attachment_content: str = "",
    history: List[Dict[str, Any]] = [],
    email_id: str = None
) -> Dict[str, Any]:
    """Generates a policy-grounded reply using Surgical RAG context."""
    
    # 1. Prepare Surgical Context (Anchor-Turn Windowing)
    safe_history = history if history else []
    
    # Temporal Truncation (if applicable)
    if email_id and safe_history:
        found_idx = -1
        for i, m in enumerate(safe_history):
            if str(m.get('id', '')) == str(email_id) or str(m.get('email_id', '')) == str(email_id):
                found_idx = i
                break
        if found_idx != -1:
            safe_history = safe_history[:found_idx + 1]
            
    # Solve for Anchor Turn: Last Dept Reply + Its Citizen Trigger
    unreplied_msgs = []
    anchor_turn = []
    rev_history = list(reversed(safe_history))
    last_sent_idx = -1
    
    for i, msg in enumerate(rev_history):
        content_upper = str(msg.get('content', '')).upper()
        subject_upper = str(msg.get('subject', '')).upper()
        if (msg.get('is_sent') or msg.get('isSent')) and "[AICOE-SEED]" not in content_upper and "[AICOE-SEED]" not in subject_upper:
            last_sent_idx = i
            break
            
    if last_sent_idx == -1:
        unreplied_msgs = rev_history[:RAG_UNREPLIED_MAX]
    else:
        unreplied_msgs = rev_history[:last_sent_idx][:RAG_UNREPLIED_MAX]
        # Anchor consists of Dept Reply + Its Citizen Trigger (The "Handshake")
        anchor_turn.append(rev_history[last_sent_idx])
        for j in range(last_sent_idx + 1, len(rev_history)):
            if len(anchor_turn) >= RAG_ANCHOR_DEPTH:
                break
            msg_j = rev_history[j]
            if not (msg_j.get('is_sent') or msg_j.get('isSent')):
                anchor_turn.append(msg_j)

    # 2. Build Surgical Retrieval Query
    retrieval_query_parts = [f"Subject: {email_subject}", email_content, attachment_content]
    if not unreplied_msgs and len(anchor_turn) >= 2:
        retrieval_query_parts.append(anchor_turn[1].get('content', ''))
    for m in unreplied_msgs:
        if m.get('id') != (safe_history[-1].get('id') if safe_history else None):
            retrieval_query_parts.append(m.get('content', ''))
            
    search_query = f"Category: {category} | " + " ".join([p for p in retrieval_query_parts if p]).strip()
    chunks = retrieve_policy_chunks(search_query[:1000], user_email)
    
    if not chunks:
        return {
            "suggested_reply": "Dear Sir/Madam,\n\nYour grievance has been received and is under review. The institution will process the matter as per applicable policy provisions.\n\nSincerely,\nGrievance Support Desk",
            "evidence": [],
            "status": "no_policy"
        }

    # 3. Format History for LLM (Chronological Surgical Window)
    history_to_format = []
    if anchor_turn: history_to_format.extend(reversed(anchor_turn))
    if unreplied_msgs: history_to_format.extend(reversed(unreplied_msgs))
    
    history_lines = []
    for m in history_to_format:
        is_dept = bool(m.get('is_sent') or m.get('isSent'))
        role = "Dpt-Response (You)" if is_dept else "Citizen-Inquiry"
        if m.get('id') != (safe_history[-1].get('id') if safe_history else None):
            history_lines.append(f"[{role}]: {m.get('content', '')[:300]}")
    
    history_text = "\n".join(history_lines)
    citizen_name = str(sender).split('<')[0].strip() if sender and str(sender).lower() != "nan" else "Sir/Madam"

    # 4. Final Generation Prompt
    context_text = "\n\n".join([f"[Clause {c['metadata']['clause_id']}] {c['text']}" for c in chunks])
    
    prompt = f"""
    {SYSTEM_PROMPT}

    CONVERSATION HISTORY:
    {history_text}
    
    CURRENT INQUIRY:
    Subject: {email_subject}
    From: {sender}
    Content: {email_content}
    OCR-Attachments: {attachment_content if attachment_content else "None"}
    
    POLICY CONTEXT:
    {context_text}
    
    TASK:
    Write a professional reply to {citizen_name}. 
    - Respond directly to the inquiry using the policy context.
    - Reference specific Clause IDs (e.g., EXM-01).
    - Start with 'Dear {citizen_name},' and end with 'Sincerely, Grievance Support Desk'.
    """

    api_key = os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else None
    
    if not client:
        return {"suggested_reply": "AI Service currently unavailable.", "status": "error"}

    from config import ULTIMATE_FALLBACK_LIST
    response = generate_content_with_fallback(
        client=client,
        contents=prompt,
        model_list=ULTIMATE_FALLBACK_LIST,
        label="RAG-Service"
    )

    if response:
        try:
            reply = response.text
        except:
            reply = str(response)
    else:
        reply = "Error generating reply."
    
    # Strip LLM-injected "Subject:" tags
    if "subject:" in reply.lower():
        lines = [l for l in reply.split('\n') if not l.strip().lower().startswith("subject:")]
        reply = "\n".join(lines).strip()

    return {
        "suggested_reply": reply,
        "evidence": chunks,
        "status": "ok",
        "trust_score": chunks[0]["score"] if chunks else 0.0,
        "trust_label": "High" if chunks and chunks[0]["score"] > 0.7 else "Medium"
    }
