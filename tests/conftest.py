"""
Shared pytest fixtures for the Pamorya chatbot test suite.

Design principles:
- No real DB or LLM calls in unit tests.
- Use SQLite in-memory for integration tests that need persistence.
- Patch external services (Replicate, Tavily, Gemini) at the boundary.
"""
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Environment stubs — set before any app module is imported
# ---------------------------------------------------------------------------
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("REPLICATE_API_TOKEN", "test-replicate-token")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "test-key")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-secret")
# Leave DATABASE_URL unset so agent falls back to SQLite checkpointer


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_agent_app():
    """A minimal mock of the compiled LangGraph app used in server.py."""
    mock = MagicMock()
    mock.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))
    mock.aupdate_state = AsyncMock(return_value=None)

    async def _fake_stream(*args, **kwargs):
        from langchain_core.messages import AIMessage
        yield {"messages": [AIMessage(content="Hello! How can I help you today?")]}

    mock.astream = _fake_stream
    return mock


@pytest.fixture
def mock_vto():
    """Stub for the VTO agent."""
    return MagicMock(return_value="Here is your virtual try-on image!")
