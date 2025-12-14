import uvicorn
import uuid
import shutil
import os
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

# --- SECURITY: Rate Limiting Imports ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import your agents
from app.agent import app as rag_agent_app
from app.vto_agent import handle_vto_message

# --- CONFIGURATION ---
UPLOAD_DIR = "uploaded_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# SECURITY: Allowed file types and Max Size (5MB)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "avif"}
MAX_FILE_SIZE = 5 * 1024 * 1024

# --- INITIALIZE APP ---
# 1. Setup the Rate Limiter (The Bouncer)
limiter = Limiter(key_func=get_remote_address)

api = FastAPI(
    title="Apparel Chatbot API",
    description="Secure API for the multi-agent apparel customer service chatbot."
)

# 2. Connect Limiter to API
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Mount Static Files (So we can see VTO results)
api.mount("/uploaded_images", StaticFiles(directory=UPLOAD_DIR), name="images")

# Mount the product images folder
os.makedirs("product_images", exist_ok=True) # Create if missing
api.mount("/product_images", StaticFiles(directory="product_images"), name="products")

# --- SECURITY: CORS (The Perimeter Fence) ---
# Only allow these specific websites to talk to your server
origins = [
    "http://localhost:3000",  # Your local React Frontend
    "http://127.0.0.1:3000",  # Alternative local address
    # "https://xxxx-xxxx.ngrok-free.app" # <--- UNCOMMENT THIS when you run ngrok
]

api.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Only allow reading/writing, no deleting
    allow_headers=["*"],
)


class OutputChat(BaseModel):
    response: str
    thread_id: str


# --- THE CHAT ENDPOINT ---
@api.post("/chat", response_model=OutputChat)
@limiter.limit("50/minute")  # SECURITY: Allow max 5 messages per minute per user
async def chat(
        request: Request,  # Required for Rate Limiting
        query: str = Form(...),
        thread_id: str = Form(None),
        mode: str = Form("standard"),
        file: UploadFile = File(None)
):
    # 1. Ensure Thread ID
    if not thread_id:
        thread_id = str(uuid.uuid4())

    image_path = None

    # --- SECURITY: File Validation (The ID Check) ---
    if file:
        # A. Check File Size (Prevent crash via massive files)
        file.file.seek(0, 2)  # Move to end of file
        size = file.file.tell()  # Get size
        file.file.seek(0)  # Reset to start

        if size > MAX_FILE_SIZE:
            return OutputChat(response="Error: Image is too large. Max size is 5MB.", thread_id=thread_id)

        # B. Check Extension (Prevent scripts)
        filename = file.filename.lower()
        ext = filename.split(".")[-1] if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return OutputChat(response="Error: Invalid file type. Only JPG, PNG, WEBP allowed.", thread_id=thread_id)

        # C. Sanitize Filename (Prevent overwriting/hacking)
        # We IGNORE the user's filename (e.g., 'hack.exe'). We give it a random ID.
        safe_filename = f"{uuid.uuid4()}.{ext}"
        file_location = os.path.join(UPLOAD_DIR, safe_filename)

        # Save securely
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)

        image_path = file_location
        print(f"Securely saved file to: {image_path}")

    # --- AGENT LOGIC (Unchanged) ---
    final_response = "Error processing request."

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

    if final_response is None:
        final_response = "Sorry, I couldn't find an answer to that."

    return OutputChat(response=final_response, thread_id=thread_id)


if __name__ == "__main__":
    print("Starting SECURE API server...")
    uvicorn.run("server:api", host="127.0.0.1", port=8000, reload=True)