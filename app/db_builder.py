import pandas as pd
import os
import re
from sqlalchemy import inspect
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory


def init_db():
    """Creates tables ONLY if they don't exist."""
    inspector = inspect(engine)
    if not inspector.has_table("products"):
        print("--- 🆕 New Database Detected. Creating Tables... ---")
        Base.metadata.create_all(bind=engine)
        return True
    return False


def clean_column_name(col_name):
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def clean_prefix(value, prefix):
    val_str = str(value).strip()
    if val_str.lower().startswith(prefix.lower()):
        return re.sub(f"^{re.escape(prefix)}[:\s]*", "", val_str, flags=re.IGNORECASE)
    return val_str


def is_sold_out(row):
    for val in row.values:
        if isinstance(val, str) and "sold out" in val.lower():
            return True
    return False


# --- 🧠 NEW: Smart Categorization Logic ---
def detect_category(name, description, is_set_bundle=False):
    """Infers category from product name and description keywords."""
    text = (str(name) + " " + str(description)).lower()

    if is_set_bundle or "full set" in text or "ensemble" in text:
        return "Sets & Co-ords"
    if "skirt" in text:
        return "Skirts"
    if "pant" in text or "trouser" in text or "culotte" in text:
        return "Pants & Trousers"
    if "jumper" in text or "cardigan" in text or "sweater" in text:
        return "Jumpers & Knits"
    if "blouse" in text or "shirt" in text:
        return "Tops & Blouses"
    if "croptop" in text or "crop top" in text or "tank" in text or "top" in text:
        return "Tops & Blouses"
    if "dress" in text or "gown" in text or "frock" in text:
        return "Dresses"

    return "General"


def upsert_product(db, name, category, price, desc, img, colour, size, qty):
    # Check Exists
    existing_prod = db.query(Product).filter(
        Product.product_name == name,
        Product.colour == colour
    ).first()

    if existing_prod:
        existing_prod.price = price
        existing_prod.description = desc
        existing_prod.category = category  # Update category if logic changes
        if img: existing_prod.image_url = img
        prod_id = existing_prod.product_id
    else:
        new_prod = Product(
            product_name=name, category=category, price=price,
            description=desc, image_url=img, colour=colour
        )
        db.add(new_prod)
        db.flush()
        prod_id = new_prod.product_id

    # Inventory
    if pd.notna(size) and str(size).strip():
        clean_size = str(size).strip()
        inv = db.query(Inventory).filter(Inventory.product_id == prod_id, Inventory.size == clean_size).first()
        if inv:
            inv.stock_quantity = qty
        else:
            db.add(Inventory(product_id=prod_id, size=clean_size, stock_quantity=qty))


def populate_initial_data():
    db = SessionLocal()
    try:
        print("--- 📊 Reading Excel for Database Sync... ---")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(base_dir, "Pamorya_Stock(1).xlsx")

        # Fallback to original name if needed
        if not os.path.exists(excel_path):
            excel_path = os.path.join(base_dir, "Pamorya_Stock.xlsx")

        if not os.path.exists(excel_path):
            print("❌ No Excel file found.")
            return

        print(f"--- 📂 Processing: {os.path.basename(excel_path)} ---")

        try:
            df_check = pd.read_excel(excel_path)
            if "Dress Name" not in df_check.columns:
                df_raw = pd.read_excel(excel_path, header=None)
                row0 = df_raw.iloc[0].fillna('').astype(str).apply(clean_column_name)
                row1 = df_raw.iloc[1].fillna('').astype(str).apply(clean_column_name)
                new_headers = [f"{r0} {r1}" if (r0 and r1 and r0 != r1) else (r1 if r1 else r0) for r0, r1 in
                               zip(row0, row1)]
                df = df_raw.iloc[2:].copy()
                df.columns = new_headers
            else:
                df = df_check
        except Exception as e:
            print(f"❌ Error reading Excel: {e}")
            return

        print("--- 🧹 Cleaning Data Prefixes... ---")
        cols_to_clean = {'Dress Name': 'Dress Name', 'Colour': 'Colour', 'Dress description': 'Dress description'}
        for col, prefix in cols_to_clean.items():
            if col in df.columns:
                df[col] = df[col].astype(str).apply(lambda x: clean_prefix(x, prefix))

        col_map = {}
        for col in df.columns:
            c = col.lower().strip()
            if "size" in c and "quantity" in c:
                col_map[col] = "Quantity Size"
            elif c == "size":
                col_map[col] = "Quantity Size"
            elif "quantity" in c:
                col_map[col] = "Quantity for each"
            elif "image" in c:
                col_map[col] = "image_url"
            elif "unit price" in c:
                col_map[col] = "Unit Price (LKR)"
            elif "full set" in c or "set price" in c:
                col_map[col] = "Full set Price"
            elif "description" in c:
                col_map[col] = "Dress description"
        df.rename(columns=col_map, inplace=True)

        fill_cols = [c for c in df.columns if
                     c in ['Dress Code', 'Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)',
                           'Full set Price', 'image_url']]
        df[fill_cols] = df[fill_cols].ffill()

        print("--- 🔄 Syncing Inventory & Categories... ---")
        grouped = df.groupby(['Dress Name', 'Colour'])
        for (name, colour), group in grouped:
            name, colour = str(name).strip(), str(colour).strip()
            first = group.iloc[0]
            desc = str(first.get('Dress description', '')).strip()
            img = first.get('image_url', None)
            is_sold = any(is_sold_out(r) for _, r in group.iterrows())

            # 1. Individual Item
            u_price = pd.to_numeric(first.get('Unit Price (LKR)'), errors='coerce')
            if u_price > 0:
                # 🧠 Detect Category automatically
                cat = detect_category(name, desc, is_set_bundle=False)
                upsert_product(db, name, cat, float(u_price), desc, img, colour, None, 0)
                for _, r in group.iterrows():
                    qty = 0 if is_sold else int(r.get('Quantity for each', 0) or 0)
                    upsert_product(db, name, cat, float(u_price), desc, img, colour, r.get('Quantity Size'), qty)

            # 2. Set Bundle
            s_price = pd.to_numeric(first.get('Full set Price'), errors='coerce')
            if s_price > 0:
                b_name = f"{name} - Full Set"
                b_desc = f"{desc}\n(This is a complete set including all matching pieces.)"
                # 🧠 Force "Sets" category
                cat = detect_category(name, desc, is_set_bundle=True)
                upsert_product(db, b_name, cat, float(s_price), b_desc, img, colour, None, 0)
                for _, r in group.iterrows():
                    qty = 0 if is_sold else int(r.get('Quantity for each', 0) or 0)
                    upsert_product(db, b_name, cat, float(s_price), b_desc, img, colour, r.get('Quantity Size'), qty)

        db.commit()
        print(f"✅ Database Sync Complete. Processed {len(grouped)} groups.")
    except Exception as e:
        print(f"❌ DB Sync Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    populate_initial_data()