# check_db.py
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "apparel.db")

print(f"--- Checking database at: {DB_PATH} ---")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n--- Checking 'products' table for Image URLs ---")

    # Select only the product name and its image URL
    cursor.execute("SELECT product_name, image_url FROM products")

    products = cursor.fetchall()

    if not products:
        print("!!! ERROR: The 'products' table is EMPTY. !!!")
        print("The db_builder.py script did not load the CSV data.")
    else:
        print(f"SUCCESS: Found {len(products)} products. Displaying (Name, Image_URL):")
        print("--------------------------------------------------")
        for product in products:
            print(f"- Name: {product[0]}")
            print(f"  URL: {product[1]}")  # product[1] is the image_url
            print("---")

    conn.close()

except Exception as e:
    print(f"\nAn error occurred while checking the database: {e}")

print("\n--- Check complete. ---")