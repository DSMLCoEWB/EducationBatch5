"""
RAG Retriever

Free-deployment optimized retriever with strict grounding support:
- Lightweight single embedding model (MiniLM only)
- No cross-encoder reranker
- One-time global model/index initialization
- Fast non-blocking loading mode for request path
- Cached hybrid retrieval (semantic + lexical)
"""

import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_PATH = DATA_DIR / "faiss.index"
CHUNKS_PATH = DATA_DIR / "policy_chunks.json"
DEMO_CHUNKS_PATH = DATA_DIR / "demo_policy_chunks.json"
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# Keep retrieval surface bounded for low latency on free instances.
TOP_K = min(5, max(1, int(os.getenv("RAG_TOP_K", "5"))))
CANDIDATE_POOL = min(5, max(TOP_K, int(os.getenv("RAG_CANDIDATE_POOL", "5"))))
OVERSAMPLE_LIMIT = min(20, max(10, int(os.getenv("RAG_OVERSAMPLE_LIMIT", "20"))))

MIN_FINAL_SCORE = float(os.getenv("RAG_MIN_FINAL_SCORE", "0.20"))
RETRIEVAL_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_RETRIEVAL_CONF_THRESHOLD", "0.55"))

# Domain keyword expansion for academic queries
ACADEMIC_EXPANSION = {
    "result": "marks grade examination scorecard transcript performance",
    "semester": "term session academic year part",
    "suspension": "disciplinary inquiry penalty reinstatement debarment",
    "exam": "test assessment paper evaluation boards",
    "attendance": "presence absence leave shortage condonation",
    "misconduct": "cheating malpractice unfair means plagiarism",
    "cert": "certificate diploma degree provisional migration",
}

# Domain terms for direct scoring boost
BOOST_TERMS = ["suspension", "disciplinary", "reinstatement", "fir", "arrest", "misconduct", "cheating", "expulsion"]

# Mandatory hybrid weights requested.
SEMANTIC_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3

MAX_CHUNK_EMBED_TOKENS = int(os.getenv("RAG_MAX_CHUNK_EMBED_TOKENS", "420"))
EMBED_CACHE_SIZE = int(os.getenv("RAG_EMBED_CACHE_SIZE", "256"))
RETRIEVAL_CACHE_SIZE = int(os.getenv("RAG_RETRIEVAL_CACHE_SIZE", "256"))
RAG_WARMUP = os.getenv("RAG_WARMUP", "true").lower() == "true"

# Force lightweight model only.
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

rag_model: Optional[SentenceTransformer] = None
reranker = None
index = None
policy_chunks: Optional[List[Dict[str, Any]]] = None
policy_chunk_embeddings: Optional[np.ndarray] = None

model_load_error: Optional[str] = None
retriever_loaded = False
_retriever_loading = False

_embed_cache: Dict[str, np.ndarray] = {}
_retrieval_cache: Dict[str, List[Dict[str, Any]]] = {}
_chunk_embed_cache: Dict[int, np.ndarray] = {}

_cache_lock = Lock()
_loader_lock = Lock()


def get_demo_mode() -> bool:
    return DEMO_MODE


def get_knowledge_source_label() -> str:
    if DEMO_MODE:
        return "Simulated Policy Corpus (Demo Mode)"
    return "Institutional Policy Corpus"


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


def get_model_load_error() -> Optional[str]:
    return model_load_error


def is_retriever_loading() -> bool:
    return _retriever_loading


def _normalize_policy_chunks(raw_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_chunks):
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        text = item.get("text", "")

        normalized.append(
            {
                "chunk_id": i,
                "text": text,
                "policy_id": item.get("policy_id") or metadata.get("policy_id") or "unknown",
                "section_title": item.get("section_title") or metadata.get("section") or "General",
                "clause_id": item.get("clause_id") or metadata.get("clause_id") or str(i),
            }
        )

    return normalized


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", _normalize_text(text))


def _token_overlap_ratio(a: str, b: str) -> float:
    ta = set(_tokenize(a))
    tb = set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    den = max(len(ta), 1)
    return inter / den


def _truncate_for_embedding(text: str, max_tokens: int = MAX_CHUNK_EMBED_TOKENS) -> str:
    words = re.findall(r"\S+", text or "")
    if len(words) <= max_tokens:
        return text or ""
    return " ".join(words[:max_tokens])


def _encode_texts(texts: List[str], batch_size: int = 128) -> Optional[np.ndarray]:
    if rag_model is None or not texts:
        return None
    try:
        emb = rag_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=batch_size,
            convert_to_numpy=True,
        )
        return np.asarray(emb, dtype=np.float32)
    except Exception as e:
        logger.warning("Batch embedding failed: %s", e)
        return None


def _cosine_sim(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))


def _chunk_embedding(chunk: Dict[str, Any]) -> Optional[np.ndarray]:
    chunk_id = int(chunk.get("chunk_id", -1))

    if policy_chunk_embeddings is not None and 0 <= chunk_id < len(policy_chunk_embeddings):
        return policy_chunk_embeddings[chunk_id]

    cached = _chunk_embed_cache.get(chunk_id)
    if cached is not None:
        return cached

    text = _truncate_for_embedding(chunk.get("text", ""))
    emb = _encode_texts([text], batch_size=1)
    if emb is None:
        return None

    vec = emb[0]
    if chunk_id >= 0:
        _chunk_embed_cache[chunk_id] = vec
    return vec


def _semantic_support_with_fallback(
    sentence: str,
    sentence_emb: Optional[np.ndarray],
    candidate_chunks: List[Dict[str, Any]],
) -> float:
    best = 0.0

    if sentence_emb is not None:
        for c in candidate_chunks:
            c_emb = _chunk_embedding(c)
            score = _cosine_sim(sentence_emb, c_emb)
            if score > best:
                best = score

        if best > 0.0:
            return float(best)

    for c in candidate_chunks:
        score = _token_overlap_ratio(sentence, c.get("text", ""))
        if score > best:
            best = score

    return float(best)


def _find_supporting_span(sentence: str, chunk_text: str, window_tokens: int = 40) -> Dict[str, Any]:
    sent_tokens = _tokenize(sentence)
    chunk_tokens = _tokenize(chunk_text)

    if not sent_tokens or not chunk_tokens:
        return {
            "score": 0.0,
            "span_start": 0,
            "span_end": min(len(chunk_text), 200),
            "source_text_snippet": (chunk_text or "")[:200],
        }

    best_score = 0.0
    best_i = 0

    sentence_set = set(sent_tokens)
    for i in range(0, max(1, len(chunk_tokens) - window_tokens + 1)):
        window = set(chunk_tokens[i : i + window_tokens])
        overlap = len(window & sentence_set) / max(len(sentence_set), 1)
        if overlap > best_score:
            best_score = overlap
            best_i = i

    chunk_words = re.findall(r"\S+", chunk_text or "")
    start_word = max(0, min(best_i, max(len(chunk_words) - 1, 0)))
    end_word = max(start_word, min(start_word + window_tokens, len(chunk_words)))

    if not chunk_words:
        return {
            "score": float(best_score),
            "span_start": 0,
            "span_end": min(len(chunk_text), 200),
            "source_text_snippet": (chunk_text or "")[:200],
        }

    prefix = " ".join(chunk_words[:start_word])
    span_text = " ".join(chunk_words[start_word:end_word])
    span_start = len(prefix) + (1 if prefix else 0)
    span_end = span_start + len(span_text)

    return {
        "score": float(best_score),
        "span_start": int(max(0, span_start)),
        "span_end": int(max(span_start, span_end)),
        "source_text_snippet": span_text[:260],
    }


def _lexical_overlap_score(query: str, text: str) -> float:
    q_tokens = set(_tokenize(query))
    t_tokens = set(_tokenize(text))
    if not q_tokens or not t_tokens:
        return 0.0
    
    # Base overlap ratio
    overlap = len(q_tokens & t_tokens) / max(len(q_tokens), 1)
    
    # Keyword boost for prioritized domain terms
    boost = 0.0
    for term in BOOST_TERMS:
        if term in q_tokens and term in t_tokens:
            boost += 0.08  # Incremental boost for each critical term match
            
    return min(1.3, overlap + boost)


def _expand_query(query: str) -> str:
    tokens = set(_tokenize(query))
    expanded = list(tokens)
    
    for word, synonyms in ACADEMIC_EXPANSION.items():
        if word in tokens:
            expanded.append(synonyms)
            
    return " ".join(expanded).strip() or query


def _embedding_for_query(query: str) -> Optional[np.ndarray]:
    key = _normalize_text(query)
    cached = _cache_get(_embed_cache, key)
    if cached is not None:
        return np.asarray(cached, dtype=np.float32)

    emb = _encode_texts([query], batch_size=1)
    if emb is None:
        return None

    vec = emb.astype(np.float32)
    _cache_put(_embed_cache, key, vec, EMBED_CACHE_SIZE)
    return vec


def _load_retriever_assets() -> bool:
    global rag_model, reranker, index, policy_chunks, policy_chunk_embeddings, retriever_loaded, model_load_error, _retriever_loading

    try:
        model_load_error = None

        logger.info("Loading embedding model: %s", EMBED_MODEL_NAME)
        rag_model = SentenceTransformer(EMBED_MODEL_NAME)

        # Mandatory: disable heavy reranker entirely.
        reranker = None

        chunks_path = DEMO_CHUNKS_PATH if DEMO_MODE else CHUNKS_PATH

        if not chunks_path.exists():
            model_load_error = f"Policy chunks file missing: {chunks_path}"
            retriever_loaded = False
            return False

        with open(chunks_path, "r", encoding="utf-8") as f:
            raw_chunks = json.load(f)
        policy_chunks = _normalize_policy_chunks(raw_chunks)

        if not policy_chunks:
            model_load_error = "policy_chunks is empty or invalid"
            retriever_loaded = False
            return False

        # Precompute chunk embeddings once to speed sentence-level validation support checks.
        texts = [_truncate_for_embedding(c.get("text", "")) for c in policy_chunks]
        emb = _encode_texts(texts, batch_size=128)
        policy_chunk_embeddings = emb.astype(np.float32) if emb is not None else None

        if policy_chunk_embeddings is None or len(policy_chunk_embeddings) == 0:
            model_load_error = "Failed to compute policy chunk embeddings"
            retriever_loaded = False
            return False

        # In demo mode we may not have a persisted FAISS index; build from precomputed vectors.
        if DEMO_MODE:
            dim = policy_chunk_embeddings.shape[1]
            index = faiss.IndexFlatIP(dim)
            index.add(policy_chunk_embeddings)
        else:
            if not INDEX_PATH.exists():
                model_load_error = f"FAISS index missing: {INDEX_PATH}"
                retriever_loaded = False
                return False
            index = faiss.read_index(str(INDEX_PATH))

        if RAG_WARMUP and rag_model is not None:
            try:
                _ = rag_model.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
            except Exception:
                pass

        retriever_loaded = True
        logger.info(
            "Retriever ready | demo_mode=%s chunks=%d top_k=%d candidate_pool=%d",
            DEMO_MODE,
            len(policy_chunks),
            TOP_K,
            CANDIDATE_POOL,
        )
        return True
    except Exception as e:
        model_load_error = f"Retriever initialization failed: {e}"
        retriever_loaded = False
        logger.error(model_load_error)
        return False
    finally:
        with _loader_lock:
            _retriever_loading = False


def ensure_retriever_loaded(block: bool = True) -> bool:
    global _retriever_loading

    if retriever_loaded:
        return True

    with _loader_lock:
        if retriever_loaded:
            return True

        if _retriever_loading:
            return False

        _retriever_loading = True

    if block:
        return _load_retriever_assets()

    t = threading.Thread(target=_load_retriever_assets, name="rag-loader", daemon=True)
    t.start()
    return False


def retrieve_policy_chunks(
    query: str,
    top_k: int = TOP_K,
    candidate_pool: int = CANDIDATE_POOL,
    policy_id_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    return_metrics: bool = False,
) -> Any:
    if not query or not query.strip():
        empty_metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": False}
        return ([], empty_metrics) if return_metrics else []

    top_k = min(5, max(1, int(top_k)))
    candidate_pool = min(5, max(top_k, int(candidate_pool)))

    key_payload = {
        "q": _normalize_text(query),
        "k": top_k,
        "pool": candidate_pool,
        "pid": policy_id_filter or "",
        "sec": section_filter or "",
    }
    cache_key = hashlib.sha1(json.dumps(key_payload, sort_keys=True).encode("utf-8")).hexdigest()
    cached = _cache_get(_retrieval_cache, cache_key)
    if cached is not None:
        metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": True}
        return (cached, metrics) if return_metrics else cached

    # Non-blocking behavior in request path. Startup can call ensure_retriever_loaded(block=True) once.
    if not retriever_loaded:
        if not ensure_retriever_loaded(block=False):
            metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": False}
            return ([], metrics) if return_metrics else []

    if not retriever_loaded or index is None or policy_chunks is None:
        metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": False}
        return ([], metrics) if return_metrics else []

    # Apply query expansion for academic context
    expanded_query = _expand_query(query)
    q_vec = _embedding_for_query(expanded_query)
    
    if q_vec is None:
        metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": False}
        return ([], metrics) if return_metrics else []

    oversample = min(max(candidate_pool * 3, 12), OVERSAMPLE_LIMIT)
    t_retrieval = time.time()

    try:
        scores, indices = index.search(q_vec, oversample)
    except Exception as e:
        logger.error("FAISS search failed: %s", e)
        metrics = {"retrieval_ms": 0, "rerank_ms": 0, "cache_hit": False}
        return ([], metrics) if return_metrics else []

    candidates: List[Dict[str, Any]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(policy_chunks):
            continue

        chunk = policy_chunks[idx]

        if policy_id_filter and str(chunk.get("policy_id", "")) != str(policy_id_filter):
            continue
        if section_filter and str(chunk.get("section_title", "")) != str(section_filter):
            continue

        text = chunk.get("text", "")
        semantic_score = float(score)
        # Use simple original query for lexical overlap to avoid noise from expansion
        lexical_score = _lexical_overlap_score(query, text)
        final_score = (semantic_score * SEMANTIC_WEIGHT) + (lexical_score * LEXICAL_WEIGHT)

        # Removed: if final_score < MIN_FINAL_SCORE: continue
        # Always return best matches to maximize recall

        candidates.append(
            {
                "chunk_id": idx,
                "text": text,
                "policy_id": chunk.get("policy_id", "unknown"),
                "section_title": chunk.get("section_title", "General"),
                "clause_id": chunk.get("clause_id", str(idx)),
                "semantic_score": semantic_score,
                "lexical_score": lexical_score,
                "final_score": final_score,
            }
        )

    if not candidates:
        metrics = {"retrieval_ms": int((time.time() - t_retrieval) * 1000), "rerank_ms": 0, "cache_hit": False}
        return ([], metrics) if return_metrics else []

    # No reranker pass by design.
    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    out = candidates[:top_k]

    _cache_put(_retrieval_cache, cache_key, out, RETRIEVAL_CACHE_SIZE)

    retrieval_ms = int((time.time() - t_retrieval) * 1000)
    metrics = {"retrieval_ms": retrieval_ms, "rerank_ms": 0, "cache_hit": False}
    return (out, metrics) if return_metrics else out
