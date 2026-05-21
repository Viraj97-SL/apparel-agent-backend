"""
Layer 2 — Episodic Memory (Redis-backed session cache).

Stores per-session context: last viewed products, active cart summary,
VTO state, and conversation summary. Acts as a fast cache in front of
the PostgreSQL LangGraph checkpointer.

Redis key schema:
  session:{thread_id}          → JSON blob, TTL 24h
  session:{thread_id}:products → last 5 viewed product names, TTL 24h
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_CLIENT = None
SESSION_TTL = 86_400  # 24 hours


def _get_redis():
    """Lazy singleton Redis client. Falls back gracefully if Redis is unavailable."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL not set — episodic memory disabled (in-memory only)")
        return None

    try:
        import redis  # type: ignore

        _REDIS_CLIENT = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        _REDIS_CLIENT.ping()
        logger.info("Episodic memory: Redis connected")
    except Exception as e:
        logger.warning("Redis unavailable (%s) — episodic memory disabled", e)
        _REDIS_CLIENT = None

    return _REDIS_CLIENT


class EpisodicMemory:
    """
    Read/write session-scoped context to Redis.
    All methods are synchronous (Redis is fast enough; async wrapper can be
    added later if needed).
    """

    def get_session_context(self, thread_id: str) -> dict:
        r = _get_redis()
        if not r:
            return {}
        try:
            raw = r.get(f"session:{thread_id}")
            return json.loads(raw) if raw else {}
        except Exception as e:
            logger.warning("Episodic read error: %s", e)
            return {}

    def update_session_context(self, thread_id: str, updates: dict[str, Any]) -> None:
        r = _get_redis()
        if not r:
            return
        try:
            key = f"session:{thread_id}"
            existing = self.get_session_context(thread_id)
            existing.update(updates)
            r.setex(key, SESSION_TTL, json.dumps(existing))
        except Exception as e:
            logger.warning("Episodic write error: %s", e)

    def track_viewed_product(self, thread_id: str, product_name: str) -> None:
        r = _get_redis()
        if not r:
            return
        try:
            key = f"session:{thread_id}:products"
            r.lpush(key, product_name)
            r.ltrim(key, 0, 4)  # keep last 5
            r.expire(key, SESSION_TTL)
        except Exception as e:
            logger.warning("Episodic product track error: %s", e)

    def get_recent_products(self, thread_id: str) -> list[str]:
        r = _get_redis()
        if not r:
            return []
        try:
            return r.lrange(f"session:{thread_id}:products", 0, -1)
        except Exception:
            return []

    def clear_session(self, thread_id: str) -> None:
        r = _get_redis()
        if not r:
            return
        try:
            r.delete(f"session:{thread_id}", f"session:{thread_id}:products")
        except Exception as e:
            logger.warning("Episodic clear error: %s", e)


# Module-level singleton
episodic_memory = EpisodicMemory()
