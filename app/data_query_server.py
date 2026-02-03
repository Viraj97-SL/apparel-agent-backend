import os
import difflib
import re
import sys
from time import sleep
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from app.database import SessionLocal

# --- 1. Setup ---
load_dotenv(verbose=False)
mcp = FastMCP("data_query")

# 🚨 CONFIG CLOUDINARY_BASE_URL
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1/apparel_bot_products/"


# --- 2. Helper Functions ---
def clean_image_url(raw_url):
    if not raw_url or str(raw_url).lower() == "nan":
        return ""
    raw_url = str(raw_url).strip()
    return raw_url if raw_url.startswith("http") else f"{CLOUDINARY_BASE_URL}{raw_url}"


def format_image_tag(url_string, alt_text):
    if not url_string:
        return ""
    urls = [clean_image_url(u) for u in url_string.split(',')]
    tags = []
    for u in urls[:3]:
        if u:
            tags.append(
                f'<img src="{u}" alt="{alt_text}" style="max-width: 150px; border-radius: 8px; margin: 5px;" />'
            )
    return "".join(tags)


# --- 3. Retry Decorator ---
def execute_with_retry(func, max_retries=3, initial_delay=1):
    """
    Retry DB operations on pool/timeout errors with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except (OperationalError, TimeoutError) as e:
            if "QueuePool" in str(e) or "timeout" in str(e):
                delay = initial_delay * (2 ** attempt)
                print(f"DB retry {attempt + 1}/{max_retries} after error: {str(e)}. Waiting {delay}s...")
                sleep(delay)
                continue
            raise
    raise Exception(f"Max retries ({max_retries}) exceeded for DB operation.")


# --- 4. THE TOOLS ---
@mcp.tool()
def list_products():
    """Lists ALL available products."""

    def run_query():
        with SessionLocal() as session:
            try:
                # Optimized query to just get names and prices of in-stock items
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
                    output.append(f"• **{name}** - LKR {price}\n {img_tag}")
                return "\n\n".join(output)
            except Exception as e:
                return f"System Error listing products: {str(e)}"

    return execute_with_retry(run_query)


@mcp.tool()
def query_product_database(search_query: str):
    """ Finds products by Name/Category/Description. Handles 'Tie-Shoulder' via keyword splitting. """
    if not search_query:
        return "Please provide a search term."

    # Prevent infinite recursion for fuzzy matches
    search_query = search_query.strip()

    def run_query():
        with SessionLocal() as session:
            try:
                # 1. SEARCH QUERY (Removed stock_quantity > 0 filter here to detect Out of Stock items)
                term = f"%{search_query}%"

                # Base query gets product info regardless of stock
                sql = text("""
                           SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity
                           FROM products p
                                    LEFT JOIN inventory i ON p.product_id = i.product_id
                           WHERE (p.product_name ILIKE :q OR p.description ILIKE :q OR p.category ILIKE :q)
                           LIMIT 30
                           """)
                results = session.execute(sql, {"q": term}).fetchall()

                # 2. KEYWORD SPLIT (Fallback)
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
                            WHERE ({" AND ".join(conditions)})
                        """)
                        results = session.execute(keyword_sql, params).fetchall()

                # 3. FUZZY MATCH (Only if strictly no results found)
                if not results:
                    # Get ALL product names efficiently
                    all_names_res = session.execute(text("SELECT product_name FROM products")).fetchall()
                    all_names = [r[0] for r in all_names_res]

                    matches = difflib.get_close_matches(search_query, all_names, n=1, cutoff=0.5)

                    if matches:
                        match_name = matches[0]
                        # CRITICAL FIX: Prevent infinite recursion loop
                        # Only recurse if the match is significantly different from input
                        if match_name.lower() != search_query.lower():
                            return query_product_database(match_name)
                        else:
                            # If it matches itself but wasn't found in SQL, something is wrong or it's a data sync issue
                            return f"Found '{match_name}' in index but failed to retrieve details. Please check database."

                if not results:
                    return f"No matches found for '{search_query}'."

                # 4. PROCESS RESULTS & CHECK STOCK
                products = {}
                for r in results:
                    name = r[0]
                    stock = r[5] if r[5] is not None else 0

                    if name not in products:
                        products[name] = {
                            "price": r[1],
                            "desc": r[2],
                            "image_html": format_image_tag(r[3], name),
                            "sizes": [],
                            "total_stock": 0
                        }

                    # Only show size if stock > 0
                    if stock > 0:
                        products[name]["sizes"].append(f"{r[4]} ({stock} left)")
                        products[name]["total_stock"] += stock
                    else:
                        products[name]["sizes"].append(f"{r[4]} (Out of Stock)")

                output = []
                for name, details in products.items():
                    # Filter: Only show "Out of Stock" warning if total stock is 0
                    stock_msg = ""
                    if details["total_stock"] == 0:
                        stock_msg = "\n⚠️ **Currently Out of Stock**"

                    # Consolidate sizes
                    size_str = ", ".join(details['sizes']) if details['sizes'] else "No stock info"

                    entry = (
                        f"**{name}** - LKR {details['price']}{stock_msg}\n"
                        f"{details['desc']}\n"
                        f"Sizes: {size_str}\n"
                        f"{details['image_html']}"
                    )
                    output.append(entry)

                return "\n\n".join(output)

            except Exception as e:
                return f"System Error: {str(e)}"

    return execute_with_retry(run_query)


if __name__ == "__main__":
    mcp.run(transport="stdio")