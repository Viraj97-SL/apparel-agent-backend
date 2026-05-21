"""
Virtual Try-On Agent — upgraded to Fashn.ai primary with async job pattern.

VTO Flow:
  1. User uploads photo → stored to disk/Cloudinary
  2. User names a product → looked up in DB
  3. POST /vto/start   → enqueues job, returns job_id immediately
  4. Background task   → calls Fashn.ai (or Replicate fallback)
  5. GET /vto/status/{job_id} → returns progress or result URL

Result cache: Redis key vto:{sha256(thread_id:product_id)}, TTL 30 days.
If cache hit → returns instantly without calling Fashn.ai.
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import time
import uuid
from datetime import date
from typing import Optional

import httpx
import requests
import replicate
from dotenv import load_dotenv

from app.database import SessionLocal
from app.models import Product, VtoSession

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_BASE_URL = (
    f"https://res.cloudinary.com/{CLOUDINARY_CLOUD_NAME}/image/upload/"
    "v1765694934/apparel_bot_products/"
)

FASHN_API_KEY = os.getenv("FASHN_API_KEY", "")
FASHN_BASE_URL = "https://api.fashn.ai/v1"

DAILY_LIMIT = 5

# Fashn.ai category mapping
FASHN_CATEGORY_MAP = {
    "Dresses":              "full-body",
    "Skirts":               "lower-body",
    "Pants & Trousers":     "lower-body",
    "Tops & Blouses":       "upper-body",
    "Sets & Co-ords":       "full-body",
    "Jumpers & Knits":      "upper-body",
    "Jackets & Outerwear":  "upper-body",
}

# Replicate fallback category mapping
REPLICATE_CATEGORY_MAP = {
    "Dresses":              "dresses",
    "Skirts":               "lower_body",
    "Pants & Trousers":     "lower_body",
    "Tops & Blouses":       "upper_body",
    "Sets & Co-ords":       "dresses",
    "Jumpers & Knits":      "upper_body",
    "Jackets & Outerwear":  "upper_body",
}

# Guidance messages
STEP1_GUIDANCE = (
    "**Step 1 of 3 — Upload Your Photo**\n\n"
    "📸 For best results:\n"
    "  • Full-body shot (head to toe)\n"
    "  • Stand against a plain wall\n"
    "  • Good natural lighting\n"
    "  • Wear fitted clothes so the AI can see your shape\n\n"
    "Ready? Hit the 📎 clip icon to upload!"
)

STEP2_GUIDANCE = (
    "**Step 2 of 3 — Choose a Product**\n\n"
    "Great photo! Now tell me which Pamorya piece you'd like to try on.\n"
    "Example: \"Crimson Canvas\" or \"Wild Bloom Whisper\""
)


# ---------------------------------------------------------------------------
# Redis result cache (Layer 2 episodic memory)
# ---------------------------------------------------------------------------
def _cache_key(thread_id: str, product_name: str) -> str:
    raw = f"{thread_id}:{product_name}".encode()
    return f"vto:{hashlib.sha256(raw).hexdigest()}"


def _get_cached_result(thread_id: str, product_name: str) -> Optional[str]:
    from app.memory.episodic import _get_redis
    r = _get_redis()
    if not r:
        return None
    try:
        return r.get(_cache_key(thread_id, product_name))
    except Exception:
        return None


def _cache_result(thread_id: str, product_name: str, image_url: str) -> None:
    from app.memory.episodic import _get_redis
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(_cache_key(thread_id, product_name), 2_592_000, image_url)  # 30 days
    except Exception as e:
        logger.warning("VTO cache write failed: %s", e)


# ---------------------------------------------------------------------------
# Async Job Store (Redis-backed)
# ---------------------------------------------------------------------------
JOB_TTL = 3600  # 1 hour


def _job_key(job_id: str) -> str:
    return f"vto_job:{job_id}"


def set_job_status(job_id: str, status: str, result_url: str = "", error: str = "") -> None:
    from app.memory.episodic import _get_redis
    r = _get_redis()
    payload = json.dumps({"status": status, "result_url": result_url, "error": error})
    if r:
        try:
            r.setex(_job_key(job_id), JOB_TTL, payload)
        except Exception:
            pass
    # fallback: in-process dict for local dev
    _IN_MEMORY_JOBS[job_id] = payload


def get_job_status(job_id: str) -> dict:
    from app.memory.episodic import _get_redis
    r = _get_redis()
    raw = None
    if r:
        try:
            raw = r.get(_job_key(job_id))
        except Exception:
            pass
    if raw is None:
        raw = _IN_MEMORY_JOBS.get(job_id)
    if raw:
        return json.loads(raw)
    return {"status": "not_found", "result_url": "", "error": ""}


_IN_MEMORY_JOBS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_or_create_session(db, thread_id: str) -> VtoSession:
    session = db.query(VtoSession).filter(VtoSession.thread_id == thread_id).first()
    if not session:
        session = VtoSession(thread_id=thread_id)
        db.add(session)
        db.flush()
    return session


def check_and_increment_limit(db, thread_id: str, daily_limit: int = DAILY_LIMIT) -> bool:
    today = str(date.today())
    vto = get_or_create_session(db, thread_id)
    if vto.usage_date != today:
        vto.usage_date = today
        vto.usage_count = 0
    if vto.usage_count >= daily_limit:
        return False
    vto.usage_count += 1
    db.flush()
    return True


def get_product_from_db(product_query: str) -> Optional[dict]:
    db = SessionLocal()
    try:
        product = (
            db.query(Product)
            .filter(Product.product_name.ilike(f"%{product_query}%"))
            .first()
        )
        if product and product.image_url:
            urls = [u.strip() for u in product.image_url.split(",") if u.strip()]
            return {
                "name": product.product_name,
                "url": urls[0],
                "category": product.category or "",
            }
    except Exception as e:
        logger.error("DB Error in VTO: %s", e)
    finally:
        db.close()
    return None


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def download_image_temp(url: str, tag: str) -> Optional[str]:
    temp_path = f"temp_{tag}.jpg"
    if "localhost" in url or not url.startswith("http"):
        url = f"{CLOUDINARY_BASE_URL}{os.path.basename(url)}"
    try:
        r = requests.get(url, stream=True, timeout=15)
        if r.status_code == 200:
            with open(temp_path, "wb") as f:
                f.write(r.content)
            return temp_path
        logger.warning("Image download failed: %s → %d", url, r.status_code)
    except Exception as e:
        logger.error("Image download error: %s", e)
    return None


# ---------------------------------------------------------------------------
# Fashn.ai VTO (primary)
# ---------------------------------------------------------------------------
async def run_fashn_vto(
    person_image_url: str,
    garment_image_url: str,
    category: str,
) -> Optional[str]:
    """
    Call Fashn.ai async API. Polls until result is ready (max 120s).
    Returns the output image URL or None on failure.
    """
    if not FASHN_API_KEY:
        logger.warning("FASHN_API_KEY not set — skipping Fashn.ai")
        return None

    fashn_category = FASHN_CATEGORY_MAP.get(category, "upper-body")

    async with httpx.AsyncClient(timeout=30) as client:
        # Submit job
        try:
            resp = await client.post(
                f"{FASHN_BASE_URL}/run",
                headers={"Authorization": f"Bearer {FASHN_API_KEY}"},
                json={
                    "model_image": person_image_url,
                    "garment_image": garment_image_url,
                    "category": fashn_category,
                    "mode": "quality",
                },
            )
            resp.raise_for_status()
            prediction_id = resp.json().get("id")
            if not prediction_id:
                logger.error("Fashn.ai returned no prediction ID: %s", resp.text)
                return None
        except Exception as e:
            logger.error("Fashn.ai submit failed: %s", e)
            return None

        # Poll for result (max 120s, every 4s)
        for _ in range(30):
            await asyncio.sleep(4)
            try:
                status_resp = await client.get(
                    f"{FASHN_BASE_URL}/status/{prediction_id}",
                    headers={"Authorization": f"Bearer {FASHN_API_KEY}"},
                )
                data = status_resp.json()
                state = data.get("status", "")
                if state == "completed":
                    output = data.get("output") or data.get("image")
                    return str(output) if output else None
                if state == "failed":
                    logger.error("Fashn.ai job failed: %s", data.get("error"))
                    return None
            except Exception as e:
                logger.warning("Fashn.ai poll error: %s", e)

    logger.error("Fashn.ai timed out after 120s")
    return None


# ---------------------------------------------------------------------------
# Replicate VTO (fallback — IDM-VTON)
# ---------------------------------------------------------------------------
def run_replicate_vto_sync(
    user_image_path: str,
    product_image_path: str,
    product_name: str,
    product_category: str,
) -> Optional[str]:
    """Synchronous Replicate call — run in a thread when used from async context."""
    category = REPLICATE_CATEGORY_MAP.get(product_category, "dresses")
    seed = random.randint(1, 9999)
    try:
        output = replicate.run(
            "cuuupid/idm-vton:c871bb9b0466074280c2a9a7386749c8b0f4154817d1220268597f9c73335508",
            input={
                "garm_img":    open(product_image_path, "rb"),
                "human_img":   open(user_image_path, "rb"),
                "garment_des": product_name,
                "category":    category,
                "crop":        False,
                "seed":        seed,
            },
        )
        url = str(output)
        if url.startswith("['") and url.endswith("']"):
            url = url[2:-2]
        return url if url.startswith("http") else None
    except Exception as e:
        logger.error("Replicate VTO error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Background worker — called via asyncio.create_task
# ---------------------------------------------------------------------------
async def process_vto_job(
    job_id: str,
    thread_id: str,
    user_image_path: str,
    product_image_url: str,
    product_name: str,
    product_category: str,
) -> None:
    """
    Runs the full VTO pipeline:
      1. Check cache → return instantly if hit
      2. Try Fashn.ai (primary)
      3. Fall back to Replicate IDM-VTON
    Updates job status in Redis throughout.
    """
    set_job_status(job_id, "processing")

    # Cache check
    cached = _get_cached_result(thread_id, product_name)
    if cached:
        logger.info("VTO cache hit for thread=%s product=%s", thread_id, product_name)
        set_job_status(job_id, "completed", result_url=cached)
        return

    result_url: Optional[str] = None

    # Primary: Fashn.ai (needs publicly accessible URLs — upload user image if local)
    if os.path.exists(user_image_path):
        # For Fashn.ai we need a URL, not a file path.
        # Try Cloudinary upload; fall through to Replicate if upload fails.
        try:
            import cloudinary.uploader  # type: ignore
            upload = cloudinary.uploader.upload(user_image_path, folder="pamorya_vto_users")
            user_image_url = upload.get("secure_url", "")
            if user_image_url:
                result_url = await run_fashn_vto(user_image_url, product_image_url, product_category)
        except Exception as e:
            logger.warning("Fashn.ai path (Cloudinary upload) failed: %s — trying Replicate", e)

    # Fallback: Replicate IDM-VTON (accepts local file handles)
    if not result_url:
        logger.info("Falling back to Replicate IDM-VTON")
        local_product = download_image_temp(product_image_url, "prod")
        if local_product:
            result_url = await asyncio.to_thread(
                run_replicate_vto_sync,
                user_image_path, local_product, product_name, product_category,
            )
            if local_product and os.path.exists(local_product):
                os.remove(local_product)

    if result_url:
        _cache_result(thread_id, product_name, result_url)
        set_job_status(job_id, "completed", result_url=result_url)
        logger.info("VTO completed: job_id=%s url=%s", job_id, result_url)
    else:
        set_job_status(job_id, "failed", error="Both Fashn.ai and Replicate failed")
        logger.error("VTO failed for job_id=%s", job_id)


# ---------------------------------------------------------------------------
# Synchronous entry point (used by /chat and WhatsApp webhook)
# ---------------------------------------------------------------------------
def handle_vto_message(thread_id: str, user_text: str, image_path: Optional[str] = None) -> str:
    """
    Stateful VTO flow called by the /chat endpoint.
    Returns a user-facing string at each step.
    For Step 3 (generation), returns an immediate job-queued message and
    starts the async worker in the background.
    """
    db = SessionLocal()
    try:
        vto = get_or_create_session(db, thread_id)

        # Step 1 — user uploaded a photo
        if image_path:
            vto.user_image = image_path
            db.commit()
            if not user_text or len(user_text.strip()) < 2:
                return STEP2_GUIDANCE

        # Resolve product from text
        product_data = None
        if user_text and len(user_text.strip()) > 2:
            product_data = get_product_from_db(user_text)
            if product_data:
                vto.product_image = product_data["url"]
                vto.product_name = product_data["name"]
                db.commit()

        # Guard: need photo
        if not vto.user_image:
            return STEP1_GUIDANCE

        # Guard: need product
        if not vto.product_image:
            if not product_data and user_text and len(user_text.strip()) > 2:
                return (
                    f"I couldn't find **\"{user_text}\"** in our catalogue.\n"
                    "Please try another product name, e.g. \"Crimson Canvas\" or \"Wild Bloom Whisper\"."
                )
            return STEP2_GUIDANCE

        # Check cache before counting against limit
        cached = _get_cached_result(thread_id, vto.product_name)
        if cached:
            return (
                f"Here's your look (cached) 🎉\n\n"
                f'<img src="{cached}" alt="Virtual Try-On: {vto.product_name}" '
                f'style="max-width:100%;border-radius:8px;" />\n\n'
                "Want to try another style? Just tell me another product name."
            )

        # Daily limit check
        if not check_and_increment_limit(db, thread_id, DAILY_LIMIT):
            db.commit()
            return (
                f"You've reached today's limit of {DAILY_LIMIT} try-ons. "
                "Come back tomorrow! 😊"
            )
        db.commit()

        # Launch async job
        job_id = str(uuid.uuid4())
        set_job_status(job_id, "queued")

        asyncio.create_task(
            process_vto_job(
                job_id=job_id,
                thread_id=thread_id,
                user_image_path=vto.user_image,
                product_image_url=vto.product_image,
                product_name=vto.product_name,
                product_category=product_data["category"] if product_data else vto.product_name,
            )
        )

        return (
            f"✨ Generating your look with **{vto.product_name}**!\n\n"
            f"This takes about 20–30 seconds. Your job ID is: `{job_id}`\n\n"
            "You can check the status with the **Check Try-On** button, "
            "or I'll show you the result as soon as it's ready."
        )

    except Exception as e:
        db.rollback()
        logger.error("VTO Handler Error: %s", e)
        return "Something went wrong with the try-on. Please try again."
    finally:
        db.close()
