import os
import sys
import json
import uuid
import re
import difflib  # <--- NEW: For spelling correction
from typing import List, Optional, Dict, Any, Union

# Third-party imports
from dotenv import load_dotenv
from sqlalchemy import text, or_
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from mcp.server.fastmcp import FastMCP

# --- NEW IMPORTS (Postgres/ORM) ---
from app.database import engine, SessionLocal
from app.models import Product, Inventory, Order, Customer, OrderItem, Return, RestockNotification


# --- Helper for Safe Logging ---
def log_warning(msg: str):
    sys.stderr.write(f"[WARNING] {msg}\n")
    sys.stderr.flush()


# --- 1. Cloud-Aware Environment Setup ---
load_dotenv()

google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    log_warning("GOOGLE_API_KEY not found in env.")

# --- 2. Initialize LLM ---
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-8b",
    google_api_key=google_api_key,
    temperature=0
)

# --- 3. Initialize MCP Server ---
mcp = FastMCP("data_query")

# 🚨 CONFIG: Cloudinary Path 🚨
CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/"


# --- 4. HUMAN-PROOFING HELPER FUNCTIONS ---

def text_to_int(text_val: Union[str, int]) -> int:
    """Converts 'one', 'two', '10' to integer 1, 2, 10."""
    if isinstance(text_val, int):
        return text_val

    text_val = str(text_val).lower().strip()
    if text_val.isdigit():
        return int(text_val)

    mapping = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "a pair": 2, "a couple": 2, "single": 1
    }
    return mapping.get(text_val, 1)  # Default to 1 if unknown


def clean_phone(phone: str) -> str:
    """Removes spaces, dashes, brackets from phone numbers."""
    # Keep only digits and the plus sign
    return re.sub(r'[^\d+]', '', str(phone))


def smart_find_product(session, search_term: str) -> Optional[Product]:
    """
    Tries to find a product using:
    1. Exact match (case-insensitive)
    2. Partial match (SQL ILIKE)
    3. Fuzzy match (Spelling correction)
    """
    # 1. Try SQL ILIKE (Partial match)
    # This covers "Verona" -> "Verona Vine"
    exact_or_partial = session.query(Product).filter(
        Product.product_name.ilike(f"%{search_term}%")
    ).first()

    if exact_or_partial:
        return exact_or_partial

    # 2. Fuzzy Match (Spelling errors)
    # If "Verone" or "Cimson", SQL fails. We need Python to fix it.
    all_products = session.query(Product.product_name).all()
    all_names = [p[0] for p in all_products]

    # Get closest match (0.6 cutoff means 60% similarity required)
    matches = difflib.get_close_matches(search_term, all_names, n=1, cutoff=0.6)

    if matches:
        best_guess = matches[0]
        print(f"   -> Fuzzy Match: corrected '{search_term}' to '{best_guess}'")
        return session.query(Product).filter(Product.product_name == best_guess).first()

    return None


# --- 5. TOOLS ---

@mcp.tool()
async def list_products(limit: int = 5) -> str:
    """Lists available products for users to browse."""
    session = SessionLocal()
    try:
        products = session.query(Product).limit(limit).all()
        if not products:
            return "We currently have no products listed."

        output = []
        for p in products:
            img_tag = ""
            if p.image_url:
                raw_url = str(p.image_url)
                if "localhost" in raw_url:
                    filename = raw_url.split("/")[-1]
                    full_url = f"{CLOUDINARY_BASE_URL}{filename}"
                elif raw_url.startswith("http"):
                    full_url = raw_url
                else:
                    full_url = f"{CLOUDINARY_BASE_URL}{raw_url}"
                img_tag = f'<img src="{full_url}" alt="{p.product_name}" style="max-width: 150px; border-radius: 8px;" />'

            output.append(f"• **{p.product_name}** - LKR {p.price}\n  {p.description}\n  {img_tag}")

        return "\n\n".join(output) + "\n\n(Ask for more details on any item!)"
    except Exception as e:
        return f"Error listing products: {str(e)}"
    finally:
        session.close()


@mcp.tool()
async def create_draft_order(
        customer_email: str,
        customer_name: str,
        shipping_address: str,
        phone_number: str,
        items: str
) -> str:
    """
    Creates a new order.
    'items' must be a JSON string: '[{"product_name": "...", "size": "...", "quantity": 1}]'
    """
    session = SessionLocal()
    try:
        # --- ROBUST PARSING ---
        item_list = []
        if isinstance(items, str):
            try:
                cleaned_items = items.strip()
                if cleaned_items.startswith("```"):
                    lines = cleaned_items.splitlines()
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines[-1].startswith("```"): lines = lines[:-1]
                    cleaned_items = "\n".join(lines)
                item_list = json.loads(cleaned_items)
            except:
                return f"Error: Could not parse items JSON. Received: {items}"
        elif isinstance(items, list):
            item_list = items

        # --- PHONE CLEANING ---
        clean_phone_number = clean_phone(phone_number)

        # 2. Find/Create Customer
        customer = session.query(Customer).filter(Customer.email == customer_email).first()
        if not customer:
            customer = Customer(
                email=customer_email,
                full_name=customer_name,
                phone_number=clean_phone_number,
                shipping_address=shipping_address
            )
            session.add(customer)
            session.flush()
        else:
            customer.full_name = customer_name
            customer.shipping_address = shipping_address
            customer.phone_number = clean_phone_number

        # 3. Process Items
        total_amount = 0.0
        order_items_objects = []

        if not item_list: return "Error: No items found."

        for item in item_list:
            p_name_input = item.get("product_name") or item.get("product")
            size_input = item.get("size")
            qty_input = item.get("quantity", 1)

            # A. SMART QUANTITY ("one" -> 1)
            qty = text_to_int(qty_input)

            if not p_name_input or not size_input:
                return f"Error: Missing product name or size in {item}"

            # B. SMART PRODUCT SEARCH (Fuzzy Match)
            product = smart_find_product(session, p_name_input)
            if not product:
                return f"Error: We couldn't find a product matching '{p_name_input}'. Please check the name."

            # C. SMART SIZE SEARCH (Case Insensitive)
            # We iterate through inventory to find the closest size match (e.g. 'm' -> 'M')
            inventory = session.query(Inventory).filter(
                Inventory.product_id == product.product_id,
                Inventory.size.ilike(size_input)  # ILIKE handles 'm' vs 'M'
            ).first()

            if not inventory:
                return f"Error: Size '{size_input}' is not available for {product.product_name}."

            if inventory.stock_quantity < qty:
                return f"Error: Only {inventory.stock_quantity} left of {product.product_name} (Size {size_input})."

            # Deduct Stock
            inventory.stock_quantity -= qty

            line_total = product.price * qty
            total_amount += line_total

            order_item = OrderItem(
                product_name=product.product_name,
                size=inventory.size,  # Use the official DB size (e.g. "M") not user input ("m")
                quantity=qty,
                price_at_purchase=product.price
            )
            order_items_objects.append(order_item)

        # 4. Create Order
        new_order = Order(
            customer_id=customer.customer_id,
            status="pending_payment",
            total_amount=total_amount
        )
        session.add(new_order)
        session.flush()

        for obj in order_items_objects:
            obj.order_id = new_order.order_id
            session.add(obj)

        session.commit()
        return json.dumps({
            "status": "success",
            "order_id": new_order.order_id,
            "total": total_amount,
            "message": "Draft order created. Proceed to payment."
        })

    except Exception as e:
        session.rollback()
        return f"Error creating order: {str(e)}"
    finally:
        session.close()


@mcp.tool()
async def generate_payment_link(order_id: str) -> str:
    """Generates a mock payment link."""
    mock_link = f"[https://checkout.stripe.com/pay/](https://checkout.stripe.com/pay/){order_id}?currency=lkr"
    return json.dumps({
        "payment_url": mock_link,
        "note": "This is a simulation link. In production, connect Stripe here."
    })


# --- KEEP EXISTING QUERY TOOLS ---
# (Keeping these compact as they haven't changed)

@mcp.tool()
def sql_db_query(query: str) -> str:
    try:
        db = SQLDatabase(engine, include_tables=['orders', 'customers', 'returns'])
        sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        query_tool = next(t for t in sql_toolkit.get_tools() if t.name == 'sql_db_query')
        return query_tool.invoke({"query": query})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def sql_db_schema(table_names: Optional[str] = None) -> str:
    try:
        db = SQLDatabase(engine, include_tables=['orders', 'customers', 'returns'])
        sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        schema_tool = next(t for t in sql_toolkit.get_tools() if t.name == 'sql_db_schema')
        return schema_tool.invoke({"table_names": table_names or ""})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def query_product_database(product_name: str = None, category: str = None, colour: str = None,
                                 size: str = None) -> str:
    # 🚨 CONFIG: Cloudinary Path 🚨
    CLOUDINARY_BASE_URL = "[https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/](https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/)"

    # Clean inputs
    if product_name == "None": product_name = None
    if category == "None": category = None
    if colour == "None": colour = None
    if size == "None": size = None

    session = SessionLocal()
    try:
        # Start building the query
        query = session.query(Product, Inventory.size, Inventory.stock_quantity) \
            .outerjoin(Inventory, Product.product_id == Inventory.product_id)

        # Apply filters
        if product_name:
            query = query.filter(Product.product_name.ilike(f"%{product_name}%"))
        if category:
            query = query.filter(Product.category.ilike(f"%{category}%"))
        if colour:
            query = query.filter(Product.colour.ilike(f"%{colour}%"))
        if size:
            query = query.filter(Inventory.size.ilike(f"%{size}%"))

        results = query.limit(5).all()

        if not results:
            return "No exact match found. Try searching with fewer details."

        formatted_results = []
        for prod, inv_size, inv_qty in results:
            try:
                # 1. Handle Stock Logic safely
                if inv_qty is not None:
                    stock_status = f"Out of Stock (size {inv_size})" if inv_qty <= 0 else f"In Stock (size {inv_size}, {inv_qty} left)"
                else:
                    stock_status = "Stock unknown"

                # 2. Handle Image Logic
                image_tag = ""
                if prod.image_url:
                    raw_url = str(prod.image_url)
                    if "localhost" in raw_url:
                        filename = raw_url.split("/")[-1]
                        full_url = f"{CLOUDINARY_BASE_URL}{filename}"
                    elif raw_url.startswith("http"):
                        full_url = raw_url
                    else:
                        full_url = f"{CLOUDINARY_BASE_URL}{raw_url}"
                    image_tag = f'<img src="{full_url}" alt="{prod.product_name}" style="max-width: 200px; border-radius: 8px;" />'

                formatted_results.append(
                    f"Product: {prod.product_name}\nPrice: {prod.price}\nColour: {prod.colour}\nSize: {inv_size}\nDescription: {prod.description}\nStatus: {stock_status}\n{image_tag}"
                )
            except Exception:
                continue

        return "\n\n---PRODUCT---\n\n".join(formatted_results)

    except Exception as e:
        return f"Error querying product database: {str(e)}"
    finally:
        session.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")