"""
Tests for the VTO pipeline — retry logic, cache, fallback, and status messages.
All external HTTP calls (Fashn.ai, Replicate, Cloudinary) are mocked.
"""
import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("REPLICATE_API_TOKEN", "test-token")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "test-ck")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-cs")
os.environ.setdefault("FASHN_API_KEY", "test-fashn-key")


class TestJobStatusStore:
    """In-process job store behaves correctly without Redis."""

    def test_set_and_get_job_status(self):
        from app.vto_agent import set_job_status, get_job_status
        job_id = "test-job-1"
        set_job_status(job_id, "processing")
        result = get_job_status(job_id)
        assert result["status"] == "processing"
        assert result["message"] != ""

    def test_completed_status_includes_result_url(self):
        from app.vto_agent import set_job_status, get_job_status
        job_id = "test-job-2"
        set_job_status(job_id, "completed", result_url="https://example.com/result.jpg", provider="fashn.ai")
        result = get_job_status(job_id)
        assert result["status"] == "completed"
        assert result["result_url"] == "https://example.com/result.jpg"
        assert result["provider"] == "fashn.ai"

    def test_not_found_returns_sensible_default(self):
        from app.vto_agent import get_job_status
        result = get_job_status("nonexistent-job-xyz")
        assert result["status"] == "not_found"
        assert isinstance(result["estimated_seconds_remaining"], int)

    def test_estimated_seconds_remaining_decreases(self):
        import time
        from app.vto_agent import set_job_status, get_job_status, _IN_MEMORY_JOBS, _job_key
        job_id = "test-job-timing"
        # Inject a job with started_at in the past
        payload = json.dumps({
            "status": "processing",
            "result_url": "",
            "error": "",
            "provider": "",
            "message": "Processing...",
            "started_at": time.time() - 20,  # 20 seconds ago
        })
        _IN_MEMORY_JOBS[_job_key(job_id)] = payload
        result = get_job_status(job_id)
        assert result["estimated_seconds_remaining"] <= 15  # 35 - 20 = 15


class TestVtoCacheHit:
    """When a cached result exists, the job completes instantly."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fashn(self):
        from app.vto_agent import process_vto_job, set_job_status, get_job_status

        with patch("app.vto_agent._get_cached_result", return_value="https://cached.jpg"):
            with patch("app.vto_agent.run_fashn_vto") as mock_fashn:
                await process_vto_job(
                    job_id="cache-job",
                    thread_id="t1",
                    user_image_path="/tmp/user.jpg",
                    product_image_url="https://product.jpg",
                    product_name="Crimson Canvas",
                    product_category="Dresses",
                )
                mock_fashn.assert_not_called()

        result = get_job_status("cache-job")
        assert result["status"] == "completed"
        assert result["result_url"] == "https://cached.jpg"


class TestFashnRetry:
    """Fashn.ai retries on server errors and falls back to Replicate on total failure."""

    @pytest.mark.asyncio
    async def test_fashn_falls_back_to_replicate_on_failure(self, tmp_path):
        user_img = tmp_path / "user.jpg"
        user_img.write_bytes(b"fake-image")

        with patch("app.vto_agent._get_cached_result", return_value=None):
            with patch("cloudinary.uploader.upload", return_value={"secure_url": "https://cloud.jpg"}):
                with patch("app.vto_agent.run_fashn_vto", new_callable=AsyncMock, return_value=None):
                    with patch("app.vto_agent.run_replicate_vto_sync", return_value="https://replicate.jpg"):
                        with patch("app.vto_agent.download_image_temp", return_value=str(tmp_path / "prod.jpg")):
                            prod_img = tmp_path / "prod.jpg"
                            prod_img.write_bytes(b"prod")
                            with patch("os.path.exists", return_value=True):
                                with patch("os.remove"):
                                    from app.vto_agent import process_vto_job, get_job_status
                                    await process_vto_job(
                                        job_id="fallback-job",
                                        thread_id="t2",
                                        user_image_path=str(user_img),
                                        product_image_url="https://product.jpg",
                                        product_name="Blue Floral Bloom",
                                        product_category="Tops & Blouses",
                                    )

        result = get_job_status("fallback-job")
        assert result["status"] == "completed"
        assert result["result_url"] == "https://replicate.jpg"
        assert result["provider"] == "replicate"

    @pytest.mark.asyncio
    async def test_total_failure_marks_job_failed(self, tmp_path):
        user_img = tmp_path / "user.jpg"
        user_img.write_bytes(b"fake")

        with patch("app.vto_agent._get_cached_result", return_value=None):
            with patch("cloudinary.uploader.upload", side_effect=Exception("cloudinary down")):
                with patch("app.vto_agent.download_image_temp", return_value=None):
                    from app.vto_agent import process_vto_job, get_job_status
                    with patch("os.path.exists", return_value=True):
                        await process_vto_job(
                            job_id="fail-job",
                            thread_id="t3",
                            user_image_path=str(user_img),
                            product_image_url="https://product.jpg",
                            product_name="Forest Glade Wrap",
                            product_category="Dresses",
                        )

        result = get_job_status("fail-job")
        assert result["status"] == "failed"
        assert result["result_url"] == ""


class TestFashnVtoFunction:
    """Unit tests for the run_fashn_vto function itself."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("FASHN_API_KEY", "")
        from app import vto_agent
        vto_agent.FASHN_API_KEY = ""
        result = await vto_agent.run_fashn_vto("https://person.jpg", "https://garment.jpg", "Dresses")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_url_on_success(self):
        from unittest.mock import AsyncMock
        import app.vto_agent as vto_agent

        # Reset the API key — a prior test may have zeroed it on the module object
        original_key = vto_agent.FASHN_API_KEY
        vto_agent.FASHN_API_KEY = "test-fashn-key"

        # Use MagicMock for response objects: .json() must return a plain dict,
        # not a coroutine (AsyncMock children are AsyncMock by default in Py 3.8+).
        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"id": "pred-123"}
        submit_resp.raise_for_status = MagicMock()

        poll_resp = MagicMock()
        poll_resp.json.return_value = {"status": "completed", "output": "https://fashn.ai/result.jpg"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=submit_resp)
        mock_client.get = AsyncMock(return_value=poll_resp)

        try:
            with patch("httpx.AsyncClient", return_value=mock_client):
                with patch("asyncio.sleep"):  # skip real delays in poll loop
                    result = await vto_agent.run_fashn_vto(
                        "https://person.jpg", "https://garment.jpg", "Dresses"
                    )
        finally:
            vto_agent.FASHN_API_KEY = original_key

        assert result == "https://fashn.ai/result.jpg"
