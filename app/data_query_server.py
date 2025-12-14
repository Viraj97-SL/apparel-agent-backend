import os
import json
import uuid
import datetime
import sqlite3
from dotenv import load_dotenv
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from sqlalchemy import create_engine, text
from mcp.server.fastmcp import FastMCP
from langchain_groq import ChatGroq

# Load environment variables
import os
from dotenv import load_dotenv

# Try to load .env (It's okay if it fails on Railway)
load_dotenv()

# Get the key from the System Environment (Railway Variables)
google_api_key = os.getenv("GOOGLE_API_KEY")

# Only crash if the key is missing from EVERYWHERE
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY is missing from environment variables.")

# --- Database Setup ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
DB_PATH = os.path.join(project_root, "apparel.db")
DB_URI = f"sqlite:///{DB_PATH}"

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"Database file not found at {DB_PATH}.")

# READ-ONLY toolkit
db = SQLDatabase.from_uri(DB_URI, include_tables=['orders', 'customers', 'returns'])

# WRITE engine
write_engine = create_engine(DB_URI)

# Initialize LLM
#llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GOOGLE_API_KEY)
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=os.getenv("GROQ_API_KEY")
)

# MCP Server
mcp = FastMCP("data_query")


# Tool 1: SQL db query
@mcp.tool()
def sql_db_query(query: str) -> str:
    """Execute a SQL query on 'orders', 'customers', or 'returns'. Do NOT use for products."""
    sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    query_tool = [t for t in sql_toolkit.get_tools() if t.name == 'sql_db_query'][0]
    return query_tool.invoke({"query": query})


# Tool 2: SQL db schema
@mcp.tool()
def sql_db_schema(table_names: Optional[str] = None) -> str:
    """Get schema of 'orders', 'customers', or 'returns'."""
    sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    schema_tool = [t for t in sql_toolkit.get_tools() if t.name == 'sql_db_schema'][0]
    return schema_tool.invoke({"table_names": table_names or ""})


# Tool 3: Initiate Return
@mcp.tool()
async def initiate_return(order_id: str, product_ids: List[str]) -> str:
    """Initiate a return record."""
    try:
        return_id = f"RET-{uuid.uuid4().hex[:6].upper()}"
        return_date = datetime.date.today().isoformat()
        products_json = json.dumps(product_ids)
        with write_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO returns (return_id, order_id, product_ids, status, return_date) VALUES (:rid, :oid, :pids, :stat, :rdate)"),
                {"rid": return_id, "oid": order_id, "pids": products_json, "stat": "Pending", "rdate": return_date}
            )
            conn.commit()
        return json.dumps({"status": "Return Initiated", "return_id": return_id})
    except Exception as e:
        return f"Error: {e}"


# Tool 4: Product Database Query (COMPLETELY FIXED SCHEMA)
# In app/data_query_server.py

@mcp.tool()
async def query_product_database(
        product_name: Optional[str] = None,
        category: Optional[str] = None,
        colour: Optional[str] = None,
        size: Optional[str] = None
) -> str:
    """
    Search the 'products' table. Returns price, stock, and details.
    """
    # --- FIX: SANITIZE INPUTS ---
    # The LLM sometimes sends the string "None" instead of actual Python None.
    # We must convert these to real None so the SQL query ignores them.
    if product_name == "None": product_name = None
    if category == "None": category = None
    if colour == "None": colour = None
    if size == "None": size = None
    # ----------------------------

    query = """
            SELECT p.product_name, \
                   p.category, \
                   p.price, \
                   p.image_url, \
                   p.colour, \
                   p.description, \
                   i.size, \
                   i.stock_quantity
            FROM products p
                     LEFT JOIN inventory i ON p.product_id = i.product_id
            WHERE 1 = 1 \
            """
    params = {}

    if product_name:
        query += " AND p.product_name LIKE :product_name"
        params['product_name'] = f"%{product_name}%"
    if category:
        query += " AND p.category LIKE :category"
        params['category'] = f"%{category}%"
    if colour:
        query += " AND p.colour LIKE :colour"
        params['colour'] = f"%{colour}%"
    if size:
        query += " AND i.size LIKE :size"
        params['size'] = f"%{size}%"

    query += " LIMIT 5"

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            results = cursor.execute(query, params).fetchall()

            if not results:
                return "No products found matching those criteria."

            formatted_results = []
            for row in results:
                # Stock Logic
                qty = row['stock_quantity']
                if qty is not None:
                    stock_status = f"Out of Stock (size {row['size']})" if qty <= 0 else f"In Stock (size {row['size']}, {qty} left)"
                else:
                    stock_status = "Stock unknown"

                # Image Tag
                image_tag = f'<img src="{row["image_url"]}" alt="Image" />' if row['image_url'] else ""

                formatted_results.append(
                    f"Product: {row['product_name']}\n"
                    f"Price: {row['price']}\n"
                    f"Colour: {row['colour']}\n"
                    f"Size: {row['size']}\n"
                    f"Description: {row['description']}\n"
                    f"Status: {stock_status}\n"
                    f"{image_tag}"
                )

            return "\n\n---PRODUCT---\n\n".join(formatted_results)

    except Exception as e:
        return f"Error: Failed to query product database. Reason: {e}"


# Tool 5: Restock Notification
@mcp.tool()
async def add_restock_notification(product_name: str, customer_email: str, size: str,
                                   colour: Optional[str] = None) -> str:
    """Add a customer to the waitlist."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Find product ID
            pid_res = cursor.execute("SELECT product_id FROM products WHERE product_name LIKE ?",
                                     (f"%{product_name}%",)).fetchone()
            if not pid_res:
                return f"Error: Product '{product_name}' not found."
            product_id = pid_res[0]

        with write_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO restock_notifications (customer_email, product_id, size, status) VALUES (:email, :pid, :size, 'Pending')"),
                {"email": customer_email, "pid": product_id, "size": size}
            )
            conn.commit()
        return json.dumps({"status": "Success", "message": f"Added {customer_email} to waitlist."})
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")