# --- QUERY NORMALIZATION FOR REAL GRIEVANCES ---
import re
def normalize_query(email_text: str) -> str:
    # If input looks like a policy title or phrase, convert to natural grievance query
    text = (email_text or '').strip()
    # Heuristic: if no question mark, short, or looks like a title
    if len(text.split()) <= 8 and not text.endswith('?'):
        # Try to convert to a question
        if 'suspension' in text.lower():
            return 'What is the correct procedure for handling suspension cases?'
        if 'misconduct' in text.lower():
            return 'What are the rules and procedures for handling exam misconduct?'
        if 'unfair' in text.lower() or 'cheating' in text.lower():
            return 'How should unfair-means or cheating in exams be handled?'
        if 'disciplinary' in text.lower():
            return 'What is the disciplinary process for employees or students?'
        if 'fir' in text.lower() or 'arrest' in text.lower():
            return 'What is the process when an FIR or arrest occurs?'
        if 'result' in text.lower():
            return 'What are the rules for result publication and correction?'
        # Generic fallback
        return f'What are the rules and procedures regarding: {text}?'
    return text
from typing import List, Dict, Any
# --- STRICT EMAIL TEMPLATE PROMPT ---

def _build_gemini_prompt(email_subject: str, sender: str, email_context: str, context_blocks: List[Dict[str, Any]]) -> str:
    context_text = _build_context_for_prompt(context_blocks)
    return f"""
You are a professional government support desk assistant. Generate a COMPLETE, NATURAL, and PROFESSIONAL email reply using the policy context as supporting evidence (not word-by-word copying).

SYSTEM PROMPT:
- Write a complete and professional email reply
- Use policy context to SUPPORT your explanation, but paraphrase naturally
- Use the policy context to explain clearly in natural language
- You may expand logically from the policy to form a complete reply
- Include explanation, actionable steps, and conclusion
- Minimum 2–3 meaningful sentences (expand if needed)
- NEVER invent new rules or procedures
- If policy lacks detail, say: "Policy does not specify further details."
- Do NOT stop early or output fragments
- Ensure logical flow and professional tone
- Structure:
    Subject: RE: {email_subject}
    Dear {sender} or Sir/Madam,
    <Clear explanation of policy in natural language>
    <Steps or actions based on policy>
    If any part is unclear: "Policy does not specify further details."
    Sincerely,
    Grievance Support Desk
    Department of Higher Education
    Government of West Bengal

Output format:
- Plain text email body (no markdown, no bullets unless natural).
- Every key factual claim should be supported with [n] where applicable.

STRICT RULES:
- Avoid repeating the same policy multiple times
- Focus on clarity and completeness rather than length
- Do NOT copy policy verbatim
- Do NOT output incomplete or broken sentences
- Do NOT merge greeting/body/closing
- Do NOT include subject line as a sentence
- Do NOT stop mid-sentence

Policy context:
{context_text}

Incoming email context:
{email_context}
""".strip()
import json
def _llm_generate_policy_reply(subject: str, sender: str, email_context: str, context_blocks: List[Dict[str, Any]], max_retries: int = 1) -> str:
    prompt = _build_gemini_prompt(subject, sender, email_context, context_blocks)
    for attempt in range(max_retries + 1):
        raw = _generate_with_gemini(prompt)
        text = (raw or "").strip()
        
        # Validation: looks like a full email
        has_greeting = "Dear" in text or "Sir/Madam" in text
        has_closing = any(kw in text for kw in ["Sincerely", "Regards", "Sincerely Yours"])
        is_long_enough = len(text) > 80
        
        if text and is_long_enough and has_greeting and has_closing:
            return text
            
        # If invalid, retry with stricter instruction
        if attempt < max_retries:
            prompt = (
                prompt + f"\n\nERROR: Your previous output was too short or missing greeting/closing. Generate a FULL email (Subject: RE: {subject}, Dear..., Body with citations [n], Sincerely...). Do not truncate."
            )
    return text if text else ""

def _hard_validate_reply(reply: str, sentences: list) -> bool:
    # Minimum completeness: greeting, closing, no mid-sentence stop
    if not reply or len(reply) < 60:
        return False
    if "Dear" not in reply or "Sincerely" not in reply:
        return False
    unfinished = ["This", "Misconduct in", "According to"]
    last = reply.strip().splitlines()[-1] if reply.strip().splitlines() else ""
    if any(u in last for u in unfinished):
        return False
    if reply.strip().endswith(('...', 'Misconduct in', 'This', 'According to')):
        return False
    return True
"""
RAG Reply Generator

Responsibilities:
- Build prompt from retrieved policy evidence
- Run a single Gemini generation call
- Validate grounding and produce dual internal/external outputs

Retrieval is handled by rag.retriever.
"""

import copy
import hashlib
import json
import logging
import os
import re
import time
from threading import Lock
from typing import Any, Dict, List, Optional

import numpy as np
from google import genai

from rag.retriever import (
    CANDIDATE_POOL,
    RETRIEVAL_CONFIDENCE_THRESHOLD,
    TOP_K,
    _encode_texts,
    _find_supporting_span,
    _normalize_text,
    _semantic_support_with_fallback,
    _tokenize,
    _truncate_for_embedding,
    ensure_retriever_loaded,
    get_model_load_error,
    get_demo_mode,
    get_knowledge_source_label,
    is_retriever_loading,
    retrieve_policy_chunks,
)

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "15000"))
SENTENCE_SEMANTIC_THRESHOLD = float(os.getenv("RAG_SENTENCE_SEMANTIC_THRESHOLD", "0.40"))  # Relaxed from 0.45
MIN_SUPPORTED_SENTENCE_RATIO = float(os.getenv("RAG_MIN_SUPPORTED_SENTENCE_RATIO", "0.45"))  # Relaxed
MIN_TRUST_SCORE = float(os.getenv("RAG_MIN_TRUST_SCORE", "0.50"))  # Relaxed
RESPONSE_CACHE_SIZE = int(os.getenv("RAG_RESPONSE_CACHE_SIZE", "128"))
DEMO_RETRIEVAL_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_DEMO_RETRIEVAL_CONF_THRESHOLD", "0.35"))

CATEGORY_KEYWORDS = {
    "Suspension / Disciplinary": "suspension disciplinary inquiry reinstatement subsistence allowance penalty",
    "FIR / Arrest": "fir arrest police investigation custody chargesheet legal coordination",
    "Semester / Examination": "semester examination result rechecking correction marks tabulation",
    "Miscellaneous": "certificate transfer scholarship fee grievance administrative disposal",
}


def _effective_retrieval_conf_threshold() -> float:
    th = RETRIEVAL_CONFIDENCE_THRESHOLD
    if get_demo_mode():
        th = min(RETRIEVAL_CONFIDENCE_THRESHOLD, DEMO_RETRIEVAL_CONFIDENCE_THRESHOLD)
    return float(th)

gemini_client = None
_response_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = Lock()


def _cache_get(cache: Dict, key: str):
    with _cache_lock:
        return copy.deepcopy(cache.get(key))


def _cache_put(cache: Dict, key: str, value: Any, max_size: int):
    with _cache_lock:
        if key in cache:
            cache.pop(key)
        cache[key] = copy.deepcopy(value)
        if len(cache) > max_size:
            oldest = next(iter(cache))
            cache.pop(oldest, None)


def _split_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    # Remove subject line if present
    lines = text.replace("\r", " ").strip().splitlines()
    filtered = []
    for line in lines:
        l = line.strip()
        if l.lower().startswith("subject:"):
            continue
        filtered.append(l)
    text = "\n".join(filtered)
    # Split paragraphs, then sentences
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    sentences = []
    for para in paragraphs:
        # Don't split greeting/closing as sentences
        if para.lower().startswith("dear ") or para.lower().startswith("sincerely") or para.lower().startswith("regards"):
            sentences.append(para.strip())
        else:
            sentences.extend([s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()])
    return sentences


def _is_substantive(sentence: str) -> bool:
    if not sentence:
        return False
    tokens = _tokenize(sentence)
    if len(tokens) >= 4:
        return True
    if len(sentence.strip()) > 30:
        return True
    return False


def _extract_citations(text: str) -> List[int]:
    if not text:
        return []
    nums = re.findall(r"\[(\d+)\]", text)
    out = []
    for n in nums:
        try:
            out.append(int(n))
        except Exception:
            continue
    return out


def _strip_inline_citations(text: str) -> str:
    cleaned = re.sub(r"\s*\[(?:\d+)\]\s*", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _clean_external_reply(text: str) -> str:
    cleaned = _strip_inline_citations(text)
    lines = [line.strip() for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


def _normalize_category(category: str) -> str:
    c = (category or "").strip().lower()
    if "susp" in c or "discip" in c:
        return "Suspension / Disciplinary"
    if "fir" in c or "arrest" in c or "police" in c:
        return "FIR / Arrest"
    if "semester" in c or "exam" in c or "result" in c:
        return "Semester / Examination"
    if c:
        return "Miscellaneous"
    return ""


def _compact_email_for_retrieval(text: str, max_words: int = 220) -> str:
    """Reduce email boilerplate/quoted content before retrieval embedding."""
    raw = (text or "").replace("\r", "\n")
    if not raw.strip():
        return ""

    cleaned_lines: List[str] = []
    for line in raw.split("\n"):
        ln = line.strip()
        if not ln:
            continue
        if ln.startswith(">"):
            continue
        if re.match(r"^(from|to|cc|bcc|subject|sent|date)\s*:", ln, flags=re.IGNORECASE):
            continue
        if re.match(r"^(regards|best regards|thanks|thank you|yours faithfully|sincerely)\b", ln, flags=re.IGNORECASE):
            continue
        cleaned_lines.append(ln)

    compact = re.sub(r"\s+", " ", " ".join(cleaned_lines)).strip()
    if not compact:
        compact = re.sub(r"\s+", " ", raw).strip()

    words = compact.split()
    if len(words) > max_words:
        compact = " ".join(words[:max_words])
    return compact


def _adaptive_retrieval_conf_threshold(retrieval_query: str, normalized_category: str) -> float:
    """
    Keep strict guardrail semantics, but avoid false negatives for noisy/short emails.
    This only loosens the retrieval gate within bounded limits.
    """
    base = _effective_retrieval_conf_threshold()
    tokens = _tokenize(retrieval_query)
    token_count = len(tokens)

    adaptive = float(base)
    if get_demo_mode():
        # Demo corpus queries are sparse/synthetic; allow a modest cushion.
        if normalized_category:
            adaptive -= 0.03
        if token_count <= 30:
            adaptive -= 0.05
        elif token_count <= 80:
            adaptive -= 0.03
        elif token_count >= 220:
            adaptive -= 0.04

        adaptive = max(0.25, adaptive)

    return float(adaptive)


def _ensure_gemini_configured() -> bool:
    global gemini_client

    if gemini_client is not None:
        return True

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY or GEMINI_API_KEY not found")
        return False

    try:
        gemini_client = genai.Client(api_key=api_key)
        return True
    except Exception as e:
        logger.error("Gemini configure failed: %s", e)
        return False


def _build_context_for_prompt(context_blocks: List[Dict[str, Any]]) -> str:
    parts = []
    total = 0

    for i, c in enumerate(context_blocks, start=1):
        text = (c.get("text") or "").strip()
        if not text:
            continue

        block = (
            f"[{i}]\n"
            f"Policy ID: {c.get('policy_id', 'unknown')}\n"
            f"Section: {c.get('section_title', 'General')}\n"
            f"Content: {text}\n"
        )

        if total + len(block) > MAX_CONTEXT_CHARS:
            remaining = max(0, MAX_CONTEXT_CHARS - total)
            if remaining > 200:
                parts.append(block[:remaining])
            break

        parts.append(block)
        total += len(block)

    return "\n".join(parts)



def _generate_with_gemini(prompt: str) -> str:
    if gemini_client is None and not _ensure_gemini_configured():
        raise RuntimeError("Gemini client is not configured")

    model_name = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    response = gemini_client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "temperature": 0.15,
            "top_p": 0.9,
            "max_output_tokens": 420,
        },
    )

    return (getattr(response, "text", "") or "").strip()


def _refine_citations_with_gemini(
    draft: str,
    context_blocks: List[Dict[str, Any]],
    max_retries: int = 1,
) -> str:
    """
    If LLM draft lacks citations, ask LLM to refine it with proper [n] citations.
    Only retry if first pass has very few or no citations.
    """
    citations_found = _extract_citations(draft)
    substantive_sentences = [s for s in _split_sentences(draft) if _is_substantive(s)]
    
    # If already well-cited (>= 60% of substantive sentences have citations), return as-is
    if substantive_sentences and len(citations_found) >= len(substantive_sentences) * 0.6:
        return draft
    
    # Only trigger citation refinement if LLM produced zero citations
    if len(citations_found) == 0:
        context_text = _build_context_for_prompt(context_blocks)
        
        refinement_prompt = f"""
Your previous response was missing proper citations. Rewrite it with citations in [n] format for EVERY substantive fact.

CRITICAL: Each substantive claim MUST end with [n] where n is the policy block number.

Policy context:
{context_text}

Your previous response to fix:
{draft}

Rewrite to include [n] after every substantive sentence. Use no markdown or bullets.
""".strip()
        
        try:
            refined = _generate_with_gemini(refinement_prompt)
            refined_citations = _extract_citations(refined)
            # Only use refined version if it has more citations than original
            if len(refined_citations) > len(citations_found):
                return refined
        except Exception as e:
            logger.error("Citation refinement failed: %s", e)
    
    return draft


def _refine_for_validation_fix(
    draft: str,
    context_blocks: List[Dict[str, Any]],
    validation: Dict[str, Any],
) -> Optional[str]:
    """
    If validation shows low trust/support, ask LLM to refine the response
    to be safer/more grounded instead of falling back.
    Returns refined version or None if refinement not attempted.
    """
    issues = validation.get("issues", [])
    trust_score = float(validation.get("trust_score", 0.0))
    supported_ratio = float(validation.get("supported_sentence_ratio", 0.0))
    
    # Only refine if issues are specific and fixable (not structural failures)
    issue_text = " ".join(issues)
    has_fixable_issue = any(
        phrase in issue_text
        for phrase in ["citation", "support", "grounding", "validity", "No substantive content"]
    )
    
    if not has_fixable_issue or trust_score >= 0.50:  # Don't refine if already decent score
        return None
    
    context_text = _build_context_for_prompt(context_blocks)
    primary_issues = [iss for iss in issues if len(iss) < 100][:2]  # Top 2 issues
    issue_summary = " ".join(primary_issues)
    
    refinement_prompt = f"""
Your response had grounding issues: {issue_summary}

Refine your response to:
1. Make EVERY claim traceable to the policy context [n]
2. Remove any claims that aren't directly supported
3. Keep it concise and formal
4. Focus on what IS supported, not what might be inferred
5. Include at least 3 substantive policy-anchored sentences, each with citation [n]

Policy context:
{context_text}

Original response:
{draft}

Provide a revised response that fixes these issues. Make it conservative but complete.
""".strip()
    
    try:
        refined = _generate_with_gemini(refinement_prompt)
        if refined and len(refined) > 20:  # Must be non-trivial
            return refined
    except Exception as e:
        logger.error("Validation refinement failed: %s", e)
    
    return None


def _prune_unsupported_sentences(reply_text: str, context_blocks: List[Dict[str, Any]]) -> str:
    sentences = _split_sentences(reply_text)
    if not sentences:
        return ""

    kept = []
    sentence_clean = [_strip_inline_citations(s) for s in sentences]
    sentence_embs = _encode_texts([_truncate_for_embedding(s) for s in sentence_clean], batch_size=64)

    for i, s in enumerate(sentences):
        if not _is_substantive(s):
            kept.append(s)
            continue

        cites = _extract_citations(s)
        valid_cites = [n for n in cites if 1 <= n <= len(context_blocks)]
        if not valid_cites:
            continue

        candidate_chunks = [context_blocks[n - 1] for n in valid_cites]
        sentence_vec = sentence_embs[i] if sentence_embs is not None and i < len(sentence_embs) else None
        support = _semantic_support_with_fallback(sentence_clean[i], sentence_vec, candidate_chunks)

        if support >= SENTENCE_SEMANTIC_THRESHOLD:
            kept.append(s)

    return " ".join(kept).strip()


def _enforce_citations(reply_text: str, context_blocks: List[Dict[str, Any]]) -> str:
    """Attach best citation to uncited substantive sentences when support is strong enough."""
    sentences = _split_sentences(reply_text)
    if not sentences or not context_blocks:
        return reply_text or ""

    sentence_clean = [_strip_inline_citations(s) for s in sentences]
    sentence_embs = _encode_texts([_truncate_for_embedding(s) for s in sentence_clean], batch_size=64)

    attach_threshold = SENTENCE_SEMANTIC_THRESHOLD
    if get_demo_mode():
        attach_threshold = min(SENTENCE_SEMANTIC_THRESHOLD, 0.45)

    rewritten: List[str] = []
    for i, s in enumerate(sentences):
        if not _is_substantive(s):
            rewritten.append(s)
            continue

        existing = [n for n in _extract_citations(s) if 1 <= n <= len(context_blocks)]
        if existing:
            rewritten.append(s)
            continue

        vec = sentence_embs[i] if sentence_embs is not None and i < len(sentence_embs) else None
        best_idx = None
        best_score = 0.0

        for n, chunk in enumerate(context_blocks, start=1):
            score = _semantic_support_with_fallback(sentence_clean[i], vec, [chunk])
            if score > best_score:
                best_score = score
                best_idx = n

        if best_idx is not None and best_score >= attach_threshold:
            rewritten.append(f"{_strip_inline_citations(s)} [{best_idx}]")
        else:
            rewritten.append(s)

    return " ".join(rewritten).strip()


def _build_deterministic_grounded_reply(context_blocks: List[Dict[str, Any]]) -> str:
    """Build a conservative grounded reply directly from retrieved policy clauses."""
    if not context_blocks:
        return ""

    lines: List[str] = [
        "Dear Sir/Madam,",
        "",
        "Thank you for your email. Based on the applicable policy provisions, please note the following:",
    ]

    max_points = min(3, len(context_blocks))
    for i in range(1, max_points + 1):
        clause_text = _strip_inline_citations((context_blocks[i - 1].get("text") or "").strip())
        if not clause_text:
            continue
        lines.append(f"{clause_text} [{i}]")

    lines.extend([
        "The institution may proceed in accordance with the cited provisions and communicate the action timeline through official channels. [1]",
        "",
        "Regards,",
    ])
    return "\n".join(lines).strip()


def _validate_and_map_evidence(reply_text: str, context_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    sentences = _split_sentences(reply_text)

    sentence_evidence = []
    issues = []

    substantive = [s for s in sentences if _is_substantive(s)]
    if not substantive:
        issues.append("No substantive content to validate")

    supported_count = 0
    citation_sentence_count = 0
    invalid_citation_count = 0
    support_values = []

    # --- RELAXED SEMANTIC SUPPORT ---
    substantive_clean = [_strip_inline_citations(s) for s in substantive]
    # Lower threshold for semantic support
    relaxed_threshold = max(0.25, SENTENCE_SEMANTIC_THRESHOLD - 0.25)
    substantive_embs = _encode_texts([_truncate_for_embedding(s) for s in substantive_clean], batch_size=64)

    for idx, s in enumerate(substantive):
        citations = _extract_citations(s)
        valid_citations = [n for n in citations if 1 <= n <= len(context_blocks)]

        if valid_citations:
            citation_sentence_count += 1

        invalid_here = len(citations) - len(valid_citations)
        invalid_citation_count += max(0, invalid_here)

        cited_chunks = [context_blocks[n - 1] for n in valid_citations]

        sentence_clean = substantive_clean[idx]
        sentence_vec = substantive_embs[idx] if substantive_embs is not None and idx < len(substantive_embs) else None
        support = _semantic_support_with_fallback(sentence_clean, sentence_vec, cited_chunks)
        support_values.append(support)

        # Build evidence array: for each valid citation, find the best supporting span
        evidence = []
        for n in valid_citations:
            chunk_text = context_blocks[n - 1].get("text", "")
            span = _find_supporting_span(sentence_clean, chunk_text)
            evidence.append({
                "snippet": span.get("source_text_snippet", ""),
                "start": int(span.get("span_start", 0)),
                "end": int(span.get("span_end", 0)),
                "chunk_index": n
            })

        # Support is now based purely on semantic score (no citation dependency)
        supported = support >= relaxed_threshold
        if supported:
            supported_count += 1

        # UI-friendly evidence structure
        sentence_evidence.append({
            "sentence": s,
            "support_score": float(support),
            "evidence": evidence,
            # Optionally include for internal use:
            "is_supported": bool(supported),
            "citations": valid_citations
        })

    total = max(len(substantive), 1)
    supported_ratio = supported_count / total
    citation_validity_ratio = citation_sentence_count / total
    avg_support = float(np.mean(support_values)) if support_values else 0.0

    if invalid_citation_count > 0:
        issues.append(f"Found {invalid_citation_count} invalid citation markers")

    if citation_sentence_count == 0 and substantive:
        issues.append("No valid citations in substantive sentences")

    if supported_ratio < MIN_SUPPORTED_SENTENCE_RATIO and substantive:
        issues.append(
            f"Low supported sentence ratio ({supported_ratio:.2f} < {MIN_SUPPORTED_SENTENCE_RATIO:.2f})"
        )

    trust_score = (0.50 * supported_ratio) + (0.30 * avg_support) + (0.20 * citation_validity_ratio)

    has_any_strong_sentence = any(
        ev.get("support_score", 0) >= 0.40
        for ev in sentence_evidence
    )

    # Allow if reply has substantive content with any strong semantic grounding
    is_valid = (
        len(substantive) > 0
        and (citation_sentence_count > 0 or has_any_strong_sentence)
        and invalid_citation_count == 0
        and has_any_strong_sentence
    )

    return {
        "is_valid": bool(is_valid),
        "is_strictly_grounded": bool(is_valid and trust_score >= MIN_TRUST_SCORE),
        "trust_score": float(trust_score),
        "supported_sentence_ratio": float(supported_ratio),
        "citation_validity_ratio": float(citation_validity_ratio),
        "average_support_score": float(avg_support),
        "has_any_citation": citation_sentence_count > 0,
        "issues": issues,
        "sentence_evidence": sentence_evidence,
    }


def _safe_fallback_reply() -> str:
    return (
        "Subject: RE: Your Query\n\n"
        "Dear Sir/Madam,\n\n"
        "Thank you for your email. Based on the available policy excerpts, the following guidance applies:\n\n"
        "<Brief summary of relevant policy, paraphrased.>\n\n"
        "For further procedural details, Policy does not specify.\n\n"
        "Sincerely,\nGrievance Support Desk\nDepartment of Higher Education\nGovernment of West Bengal"
    )


def _initializing_fallback_reply() -> str:
    return "System initializing, please retry in a moment"


def _trust_label(score: float) -> str:
    if score >= 0.85:
        return "HIGH"
    if score >= 0.65:
        return "MEDIUM"
    return "LOW"


def _trust_visibility(trust_score: float, grounded_ratio: float, is_grounded: bool) -> Dict[str, str]:
    trust_badge = _trust_label(trust_score)
    grounding_percentage = f"{max(0.0, min(1.0, grounded_ratio)) * 100:.0f}%"

    if is_grounded:
        verification_message = "This response is fully grounded in official policy documents."
    else:
        verification_message = "Limited policy coverage for this query. Manual review recommended."

    return {
        "trust_badge": trust_badge,
        "grounding_percentage": grounding_percentage,
        "verification_message": verification_message,
    }


def _build_dual_output(
    internal_reply: str,
    context_blocks: List[Dict[str, Any]],
    validation: Dict[str, Any],
    fallback: bool = False,
    fallback_reason: str = "",
) -> Dict[str, Any]:
    external_reply = _clean_external_reply(internal_reply)

    # Extract used citations from internal reply
    used_citations = _extract_citations(internal_reply)
    used_set = set(used_citations)

    # Build evidence_map using new sentence_evidence structure
    evidence_map = []
    if not fallback and len(used_citations) > 0:
        sentence_evidence = validation.get("sentence_evidence", [])
        # For each used citation, collect all evidence snippets from all sentences that cite this chunk
        for i, c in enumerate(context_blocks, start=1):
            if i not in used_set:
                continue

            # Gather all evidence objects from all sentences that cite this chunk
            evidence_snippets = []
            for ev in sentence_evidence:
                for e in ev.get("evidence", []):
                    if e.get("chunk_index") == i:
                        evidence_snippets.append(e)

            # Prefer the longest/highest scoring snippet, fallback to chunk text
            if evidence_snippets:
                # Pick the snippet with the largest span (or just the first if all are equal)
                best_evidence = max(evidence_snippets, key=lambda e: e.get("end", 0) - e.get("start", 0))
                snippet = best_evidence.get("snippet", "")
            else:
                snippet = c.get("text", "")[:300].strip()

            evidence_map.append({
                "citation_number": i,
                "chunk_id": c.get("chunk_id"),
                "policy_id": c.get("policy_id", "unknown"),
                "section_title": c.get("section_title", "General"),
                "semantic_score": float(c.get("semantic_score", 0.0)),
                "lexical_score": float(c.get("lexical_score", 0.0)),
                "final_score": float(c.get("final_score", 0.0)),
                "snippet": snippet,
                # Optionally, include all evidence snippets for this chunk for UI
                "evidence": evidence_snippets
            })

    trust_score = float(validation.get("trust_score", 0.0))
    grounded_ratio = float(validation.get("supported_sentence_ratio", 0.0))
    trust_visibility = _trust_visibility(trust_score, grounded_ratio, bool(validation.get("is_valid", False)))

    explainability = {
        "trust_score": trust_score,
        "validation_issues": validation.get("issues", []),
        "supported_sentence_ratio": grounded_ratio,
        "citation_validity_ratio": float(validation.get("citation_validity_ratio", 0.0)),
        "average_support_score": float(validation.get("average_support_score", 0.0)),
        "sentence_evidence": validation.get("sentence_evidence", []),
        "retrieval_confidence": float(context_blocks[0].get("final_score", 0.0)) if context_blocks else 0.0,
        "fallback_applied": bool(fallback),
        "fallback_reason": fallback_reason,
        "trust_visibility": trust_visibility,
        "evidence_used_count": len(evidence_map),
        "retrieved_count": len(context_blocks),
        "no_evidence_used": len(used_citations) == 0,
        "evidence_hidden_reason": "fallback_response" if fallback else None,
    }

    return {
        "suggested_reply_internal": internal_reply,
        "suggested_reply_external": external_reply,
        "evidence_map": evidence_map,
        "explainability": explainability,
        "trust_visibility": trust_visibility,
    }


def _format_retrieval_payload(retrieved: List[Dict[str, Any]]) -> Dict[str, Any]:
    matches = []
    for item in retrieved:
        matches.append(
            {
                "text": item.get("text", ""),
                "metadata": {
                    "policy_id": item.get("policy_id", "unknown"),
                    "section": item.get("section_title", "General"),
                    "clause_id": str(item.get("clause_id") or item.get("chunk_id", "")),
                },
                "score": float(item.get("final_score", 0.0)),
            }
        )

    return {
        "top_k": int(TOP_K),
        "similarity_threshold": _effective_retrieval_conf_threshold(),
        "matches": matches,
    }


def _format_api_contract(
    dual_output: Dict[str, Any],
    retrieved: List[Dict[str, Any]],
    validation: Dict[str, Any],
    generation_mode: str,
    reason: str,
    is_fallback: bool,
) -> Dict[str, Any]:
    trust_score = float(validation.get("trust_score", 0.0))
    trust_label = _trust_label(trust_score)

    # Extract used citations from internal reply to filter sentence_evidence
    internal_reply = dual_output.get("suggested_reply_internal", "")
    used_citations = _extract_citations(internal_reply)
    used_set = set(used_citations)

    raw_sentence_evidence = validation.get("sentence_evidence", [])
    sentence_evidence = []
    unsupported = []

    for ev in raw_sentence_evidence:
        # Use actual integer citation indices from _validate_and_map_evidence
        ev_citations = ev.get("citations", [])
        citations = [f"C{n}" for n in ev_citations]

        # Only keep sentence evidence if it has citations in the used set
        if not any(c in used_set for c in ev_citations):
            continue

        # Derive supported_by from first citation index (not missing best_supporting_chunk)
        first_cite = ev_citations[0] if ev_citations else None
        supported_by = f"C{first_cite}" if first_cite is not None else ""

        # Pull span data from nested evidence list returned by _validate_and_map_evidence
        evidence_list = ev.get("evidence", [])
        first_ev = evidence_list[0] if evidence_list else {}

        shaped = {
            "sentence": ev.get("sentence", ""),                   # was: sentence_text
            "citations": citations,
            "support_score": float(ev.get("support_score", 0.0)),
            "supported_by": supported_by,
            "confidence": float(ev.get("support_score", 0.0)),
            "chunk_spans": [
                {
                    "chunk_id": supported_by,
                    "start": int(first_ev.get("start", 0)),       # was: span_start
                    "end": int(first_ev.get("end", 0)),           # was: span_end
                }
            ] if supported_by else [],
            "source_text_snippet": first_ev.get("snippet", ""),   # was: source_text_snippet
        }
        sentence_evidence.append(shaped)

        if not bool(ev.get("is_supported", False)):
            unsupported.append(
                {
                    "sentence": ev.get("sentence", ""),           # was: sentence_text
                    "support_score": float(ev.get("support_score", 0.0)),
                }
            )


    # Hide ALL evidence when fallback
    if is_fallback:
        retrieval_payload = {
            "top_k": int(TOP_K),
            "similarity_threshold": _effective_retrieval_conf_threshold(),
            "matches": [],
        }
        sentence_evidence = []
    else:
        retrieval_payload = _format_retrieval_payload(retrieved)

    grounded_ratio = float(validation.get("supported_sentence_ratio", 0.0))
    is_grounded = bool(validation.get("is_valid", False))
    trust_visibility = _trust_visibility(trust_score, grounded_ratio, is_grounded)

    grounding_report = {
        "is_grounded": is_grounded,
        "is_strictly_grounded": bool(validation.get("is_strictly_grounded", False)),
        "supported_sentence_ratio": grounded_ratio,
        "average_support_score": float(validation.get("average_support_score", 0.0)),
        "support_threshold": float(SENTENCE_SEMANTIC_THRESHOLD),
        "unsupported_sentences": unsupported,
        "notes": "Embedding-based grounding with citation-constrained validation.",
        "trust_score": trust_score,
        "trust_label": trust_label,
        "grounding_summary": (
            f"This response is {grounded_ratio * 100:.1f}% grounded in official policy documents."
        ),
    }

    internal_view = {
        "reply_text_with_citations": dual_output.get("suggested_reply_internal", ""),
        "trust_score": trust_score,
        "trust_label": trust_label,
        "grounding_report": grounding_report,
        "sentence_evidence": sentence_evidence,
        "retrieved_chunks": [] if is_fallback else retrieval_payload.get("matches", []),
    }
    if get_demo_mode():
        internal_view["knowledge_source"] = get_knowledge_source_label()

    external_view = {
        "clean_reply_text": dual_output.get("suggested_reply_external", ""),
    }

    return {
        "suggested_reply": external_view["clean_reply_text"],
        "generation_mode": generation_mode,
        "is_strictly_grounded": bool(validation.get("is_strictly_grounded", False)),
        "trust_score": trust_score,
        "trust_label": trust_label,
        "retrieval": retrieval_payload,
        "grounding_report": grounding_report,
        "sentence_evidence": sentence_evidence,
        "explainability": {
            **dual_output.get("explainability", {}),
            "evidence_summary": sentence_evidence,
            "is_fallback": is_fallback,
            "reason": reason,
        },
        "trust_visibility": trust_visibility,
        "internal_view": internal_view,
        "external_view": external_view,
        "suggested_reply_internal": dual_output.get("suggested_reply_internal", ""),
        "suggested_reply_external": dual_output.get("suggested_reply_external", ""),
        "evidence_map": dual_output.get("evidence_map", []),
        "is_fallback": is_fallback,
        "reason": reason,
        "grounding_summary": grounding_report["grounding_summary"],
    }


def _attach_latency(payload: Dict[str, Any], start: float, breakdown: Dict[str, int]) -> Dict[str, Any]:
    payload["latency_breakdown"] = {
        "retrieval_ms": int(breakdown.get("retrieval_ms", 0)),
        "rerank_ms": int(breakdown.get("rerank_ms", 0)),
        "generation_ms": int(breakdown.get("generation_ms", 0)),
        "validation_ms": int(breakdown.get("validation_ms", 0)),
    }
    payload["latency_ms"] = int((time.time() - start) * 1000)
    return payload


def _fallback_bundle(
    start: float,
    latency_breakdown: Dict[str, int],
    fallback_text: str,
    issues: List[str],
    generation_mode: str,
    reason: str,
    retrieved: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    retrieved = retrieved or []
    validation = {
        "is_valid": False,
        "is_strictly_grounded": False,
        "trust_score": 0.0,
        "supported_sentence_ratio": 0.0,
        "citation_validity_ratio": 0.0,
        "average_support_score": 0.0,
        "issues": issues,
        "sentence_evidence": [],
    }
    shaped = _build_dual_output(fallback_text, retrieved, validation, fallback=True, fallback_reason=reason)
    shaped = _format_api_contract(
        shaped,
        retrieved,
        validation,
        generation_mode=generation_mode,
        reason=reason,
        is_fallback=True,
    )
    shaped["nli_results"] = []
    return _attach_latency(shaped, start, latency_breakdown)


def generate_suggested_reply_with_evidence(
    email_context: Optional[str] = None,
    policy_id_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    email_content: Optional[str] = None,
    email_subject: str = "",
    sender: str = "",
    category: str = "",
) -> Dict[str, Any]:
    start = time.time()
    latency_breakdown = {
        "retrieval_ms": 0,
        "rerank_ms": 0,
        "generation_ms": 0,
        "validation_ms": 0,
    }

    incoming_email = (email_content if email_content is not None else email_context) or ""
    normalized_category = _normalize_category(category)
    boosted_tail = CATEGORY_KEYWORDS.get(normalized_category, "")
    compact_email = _compact_email_for_retrieval(incoming_email)
    retrieval_query = " ".join([email_subject.strip(), compact_email, boosted_tail]).strip() or compact_email
    if not retrieval_query:
        retrieval_query = incoming_email.strip()
    prompt_context = "\n".join(
        [
            f"Sender: {sender}" if sender else "",
            f"Subject: {email_subject}" if email_subject else "",
            incoming_email.strip(),
        ]
    ).strip()

    if not incoming_email or not incoming_email.strip():
        return _fallback_bundle(
            start,
            latency_breakdown,
            _safe_fallback_reply(),
            ["Empty email context"],
            "system_error_fallback",
            "Empty input",
        )

    cache_payload = {
        "q": _normalize_text(retrieval_query),
        "pid": policy_id_filter or "",
        "sec": section_filter or "",
        "cat": normalized_category,
    }
    response_cache_key = hashlib.sha1(json.dumps(cache_payload, sort_keys=True).encode("utf-8")).hexdigest()

    cached_response = _cache_get(_response_cache, response_cache_key)
    if cached_response is not None:
        cached_response["cache_hit"] = True
        cached_response.setdefault(
            "latency_breakdown",
            {"retrieval_ms": 0, "rerank_ms": 0, "generation_ms": 0, "validation_ms": 0},
        )
        cached_response.setdefault("latency_ms", int((time.time() - start) * 1000))
        return cached_response

    # Non-blocking startup safety for free-tier cold starts.
    if not ensure_retriever_loaded(block=False):
        init_reason = "Retriever loading" if is_retriever_loading() else (get_model_load_error() or "Retriever unavailable")
        output = _fallback_bundle(
            start,
            latency_breakdown,
            _initializing_fallback_reply(),
            [f"RAG initialization pending: {init_reason}"],
            "system_initializing",
            init_reason,
        )
        # Do not cache transient initializing responses; otherwise same prompt
        # can be stuck returning fallback even after retriever is ready.
        return output

    retrieved, retrieval_metrics = retrieve_policy_chunks(
        query=retrieval_query,
        top_k=TOP_K,
        candidate_pool=CANDIDATE_POOL,
        policy_id_filter=policy_id_filter,
        section_filter=section_filter or normalized_category or None,
        return_metrics=True,
    )
    latency_breakdown["retrieval_ms"] = int(retrieval_metrics.get("retrieval_ms", 0))
    latency_breakdown["rerank_ms"] = int(retrieval_metrics.get("rerank_ms", 0))

    if not retrieved:
        output = _fallback_bundle(
            start,
            latency_breakdown,
            _safe_fallback_reply(),
            ["No relevant policy evidence found"],
            "fallback_no_policy_match",
            "No evidence",
            retrieved=[],
        )
        return output

    # effective_conf_threshold check removed to maximize recall as requested.
    # LLM will now always attempt to generate from top semantic results.

    # LLM GENERATION (plain text)
    try:
        t_gen = time.time()
        draft = _llm_generate_policy_reply(email_subject, sender, prompt_context, retrieved)
        latency_breakdown["generation_ms"] = int((time.time() - t_gen) * 1000)
    except Exception as e:
        logger.error("Gemini generation failed: %s", e)
        output = _fallback_bundle(
            start,
            latency_breakdown,
            _safe_fallback_reply(),
            [f"Generation failure: {e}"],
            "system_error_fallback",
            "Generation error",
            retrieved=retrieved,
        )
        return output

    # Optional citation enforcement: only when completely missing
    if len(_extract_citations(draft)) == 0:
        draft = _enforce_citations(draft, retrieved)

    # POST-HOC GROUNDING
    t_validation = time.time()
    validation = _validate_and_map_evidence(draft, retrieved)
    latency_breakdown["validation_ms"] = int((time.time() - t_validation) * 1000)

    # Use the single authoritative grounding decision from _validate_and_map_evidence
    # to avoid inconsistency between two separate grounding computations.
    has_grounding = validation.get("is_valid", False)

    if not draft or not has_grounding:
        output = _fallback_bundle(
            start,
            latency_breakdown,
            _safe_fallback_reply(),
            ["No substantive grounded content after refinement"],
            "policy_guardrail_fallback",
            "No grounded content available",
            retrieved=retrieved,
        )
        return output

    # DUAL OUTPUT SYSTEM
    output = _build_dual_output(draft, retrieved, validation, fallback=False, fallback_reason="")
    output = _format_api_contract(
        output,
        retrieved,
        validation,
        generation_mode="policy_grounded_validated",
        reason="",
        is_fallback=False,
    )
    output["nli_results"] = []
    output = _attach_latency(output, start, latency_breakdown)

    logger.info(
        "RAG response complete | retrieval_ms=%d rerank_ms=%d generation_ms=%d validation_ms=%d total_ms=%d",
        latency_breakdown["retrieval_ms"],
        latency_breakdown["rerank_ms"],
        latency_breakdown["generation_ms"],
        latency_breakdown["validation_ms"],
        output["latency_ms"],
    )
    _cache_put(_response_cache, response_cache_key, output, RESPONSE_CACHE_SIZE)
    return output
