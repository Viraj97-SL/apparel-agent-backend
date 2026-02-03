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

load_dotenv(verbose=False)
mcp = FastMCP("data_query")

CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1/apparel_bot_products/"


def clean_image_url(raw_url):
    if not raw_url or str(raw_url).lower() == "nan": return ""
    raw_url = str(raw_url).strip()
    return raw_url if raw_url.startswith("http") else f"{CLOUDINARY_BASE_URL}{raw_url}"


def format_image_tag(url_string, alt_text):
    if not url_string: return ""
    urls = [clean_image_url(u) for u in url_string.split(',')]
    tags = []
    # Limit to 3 images max
    for u in urls[:3]:
        if u: tags.append(
            f'<img src="{u}" alt="{alt_text}" style="max-width: 150px; border-radius: 8px; margin: 5px;" />')
    return "".join(tags)


def execute_with_retry(func, max_retries=3, initial_delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except (OperationalError, TimeoutError) as e:
            if "QueuePool" in str(e) or "timeout" in str(e):
                delay = initial_delay * (2 ** attempt)
                print(f"DB retry {attempt + 1}/{max_retries}. Waiting {delay}s...")
                sleep(delay)
                continue
            raise
    raise Exception(f"Max retries exceeded.")


# --- NEW TOOL: Categories ---
@mcp.tool()
def get_available_categories():
    """Returns a list of product categories (e.g. Dresses, Skirts) with counts."""

    def run_query():
        with SessionLocal() as session:
            try:
                # Count in-stock products per category
                sql = text("""
                           SELECT category, COUNT(DISTINCT p.product_id) as count
                           FROM products p
                                    JOIN inventory i ON p.product_id = i.product_id
                           WHERE i.stock_quantity > 0
                           GROUP BY category
                           ORDER BY count DESC
                           """)
                results = session.execute(sql).fetchall()
                if not results: return "No categories found."

                output = ["**Available Collections:**"]
                for r in results:
                    cat = r[0] if r[0] else "Uncategorized"
                    count = r[1]
                    output.append(f"- {cat} ({count} items)")

                return "\n".join(output)
            except Exception as e:
                return f"Error fetching categories: {e}"

    return execute_with_retry(run_query)


# --- UPDATED TOOL: List Products with Filter ---
@mcp.tool()
def list_products(category_filter: str = None):
    """
    Lists products.
    Args:
        category_filter: Optional. Use strict category names like 'Dresses', 'Skirts', 'Sets & Co-ords', 'Tops & Blouses'.
    """

    def run_query():
        with SessionLocal() as session:
            try:
                # Base Query
                query_str = """
                            SELECT DISTINCT p.product_name, p.price, p.image_url
                            FROM products p
                                     JOIN inventory i ON p.product_id = i.product_id
                            WHERE i.stock_quantity > 0 \
                            """
                params = {}

                # Apply Category Filter
                if category_filter and category_filter.lower() != "all":
                    query_str += " AND p.category ILIKE :cat"
                    params["cat"] = f"%{category_filter}%"

                query_str += " ORDER BY p.product_name ASC LIMIT 20"

                results = session.execute(text(query_str), params).fetchall()

                if not results:
                    return f"No products found in category '{category_filter}'."

                output = []
                if category_filter:
                    output.append(f"**Showing results for: {category_filter}**\n")

                for r in results:
                    name, price, img_raw = r[0], r[1], r[2]
                    first_img = clean_image_url(str(img_raw).split(',')[0]) if img_raw else ""
                    img_tag = f'<img src="{first_img}" alt="{name}" style="max-width: 100px; border-radius: 5px;" />' if first_img else ""
                    output.append(f"• **{name}** - LKR {price}\n {img_tag}")

                return "\n\n".join(output)
            except Exception as e:
                return f"System Error listing products: {str(e)}"

    return execute_with_retry(run_query)


@mcp.tool()
def query_product_database(search_query: str):
    """ Finds products by Name/Category/Description. Handles 'Tie-Shoulder' via keyword splitting. """
    if not search_query: return "Please provide a search term."
    search_query = search_query.strip()

    def run_query():
        with SessionLocal() as session:
            try:
                # 1. SEARCH
                term = f"%{search_query}%"
                sql = text("""
                           SELECT p.product_name,
                                  p.price,
                                  p.description,
                                  p.image_url,
                                  i.size,
                                  i.stock_quantity,
                                  p.category
                           FROM products p
                                    LEFT JOIN inventory i ON p.product_id = i.product_id
                           WHERE (p.product_name ILIKE :q OR p.description ILIKE :q OR p.category ILIKE :q)
                           LIMIT 100
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
                            SELECT p.product_name, p.price, p.description, p.image_url, i.size, i.stock_quantity, p.category
                            FROM products p
                            LEFT JOIN inventory i ON p.product_id = i.product_id
                            WHERE ({" AND ".join(conditions)})
                            LIMIT 100
                        """)
                        results = session.execute(keyword_sql, params).fetchall()

                # 3. FUZZY MATCH (Fallback)
                if not results:
                    all_names_res = session.execute(text("SELECT product_name FROM products")).fetchall()
                    all_names = [r[0] for r in all_names_res]
                    matches = difflib.get_close_matches(search_query, all_names, n=1, cutoff=0.5)
                    if matches:
                        match_name = matches[0]
                        if match_name.lower() != search_query.lower():
                            return query_product_database(match_name)

                if not results:
                    return f"No matches found for '{search_query}'."

                # 4. PROCESS RESULTS
                products = {}
                for r in results:
                    name = r[0]
                    stock = r[5] if r[5] is not None else 0
                    if name not in products:
                        if len(products) >= 5: continue
                        products[name] = {
                            "price": r[1],
                            "desc": r[2],
                            "image_html": format_image_tag(r[3], name),
                            "cat": r[6],
                            "sizes": [],
                            "total_stock": 0
                        }

                    if name in products:
                        if stock > 0:
                            products[name]["sizes"].append(f"{r[4]} ({stock} left)")
                            products[name]["total_stock"] += stock
                        else:
                            products[name]["sizes"].append(f"{r[4]} (Out of Stock)")

                output = []
                for name, details in products.items():
                    stock_msg = "\n⚠️ **Currently Out of Stock**" if details["total_stock"] == 0 else ""
                    size_str = ", ".join(details['sizes']) if details['sizes'] else "No stock info"
                    entry = (
                        f"**{name}** ({details['cat']}) - LKR {details['price']}{stock_msg}\n"
                        f"{details['desc']}\n"
                        f"Sizes: {size_str}\n"
                        f"{details['image_html']}"
                    )
                    output.append(entry)

                if len(results) >= 100:
                    output.append("*(Results limited to top 5 matches.)*")

                return "\n\n".join(output)

            except Exception as e:
                return f"System Error: {str(e)}"

    return execute_with_retry(run_query)


if __name__ == "__main__":
    mcp.run(transport="stdio")