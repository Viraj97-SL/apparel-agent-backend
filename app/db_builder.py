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
    """Reads Excel, handles merged headers AND merged cells, then populates DB."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Try CSV first if user uploaded that, otherwise Excel
    excel_path = os.path.join(base_dir, "Pamorya Stock(1).xlsx")
    csv_path = os.path.join(base_dir, "Pamorya Stock(1) (1).xlsx - Sheet1.csv")

    path_to_use = None
    if os.path.exists(csv_path):
        path_to_use = csv_path
        print(f"Reading CSV file from: {os.path.basename(csv_path)}")
        # CSVs from Excel often don't have the double-header issue in the same way,
        # but let's assume the structure is identical.
        df_raw = pd.read_csv(csv_path, header=None)
    elif os.path.exists(excel_path):
        path_to_use = excel_path
        print(f"Reading Excel file from: {os.path.basename(excel_path)}")
        df_raw = pd.read_excel(excel_path, header=None)
    else:
        print(f"❌ No data file found. Please upload 'Pamorya Stock(1).xlsx' or the CSV.")
        return

    try:
        # --- 1. HANDLE DOUBLE HEADERS ---
        # Combine Row 0 and Row 1 to make single headers
        row0 = df_raw.iloc[0].fillna('').astype(str).apply(clean_column_name)
        row1 = df_raw.iloc[1].fillna('').astype(str).apply(clean_column_name)

        new_headers = []
        for r0, r1 in zip(row0, row1):
            if r0 and r1 and r0 != r1:
                combined = f"{r0} {r1}"
            elif r1:
                combined = r1
            else:
                combined = r0
            new_headers.append(combined)

        # Drop the header rows and set new column names
        df = df_raw.iloc[2:].copy()
        df.columns = new_headers
        df.reset_index(drop=True, inplace=True)

        # Map to friendly names
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

        # --- 2. CRITICAL FIX: FORWARD FILL MERGED CELLS ---
        # Identify columns that define the "Product" (and are likely merged in Excel)
        product_cols = [c for c in df.columns if
                        c in ['Dress Code', 'Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)',
                              'image_url']]

        # Forward Fill: If a cell is empty (NaN), copy the value from the row above it.
        # This fixes the issue where "Small" has a product name but "Medium" below it does not.
        df[product_cols] = df[product_cols].ffill()

        # Clean Price (remove non-numeric chars)
        if 'Unit Price (LKR)' in df.columns:
            df['Unit Price (LKR)'] = pd.to_numeric(df['Unit Price (LKR)'], errors='coerce').fillna(0)

    except Exception as e:
        print(f"❌ Error processing file structure: {e}")
        return

    db: Session = SessionLocal()

    # --- UNCOMMENT THESE LINES TO FORCE A RE-SEED ---
    # This deletes all existing rows so we can import the fixed data
    #print("⚠️  Force-Clearing Database for fresh seed...")
    #db.query(Product).delete()
    #db.commit()

    if db.query(Product).count() == 0:
        print("⚠️ Database is empty. Seeding data...")

        products_added = 0
        inventory_added = 0

        # We group by the "Product Identity"
        # If 'Dress Name' is missing, we skip.
        if 'Dress Name' not in df.columns:
            print("❌ Error: 'Dress Name' column not found.")
            return

        grouped = df.groupby(['Dress Name', 'Colour'])

        for (name, colour), group in grouped:
            # Take the first row of the group for product details
            first_row = group.iloc[0]

            price = first_row.get('Unit Price (LKR)', 0)
            desc = first_row.get('Dress description', '')
            img = first_row.get('image_url', None)

            # Create Product
            new_product = Product(
                product_name=str(name).strip(),
                category="Dresses",
                price=float(price),
                description=str(desc).strip(),
                image_url=str(img).strip() if pd.notna(img) else None,
                colour=str(colour).strip()
            )
            db.add(new_product)
            db.flush()  # Get ID
            products_added += 1

            # Iterate through ALL rows in this group to get sizes
            for _, row in group.iterrows():
                size = row.get('Quantity Size', row.get('Size', 'Standard'))
                qty = row.get('Quantity for each', 0)

                # Only add if we have a valid size
                if pd.notna(size) and str(size).strip() != "":
                    inv_item = Inventory(
                        product_id=new_product.product_id,
                        size=str(size).strip(),
                        stock_quantity=int(qty) if pd.notna(qty) else 0
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