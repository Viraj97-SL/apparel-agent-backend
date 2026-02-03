import os
import difflib
import re
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Third-party imports
from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal

# --- 1. Setup ---
# Load env vars but suppress any output that might break MCP
load_dotenv(verbose=False)

mcp = FastMCP("data_query")

# 🚨 CONFIG
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1/apparel_bot_products/"


# --- 2. Helper Functions ---

def clean_image_url(raw_url):
    if not raw_url or str(raw_url).lower() == "nan": return ""
    raw_url = str(raw_url).strip()
    return raw_url if raw_url.startswith("http") else f"{CLOUDINARY_BASE_URL}{raw_url}"


def format_image_tag(url_string, alt_text):
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
    """Lists ALL available products."""
    with SessionLocal() as session:
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


@mcp.tool()
def query_product_database(search_query: str):
    """
    Finds products by Name/Category/Description.
    Handles 'Tie-Shoulder' via keyword splitting.
    """
    if not search_query: return "Please provide a search term."

    with SessionLocal() as session:
        try:
            # 1. EXACT/ILIKE SEARCH
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

            # 2. KEYWORD SPLIT (Fixes 'Tie-Shoulder')
            if not results:
                clean_query = re.sub(r'[^\w\s]', ' ', search_query)
                keywords = [w for w in clean_query.split() if len(w) > 2]

                if len(keywords) > 1:
                    conditions = [f"p.product_name ILIKE :w{i}" for i in range(len(keywords))]
                    params = {f"w{i}": f"%{w}%" for i, w in enumerate(keywords)}

                    keyword_sql = text(f"""
                        SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity
                        FROM products p
                        LEFT JOIN inventory i ON p.product_id = i.product_id
                        WHERE ({" AND ".join(conditions)}) AND i.stock_quantity > 0
                    """)
                    results = session.execute(keyword_sql, params).fetchall()

            # 3. FUZZY MATCH
            if not results:
                all_names_res = session.execute(text("SELECT product_name FROM products")).fetchall()
                all_names = [r[0] for r in all_names_res]
                matches = difflib.get_close_matches(search_query, all_names, n=1, cutoff=0.5)
                if matches:
                    return query_product_database(matches[0])  # Retry with fixed name

            if not results:
                return f"No matches found for '{search_query}'."

            # Format Results
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
                qty_text = f"({r[5]} left)" if r[5] is not None else ""
                products[name]["sizes"].append(f"{r[4]} {qty_text}")

            output = []
            for name, details in products.items():
                entry = (
                    f"**{name}** - LKR {details['price']}\n"
                    f"{details['desc']}\n"
                    f"Sizes: {', '.join(details['sizes'])}\n"
                    f"{details['image_html']}"
                )
                output.append(entry)

            return "\n\n".join(output)

        except Exception as e:
            return f"System Error: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")