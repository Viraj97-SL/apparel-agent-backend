import asyncio
import logging
import os
import re
import shutil
import time
import traceback
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.observability import configure_langsmith

# --- DB IMPORTS ---
from app.db_builder import init_db, populate_initial_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure LangSmith before the agent module loads
configure_langsmith()

# --- SECURITY: Rate Limiting ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# --- AGENT IMPORTS ---
from app.agent import workflow, ensure_tools, create_memory
from app.vto_agent import handle_vto_message

rag_agent_app = None  # compiled in lifespan after the event loop is running
from app.whatsapp_adapter import (
    parse_twilio_payload,
    download_whatsapp_image,
    format_for_whatsapp,
    send_whatsapp_reply,
)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
UPLOAD_DIR = "uploaded_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# SECURITY: Allowed file types and max size (5 MB)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Input guardrails
MAX_QUERY_LENGTH = 2_000           # characters
AGENT_TIMEOUT_SECONDS = 90         # cap a single agent run

# CORS — restrict to known origins; override via env for flexibility
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "https://apparel-agent-frontend.vercel.app,http://localhost:3000,http://localhost:8000",
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Patterns that look like prompt-injection attempts
_INJECTION_PATTERNS = re.compile(
    r"(ignore (previous|all|prior|above) instructions?|"
    r"you are now|forget (your|all) (instructions?|rules?)|"
    r"system prompt|act as (an? )?[a-z]+|jailbreak|"
    r"do anything now|dan mode)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LIFESPAN MANAGER
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_agent_app
    print("🔄 Lifespan: Checking database status...")
    try:
        init_db()
        populate_initial_data()
    except Exception as exc:
        print(f"❌ DB Startup Error: {exc}")
    try:
        await ensure_tools()
        memory = await create_memory()
        rag_agent_app = workflow.compile(checkpointer=memory)
        print("✅ LangGraph agent initialized.")
    except Exception as exc:
        print(f"❌ Agent Startup Error: {exc}")
    yield
    print("🛑 Shutdown: Server closing...")


# ---------------------------------------------------------------------------
# INITIALIZE APP
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Apparel Chatbot API",
    version="1.0",
    lifespan=lifespan,
    servers=[
        {"url": "https://apparel-agent-backend-production.up.railway.app", "description": "Production Server"},
        {"url": "http://localhost:8000", "description": "Local Development"},
    ],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/uploaded_images", StaticFiles(directory=UPLOAD_DIR), name="images")
os.makedirs("product_images", exist_ok=True)
app.mount("/product_images", StaticFiles(directory="product_images"), name="products")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------------------------------------------------------------------------
# RESPONSE MODEL
# ---------------------------------------------------------------------------
class OutputChat(BaseModel):
    response: str
    thread_id: str


# ---------------------------------------------------------------------------
# STALE-STATE RESOLVER
# Fix: when MCP tool retries under DB pressure the checkpointer persists
# an intermediate AIMessage that has tool_calls but no matching ToolMessages.
# If the user sends Q2 before Q1 finishes, LangGraph resumes that stale
# checkpoint and returns Q1's answer for Q2.
#
# This resolver detects the dirty state and injects synthetic cleanup
# ToolMessages so the graph reaches a clean handoff point before Q2 runs.
# ---------------------------------------------------------------------------
async def resolve_stale_state(config: dict) -> bool:
    """
    Inspect the current checkpoint for a thread.
    If the last persisted message is an AIMessage with unresolved tool_calls
    (i.e. no matching ToolMessage was ever appended), inject cleanup
    ToolMessages to force a known-good state before processing new input.

    Returns True if a stale state was detected and patched.
    """
    try:
        snapshot = await rag_agent_app.aget_state(config)
        if not snapshot or not snapshot.values:
            return False

        messages = snapshot.values.get("messages", [])
        if not messages:
            return False

        last_msg = messages[-1]

        # A stale state: the last saved message is an AI turn that generated
        # tool calls but the run was interrupted before ToolMessages arrived.
        if not (isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)):
            return False

        # Verify there is truly no ToolMessage covering these tool_call ids
        pending_ids = {tc["id"] for tc in last_msg.tool_calls}
        covered_ids = {
            m.tool_call_id
            for m in messages
            if isinstance(m, ToolMessage) and hasattr(m, "tool_call_id")
        }
        unresolved = pending_ids - covered_ids
        if not unresolved:
            return False

        print(
            f"⚠️  Stale state on thread {config['configurable']['thread_id']}: "
            f"{len(unresolved)} unresolved tool call(s). Injecting cleanup..."
        )

        cleanup_messages = [
            ToolMessage(
                content=(
                    "[Previous request was interrupted before completing. "
                    "The following message is a fresh question.]"
                ),
                tool_call_id=tc_id,
            )
            for tc_id in unresolved
        ]

        await rag_agent_app.aupdate_state(config, {"messages": cleanup_messages})
        print("✅ Stale state resolved — clean handoff point established.")
        return True

    except Exception as exc:
        # Non-fatal: log and continue.  A stale state is better than a crash.
        print(f"⚠️  resolve_stale_state error (non-fatal): {exc}")
        return False


# ---------------------------------------------------------------------------
# INPUT VALIDATION
# ---------------------------------------------------------------------------
def validate_query(query: str) -> str | None:
    """
    Returns an error string if the query fails validation, else None.
    Checks: empty, too long, obvious prompt-injection patterns.
    """
    stripped = query.strip()
    if not stripped:
        return "Please enter a message."
    if len(stripped) > MAX_QUERY_LENGTH:
        return f"Your message is too long (max {MAX_QUERY_LENGTH} characters). Please shorten it."
    if _INJECTION_PATTERNS.search(stripped):
        return (
            "I'm sorry, I can only help with Pamorya clothing questions. "
            "Please ask about our products, orders, or store policies."
        )
    return None


# ---------------------------------------------------------------------------
# CHAT ENDPOINT
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=OutputChat)
@limiter.limit("50/minute")
async def chat(
    request: Request,
    query: str = Form(...),
    thread_id: str = Form(None),
    mode: str = Form("standard"),
    file: UploadFile = File(None),
):
    # 1. Ensure Thread ID
    if not thread_id:
        thread_id = str(uuid.uuid4())

    if rag_agent_app is None:
        return OutputChat(
            response="Server is still starting up. Please try again in a moment.",
            thread_id=thread_id,
        )

    # 2. Input validation
    validation_error = validate_query(query)
    if validation_error:
        return OutputChat(response=validation_error, thread_id=thread_id)

    image_path = None

    # 3. SECURITY: File validation
    if file:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE:
            return OutputChat(response="Error: Image is too large (max 5 MB).", thread_id=thread_id)
        filename = file.filename.lower()
        ext = filename.split(".")[-1] if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return OutputChat(
                response=f"Error: Invalid file type '.{ext}'. Accepted: jpg, jpeg, png, webp, avif.",
                thread_id=thread_id,
            )
        safe_filename = f"{uuid.uuid4()}.{ext}"
        file_location = os.path.join(UPLOAD_DIR, safe_filename)
        with open(file_location, "wb+") as fobj:
            shutil.copyfileobj(file.file, fobj)
        image_path = file_location

    # 4. Agent logic
    final_response: str | None = None

    try:
        if mode == "vto":
            print(f"--- VTO MODE [Thread: {thread_id}] ---")
            final_response = handle_vto_message(thread_id, query, image_path)

        else:
            print(f"--- STANDARD MODE [Thread: {thread_id}] ---")
            config = {"configurable": {"thread_id": thread_id}}

            # ----------------------------------------------------------------
            # FIX: Resolve stale state BEFORE processing the new message.
            # If a previous run was interrupted mid-tool-call the checkpoint
            # holds an AIMessage with dangling tool_calls.  Without cleanup,
            # LangGraph would resume that stale state and return Q1's answer
            # for Q2.  The resolver injects synthetic ToolMessages to close
            # the open tool call so the graph starts fresh for this message.
            # ----------------------------------------------------------------
            await resolve_stale_state(config)

            input_message = [HumanMessage(content=query)]

            # ----------------------------------------------------------------
            # FIX: asyncio.timeout caps slow runs instead of letting them hang
            # indefinitely.  A TimeoutError is caught below and surfaced as a
            # friendly message; the interrupted state will be cleaned up the
            # next time resolve_stale_state runs.
            # ----------------------------------------------------------------
            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                async for event in rag_agent_app.astream(
                    {"messages": input_message},
                    config=config,
                    stream_mode="values",
                ):
                    new_messages = event.get("messages", [])
                    if not new_messages:
                        continue
                    last_message = new_messages[-1]

                    if isinstance(last_message, AIMessage) and last_message.content:
                        raw_content = last_message.content
                        text_content = ""
                        if isinstance(raw_content, str):
                            text_content = raw_content
                        elif isinstance(raw_content, list):
                            for part in raw_content:
                                if isinstance(part, dict) and "text" in part:
                                    text_content += part["text"]

                        if text_content.strip():
                            final_response = text_content

    except asyncio.TimeoutError:
        print(f"⏱️  Agent timed out after {AGENT_TIMEOUT_SECONDS}s [Thread: {thread_id}]")
        final_response = (
            "I'm taking a bit longer than usual on that one — sorry about that! "
            "Please try asking again in a moment."
        )

    except Exception as exc:
        print(f"❌ INTERNAL ERROR [Thread: {thread_id}]: {exc}")
        traceback.print_exc()
        final_response = "I encountered a temporary error. Please try asking again."

    # 5. Fallback if no response was collected
    if not final_response:
        final_response = (
            "I processed your request but didn't receive a text response. "
            "Please try rephrasing your question."
        )

    return OutputChat(response=final_response, thread_id=thread_id)


# ---------------------------------------------------------------------------
# WHATSAPP WEBHOOK (Twilio)
# ---------------------------------------------------------------------------
@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receives incoming WhatsApp messages from Twilio, runs the agent,
    and sends a reply back via the Twilio Messages API.

    Required env vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
    Set the Twilio sandbox/webhook URL to: https://<your-domain>/whatsapp
    """
    form = await request.form()
    payload = parse_twilio_payload(dict(form))

    thread_id  = payload["thread_id"]
    user_text  = payload["text"]
    media_url  = payload["media_url"]
    sender     = payload["from"]

    print(f"--- WhatsApp [{thread_id}]: '{user_text}' | media={bool(media_url)} ---")

    # Download any attached image
    image_path: str | None = None
    if media_url:
        image_path = await download_whatsapp_image(media_url)

    final_response = ""

    try:
        # Determine mode: VTO if an image is present OR if recent history suggests VTO
        # For simplicity, treat image uploads as VTO mode; text-only as standard
        if image_path and not user_text:
            # Photo with no text → VTO photo step
            final_response = handle_vto_message(thread_id, "", image_path)
        elif image_path:
            # Photo + text → could be VTO product selection or general
            final_response = handle_vto_message(thread_id, user_text, image_path)
        else:
            # Standard text → LangGraph agent
            config = {"configurable": {"thread_id": thread_id}}
            await resolve_stale_state(config)

            input_message = [HumanMessage(content=user_text or "Hello")]

            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                async for event in rag_agent_app.astream(
                    {"messages": input_message},
                    config=config,
                    stream_mode="values",
                ):
                    new_messages = event.get("messages", [])
                    if not new_messages:
                        continue
                    last_message = new_messages[-1]
                    if isinstance(last_message, AIMessage) and last_message.content:
                        raw_content = last_message.content
                        text_content = ""
                        if isinstance(raw_content, str):
                            text_content = raw_content
                        elif isinstance(raw_content, list):
                            for part in raw_content:
                                if isinstance(part, dict) and "text" in part:
                                    text_content += part["text"]
                        if text_content.strip():
                            final_response = text_content

    except asyncio.TimeoutError:
        final_response = "I'm taking a bit longer than usual — please try again in a moment."
    except Exception as exc:
        print(f"❌ WhatsApp agent error: {exc}")
        traceback.print_exc()
        final_response = "I encountered a temporary error. Please try again."

    if not final_response:
        final_response = "I processed your request but couldn't generate a response."

    # Format and send reply
    text_body, image_urls = format_for_whatsapp(final_response)
    await send_whatsapp_reply(to=sender, text=text_body, media_urls=image_urls)

    # Twilio expects a 200 OK (empty TwiML or plain 200 is fine for async replies)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# VTO ASYNC ENDPOINTS
# ---------------------------------------------------------------------------
class VtoStartResponse(BaseModel):
    job_id: str
    status: str
    estimated_seconds: int


class VtoStatusResponse(BaseModel):
    job_id: str
    status: str
    result_url: str
    error: str
    message: str = ""
    provider: str = ""
    estimated_seconds_remaining: int = 0


@app.post("/vto/start", response_model=VtoStartResponse)
@limiter.limit("10/minute")
async def vto_start(
    request: Request,
    thread_id: str = Form(...),
    product_name: str = Form(...),
    file: UploadFile = File(None),
):
    """
    Enqueue a VTO job and return immediately.
    Frontend polls /vto/status/{job_id} for the result.
    """
    from app.vto_agent import (
        get_product_from_db, get_or_create_session, check_and_increment_limit,
        process_vto_job, set_job_status, _get_cached_result
    )

    if not thread_id:
        thread_id = str(uuid.uuid4())

    # Handle file upload
    image_path = None
    if file:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE:
            return VtoStartResponse(job_id="", status="error", estimated_seconds=0)
        ext = (file.filename.lower().split(".")[-1] if "." in file.filename else "")
        if ext not in ALLOWED_EXTENSIONS:
            return VtoStartResponse(job_id="", status="error", estimated_seconds=0)
        safe_filename = f"{uuid.uuid4()}.{ext}"
        file_location = os.path.join(UPLOAD_DIR, safe_filename)
        with open(file_location, "wb+") as f:
            shutil.copyfileobj(file.file, f)
        image_path = file_location

    # Look up product
    from app.database import SessionLocal
    from app.models import VtoSession

    product_data = get_product_from_db(product_name)
    if not product_data:
        return VtoStartResponse(job_id="", status="product_not_found", estimated_seconds=0)

    # Cache check
    cached = _get_cached_result(thread_id, product_data["name"])
    if cached:
        job_id = str(uuid.uuid4())
        set_job_status(job_id, "completed", result_url=cached)
        return VtoStartResponse(job_id=job_id, status="cached", estimated_seconds=0)

    # Resolve user image from session if not uploaded now
    db = SessionLocal()
    try:
        vto = get_or_create_session(db, thread_id)
        if image_path:
            vto.user_image = image_path
        if not vto.user_image:
            db.close()
            return VtoStartResponse(job_id="", status="no_user_photo", estimated_seconds=0)
        user_image = vto.user_image
        if not check_and_increment_limit(db, thread_id):
            db.close()
            return VtoStartResponse(job_id="", status="daily_limit_reached", estimated_seconds=0)
        db.commit()
    finally:
        db.close()

    job_id = str(uuid.uuid4())
    set_job_status(job_id, "queued")

    asyncio.create_task(
        process_vto_job(
            job_id=job_id,
            thread_id=thread_id,
            user_image_path=user_image,
            product_image_url=product_data["url"],
            product_name=product_data["name"],
            product_category=product_data["category"],
        )
    )

    return VtoStartResponse(job_id=job_id, status="queued", estimated_seconds=25)


@app.get("/vto/status/{job_id}", response_model=VtoStatusResponse)
async def vto_status(job_id: str):
    """Poll for VTO job result. Frontend calls this every 3s until status=completed."""
    from app.vto_agent import get_job_status
    data = get_job_status(job_id)
    return VtoStatusResponse(
        job_id=job_id,
        status=data.get("status", "not_found"),
        result_url=data.get("result_url", ""),
        error=data.get("error", ""),
        message=data.get("message", ""),
        provider=data.get("provider", ""),
        estimated_seconds_remaining=data.get("estimated_seconds_remaining", 0),
    )


# ---------------------------------------------------------------------------
# TRENDING PRODUCTS ENDPOINT
# ---------------------------------------------------------------------------

# Cloudinary image URLs for known products (used to enrich DB results)
_PRODUCT_IMAGE_MAP: dict[str, str] = {
    "Wild Bloom Whisper": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769167858/PWBW01_v1lxc3.jpg",
    "Midnight Velvet Dream": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694929/apparel_bot_products/PMVD011.jpg",
    "Pink Rhapsody": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694925/apparel_bot_products/PPR02.jpg",
    "Rosé Ruffle Gingham": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960032/PRRGM059_03_fedgsr.jpg",
    "White Wrap Daydress": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960130/PWWD03_01_sfktbz.jpg",
    "Blue Floral Bloom": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PFB019.jpg",
    "Azure Teal Dream": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960086/PATD044_03_iuenxy.jpg",
    "Polished Sophistication": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960161/PPS025_01_ax45ln.jpg",
    "Crimson Canvas": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PCC010.jpg",
    "The Every-Wear Edge": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694927/apparel_bot_products/PEWE06.jpg",
    "Forest Glade Wrap": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960101/PFGW039_03_l67xv5.jpg",
    "Summer Picnic Gingham": "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694928/apparel_bot_products/PSPG08.jpg",
}

_TRENDING_NAMES = list(_PRODUCT_IMAGE_MAP.keys())


def _resolve_image(product) -> str | None:
    """Return the best image URL for a product: map lookup → DB field → None."""
    mapped = _PRODUCT_IMAGE_MAP.get(product.product_name)
    if mapped:
        return mapped
    if product.image_url:
        first = product.image_url.split(",")[0].strip()
        return first if first.startswith("http") else None
    return None


@app.get("/api/trending")
async def trending():
    """Return up to 12 trending products with image URLs for the frontend."""
    try:
        from app.database import SessionLocal
        from app.models import Product

        with SessionLocal() as db:
            # Prefer known trending products, then fill with any others
            known = db.query(Product).filter(
                Product.product_name.in_(_TRENDING_NAMES)
            ).all()

            result = [
                {
                    "product_name": p.product_name,
                    "price": int(p.price) if p.price else 0,
                    "category": p.category or "",
                    "image_url": _resolve_image(p),
                }
                for p in known
            ]

            # Pad with other products if fewer than 6
            if len(result) < 6:
                others = db.query(Product).filter(
                    Product.product_name.notin_(_TRENDING_NAMES)
                ).limit(6 - len(result)).all()
                result += [
                    {
                        "product_name": p.product_name,
                        "price": int(p.price) if p.price else 0,
                        "category": p.category or "",
                        "image_url": _resolve_image(p),
                    }
                    for p in others
                ]

            return result[:12]

    except Exception as e:
        logger.warning("Trending endpoint error: %s", e)
        return []


# ---------------------------------------------------------------------------
# HEALTH + METRICS ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Liveness probe — returns DB reachability and uptime."""
    from app.database import SessionLocal
    db_ok = False
    try:
        with SessionLocal() as session:
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "db": "ok" if db_ok else "unreachable",
        "version": "2.0.0",
    }


@app.get("/metrics")
async def metrics():
    """Basic operational metrics for the dashboard and LangSmith."""
    from app.models import Order, VtoSession
    from app.database import SessionLocal
    from sqlalchemy import func

    try:
        with SessionLocal() as session:
            order_count = session.query(func.count(Order.id)).scalar() or 0
            vto_count = session.query(func.count(VtoSession.thread_id)).scalar() or 0
    except Exception:
        order_count = 0
        vto_count = 0

    return {
        "orders_total": order_count,
        "vto_sessions_total": vto_count,
        "agent_version": "langgraph_v3",
        "models": {
            "supervisor": __import__("os").getenv("GEMINI_SUPERVISOR_MODEL", "gemini-2.5-pro"),
            "worker": __import__("os").getenv("GEMINI_WORKER_MODEL", "gemini-2.5-flash"),
        },
    }


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
