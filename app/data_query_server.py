import os
import sys
import json
import uuid
import datetime
from typing import List, Optional

# Third-party imports
from dotenv import load_dotenv
from sqlalchemy import text, or_
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from mcp.server.fastmcp import FastMCP

# --- NEW IMPORTS (Postgres/ORM) ---
from app.database import engine, SessionLocal
from app.models import Product, Inventory, Order, Customer, Return, RestockNotification


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


if __name__ == "__main__":
    mcp.run(transport="stdio")