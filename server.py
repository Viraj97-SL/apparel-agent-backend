import uvicorn
import uuid
import shutil
import os
import sqlite3
from contextlib import asynccontextmanager  # <--- NEW: Modern Startup Handler

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

# --- DB IMPORTS ---
from app.db_builder import init_db, populate_initial_data
from app.db_builder import init_db, populate_initial_data

# --- SECURITY: Rate Limiting Imports ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- AGENT IMPORTS ---
# Ensure these files exist and have no errors!
from app.agent import app as rag_agent_app
from app.vto_agent import handle_vto_message

# --- CONFIGURATION ---
UPLOAD_DIR = "uploaded_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = "apparel.db"  # Path for the startup check

# SECURITY: Allowed file types and Max Size (5MB)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif"}
MAX_FILE_SIZE = 5 * 1024 * 1024


# --- LIFESPAN MANAGER (The Modern Startup Way) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 Lifespan: Checking database status...")
    try:
        # 1. Initialize Tables (Postgres)
        init_db()

        # 2. Populate Data
        populate_initial_data()

    except Exception as e:
        print(f"❌ Startup Error: {e}")

    yield
    print("🛑 Shutdown: Server closing...")

# --- INITIALIZE APP ---
# 1. Setup the Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# 2. Initialize FastAPI with Lifespan
app = FastAPI(
    title="Apparel Chatbot API",
    description="Secure API for the multi-agent apparel customer service chatbot.",
    version="1.0",
    lifespan=lifespan,  # <--- CONNECT LIFESPAN HERE
    servers=[
        {"url": "https://apparel-agent-backend-production.up.railway.app", "description": "Production Server"},
        {"url": "http://localhost:8000", "description": "Local Development"}
    ]
)

# 3. Connect Limiter to API
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 4. Mount Static Files
app.mount("/uploaded_images", StaticFiles(directory=UPLOAD_DIR), name="images")
# Mount the product images folder (if you use local images)
os.makedirs("product_images", exist_ok=True)
app.mount("/product_images", StaticFiles(directory="product_images"), name="products")

# --- SECURITY: CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # <--- Allow ALL for testing (Change to specific domains in prod if needed)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OutputChat(BaseModel):
    response: str
    thread_id: str


# --- THE CHAT ENDPOINT ---
@app.post("/chat", response_model=OutputChat)
@limiter.limit("50/minute")
async def chat(
        request: Request,
        query: str = Form(...),
        thread_id: str = Form(None),
        mode: str = Form("standard"),
        file: UploadFile = File(None)
):
    # 1. Ensure Thread ID
    if not thread_id:
        thread_id = str(uuid.uuid4())

    image_path = None

    # --- SECURITY: File Validation ---
    if file:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)

        if size > MAX_FILE_SIZE:
            return OutputChat(response="Error: Image is too large. Max size is 5MB.", thread_id=thread_id)

        filename = file.filename.lower()
        ext = filename.split(".")[-1] if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return OutputChat(response="Error: Invalid file type.", thread_id=thread_id)

        safe_filename = f"{uuid.uuid4()}.{ext}"
        file_location = os.path.join(UPLOAD_DIR, safe_filename)

        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)

        image_path = file_location

    # --- AGENT LOGIC ---
    final_response = "Error processing request."

    try:
        if mode == "vto":
            print(f"--- VTO MODE [Thread: {thread_id}] ---")
            final_response = handle_vto_message(thread_id, query, image_path)
        else:
            print(f"--- STANDARD MODE [Thread: {thread_id}] ---")
            config = {"configurable": {"thread_id": thread_id}}
            input_message = [HumanMessage(content=query)]

            async for event in rag_agent_app.astream({"messages": input_message}, config=config, stream_mode="values"):
                new_messages = event.get("messages", [])
                if new_messages:
                    last_message = new_messages[-1]
                    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
                        raw_content = last_message.content
                        if isinstance(raw_content, list) and raw_content:
                            first_part = raw_content[0]
                            if "text" in first_part:
                                final_response = first_part["text"]
                        elif isinstance(raw_content, str):
                            final_response = raw_content
    except Exception as e:
        print(f"ERROR in Chat Endpoint: {e}")
        final_response = "I encountered an internal error. Please try again."

    if final_response is None:
        final_response = "Sorry, I couldn't find an answer to that."

    return OutputChat(response=final_response, thread_id=thread_id)


if __name__ == "__main__":
    # IMPORTANT: The Dockerfile runs 'uvicorn server:app', so this block is for local testing only.
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)