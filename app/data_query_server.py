import os
import sys
import difflib
import re
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy import text

# Third-party imports
from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal
from app.models import Product, Inventory

# --- 1. Setup ---
load_dotenv()
mcp = FastMCP("data_query")

# 🚨 CONFIG: Base URL for fallbacks (only used if DB has partial paths)
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1/apparel_bot_products/"


# --- 2. Advanced Helper Functions ---

def clean_image_url(raw_url: str) -> str:
    """
    Smartly handles Full URLs vs Filenames.
    """
    if not raw_url or str(raw_url).lower() == "nan":
        return ""

    raw_url = str(raw_url).strip()

    # If it's already a full link, return it
    if raw_url.startswith("http"):
        return raw_url

    # If it's just a filename (e.g., "PWBW01.jpg"), append base
    return f"{CLOUDINARY_BASE_URL}{raw_url}"


def format_image_tag(url_string: str, alt_text: str) -> str:
    """Creates HTML tags for up to 3 images."""
    if not url_string: return ""

    # Handle comma-separated lists
    urls = [clean_image_url(u) for u in url_string.split(',')]

    # Return HTML for first 3 images
    tags = []
    for u in urls[:3]:
        if u:
            tags.append(
                f'<img src="{u}" alt="{alt_text}" style="max-width: 150px; border-radius: 8px; margin: 5px;" />')
    return "".join(tags)


def smart_find_product_name(session, search_term: str) -> Optional[str]:
    """
    Advanced Logic:
    1. Exact Match
    2. SQL Partial Match (ILIKE)
    3. Spelling Correction (Difflib)
    """
    # 1. SQL ILIKE (Fastest)
    sql = text("SELECT product_name FROM products WHERE product_name ILIKE :q LIMIT 1")
    result = session.execute(sql, {"q": f"%{search_term}%"}).fetchone()
    if result:
        return result[0]

    # 2. Spelling Correction (Slower, but smarter)
    # Fetches all names to find "Verone" -> "Verona"
    all_names = [r[0] for r in session.execute(text("SELECT product_name FROM products")).fetchall()]

    matches = difflib.get_close_matches(search_term, all_names, n=1, cutoff=0.6)
    if matches:
        print(f"DEBUG: Autocorrected '{search_term}' -> '{matches[0]}'")
        return matches[0]

    return None


# --- 3. The Tools (PASSIVE ONLY - NO SALES) ---

@mcp.tool()
def list_products():
    """
    Lists ALL available products with prices.
    Use this when the user asks 'What do you have?' or 'Show me everything'.
    """
    session = SessionLocal()
    try:
        # Get all products that have stock
        sql = text("""
                   SELECT DISTINCT p.product_name, p.price, p.image_url
                   FROM products p
                            JOIN inventory i ON p.product_id = i.product_id
                   WHERE i.stock_quantity > 0
                   ORDER BY p.product_name ASC
                   """)
        results = session.execute(sql).fetchall()

        if not results:
            return "No products currently in stock."

        output = []
        for r in results:
            name, price, img_raw = r[0], r[1], r[2]
            img_tag = format_image_tag(img_raw, name)
            output.append(f"• **{name}** - LKR {price}\n  {img_tag}")

        return "\n\n".join(output)
    except Exception as e:
        return f"Error listing products: {str(e)}"
    finally:
        session.close()


@mcp.tool()
def query_product_database(search_query: str):
    """
    Smart Search. Finds products by name, category, or description.
    Handles typos (e.g. 'blue floral' finds 'Blue Floral Bloom').
    Returns: Price, Description, Sizes, Images.
    """
    session = SessionLocal()
    try:
        # 1. Try to Autocorrect the name first
        corrected_name = smart_find_product_name(session, search_query)
        final_query = corrected_name if corrected_name else search_query

        # 2. Search DB with the optimized term
        search_term = f"%{final_query}%"
        sql = text("""
                   SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity
                   FROM products p
                            LEFT JOIN inventory i ON p.product_id = i.product_id
                   WHERE (p.product_name ILIKE :q OR p.description ILIKE :q OR p.category ILIKE :q)
                     AND i.stock_quantity > 0
                   LIMIT 15
                   """)
        results = session.execute(sql, {"q": search_term}).fetchall()

        if not results:
            return f"No products found matching '{search_query}'. Try a simpler keyword."

        # 3. Group Results (Combine sizes for same product)
        products = {}
        for r in results:
            name = r[0]
            if name not in products:
                products[name] = {
                    "price": r[1],
                    "desc": r[2],
                    "image_html": format_image_tag(r[3], name),
                    "sizes": []
                }
            products[name]["sizes"].append(f"{r[4]} ({r[5]} left)")

        # 4. Format Output
        output = []
        if corrected_name and corrected_name.lower() != search_query.lower():
            output.append(f"*(Found matches for '{corrected_name}')*\n")

        for name, details in products.items():
            sizes_str = ", ".join(details["sizes"])
            entry = (
                f"**{name}** - LKR {details['price']}\n"
                f"{details['desc']}\n"
                f"Sizes: {sizes_str}\n"
                f"{details['image_html']}"
            )
            output.append(entry)

        return "\n\n".join(output)

    except Exception as e:
        return f"Database search error: {str(e)}"
    finally:
        session.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")