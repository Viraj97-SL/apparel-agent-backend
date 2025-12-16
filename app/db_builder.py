import os
import sqlite3
import pandas as pd

# --- Setup Project Paths ---
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Database and Excel paths (for local)
#DB_PATH = os.path.join(project_root, "apparel.db")
#EXCEL_PATH = os.path.join(project_root, "Pamorya Stock(1).xlsx")

#cloud deployment
# Just look for files in the same folder as this script
DB_PATH = "apparel.db"
EXCEL_PATH = "Pamorya Stock(1).xlsx"


def create_tables(conn):
    """Creates the necessary tables."""
    cursor = conn.cursor()

    # 1. Products Table
    cursor.execute("DROP TABLE IF EXISTS products")
    cursor.execute("""
                   CREATE TABLE products
                   (
                       product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                       product_code TEXT,
                       product_name TEXT NOT NULL,
                       category     TEXT,
                       colour       TEXT,
                       price        REAL,
                       description  TEXT,
                       image_url    TEXT,
                       UNIQUE (product_name, colour)
                   )
                   """)

    # 2. Inventory Table
    cursor.execute("DROP TABLE IF EXISTS inventory")
    cursor.execute("""
                   CREATE TABLE inventory
                   (
                       variant_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                       product_id     INTEGER NOT NULL,
                       size           TEXT,
                       stock_quantity INTEGER DEFAULT 0,
                       FOREIGN KEY (product_id) REFERENCES products (product_id)
                   )
                   """)

    # 3. Restock Notifications
    cursor.execute("DROP TABLE IF EXISTS restock_notifications")
    cursor.execute("""
                   CREATE TABLE restock_notifications
                   (
                       notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       customer_email  TEXT    NOT NULL,
                       product_id      INTEGER NOT NULL,
                       size            TEXT,
                       status          TEXT      DEFAULT 'Pending',
                       created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY (product_id) REFERENCES products (product_id)
                   )
                   """)

    # 4. Standard Tables
    cursor.execute("DROP TABLE IF EXISTS customers")
    cursor.execute(
        "CREATE TABLE customers (customer_id VARCHAR(10) PRIMARY KEY, name VARCHAR(100), email VARCHAR(100))")
    cursor.execute("DROP TABLE IF EXISTS orders")
    cursor.execute("""
                   CREATE TABLE orders
                   (
                       order_id    VARCHAR(10) PRIMARY KEY,
                       customer_id VARCHAR(10),
                       status      VARCHAR(50),
                       items       TEXT,
                       FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
                   )
                   """)
    cursor.execute("DROP TABLE IF EXISTS returns")
    cursor.execute("""
                   CREATE TABLE returns
                   (
                       return_id   VARCHAR(10) PRIMARY KEY,
                       order_id    VARCHAR(10),
                       product_ids TEXT,
                       status      VARCHAR(50),
                       return_date TEXT,
                       FOREIGN KEY (order_id) REFERENCES orders (order_id)
                   )
                   """)

    conn.commit()
    print("--- Database Tables Created ---")


def populate_database(conn):
    """Reads the Excel file using COLUMN INDEX to avoid header errors."""
    print(f"Reading Excel file from: {EXCEL_PATH}")

    try:
        # 1. Read the file starting at Row 1 (header=0)
        df = pd.read_excel(EXCEL_PATH, header=0)

        # 2. Rename columns by INDEX (Position) because names are messy
        # Col A (0): Code, B (1): Name, C (2): Colour, D (3): Image, E (4): Desc
        # Col F (5): Size, G (6): Quantity, H (7): Price

        # Safety check: Ensure we have enough columns
        if len(df.columns) < 8:
            print(f"Error: Expected at least 8 columns, found {len(df.columns)}")
            return

        df.columns.values[0] = 'product_code'
        df.columns.values[1] = 'product_name'
        df.columns.values[2] = 'colour'
        df.columns.values[3] = 'image_url'
        df.columns.values[4] = 'description'
        df.columns.values[5] = 'size'
        df.columns.values[6] = 'stock_quantity'
        df.columns.values[7] = 'price'

        # 3. Clean the Data
        # Remove the "garbage" row (Row 2 in Excel) which contains the text "Size" / "Quantity for each"
        # We do this by checking if the 'size' column contains the word "Size"
        df = df[df['size'].astype(str) != 'Size']

        # 4. Fix Merged Cells (Forward Fill)
        # Copies Name, Price, Image, etc. down to the rows below (for sizes S, M, L)
        cols_to_fill = ['product_code', 'product_name', 'colour', 'image_url', 'description', 'price']
        df[cols_to_fill] = df[cols_to_fill].ffill()

        cursor = conn.cursor()
        products_added = 0
        inventory_added = 0

        for index, row in df.iterrows():
            # Extract Data
            code = row['product_code']
            name = row['product_name']

            # Skip if name is empty
            if pd.isna(name):
                continue

            # Default values if missing
            cat = "Dress"
            desc = row['description'] if pd.notna(row['description']) else ""
            price = row['price'] if pd.notna(row['price']) else 0
            img = row['image_url'] if pd.notna(row['image_url']) else ""
            col = row['colour'] if pd.notna(row['colour']) else "Unknown"

            size = row['size'] if pd.notna(row['size']) else "Free Size"
            qty = row['stock_quantity'] if pd.notna(row['stock_quantity']) else 0

            # Insert/Find Product
            cursor.execute(
                "SELECT product_id FROM products WHERE product_name = ? AND colour = ?",
                (name, col)
            )
            result = cursor.fetchone()

            if result:
                p_id = result[0]
            else:
                cursor.execute("""
                               INSERT INTO products (product_code, product_name, category, colour, price, description,
                                                     image_url)
                               VALUES (?, ?, ?, ?, ?, ?, ?)
                               """, (code, name, cat, col, price, desc, img))
                p_id = cursor.lastrowid
                products_added += 1

            # Insert Inventory
            cursor.execute("""
                           INSERT INTO inventory (product_id, size, stock_quantity)
                           VALUES (?, ?, ?)
                           """, (p_id, size, qty))
            inventory_added += 1

        conn.commit()
        print(f"Success! Added {products_added} products and {inventory_added} inventory items.")

    except Exception as e:
        print(f"Error reading Excel: {e}")
        import traceback
        traceback.print_exc()


# --- Added this to the bottom of db_builder.py ---

def init_db():
    """Wrapper to create tables from server.py"""
    print("Creating tables...")
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    conn.close()


def populate_initial_data():
    """Wrapper to populate data from server.py"""
    if not os.path.exists(EXCEL_PATH):
        print(f"❌ ERROR: Excel file not found at {EXCEL_PATH}")
        print("Did you forget to 'git add' the Excel file?")
        return

    print("Populating data...")
    conn = sqlite3.connect(DB_PATH)
    populate_database(conn)
    conn.close()

if __name__ == "__main__":
    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR: File not found at {EXCEL_PATH}")
    else:
        conn = sqlite3.connect(DB_PATH)
        create_tables(conn)
        populate_database(conn)
        conn.close()
        print("Database build complete.")