import os
import sys
import json
import uuid
import datetime
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
from app.models import Product, Inventory, Order, Customer, Return, RestockNotification, OrderItem


# --- Helper for Safe Logging ---
def log_warning(msg: str):
    """Writes to stderr so it doesn't break the MCP protocol."""
    sys.stderr.write(f"[WARNING] {msg}\n")
    sys.stderr.flush()


# --- 1. Cloud-Aware Environment Setup ---
load_dotenv()

google_api_key = os.getenv("GOOGLE_API_KEY")

if not google_api_key:
    log_warning("GOOGLE_API_KEY not found in env.")

# --- 2. Initialize LLM (Gemini Flash) ---
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-8b",
    google_api_key=google_api_key,
    temperature=0
)

# --- 3. Initialize MCP Server ---
mcp = FastMCP("data_query")


# --- 4. Tools ---

@mcp.tool()
def sql_db_query(query: str) -> str:
    """Execute a SQL query on 'orders', 'customers', or 'returns'."""
    try:
        # LAZY INITIALIZATION: Only connect when the tool is CALLED
        db = SQLDatabase(engine, include_tables=['orders', 'customers', 'returns'])

        sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        # Find the specific tool from the toolkit
        query_tool = next(t for t in sql_toolkit.get_tools() if t.name == 'sql_db_query')
        return query_tool.invoke({"query": query})
    except Exception as e:
        return f"Error executing SQL query: {str(e)}"


@mcp.tool()
def sql_db_schema(table_names: Optional[str] = None) -> str:
    """Get schema of 'orders', 'customers', or 'returns'."""
    try:
        # LAZY INITIALIZATION: Only connect when the tool is CALLED
        db = SQLDatabase(engine, include_tables=['orders', 'customers', 'returns'])

        sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        schema_tool = next(t for t in sql_toolkit.get_tools() if t.name == 'sql_db_schema')
        return schema_tool.invoke({"table_names": table_names or ""})
    except Exception as e:
        return f"Error getting schema: {str(e)}"


@mcp.tool()
async def initiate_return(order_id: str, product_ids: List[str]) -> str:
    """Initiate a return record."""
    session = SessionLocal()
    try:
        # Check if order exists first
        order = session.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return f"Error: Order ID {order_id} not found."

        return_id = f"RET-{uuid.uuid4().hex[:6].upper()}"

        # Create new Return record
        new_return = Return(
            return_id=return_id,
            order_id=order_id,
            product_ids=json.dumps(product_ids),
            status="Pending",
            # return_date is set automatically by server_default
        )

        session.add(new_return)
        session.commit()
        return json.dumps({"status": "Return Initiated", "return_id": return_id})
    except Exception as e:
        session.rollback()
        return f"Error initiating return: {str(e)}"
    finally:
        session.close()


@mcp.tool()
async def query_product_database(
        product_name: Optional[str] = None,
        category: Optional[str] = None,
        colour: Optional[str] = None,
        size: Optional[str] = None
) -> str:
    """
    Search for products in the database.

    CRITICAL INSTRUCTION FOR AGENT:
    - Do NOT call this tool multiple times in parallel. Call it ONCE with the best specific details you have.
    - You CAN combine filters (e.g., product_name="Verona" AND colour="Blue").
    """
    # 🚨 CONFIG: Cloudinary Path 🚨
    CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/"

    # Clean inputs
    if product_name == "None": product_name = None
    if category == "None": category = None
    if colour == "None": colour = None
    if size == "None": size = None

    session = SessionLocal()
    try:
        # Start building the query
        # We join Product and Inventory to filter by size
        query = session.query(Product, Inventory.size, Inventory.stock_quantity) \
            .outerjoin(Inventory, Product.product_id == Inventory.product_id)

        # Apply filters dynamically
        if product_name:
            query = query.filter(Product.product_name.ilike(f"%{product_name}%"))
        if category:
            query = query.filter(Product.category.ilike(f"%{category}%"))
        if colour:
            query = query.filter(Product.colour.ilike(f"%{colour}%"))
        if size:
            query = query.filter(Inventory.size.ilike(f"%{size}%"))

        # Limit results
        results = query.limit(5).all()

        if not results:
            return "No exact match found. Try searching with fewer details (e.g., just the name or just the category)."

        formatted_results = []
        for prod, inv_size, inv_qty in results:
            # Handle stock status logic
            if inv_qty is not None:
                stock_status = f"Out of Stock (size {inv_size})" if inv_qty <= 0 else f"In Stock (size {inv_size}, {inv_qty} left)"
            else:
                stock_status = "Stock unknown"

            # Image URL logic
            image_tag = ""
            if prod.image_url:
                # Handle full URLs vs filenames
                if prod.image_url.startswith("http"):
                    full_url = prod.image_url
                else:
                    filename = prod.image_url.split("/")[-1]
                    full_url = f"{CLOUDINARY_BASE_URL}{filename}"

                image_tag = f'<img src="{full_url}" alt="{prod.product_name}" />'

            formatted_results.append(
                f"Product: {prod.product_name}\nPrice: {prod.price}\nColour: {prod.colour}\nSize: {inv_size}\nDescription: {prod.description}\nStatus: {stock_status}\n{image_tag}"
            )

        return "\n\n---PRODUCT---\n\n".join(formatted_results)

    except Exception as e:
        return f"Error querying product database: {str(e)}"
    finally:
        session.close()


@mcp.tool()
async def add_restock_notification(product_name: str, customer_email: str, size: str,
                                   colour: Optional[str] = None) -> str:
    """Add a customer to the waitlist."""
    session = SessionLocal()
    try:
        # Find product ID first
        product = session.query(Product).filter(Product.product_name.ilike(f"%{product_name}%")).first()

        if not product:
            return f"Error: Product '{product_name}' not found."

        new_notification = RestockNotification(
            customer_email=customer_email,
            product_id=product.product_id,
            size=size,
            status="Pending"
        )

        session.add(new_notification)
        session.commit()
        return json.dumps({"status": "Success", "message": f"Added {customer_email} to waitlist for {product_name}."})
    except Exception as e:
        session.rollback()
        return f"Error adding notification: {str(e)}"
    finally:
        session.close()


# --- NEW TOOLS FOR SALES & DISCOVERY ---

@mcp.tool()
async def list_products(limit: int = 5) -> str:
    """
    Lists available products for users to browse.
    Use this when the user asks "What do you sell?" or "Show me your products".
    """
    # 🚨 CONFIG: Cloudinary Path 🚨
    CLOUDINARY_BASE_URL = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/"

    session = SessionLocal()
    try:
        products = session.query(Product).limit(limit).all()
        if not products:
            return "We currently have no products listed."

        output = []
        for p in products:
            # Format Image
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


# ... (keep other imports) ...

@mcp.tool()
async def create_draft_order(
        customer_email: str,
        customer_name: str,
        shipping_address: str,
        phone_number: str,
        items: Union[str, List[Dict[str, Any]]]  # <--- Accept BOTH types
) -> str:
    """
    Creates a new order in the database.
    'items' can be a JSON string OR a list of objects.
    Example: [{"product_name": "Verona", "size": "M", "quantity": 1}]
    """
    session = SessionLocal()
    try:
        # --- ROBUST INPUT HANDLING ---
        # 1. Check what the AI sent us
        item_list = []

        if isinstance(items, str):
            # If it's a string, try to parse it as JSON
            try:
                # Clean up potential markdown formatting like ```json ... ```
                cleaned_items = items.strip()
                if cleaned_items.startswith("```"):
                    cleaned_items = cleaned_items.split("```")[1]
                    if cleaned_items.startswith("json"):
                        cleaned_items = cleaned_items[4:]

                item_list = json.loads(cleaned_items)
            except json.JSONDecodeError:
                return "Error: 'items' was a string but could not be parsed as valid JSON."

        elif isinstance(items, list):
            # If it's already a list, use it directly
            item_list = items

        else:
            return f"Error: 'items' received unexpected type: {type(items)}. Expected JSON string or List."

        # 2. Find/Create Customer
        customer = session.query(Customer).filter(Customer.email == customer_email).first()
        if not customer:
            customer = Customer(
                email=customer_email,
                full_name=customer_name,
                phone_number=phone_number,
                shipping_address=shipping_address
            )
            session.add(customer)
            session.flush()
        else:
            # Update info
            customer.full_name = customer_name
            customer.shipping_address = shipping_address
            customer.phone_number = phone_number

        # 3. Process Items & Calc Total
        total_amount = 0.0
        order_items_objects = []

        if not item_list:
            return "Error: No items provided in the order."

        for item in item_list:
            # Flexible dictionary access
            p_name = item.get("product_name") or item.get("product")
            size = item.get("size")

            # Handle quantity safely (convert string "1" to int 1)
            try:
                qty = int(item.get("quantity", 1))
            except:
                qty = 1

            if not p_name or not size:
                return f"Error: Item is missing product_name or size. Data: {item}"

            # Find Product
            product = session.query(Product).filter(Product.product_name.ilike(f"%{p_name}%")).first()
            if not product:
                return f"Error: Product '{p_name}' not found."

            # Check Stock
            inventory = session.query(Inventory).filter(
                Inventory.product_id == product.product_id,
                Inventory.size.ilike(size)
            ).first()

            if not inventory or inventory.stock_quantity < qty:
                return f"Error: Insufficient stock for '{p_name}' (Size {size})."

            # Deduct Stock
            inventory.stock_quantity -= qty

            # Add to total
            line_total = product.price * qty
            total_amount += line_total

            order_item = OrderItem(
                product_name=product.product_name,
                size=size,
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
    """
    Generates a payment link for the given order ID.
    """
    # In a real app, this would call Stripe API.
    # For now, we return a Mock Link that looks real.

    mock_link = f"https://checkout.stripe.com/pay/{order_id}?currency=lkr"

    return json.dumps({
        "payment_url": mock_link,
        "note": "This is a simulation link. In production, connect Stripe here."
    })

if __name__ == "__main__":
    mcp.run(transport="stdio")