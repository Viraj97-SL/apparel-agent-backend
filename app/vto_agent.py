import os
import sqlite3
import requests
import shutil
import uuid
import replicate
from datetime import date
from typing import Optional, Dict
from dotenv import load_dotenv

load_dotenv()

# Setup Paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(project_root, "apparel.db")

# --- CONFIGURATION ---
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/"

vto_sessions: Dict[str, dict] = {}
user_usage_tracker: Dict[str, dict] = {}
DAILY_LIMIT = 3


def check_user_limit(thread_id: str) -> bool:
    today = str(date.today())
    if thread_id not in user_usage_tracker:
        user_usage_tracker[thread_id] = {"date": today, "count": 0}
    user_data = user_usage_tracker[thread_id]
    if user_data["date"] != today:
        user_data["date"] = today
        user_data["count"] = 0
    return user_data["count"] < DAILY_LIMIT


def increment_user_usage(thread_id: str):
    if thread_id in user_usage_tracker:
        user_usage_tracker[thread_id]["count"] += 1


def get_product_image_from_db(product_query: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_name, image_url FROM products WHERE product_name LIKE ? LIMIT 1",
                           (f"%{product_query}%",))
            result = cursor.fetchone()
            if result:
                return {"name": result[0], "url": result[1]}
    except Exception as e:
        print(f"DB Error: {e}")
    return None


def download_image_temp(url_or_filename: str, filename_tag: str) -> str:
    temp_path = f"temp_{filename_tag}.jpg"
    final_url = str(url_or_filename)

    if "localhost" in final_url or "127.0.0.1" in final_url or not final_url.startswith("http"):
        clean_name = os.path.basename(final_url)
        final_url = f"{CLOUDINARY_BASE_URL}{clean_name}"

    print(f"   -> Downloading from: {final_url}")

    try:
        response = requests.get(final_url, stream=True)
        if response.status_code == 200:
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            return temp_path
        else:
            print(f"   -> Failed to download. Status Code: {response.status_code}")
    except Exception as e:
        print(f"   -> Download Error: {e}")

    return None


def handle_vto_message(thread_id: str, user_text: str, image_path: Optional[str] = None) -> str:
    if thread_id not in vto_sessions:
        vto_sessions[thread_id] = {"user_image": None, "product_image": None, "product_name": None}

    session = vto_sessions[thread_id]

    if image_path:
        session["user_image"] = image_path
        if not user_text:
            return "Great! I've received your photo. Now, which product would you like to try on?"

    if user_text and len(user_text) > 2:
        product_data = get_product_image_from_db(user_text)
        if product_data:
            session["product_image"] = product_data["url"]
            session["product_name"] = product_data["name"]
            if not image_path and not session["user_image"]:
                return f"Okay, I found the '{product_data['name']}'. Now, please upload a full-body photo of yourself."

    if not session["user_image"]:
        return "To start, please upload a clear, full-body photo of yourself."
    if not session["product_image"]:
        return "I have your photo! Now, tell me the name of the product."
    if not check_user_limit(thread_id):
        return f"Daily limit reached ({DAILY_LIMIT}). Please try again tomorrow!"

    return run_replicate_vto(thread_id, session["user_image"], session["product_image"], session["product_name"])


# --- In app/vto_agent.py ---

def run_replicate_vto(thread_id: str, user_image_path: str, product_image_url: str, product_name: str) -> str:
    # 1. Download Product Image
    local_product_path = download_image_temp(product_image_url, "product_img")

    if not local_product_path:
        return "Error: Could not find the product image on Cloudinary."

    try:
        # 2. Run Replicate (IDM-VTON) with IMPROVED PARAMETERS
        output = replicate.run(
            "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
            input={
                "garm_img": open(local_product_path, "rb"),
                "human_img": open(user_image_path, "rb"),
                "garment_des": product_name,
                # --- PARAMETER CHANGES ---
                "crop": True,  # CHANGED from False to True. Helps focus on the person.
                # "seed": 42,   # REMOVED. Removing fixed seed allows natural variation.
                # -------------------------
            }
        )

        # Force convert object to String to handle Replicate's file output object
        output_url = str(output)

        increment_user_usage(thread_id)

        if os.path.exists(local_product_path):
            os.remove(local_product_path)

        # Return HTML image for the chat window
        return f"Here is how the {product_name} looks on you!<br><br><img src=\"{output_url}\" alt=\"Virtual Try-On Result\" style=\"max-width: 100%; border-radius: 8px;\" />"

    except Exception as e:
        print(f"VTO Error: {e}")
        return "Sorry, I had trouble generating the image. Please try again later."