import os
import sqlite3
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# 1. Load Secrets
load_dotenv()

# 2. Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# 3. Setup Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "apparel.db")
IMAGES_DIR = os.path.join(BASE_DIR, "product_images")


def migrate_images():
    print("--- Starting Cloud Image Migration ---")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all products that still have "localhost" in their URL
    cursor.execute("SELECT product_id, product_name, image_url FROM products WHERE image_url LIKE '%localhost%'")
    products = cursor.fetchall()

    if not products:
        print("No products need migration! (All seem to be cloud links already)")
        return

    print(f"Found {len(products)} products to migrate...")

    updated_count = 0

    for product in products:
        p_id, p_name, local_url = product

        # Extract filename (e.g., "http://localhost:8000/.../PWBW01.jpg" -> "PWBW01.jpg")
        filename = os.path.basename(local_url)
        local_file_path = os.path.join(IMAGES_DIR, filename)

        if not os.path.exists(local_file_path):
            print(f"⚠️ Warning: File not found for {p_name} ({filename}). Skipping.")
            continue

        try:
            print(f"Uploading {filename} to Cloudinary...")

            # Upload to Cloudinary
            # use_filename=True keeps the original name (PWBW01)
            # unique_filename=False prevents it from adding random characters (PWBW01_abc123)
            response = cloudinary.uploader.upload(
                local_file_path,
                use_filename=True,
                unique_filename=False,
                folder="apparel_bot_products"
            )

            cloud_url = response['secure_url']

            # Update Database
            cursor.execute("UPDATE products SET image_url = ? WHERE product_id = ?", (cloud_url, p_id))
            updated_count += 1
            print(f"   ✅ Success! New URL: {cloud_url}")

        except Exception as e:
            print(f"   ❌ Error uploading {filename}: {e}")

    conn.commit()
    conn.close()
    print(f"--- Migration Complete. Updated {updated_count} products. ---")


if __name__ == "__main__":
    migrate_images()