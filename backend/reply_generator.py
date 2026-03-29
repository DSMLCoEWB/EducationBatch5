import json
import logging
import os
from pathlib import Path

import faiss
import numpy as np
import torch
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from openai import OpenAI
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------- CONFIG ----------
TOP_K = 5
SIMILARITY_THRESHOLD = 0.60
LLM_MODEL = "gpt-4o-mini"
HF_REPO_ID = os.getenv("HF_REPO_ID", "")

SYSTEM_PROMPT = """
You are a strict policy-bound compliance assistant for a Higher Education Department grievance redressal system.
Rules:
- Use ONLY the provided policy excerpts to generate replies.
- Do NOT rely on outside knowledge.
- If policy does not cover the query, say so explicitly.
- Do NOT invent rules or exceptions.
- Be formal and professional in tone.
- Address the specific grievance raised in the email.
"""

FALLBACK_SYSTEM_PROMPT = """
You are a formal grievance support assistant for the Department of Higher Education, Government of West Bengal.
If no exact policy context is available, provide professional guidance without inventing policy clauses.
"""

load_dotenv()

client = None
embedder = None
index = None
policy_chunks = []
_rag_initialized = False


def _resolve_data_paths():
    # Prefer local checked-in data path in this repository.
    base_dir = Path(__file__).resolve().parent.parent / "reply-generator-main" / "reply-generator-main" / "data"
    local_index = base_dir / "faiss.index"
    local_chunks = base_dir / "policy_chunks.json"

    if local_index.exists() and local_chunks.exists():
        return str(local_index), str(local_chunks)

    # Fallback to Hugging Face if configured.
    if HF_REPO_ID and "Username/dataset_name" not in HF_REPO_ID:
        downloaded_index = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename="faiss.index",
            repo_type="dataset"
        )
        downloaded_chunks = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename="policy_chunks.json",
            repo_type="dataset"
        )
        return downloaded_index, downloaded_chunks

    return None, None


def _ensure_rag_loaded():
    global client, embedder, index, policy_chunks, _rag_initialized

    if _rag_initialized:
        return

    _rag_initialized = True

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        client = OpenAI(api_key=openai_api_key)
    else:
        logger.warning("OPENAI_API_KEY not set. Reply generation will use static fallback response.")

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Using device '%s' for embeddings", device)
        embedder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    except Exception as e:
        logger.warning("Could not initialize embedding model: %s", e)
        embedder = None

    try:
        index_path, chunks_path = _resolve_data_paths()
        if not index_path or not chunks_path:
            raise RuntimeError("RAG data files not found in local data directory and HF_REPO_ID is not configured")

        index = faiss.read_index(index_path)
        with open(chunks_path, "r", encoding="utf-8") as f:
            policy_chunks = json.load(f)

        if index.ntotal != len(policy_chunks):
            raise RuntimeError("FAISS index and policy chunks count mismatch")

        logger.info("Loaded RAG model with %s policy chunks", len(policy_chunks))
    except Exception as e:
        logger.warning("Could not load RAG model: %s", e)
        logger.warning("Reply generation will use no-context fallback mode")
        index = None
        policy_chunks = []

def retrieve_policy_chunks(email_text: str):
    """Retrieve relevant policy chunks based on email content"""
    _ensure_rag_loaded()

    if not index or not policy_chunks:
        return []

    if embedder is None:
        return []

    query_emb = embedder.encode(
        [email_text],
        normalize_embeddings=True
    )
    query_emb = np.asarray(query_emb).astype("float32")

    scores, indices = index.search(query_emb, TOP_K)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1 or score < SIMILARITY_THRESHOLD:
            continue
        results.append({
            "text": policy_chunks[idx]["text"],
            "metadata": policy_chunks[idx]["metadata"],
            "score": float(score)
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def generate_suggested_reply(email_content: str, email_subject: str = "", sender: str = "") -> str:
    """
    Generate a policy-based reply using retrieved grievance policies.
    Ensures replies reference clause numbers, provide reasoning,
    and suggest resolution steps in an official tone.
    """

    try:
        _ensure_rag_loaded()

        email_text = email_content
        subject = email_subject
        retrieved = retrieve_policy_chunks(email_text)

        # ---------- CASE 1: POLICY MATCH FOUND ----------
        if retrieved and client is not None:

            context = "\n\n".join(
                f"Clause {c['metadata']['clause_id']} ({c['metadata']['section']}): {c['text']}"
                for c in retrieved
            )

            user_prompt = f"""
Email Sender: {sender if sender else "Not specified"}
Email Subject: {subject if subject else "Not specified"}
EMAIL CONTENT:
{email_text}
RELEVANT POLICY CLAUSES:
{context}
TASK:
Draft a formal reply from the Department of Higher Education,
Government of West Bengal.
The reply MUST include the following sections:
1. A professional acknowledgement addressing the sender.
2. Reference to the email subject.
3. Policy references including clause numbers and sections.
4. Explanation of why the policy applies to the issue.
5. Clear and practical steps the applicant should follow to resolve the matter.
6. A formal government-style closing.
IMPORTANT RULES:
- Only use the provided policy clauses.
- Do NOT invent policies or rules.
- Maintain a professional government communication tone.
- Clearly cite clause IDs when referencing policies.
"""

            response = client.chat.completions.create(
                model=LLM_MODEL,
                temperature=0.1,
                timeout=20,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )

            return (response.choices[0].message.content or "").strip()

        # ---------- CASE 2: NO POLICY MATCH ----------
        if client is None:
            raise RuntimeError("OpenAI client unavailable")

        fallback_user_prompt = f"""
Email Sender: {sender if sender else "Not specified"}
Email Subject: {subject if subject else "Not specified"}
EMAIL CONTENT:
{email_text}
TASK:
Draft a polite and professional reply from the Department of Higher Education,
Government of West Bengal.
Explain that the issue could not be directly mapped to an existing
grievance policy. Provide guidance on how the sender may submit
their grievance properly or contact the appropriate authority.
RULES:
- Do not invent any policy clauses.
- Maintain an official administrative tone.
"""

        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.2,
            timeout=20,
            messages=[
                {"role": "system", "content": FALLBACK_SYSTEM_PROMPT},
                {"role": "user", "content": fallback_user_prompt}
            ]
        )

        return (response.choices[0].message.content or "").strip()

    except Exception as e:
        logger.exception("Policy reply generation failed: %s", e)

        return """
Dear Sir/Madam,
Thank you for contacting the Department of Higher Education,
Government of West Bengal.
We regret that we are currently unable to process your request due to
a temporary system issue. Kindly try again later or contact the
grievance support desk for further assistance.
Sincerely,
Grievance Support Desk
Department of Higher Education
Government of West Bengal
""".strip()


if __name__ == "__main__":
    # Test the reply generator
    test_email = """
    We are writing to inform you about a suspension case at our college. 
    The employee has been suspended for 6 months due to misconduct. 
    Please advise on the next steps according to the policy.
    """
    
    reply = generate_suggested_reply(
        email_content=test_email,
        email_subject="Suspension Case Query",
        sender="principal@college.edu"
    )
    
    print("=" * 80)
    print("SUGGESTED REPLY:")
    print("=" * 80)
    print(reply)
