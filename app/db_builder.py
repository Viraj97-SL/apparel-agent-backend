import pandas as pd
import os
import re
from sqlalchemy import inspect
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory


def init_db():
    """
    Creates tables ONLY if they don't exist.
    NEVER drops tables. Data is safe.
    """
    inspector = inspect(engine)
    if not inspector.has_table("products"):
        print("--- 🆕 New Database Detected. Creating Tables... ---")
        Base.metadata.create_all(bind=engine)
        print("--- ✅ Tables Created Successfully ---")
        return True
    else:
        print("--- 🔄 Database tables exist. Skipping creation to protect data. ---")
        return False


def clean_column_name(col_name):
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def populate_initial_data():
    """Populates data ONLY if the Product table is empty."""
    db = SessionLocal()
    try:
        # Check if we already have data
        if db.query(Product).count() > 0:
            print("--- 📦 Data already exists. Skipping seed. ---")
            return

        print("--- ⚠️ Seeding Initial Data from Excel... ---")

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(base_dir, "Pamorya Stock(1)212.xlsx")

        if not os.path.exists(excel_path):
            # Fallback
            excel_path = os.path.join(base_dir, "Pamorya Stock(1).xlsx")
            if not os.path.exists(excel_path):
                print("❌ No Excel file found. Skipping seed.")
                return

        df_raw = pd.read_excel(excel_path, header=None)

        row0 = df_raw.iloc[0].fillna('').astype(str).apply(clean_column_name)
        row1 = df_raw.iloc[1].fillna('').astype(str).apply(clean_column_name)
        new_headers = []
        for r0, r1 in zip(row0, row1):
            combined = f"{r0} {r1}" if (r0 and r1 and r0 != r1) else (r1 if r1 else r0)
            new_headers.append(combined)

        df = df_raw.iloc[2:].copy()
        df.columns = new_headers
        df.reset_index(drop=True, inplace=True)

        col_map = {}
        for col in df.columns:
            c = col.lower()
            if "size" in c and "quantity" in c:
                col_map[col] = "Quantity Size"
            elif "quantity" in c:
                col_map[col] = "Quantity for each"
            elif "image" in c:
                col_map[col] = "image_url"
            elif "price" in c:
                col_map[col] = "Unit Price (LKR)"
            elif "description" in c:
                col_map[col] = "Dress description"
        df.rename(columns=col_map, inplace=True)

        # Forward Fill
        prod_cols = [c for c in df.columns if
                     c in ['Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)', 'image_url']]
        df[prod_cols] = df[prod_cols].ffill()
        if 'Unit Price (LKR)' in df.columns:
            df['Unit Price (LKR)'] = pd.to_numeric(df['Unit Price (LKR)'], errors='coerce').fillna(0)

        grouped = df.groupby(['Dress Name', 'Colour'])
        for (name, colour), group in grouped:
            row = group.iloc[0]
            price = row.get('Unit Price (LKR)', 0)
            desc = row.get('Dress description', '')
            img = row.get('image_url', None)
            final_img = str(img).strip() if pd.notna(img) and str(img).lower() != 'nan' else None

            prod = Product(
                product_name=str(name).strip(),
                category="Dresses",
                price=float(price),
                description=str(desc).strip(),
                image_url=final_img,
                colour=str(colour).strip()
            )
            db.add(prod)
            db.flush()

            for _, r in group.iterrows():
                size = r.get('Quantity Size', r.get('Size', 'Standard'))
                qty = r.get('Quantity for each', 0)
                if pd.notna(size) and str(size).strip():
                    inv = Inventory(
                        product_id=prod.product_id,
                        size=str(size).strip(),
                        stock_quantity=int(qty) if pd.notna(qty) else 0
                    )
                    db.add(inv)

        db.commit()
        print(f"✅ Seeding Complete.")

    except Exception as e:
        print(f"❌ Seeding Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    is_new = init_db()
    if is_new:
        populate_initial_data()