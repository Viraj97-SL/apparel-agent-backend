import os
import sqlite3
import requests
import shutil
import uuid
import replicate
from datetime import date
from typing import Optional, Dict
from dotenv import load_dotenv

# Ensure env vars are loaded
load_dotenv()

# Import your database path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(project_root, "apparel.db")
PRODUCT_IMAGES_DIR = os.path.join(project_root, "product_images")  # Path to your real images

# In-memory storage
vto_sessions: Dict[str, dict] = {}

# --- USER LIMIT TRACKER ---
user_usage_tracker: Dict[str, dict] = {}
DAILY_LIMIT = 3  # Max 3 tries per day


def check_user_limit(thread_id: str) -> bool:
    """Returns True if user is allowed, False if limit reached."""
    today = str(date.today())
    if thread_id not in user_usage_tracker:
        user_usage_tracker[thread_id] = {"date": today, "count": 0}

    user_data = user_usage_tracker[thread_id]
    if user_data["date"] != today:
        user_data["date"] = today
        user_data["count"] = 0

    if user_data["count"] >= DAILY_LIMIT:
        return False
    return True


def increment_user_usage(thread_id: str):
    if thread_id in user_usage_tracker:
        user_usage_tracker[thread_id]["count"] += 1


def get_product_image_from_db(product_query: str):
    """Search for a product image in the DB."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_name, image_url FROM products WHERE product_name LIKE ? LIMIT 1",
                           (f"%{product_query}%",))
            result = cursor.fetchone()

            if not result and " " in product_query:
                first_word = product_query.split(" ")[0]
                if len(first_word) > 2:
                    cursor.execute("SELECT product_name, image_url FROM products WHERE product_name LIKE ? LIMIT 1",
                                   (f"%{first_word}%",))
                    result = cursor.fetchone()

            if result:
                return {"name": result[0], "url": result[1]}
    except Exception as e:
        print(f"DB Error: {e}")
    return None


def download_image_temp(url: str, filename: str) -> str:
    """
    Smart Downloader:
    - If URL is 'localhost', it copies the file directly from disk (Avoiding Deadlock).
    - If URL is remote (http...), it downloads it.
    """
    temp_path = f"temp_{filename}.jpg"

    # --- DEADLOCK FIX: HANDLE LOCALHOST ---
    if "localhost" in url or "127.0.0.1" in url:
        try:
            # Extract the filename from the URL (e.g., "PMSP021.jpg")
            image_name = os.path.basename(url)
            local_source_path = os.path.join(PRODUCT_IMAGES_DIR, image_name)

            print(f"   -> Detected Local File. Copying from: {local_source_path}")

            if os.path.exists(local_source_path):
                shutil.copy(local_source_path, temp_path)
                return temp_path
            else:
                print(f"   -> Error: Local file not found at {local_source_path}")
                return None
        except Exception as e:
            print(f"   -> Local Copy Error: {e}")
            return None
    # --------------------------------------

    # Normal Download for real URLs
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            return temp_path
    except Exception as e:
        print(f"Download Error: {e}")
    return None


def handle_vto_message(thread_id: str, user_text: str, image_path: Optional[str] = None) -> str:
    """The State Machine for Virtual Try-On."""
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
        return "To start the Virtual Try-On, please upload a clear, full-body photo of yourself."
    if not session["product_image"]:
        return "I have your photo! Now, tell me the name of the product you want to try on."

    if not check_user_limit(thread_id):
        return f"I'm sorry, you have reached your limit of {DAILY_LIMIT} Virtual Try-Ons for today. Please come back tomorrow!"

    return run_replicate_vto(thread_id, session["user_image"], session["product_image"], session["product_name"])


def run_replicate_vto(thread_id: str, user_image_path: str, product_image_url: str, product_name: str) -> str:
    """Sends request to REPLICATE API (Using the Specific Version from your screenshot)."""
    print(f"--- STARTING VTO (Replicate) ---")

    # 1. Get Product Image (Local Copy or Download)
    local_product_path = download_image_temp(product_image_url, "product_img")
    if not local_product_path:
        return "Error: Could not access the product image (File not found)."

    try:
        # 2. Call Replicate API
        # We use the EXACT version hash from your screenshot
        output_url = replicate.run(
            "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
            input={
                "garm_img": open(local_product_path, "rb"),  # The Dress
                "human_img": open(user_image_path, "rb"),  # The User
                "garment_des": product_name,  # Description
                "seed": 42,
                "crop": False
            }
        )

        print(f"VTO Success! Replicate URL: {output_url}")
        increment_user_usage(thread_id)

        # 3. Save Result
        output_filename = f"vto_{uuid.uuid4().hex[:8]}.jpg"
        save_path = os.path.join("uploaded_images", output_filename)

        # Replicate returns a URL string directly
        response = requests.get(str(output_url), stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
        else:
            return "Error: Generated image could not be saved."

        # Clean up temp file
        if os.path.exists(local_product_path):
            os.remove(local_product_path)

        web_path = f"uploaded_images/{output_filename}"

        return f"Here is how the {product_name} looks on you!\n\n<img src=\"http://127.0.0.1:8000/{web_path}\" alt=\"Virtual Try-On Result\" />"

    except Exception as e:
        print(f"Replicate Error: {e}")
        return f"Sorry, I encountered an error generating the image. ({str(e)})"