import asyncio
import os
import re
import shutil
import traceback
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

# --- DB IMPORTS ---
from app.db_builder import init_db, populate_initial_data

# --- SECURITY: Rate Limiting ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# --- AGENT IMPORTS ---
from app.agent import app as rag_agent_app
from app.vto_agent import handle_vto_message
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
    print("🔄 Lifespan: Checking database status...")
    try:
        init_db()
        populate_initial_data()
    except Exception as exc:
        print(f"❌ Startup Error: {exc}")
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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
