import os
import random
import requests
import replicate
from datetime import date
from typing import Optional
from dotenv import load_dotenv

from app.database import SessionLocal
from app.models import Product, VtoSession

load_dotenv()

# --- CONFIGURATION ---
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_BASE_URL = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD_NAME}/image/upload/v1765694934/apparel_bot_products/"

DAILY_LIMIT = 5

# Category mapping from DB product.category → Replicate VTO category
CATEGORY_MAP = {
    "Dresses":          "dresses",
    "Skirts":           "lower_body",
    "Pants & Trousers": "lower_body",
    "Tops & Blouses":   "upper_body",
    "Sets & Co-ords":   "dresses",
    "Jumpers & Knits":  "upper_body",
    "Jackets & Outerwear": "upper_body",
}


# ---------------------------------------------------------------------------
# DB-backed session helpers
# ---------------------------------------------------------------------------

def get_or_create_session(db, thread_id: str) -> VtoSession:
    """Retrieve or create a VtoSession row for this thread."""
    session = db.query(VtoSession).filter(VtoSession.thread_id == thread_id).first()
    if not session:
        session = VtoSession(thread_id=thread_id)
        db.add(session)
        db.flush()
    return session


def check_and_increment_limit(db, thread_id: str, daily_limit: int = DAILY_LIMIT) -> bool:
    """
    Returns True if usage is within the daily limit and increments the counter.
    Resets the counter if the stored date differs from today.
    """
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


# ---------------------------------------------------------------------------
# Product helpers
# ---------------------------------------------------------------------------

def get_product_from_db(product_query: str) -> Optional[dict]:
    """Looks up product name, image URL, and category from the DB."""
    db = SessionLocal()
    try:
        product = db.query(Product).filter(
            Product.product_name.ilike(f"%{product_query}%")
        ).first()
        if product and product.image_url:
            return {
                "name": product.product_name,
                "url": product.image_url,
                "category": product.category or "",
            }
    except Exception as e:
        print(f"DB Error in VTO: {e}")
    finally:
        db.close()
    return None


def detect_category_from_db(category: str) -> str:
    """Maps the DB product category string to the Replicate VTO category."""
    return CATEGORY_MAP.get(category, "dresses")


def download_image_temp(url_or_filename: str, filename_tag: str) -> Optional[str]:
    temp_path = f"temp_{filename_tag}.jpg"
    final_url = str(url_or_filename)

    if "localhost" in final_url or "127.0.0.1" in final_url or not final_url.startswith("http"):
        clean_name = os.path.basename(final_url)
        final_url = f"{CLOUDINARY_BASE_URL}{clean_name}"

    print(f"   -> Downloading from: {final_url}")

    try:
        response = requests.get(final_url, stream=True)
        if response.status_code == 200:
            with open(temp_path, "wb") as f:
                f.write(response.content)
            return temp_path
        else:
            print(f"   -> Failed to download. Status Code: {response.status_code}")
    except Exception as e:
        print(f"   -> Download Error: {e}")

    return None


# ---------------------------------------------------------------------------
# Guidance messages
# ---------------------------------------------------------------------------

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

GENERATING_MSG = "✨ Generating your look… this takes ~20 seconds. Please hold on!"


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

def handle_vto_message(thread_id: str, user_text: str, image_path: Optional[str] = None) -> str:
    db = SessionLocal()
    try:
        vto = get_or_create_session(db, thread_id)

        # --- Step 1: User uploaded a photo ---
        if image_path:
            vto.user_image = image_path
            db.commit()
            if not user_text or len(user_text.strip()) < 2:
                return STEP2_GUIDANCE

        # --- Parse product name from text ---
        product_data = None
        if user_text and len(user_text.strip()) > 2:
            product_data = get_product_from_db(user_text)
            if product_data:
                vto.product_image = product_data["url"]
                vto.product_name = product_data["name"]
                db.commit()

        # --- Guard: need user photo ---
        if not vto.user_image:
            return STEP1_GUIDANCE

        # --- Guard: need product ---
        if not vto.product_image:
            if not product_data and user_text and len(user_text.strip()) > 2:
                return (
                    f"I couldn't find a product matching **\"{user_text}\"**.\n"
                    "Please try a different product name, for example: "
                    "\"Crimson Canvas\", \"Pink Rhapsody\", or \"Wild Bloom Whisper\"."
                )
            return STEP2_GUIDANCE

        # --- Check daily limit ---
        if not check_and_increment_limit(db, thread_id, DAILY_LIMIT):
            db.commit()
            return (
                f"You've reached the daily limit of {DAILY_LIMIT} try-ons. "
                "Please come back tomorrow for more! 😊"
            )

        db.commit()

        return run_replicate_vto(
            thread_id=thread_id,
            user_image_path=vto.user_image,
            product_image_url=vto.product_image,
            product_name=vto.product_name,
            product_category=product_data["category"] if product_data else "",
        )

    except Exception as e:
        db.rollback()
        print(f"VTO Handler Error: {e}")
        return "Something went wrong. Please try again."
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Replicate call
# ---------------------------------------------------------------------------

def run_replicate_vto(
    thread_id: str,
    user_image_path: str,
    product_image_url: str,
    product_name: str,
    product_category: str = "",
) -> str:
    local_product_path = download_image_temp(product_image_url, "product_img")
    if not local_product_path:
        return "Error: Could not find the product image on Cloudinary."

    # Use DB-derived category
    category = detect_category_from_db(product_category)
    print(f"-> Detected Category: {category} (from DB category: '{product_category}')")

    # Random seed for varied results each run
    seed = random.randint(1, 9999)
    print(f"-> Using seed: {seed}")

    try:
        output = replicate.run(
            "cuuupid/idm-vton:c871bb9b0466074280c2a9a7386749c8b0f4154817d1220268597f9c73335508",
            input={
                "garm_img":    open(local_product_path, "rb"),
                "human_img":   open(user_image_path, "rb"),
                "garment_des": product_name,
                "category":    category,
                "crop":        False,
                "seed":        seed,
            },
        )

        output_url = str(output)
        if output_url.startswith("['") and output_url.endswith("']"):
            output_url = output_url[2:-2]

        print(f"✅ VTO Success! URL: {output_url}")

        if not output_url.startswith("http"):
            print(f"❌ Still invalid URL: {output_url}")
            return "Sorry, the image generation failed. Please try again."

        if os.path.exists(local_product_path):
            os.remove(local_product_path)

        return (
            f"Here's your look! 🎉\n\n"
            f"<img src=\"{output_url}\" alt=\"Virtual Try-On: {product_name}\" "
            f"style=\"max-width: 100%; border-radius: 8px;\" />\n\n"
            "Want to try another style? Just tell me another product name — "
            "no need to re-upload your photo."
        )

    except Exception as e:
        print(f"VTO Error: {e}")
        return "Sorry, I had trouble generating the image. Please try again later."
