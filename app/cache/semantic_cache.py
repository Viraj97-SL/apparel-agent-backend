"""
Semantic Cache — Redis-backed LLM response cache.

Intercepts queries before hitting the Gemini API. If a semantically
similar query (cosine similarity >= threshold) was answered before,
returns the cached response instantly.

Redis key schema:
  scache:v1:{entry_id}   → JSON blob per cached entry
  scache:v1:index        → Redis sorted set: entry_id → timestamp (for LRU pruning)

Two module-level singletons are exported:
  rag_cache   — TTL 12h  (stable policy/shipping answers)
  web_cache   — TTL 6h   (trend queries, shorter because trends change)
"""

import json
import logging
import math
import os
import time
import uuid
from typing import Optional

from app.memory.episodic import _get_redis as _episodic_get_redis

logger = logging.getLogger(__name__)

CACHE_THRESHOLD: float = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.95"))
CACHE_ENABLED: bool = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() != "false"
MAX_ENTRIES: int = 500
_KEY_PREFIX: str = "scache:v1:"
_INDEX_KEY: str = "scache:v1:index"

_embeddings_instance = None


def _get_redis():
    return _episodic_get_redis()


def _get_embeddings():
    global _embeddings_instance
    if _embeddings_instance is not None:
        return _embeddings_instance
    try:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings_instance = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        logger.info("SemanticCache: HuggingFace MiniLM embeddings loaded")
    except Exception as e:
        logger.warning("SemanticCache: embeddings unavailable (%s)", e)
        return None
    return _embeddings_instance


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class SemanticCache:
    def __init__(self, ttl_seconds: int = 43200) -> None:
        self.ttl_seconds = ttl_seconds
        self.threshold = CACHE_THRESHOLD

    def get(self, query: str) -> Optional[str]:
        if not CACHE_ENABLED:
            return None

        r = _get_redis()
        emb_model = _get_embeddings()
        if r is None or emb_model is None:
            return None

        try:
            query_emb: list[float] = emb_model.embed_query(query)
            entry_ids: list[str] = r.zrevrange(_INDEX_KEY, 0, MAX_ENTRIES - 1)

            best_score: float = -1.0
            best_response: Optional[str] = None

            for entry_id in entry_ids:
                key = f"{_KEY_PREFIX}{entry_id}"
                raw = r.get(key)
                if raw is None:
                    r.zrem(_INDEX_KEY, entry_id)
                    continue

                entry: dict = json.loads(raw)

                if time.time() - entry["timestamp"] > entry["ttl_seconds"]:
                    r.delete(key)
                    r.zrem(_INDEX_KEY, entry_id)
                    continue

                score = _cosine_similarity(query_emb, entry["embedding"])
                if score > best_score:
                    best_score = score
                    best_response = entry["response"]

            if best_score >= self.threshold and best_response is not None:
                logger.info(
                    "SemanticCache HIT (score=%.4f) for: %s", best_score, query[:60]
                )
                return best_response

            logger.debug("SemanticCache MISS for: %s", query[:60])
            return None

        except Exception as e:
            logger.warning("SemanticCache.get error: %s", e)
            return None

    def put(self, query: str, response: str) -> None:
        if not CACHE_ENABLED or not response:
            return

        r = _get_redis()
        emb_model = _get_embeddings()
        if r is None or emb_model is None:
            return

        try:
            query_emb: list[float] = emb_model.embed_query(query)
            entry_id = str(uuid.uuid4())

            entry = {
                "query": query[:500],
                "embedding": query_emb,
                "response": response[:5000],
                "timestamp": time.time(),
                "ttl_seconds": self.ttl_seconds,
            }

            r.setex(
                f"{_KEY_PREFIX}{entry_id}",
                self.ttl_seconds + 3600,
                json.dumps(entry),
            )
            r.zadd(_INDEX_KEY, {entry_id: time.time()})

            total: int = r.zcard(_INDEX_KEY)
            if total > MAX_ENTRIES:
                oldest_ids: list[str] = r.zrange(_INDEX_KEY, 0, total - MAX_ENTRIES - 1)
                for old_id in oldest_ids:
                    r.delete(f"{_KEY_PREFIX}{old_id}")
                    r.zrem(_INDEX_KEY, old_id)

            logger.info("SemanticCache stored entry for: %s", query[:60])

        except Exception as e:
            logger.warning("SemanticCache.put error: %s", e)


rag_cache = SemanticCache(ttl_seconds=43200)   # 12h for policy/RAG
web_cache = SemanticCache(ttl_seconds=21600)    # 6h for trend queries
