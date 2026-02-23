"""
WhatsApp adapter for Twilio.

Architecture:
  WhatsApp User → Twilio → POST /whatsapp → this module → LangGraph agent → Twilio reply

Environment variables required:
  TWILIO_ACCOUNT_SID      - Twilio account SID (ACxxxx)
  TWILIO_AUTH_TOKEN       - Twilio auth token
  TWILIO_WHATSAPP_NUMBER  - Twilio sender number, e.g. whatsapp:+1415xxxxxxx
"""

import os
import re
import asyncio
import shutil
import tempfile
import uuid
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

load_dotenv()

TWILIO_ACCOUNT_SID     = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN      = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

TWILIO_MESSAGES_URL = (
    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
)


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------

def parse_twilio_payload(form_data: dict) -> dict:
    """
    Extract the fields we care about from a Twilio webhook form POST.

    Returns:
        {
          "from": "whatsapp:+94771234567",
          "thread_id": "whatsapp:+94771234567",   # phone as stable thread key
          "text": "Hello",
          "media_url": "https://…" or None,       # first media attachment
        }
    """
    sender   = form_data.get("From", "")
    body     = form_data.get("Body", "").strip()
    media0   = form_data.get("MediaUrl0") or None

    return {
        "from":      sender,
        "thread_id": sender,   # stable across messages from the same number
        "text":      body,
        "media_url": media0,
    }


# ---------------------------------------------------------------------------
# Media download
# ---------------------------------------------------------------------------

async def download_whatsapp_image(media_url: str) -> Optional[str]:
    """
    Download the image attached to a WhatsApp message to a temp file.
    Twilio media URLs require HTTP Basic auth with account SID + auth token.
    Returns the local file path or None on failure.
    """
    if not media_url:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                media_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                follow_redirects=True,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"⚠️ WhatsApp media download failed: {resp.status_code}")
                return None

            ext = "jpg"
            content_type = resp.headers.get("content-type", "")
            if "png" in content_type:
                ext = "png"
            elif "webp" in content_type:
                ext = "webp"

            os.makedirs("uploaded_images", exist_ok=True)
            filename  = f"{uuid.uuid4()}.{ext}"
            file_path = os.path.join("uploaded_images", filename)
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path

    except Exception as exc:
        print(f"⚠️ WhatsApp media download error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------

def format_for_whatsapp(html_response: str) -> tuple[str, list[str]]:
    """
    Convert the HTML/markdown AI response to WhatsApp-friendly plain text.

    Returns:
        (text_body, image_urls)
        text_body  — plain text with WhatsApp *bold* and newlines
        image_urls — list of image URLs to send as media messages
    """
    text = html_response

    # Extract image URLs before stripping tags
    image_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)

    # Strip all HTML tags
    text = re.sub(r'<img[^>]*>', '', text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)

    # Convert **bold** markdown → WhatsApp *bold*
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    text = text.strip()
    return text, image_urls


# ---------------------------------------------------------------------------
# Twilio send
# ---------------------------------------------------------------------------

async def send_whatsapp_reply(
    to: str,
    text: str,
    media_urls: Optional[list[str]] = None,
) -> None:
    """
    Send a reply to a WhatsApp user via the Twilio Messages API.
    Supports up to 10 media attachments per message.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        print("⚠️ Twilio credentials not configured — skipping WhatsApp send.")
        return

    media_urls = (media_urls or [])[:10]

    payload: dict = {
        "From": TWILIO_WHATSAPP_NUMBER,
        "To":   to,
        "Body": text,
    }
    for i, url in enumerate(media_urls):
        payload[f"MediaUrl{i}"] = url

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TWILIO_MESSAGES_URL,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                print(f"⚠️ Twilio send failed ({resp.status_code}): {resp.text}")
            else:
                print(f"✅ WhatsApp reply sent to {to}")
    except Exception as exc:
        print(f"⚠️ Twilio send error: {exc}")
