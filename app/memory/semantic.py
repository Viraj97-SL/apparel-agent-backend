"""
Layer 3 — Semantic Long-Term Memory (MongoDB Atlas).

Stores user facts that persist across sessions: style preferences, sizes,
budget, favourite colours, past purchase summaries.

MongoDB collection: pamorya_memory.user_memories
Document schema:
  {
    namespace: ["users", thread_id, category],  # e.g. ["users", "abc123", "preferences"]
    key:        str,                              # e.g. "preferred_size"
    value: {
      content:   str,
      confidence: float,          # 0.0–1.0
      timestamp: ISO-8601 str,
      source_thread: str,
    }
  }

Shared namespaces (no thread_id):
  ["products", "trends"]   → trending items, refreshed every 6 hours
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

MONGO_DB_NAME = "pamorya_memory"
MONGO_COLLECTION = "user_memories"
TREND_TTL_SECONDS = 21_600  # 6 hours

_mongo_client = None
_collection = None


def _get_collection():
    global _mongo_client, _collection
    if _collection is not None:
        return _collection

    mongo_url = os.getenv("MONGODB_URL")
    if not mongo_url:
        logger.warning("MONGODB_URL not set — semantic memory disabled")
        return None

    try:
        from pymongo import MongoClient  # type: ignore
        from pymongo.server_api import ServerApi

        _mongo_client = MongoClient(mongo_url, server_api=ServerApi("1"), serverSelectionTimeoutMS=3000)
        _mongo_client.admin.command("ping")
        db = _mongo_client[MONGO_DB_NAME]
        _collection = db[MONGO_COLLECTION]

        # Indexes for fast namespace + key lookups
        _collection.create_index([("namespace", 1), ("key", 1)], unique=True)
        _collection.create_index([("namespace", 1)])

        logger.info("Semantic memory: MongoDB Atlas connected")
    except Exception as e:
        logger.warning("MongoDB unavailable (%s) — semantic memory disabled", e)
        _collection = None

    return _collection


class SemanticMemory:
    """
    Read/write long-term user facts to MongoDB Atlas.
    Namespace-based storage mirrors LangGraph Store's interface so the
    agent code can swap to LangGraph's managed store later with minimal changes.
    """

    def put(
        self,
        thread_id: str,
        category: str,
        key: str,
        content: str,
        confidence: float = 0.8,
    ) -> None:
        col = _get_collection()
        if not col:
            return
        namespace = ["users", thread_id, category]
        try:
            col.update_one(
                {"namespace": namespace, "key": key},
                {
                    "$set": {
                        "value": {
                            "content": content,
                            "confidence": confidence,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "source_thread": thread_id,
                        }
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("Semantic put error: %s", e)

    def get(self, thread_id: str, category: str, key: str) -> str | None:
        col = _get_collection()
        if not col:
            return None
        try:
            doc = col.find_one({"namespace": ["users", thread_id, category], "key": key})
            return doc["value"]["content"] if doc else None
        except Exception:
            return None

    def get_all_for_thread(self, thread_id: str) -> list[dict]:
        col = _get_collection()
        if not col:
            return []
        try:
            docs = list(
                col.find(
                    {"namespace.0": "users", "namespace.1": thread_id},
                    {"_id": 0},
                )
            )
            return docs
        except Exception:
            return []

    def format_as_context(self, thread_id: str) -> str:
        """Return a concise string summary of stored user facts for prompt injection."""
        docs = self.get_all_for_thread(thread_id)
        if not docs:
            return ""
        lines = []
        for doc in docs:
            category = doc.get("namespace", ["", "", "unknown"])[2]
            key = doc.get("key", "")
            content = doc.get("value", {}).get("content", "")
            if content:
                lines.append(f"- {category}/{key}: {content}")
        return "\n".join(lines)

    def put_trend(self, key: str, content: str) -> None:
        col = _get_collection()
        if not col:
            return
        namespace = ["products", "trends"]
        try:
            col.update_one(
                {"namespace": namespace, "key": key},
                {
                    "$set": {
                        "value": {
                            "content": content,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("Semantic trend put error: %s", e)

    def get_trends(self) -> list[str]:
        col = _get_collection()
        if not col:
            return []
        try:
            docs = list(col.find({"namespace": ["products", "trends"]}, {"_id": 0}))
            return [d["value"]["content"] for d in docs if "value" in d]
        except Exception:
            return []


# Module-level singleton
semantic_memory = SemanticMemory()
