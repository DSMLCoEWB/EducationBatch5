# reply_generator.py
import os
import json
import faiss
import numpy as np
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import torch
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download

HF_REPO_ID = "Username/dataset_name"    #paste your location of the dataset (the dataset is uploaded in hugging face in my case)

INDEX_PATH = hf_hub_download(
    repo_id=HF_REPO_ID,
    filename="faiss.index",
    repo_type="dataset"
)

CHUNKS_PATH = hf_hub_download(
    repo_id=HF_REPO_ID,
    filename="policy_chunks.json",
    repo_type="dataset"
)

# ---------- CONFIG ----------

TOP_K = 5
SIMILARITY_THRESHOLD = 0.60
LLM_MODEL = "gpt-4o-mini"

# ---------- OPENAI ----------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set. Please add it to your .env file")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- EMBEDDING ----------
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device} for embeddings")
embedder = SentenceTransformer(
    "all-MiniLM-L6-v2",
    device=device
)

# ---------- LOAD DATA ----------
try:
    index = faiss.read_index(INDEX_PATH)
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        policy_chunks = json.load(f)

    if index.ntotal != len(policy_chunks):
        raise RuntimeError("FAISS index and policy chunks count mismatch")
    
    print(f"✅ Loaded RAG model with {len(policy_chunks)} policy chunks")
except Exception as e:
    print(f"⚠️ Warning: Could not load RAG model: {e}")
    print("Reply generation will use fallback mode")
    index = None
    policy_chunks = []

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

def retrieve_policy_chunks(email_text: str):
    """Retrieve relevant policy chunks based on email content"""
    if not index or not policy_chunks:
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


def generate_suggested_reply(email_text: str, subject: str = "", sender: str = "") -> str:
    """
    Generate a policy-based reply using retrieved grievance policies.
    Ensures replies reference clause numbers, provide reasoning,
    and suggest resolution steps in an official tone.
    """

    try:
        retrieved = retrieve_policy_chunks(email_text)

        # ---------- CASE 1: POLICY MATCH FOUND ----------
        if retrieved:

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

            return response.choices[0].message.content.strip()

        # ---------- CASE 2: NO POLICY MATCH ----------
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

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.exception("Policy reply generation failed")

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
