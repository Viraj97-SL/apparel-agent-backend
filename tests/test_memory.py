"""
Tests for the 3-layer memory system.
Validates graceful degradation when Redis/MongoDB are unavailable,
and correct read/write behaviour when mocked.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("GOOGLE_API_KEY", "test-key")


class TestEpisodicMemory:
    """Layer 2 — Redis-backed session cache."""

    def test_get_session_context_returns_empty_when_no_redis(self):
        """When REDIS_URL is not set, get_session_context must return {}."""
        import app.memory.episodic as ep_mod
        # Reset singleton so _get_redis re-evaluates env
        original = ep_mod._REDIS_CLIENT
        ep_mod._REDIS_CLIENT = None
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("REDIS_URL", None)
                ctx = ep_mod.EpisodicMemory().get_session_context("thread-1")
                assert ctx == {}
        finally:
            ep_mod._REDIS_CLIENT = original

    def test_update_session_context_is_noop_when_no_redis(self):
        """update_session_context must not raise when Redis is unavailable."""
        import app.memory.episodic as ep_mod
        original = ep_mod._REDIS_CLIENT
        ep_mod._REDIS_CLIENT = None
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("REDIS_URL", None)
                ep_mod.EpisodicMemory().update_session_context("thread-1", {"cart": ["item1"]})
        finally:
            ep_mod._REDIS_CLIENT = original

    def test_get_session_context_reads_from_redis(self):
        """With a mocked Redis client, get_session_context returns stored value."""
        import json
        import app.memory.episodic as ep_mod

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"recent_products": ["Crimson Canvas"]})

        original = ep_mod._REDIS_CLIENT
        ep_mod._REDIS_CLIENT = None
        try:
            with patch("app.memory.episodic._get_redis", return_value=mock_redis):
                mem = ep_mod.EpisodicMemory()
                ctx = mem.get_session_context("thread-2")
                assert ctx.get("recent_products") == ["Crimson Canvas"]
        finally:
            ep_mod._REDIS_CLIENT = original

    def test_track_viewed_product_calls_lpush(self):
        """track_viewed_product should push to the list key."""
        import app.memory.episodic as ep_mod

        mock_redis = MagicMock()
        original = ep_mod._REDIS_CLIENT
        ep_mod._REDIS_CLIENT = None
        try:
            with patch("app.memory.episodic._get_redis", return_value=mock_redis):
                ep_mod.EpisodicMemory().track_viewed_product("thread-3", "Blue Floral Bloom")
                mock_redis.lpush.assert_called_once()
        finally:
            ep_mod._REDIS_CLIENT = original

    def test_clear_session_calls_delete(self):
        """clear_session should delete both Redis keys."""
        import app.memory.episodic as ep_mod

        mock_redis = MagicMock()
        original = ep_mod._REDIS_CLIENT
        ep_mod._REDIS_CLIENT = None
        try:
            with patch("app.memory.episodic._get_redis", return_value=mock_redis):
                ep_mod.EpisodicMemory().clear_session("thread-4")
                mock_redis.delete.assert_called_once()
        finally:
            ep_mod._REDIS_CLIENT = original


class TestSemanticMemory:
    """Layer 3 — MongoDB Atlas long-term memory."""

    def test_format_as_context_returns_empty_when_no_mongo(self):
        """When MONGODB_URI is not set, format_as_context must return ''."""
        import app.memory.semantic as sem_mod
        original = sem_mod._collection
        sem_mod._collection = None
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MONGODB_URI", None)
                os.environ.pop("MONGODB_URL", None)
                result = sem_mod.SemanticMemory().format_as_context("thread-1")
                assert result == ""
        finally:
            sem_mod._collection = original

    def test_put_is_noop_when_no_mongo(self):
        """put must not raise when MongoDB is unavailable."""
        import app.memory.semantic as sem_mod
        original = sem_mod._collection
        sem_mod._collection = None
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MONGODB_URI", None)
                os.environ.pop("MONGODB_URL", None)
                sem_mod.SemanticMemory().put("thread-1", "preferences", "size", "M")
        finally:
            sem_mod._collection = original

    def test_supports_mongodb_uri_env_var(self):
        """Semantic memory should pick up MONGODB_URI (Atlas standard)."""
        import app.memory.semantic as sem_mod

        original_client = sem_mod._mongo_client
        original_col = sem_mod._collection
        sem_mod._mongo_client = None
        sem_mod._collection = None

        try:
            with patch.dict(os.environ, {"MONGODB_URI": "mongodb://fake-host"}):
                # Mock MongoClient inside the module's dynamic import
                mock_client = MagicMock()
                mock_client.admin.command.side_effect = Exception("connection refused")
                with patch("pymongo.MongoClient", return_value=mock_client):
                    col = sem_mod._get_collection()
                    # Should fail gracefully and return None
                    assert col is None
        finally:
            sem_mod._mongo_client = original_client
            sem_mod._collection = original_col

    def test_format_as_context_formats_stored_facts(self):
        """format_as_context should produce human-readable lines from stored docs."""
        import app.memory.semantic as sem_mod

        mock_collection = MagicMock()
        mock_collection.find.return_value = [
            {
                "namespace": ["users", "thread-5", "preferences"],
                "key": "preferred_size",
                "value": {"content": "M", "confidence": 0.9},
            }
        ]

        with patch("app.memory.semantic._get_collection", return_value=mock_collection):
            result = sem_mod.SemanticMemory().format_as_context("thread-5")
            assert "preferred_size" in result
            assert "M" in result
