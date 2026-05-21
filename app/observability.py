import os
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def configure_langsmith() -> bool:
    """
    Configure LangSmith tracing. Returns True if tracing is active.
    Sampling rate: 100% in dev, 10% in prod (controlled by LANGSMITH_SAMPLE_RATE env var).
    """
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        logger.warning("LANGSMITH_API_KEY not set — tracing disabled")
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "pamorya-prod")

    sample_rate = os.getenv("LANGSMITH_SAMPLE_RATE", "1.0")
    os.environ["LANGCHAIN_SAMPLING_RATE"] = sample_rate

    logger.info(
        "LangSmith tracing active — project=%s sample_rate=%s",
        os.environ["LANGCHAIN_PROJECT"],
        sample_rate,
    )
    return True


def run_metadata(thread_id: str, mode: str = "standard") -> dict:
    """Build per-run metadata tags for LangSmith traces."""
    return {
        "thread_id": thread_id,
        "mode": mode,
        "env": os.getenv("ENVIRONMENT", "development"),
    }
