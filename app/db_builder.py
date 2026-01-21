import pandas as pd
import os
import re
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory


def init_db():
    """Creates tables in the database (Postgres or SQLite)."""
    print("--- Creating Database Tables ---")
    Base.metadata.create_all(bind=engine)
    print("--- Tables Created Successfully ---")


def clean_column_name(col_name):
    """Removes extra spaces and special chars."""
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def populate_initial_data():
    """Reads Excel with double-header detection and populates the database."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, "Pamorya Stock(1).xlsx")

    if not os.path.exists(excel_path):
        print(f"❌ Excel file not found at: {excel_path}")
        return

    print(f"Reading Excel file from: {os.path.basename(excel_path)}")
    try:
        # 1. Read RAW data (no header) to inspect first 2 rows
        df_raw = pd.read_excel(excel_path, header=None)

        # 2. Construct Custom Headers (Merge Row 0 and Row 1)
        # We take the first row (index 0) and second row (index 1)
        row0 = df_raw.iloc[0].fillna('').astype(str).apply(clean_column_name)
        row1 = df_raw.iloc[1].fillna('').astype(str).apply(clean_column_name)

        new_headers = []
        for r0, r1 in zip(row0, row1):
            # Logic: Combine them if both exist, otherwise take the non-empty one
            if r0 and r1 and r0 != r1:
                combined = f"{r0} {r1}"  # e.g. "Quantity" + "Size" -> "Quantity Size"
            elif r1:
                combined = r1  # e.g. "" + "Size" -> "Size"
            else:
                combined = r0  # e.g. "image_url" + "" -> "image_url"

            new_headers.append(combined)

        print(f"   -> Constructed Headers: {new_headers}")

        # 3. Apply Headers and Drop the top 2 rows
        df = df_raw.iloc[2:].copy()  # Data starts at row index 2
        df.columns = new_headers
        df.reset_index(drop=True, inplace=True)

        # 4. Normalize Column Names for Code Compatibility
        # We need to ensure the code finds 'Quantity Size' even if the merge was messy
        # Create a mapping for "fuzzy" matching
        col_map = {}
        for col in df.columns:
            clean_col = col.lower()
            if "size" in clean_col and "quantity" in clean_col:
                col_map[col] = "Quantity Size"
            elif "quantity" in clean_col and "each" in clean_col:
                col_map[col] = "Quantity for each"
            elif "image" in clean_col and "url" in clean_col:
                col_map[col] = "image_url"
            elif "price" in clean_col and "lkr" in clean_col:
                col_map[col] = "Unit Price (LKR)"
            elif "description" in clean_col:
                col_map[col] = "Dress description"

        df.rename(columns=col_map, inplace=True)
        print(f"   -> Final Mapped Columns: {list(df.columns)}")

    except Exception as e:
        print(f"❌ Error reading/processing Excel: {e}")
        return

    db: Session = SessionLocal()

    if db.query(Product).count() == 0:
        print("⚠️ Database is empty. Seeding data...")

        products_added = 0
        inventory_added = 0

        # Group by unique product attributes
        # Use .get() to avoid KeyError if a column is slightly different
        def get_val(row, col_name, default=None):
            return row[col_name] if col_name in row else default

        # We must identify the "grouping" columns carefully
        # If 'Dress Code' is missing, fallback to 'Dress Name'
        group_cols = [c for c in
                      ['Dress Code', 'Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)', 'image_url'] if
                      c in df.columns]

        if not group_cols:
            print("❌ Critical: Could not find any product grouping columns (Name, Code, etc).")
            return

        grouped = df.groupby(group_cols)

        for keys, group in grouped:
            # Unpack keys into a dictionary for easier access
            data = dict(zip(group_cols, keys if isinstance(keys, tuple) else [keys]))

            name = data.get('Dress Name', 'Unknown Product')
            price = data.get('Unit Price (LKR)', 0)
            desc = data.get('Dress description', '')
            img = data.get('image_url', None)
            colour = data.get('Colour', 'Unknown')

            new_product = Product(
                product_name=name,
                category="Dresses",
                price=float(price) if pd.notna(price) and str(price).replace('.', '').isdigit() else 0.0,
                description=desc,
                image_url=img if pd.notna(img) else None,
                colour=colour
            )
            db.add(new_product)
            db.flush()
            products_added += 1

            for _, row in group.iterrows():
                # Flexible lookup for size/qty
                size = row.get('Quantity Size', row.get('Size', 'Standard'))
                qty = row.get('Quantity for each', 0)

                inv_item = Inventory(
                    product_id=new_product.product_id,
                    size=str(size).strip(),
                    stock_quantity=int(qty) if pd.notna(qty) and str(qty).isdigit() else 0
                )
                db.add(inv_item)
                inventory_added += 1

        db.commit()
        print(f"✅ Success! Added {products_added} products and {inventory_added} inventory items.")
    else:
        print("✅ Database already contains data. Skipping seed.")

    db.close()


if __name__ == "__main__":
    init_db()
    populate_initial_data()