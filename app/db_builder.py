import pandas as pd
import os
import re
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory, Order, OrderItem, Customer


def init_db():
    """Drops and recreates tables to sync schema."""
    print("--- ⚠️ ATTEMPTING TO DROP AND RECREATE TABLES ---")
    try:
        # Use Cascade to force drop even with foreign keys
        with engine.connect() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE;"))
            connection.execute(text("CREATE SCHEMA public;"))
            connection.commit()

        print("--- ✅ Schema Dropped. Recreating Tables... ---")
        Base.metadata.create_all(bind=engine)
        print("--- ✅ Tables Recreated Successfully ---")
    except Exception as e:
        print(f"❌ Error dropping tables: {e}")
        # Fallback to standard drop if cascade fails
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


def clean_column_name(col_name):
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def populate_initial_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, "Pamorya Stock(1)212.xlsx")

    if not os.path.exists(excel_path):
        old_path = os.path.join(base_dir, "Pamorya Stock(1).xlsx")
        if os.path.exists(old_path):
            excel_path = old_path
        else:
            print("❌ No data file found.")
            return

    try:
        df_raw = pd.read_excel(excel_path, header=None)

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

        df = df_raw.iloc[2:].copy()
        df.columns = new_headers
        df.reset_index(drop=True, inplace=True)

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

        product_cols = [c for c in df.columns if
                        c in ['Dress Code', 'Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)',
                              'image_url']]
        df[product_cols] = df[product_cols].ffill()
        if 'Unit Price (LKR)' in df.columns:
            df['Unit Price (LKR)'] = pd.to_numeric(df['Unit Price (LKR)'], errors='coerce').fillna(0)

    except Exception as e:
        print(f"❌ Error processing file: {e}")
        return

    db = SessionLocal()
    print("⚠️ Seeding data...")
    products_added = 0
    inventory_added = 0

    if 'Dress Name' not in df.columns:
        print("❌ Error: 'Dress Name' column not found.")
        return

    grouped = df.groupby(['Dress Name', 'Colour'])
    for (name, colour), group in grouped:
        first_row = group.iloc[0]
        price = first_row.get('Unit Price (LKR)', 0)
        desc = first_row.get('Dress description', '')
        img = first_row.get('image_url', None)
        final_img = str(img).strip() if pd.notna(img) and str(img).lower() != 'nan' else None

        new_product = Product(
            product_name=str(name).strip(),
            category="Dresses",
            price=float(price),
            description=str(desc).strip(),
            image_url=final_img,
            colour=str(colour).strip()
        )
        db.add(new_product)
        db.flush()
        products_added += 1

        for _, row in group.iterrows():
            size = row.get('Quantity Size', row.get('Size', 'Standard'))
            qty = row.get('Quantity for each', 0)
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
    db.close()


if __name__ == "__main__":
    init_db()
    populate_initial_data()