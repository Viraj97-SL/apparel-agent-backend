import pandas as pd
import os
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory


def init_db():
    """Creates tables in the database (Postgres or SQLite)."""
    print("--- Creating Database Tables ---")
    Base.metadata.create_all(bind=engine)
    print("--- Tables Created Successfully ---")


def populate_initial_data():
    """Reads Excel and populates the database."""
    # Logic to find the Excel file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base_dir, "Pamorya Stock(1).xlsx")

    if not os.path.exists(excel_path):
        print(f"❌ Excel file not found at: {excel_path}")
        return

    print(f"Reading Excel file from: {os.path.basename(excel_path)}")
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"❌ Error reading Excel: {e}")
        return

    db: Session = SessionLocal()

    # Optional: Clear existing products/inventory to avoid duplicates on re-seed
    # Be careful with this in production!
    if db.query(Product).count() == 0:
        print("⚠️ Database is empty. Seeding data...")

        products_added = 0
        inventory_added = 0

        # Group by Dress Code to create unique Products
        grouped = df.groupby(
            ['Dress Code', 'Dress Name', 'Colour', 'Dress description', 'Unit Price (LKR)', 'image_url'])

        for (code, name, colour, desc, price, img), group in grouped:
            # Create Product
            new_product = Product(
                product_name=name,
                category="Dresses",  # Assuming mostly dresses based on file
                price=float(price),
                description=desc,
                image_url=img if pd.notna(img) else None,
                colour=colour
            )
            db.add(new_product)
            db.flush()  # Flush to get the new_product.product_id
            products_added += 1

            # Create Inventory for each size in the group
            for _, row in group.iterrows():
                size = row['Quantity Size']
                qty = row['Quantity for each']

                # Basic cleaning
                if pd.isna(qty): qty = 0

                inv_item = Inventory(
                    product_id=new_product.product_id,
                    size=str(size).strip(),
                    stock_quantity=int(qty)
                )
                db.add(inv_item)
                inventory_added += 1

        db.commit()
        print(f"Success! Added {products_added} products and {inventory_added} inventory items.")
    else:
        print("✅ Database already contains data. Skipping seed.")

    db.close()


if __name__ == "__main__":
    init_db()
    populate_initial_data()