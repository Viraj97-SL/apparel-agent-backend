import os
import difflib
import re
from sqlalchemy import text, or_
from dotenv import load_dotenv

# Third-party imports
from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal
from app.models import Product, Inventory

# --- 1. Setup ---
load_dotenv()
mcp = FastMCP("data_query")

# 🚨 CONFIG: Base URL for images
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1/apparel_bot_products/"


# --- 2. Robust Helper Functions ---

def clean_image_url(raw_url):
    """Ensures image links are valid URLs."""
    if not raw_url or str(raw_url).lower() == "nan":
        return ""
    raw_url = str(raw_url).strip()
    if raw_url.startswith("http"):
        return raw_url
    return f"{CLOUDINARY_BASE_URL}{raw_url}"


def format_image_tag(url_string, alt_text):
    """Creates HTML tags for up to 3 images."""
    if not url_string: return ""
    urls = [clean_image_url(u) for u in url_string.split(',')]
    tags = []
    for u in urls[:3]:
        if u:
            tags.append(
                f'<img src="{u}" alt="{alt_text}" style="max-width: 150px; border-radius: 8px; margin: 5px;" />')
    return "".join(tags)


# --- 3. THE TOOLS ---

@mcp.tool()
def list_products():
    """
    Lists ALL available products with prices.
    Robust: Never crashes, even if DB is empty.
    """
    session = SessionLocal()
    try:
        sql = text("""
                   SELECT DISTINCT p.product_name, p.price, p.image_url
                   FROM products p
                            JOIN inventory i ON p.product_id = i.product_id
                   WHERE i.stock_quantity > 0
                   ORDER BY p.product_name ASC
                   """)
        results = session.execute(sql).fetchall()

        if not results:
            return "Inventory Check: No products currently in stock."

        output = []
        for r in results:
            name, price, img_raw = r[0], r[1], r[2]
            img_tag = format_image_tag(img_raw, name)
            output.append(f"• **{name}** - LKR {price}\n  {img_tag}")

        return "\n\n".join(output)
    except Exception as e:
        return f"System Error listing products: {str(e)}"
    finally:
        session.close()


@mcp.tool()
def query_product_database(search_query: str):
    """
    AGGRESSIVE SEARCH. Finds products by Name, Category, or Description.
    1. Exact Match
    2. Split-Keyword Match (Finds 'Tie-Shoulder' via 'Tie' + 'Shoulder')
    3. Fuzzy Typo Match
    """
    session = SessionLocal()
    try:
        if not search_query: return "Please provide a search term."

        # --- STRATEGY 1: Simple Database ILIKE (Matches "Blue Floral" -> "Blue Floral Bloom") ---
        term = f"%{search_query}%"
        sql = text("""
                   SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity
                   FROM products p
                            LEFT JOIN inventory i ON p.product_id = i.product_id
                   WHERE (p.product_name ILIKE :q OR p.description ILIKE :q OR p.category ILIKE :q)
                     AND i.stock_quantity > 0
                   LIMIT 20
                   """)
        results = session.execute(sql, {"q": term}).fetchall()

        # --- STRATEGY 2: Split-Keyword Search (Fixes "Tie-Shoulder" issues) ---
        # If "Tie-Shoulder Camisole" fails, we search for items containing "Tie" AND "Camisole"
        if not results:
            # Clean: Replace dashes with spaces, remove special chars
            clean_query = re.sub(r'[^\w\s]', ' ', search_query)
            keywords = [w for w in clean_query.split() if len(w) > 2]  # Ignore short words like "in", "at"

            if len(keywords) > 1:
                # Construct dynamic SQL: name ILIKE '%word1%' AND name ILIKE '%word2%'
                conditions = []
                params = {}
                for idx, word in enumerate(keywords):
                    key = f"w{idx}"
                    conditions.append(f"p.product_name ILIKE :{key}")
                    params[key] = f"%{word}%"

                where_clause = " AND ".join(conditions)
                keyword_sql = text(f"""
                    SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity
                    FROM products p
                    LEFT JOIN inventory i ON p.product_id = i.product_id
                    WHERE ({where_clause}) AND i.stock_quantity > 0
                """)
                results = session.execute(keyword_sql, params).fetchall()

        # --- STRATEGY 3: Fuzzy / Spell Check (Fixes "Camisol" -> "Camisole") ---
        if not results:
            # Get ALL product names to compare against
            all_names_res = session.execute(text("SELECT product_name FROM products")).fetchall()
            all_names = [r[0] for r in all_names_res]

            # Find closest match (0.5 cutoff allows for rough typos)
            matches = difflib.get_close_matches(search_query, all_names, n=1, cutoff=0.5)

            if matches:
                best_guess = matches[0]
                return query_product_database(best_guess)  # RECURSIVE CALL with fixed name

        # --- Final Result Processing ---
        if not results:
            return f"I searched everywhere but couldn't find a match for '{search_query}'. Try checking the full product list."

        # Group Results (Combine sizes)
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
            # Only show size if it has stock or is unknown
            qty_text = f"({r[5]} left)" if r[5] is not None else ""
            products[name]["sizes"].append(f"{r[4]} {qty_text}")

        output = []
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
        # CRITICAL: Return error as string, do not crash the server
        return f"System Error during search: {str(e)}"
    finally:
        session.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")