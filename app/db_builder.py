import pandas as pd
import os
import re
import traceback
from app.database import engine, SessionLocal
from app.models import Base, Product, Inventory, VtoSession


def init_db():
    """Idempotent table creation — creates any missing tables without touching existing ones."""
    print("--- 🔄 Ensuring all tables exist (create_all idempotent)... ---")
    Base.metadata.create_all(bind=engine)
    _apply_column_migrations()


def _apply_column_migrations():
    """ADD COLUMN IF NOT EXISTS for columns added after initial deploy.
    Safe to run on every startup — postgres IF NOT EXISTS makes it idempotent."""
    migrations = [
        # order_number added in sales overhaul sprint
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_number VARCHAR UNIQUE",
        # thread_id added to link orders to chat sessions
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS thread_id VARCHAR",
        # stripe_payment_id nullable extension
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_payment_id VARCHAR",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
            except Exception as e:
                print(f"Migration skipped ({e})")
        conn.commit()
    print("--- ✅ Column migrations applied ---")


def clean_column_name(col_name):
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def clean_prefix(value, prefix):
    val_str = str(value).strip()
    if val_str.lower().startswith(prefix.lower()):
        return re.sub(f"^{re.escape(prefix)}[:\\s]*", "", val_str, flags=re.IGNORECASE)
    return val_str


def clean_name(name: str) -> str:
    """
    Strip cosmetic artifacts from product names:
      - (**) / (*) markers (appear in some Excel entries)
      - Zero-width spaces / BOM characters from copy-paste
      - Leading/trailing '?' from UTF encoding issues
      - Extra whitespace
    """
    name = re.sub(r'\(\*+\)', '', name)                     # (**) (*) (***)
    name = re.sub(r'\*+', '', name)                         # stray *
    name = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', name)  # zero-width chars
    name = re.sub(r'^\?+\s*', '', name)                     # leading ?
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def is_sold_out(row):
    for val in row.values:
        if isinstance(val, str) and "sold out" in val.lower():
            return True
    return False


def detect_category(name: str, description: str, is_set_bundle: bool = False) -> str:
    """
    Infers category from product name and description keywords.

    KEY FIX: We strip the 'Full Set includes...' sentence from the description
    before checking keywords.  Without this, individual set components (e.g.
    'Crimson & Cloud Croptop') were wrongly categorised as 'Sets & Co-ords'
    because their description mentioned 'Full Set'.
    The 'Sets & Co-ords' label is only applied when is_set_bundle=True.
    """
    if is_set_bundle:
        return "Sets & Co-ords"

    # Strip set-reference sentences to prevent false category detection
    clean_desc = re.sub(r'[Tt]he [Ff]ull [Ss]et includes[\s\S]*', '', str(description))
    clean_desc = re.sub(r'[Tt]his item is part of a set[\s\S]*', '', clean_desc)

    text = (str(name) + " " + clean_desc).lower()

    if "skirt" in text:
        return "Skirts"
    if "pant" in text or "trouser" in text or "culotte" in text:
        return "Pants & Trousers"
    if "jumper" in text or "cardigan" in text or "sweater" in text:
        return "Jumpers & Knits"
    if "jacket" in text or "blazer" in text or "coat" in text:
        return "Jackets & Outerwear"
    if "blouse" in text or "shirt" in text:
        return "Tops & Blouses"
    if "croptop" in text or "crop top" in text or "tank" in text or "top" in text:
        return "Tops & Blouses"
    if "dress" in text or "gown" in text or "frock" in text:
        return "Dresses"
    return "General"


def extract_set_reference(description: str) -> str:
    """
    Extracts the set-reference clause from a product description so that all
    components of the same bundle share one unique key in the set registry.

    Example:
        '...The Full Set includes the [Crimson & Cloud Croptop] and [Crimson & Cloud Skirt]'
        → 'crimson & cloud croptop and crimson & cloud skirt'
    """
    match = re.search(
        r'(?:[Tt]he [Ff]ull [Ss]et includes|'
        r'[Tt]his item is part of a set\.?\s*[Tt]he [Ff]ull [Ss]et includes)\s*(.*?)(?:\.|$)',
        str(description),
        re.DOTALL,
    )
    if match:
        ref = re.sub(r'\s+', ' ', match.group(1)).strip().lower()
        ref = re.sub(r'[\[\]]', '', ref).strip(' .')    # remove brackets
        ref = re.sub(r'\bthe\s+', '', ref)              # normalise 'the '
        return ref
    return ""


def find_common_prefix(names: list) -> str:
    """Returns the common word-level prefix shared by all names in the list."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    word_groups = [n.split() for n in names]
    common = []
    for words in zip(*word_groups):
        if len({w.lower() for w in words}) == 1:
            common.append(words[0])
        else:
            break
    return " ".join(common)


def _safe_img(img) -> str | None:
    """Return the image URL string or None if the value is empty/NaN."""
    if img is None:
        return None
    s = str(img).strip()
    return s if s and s.lower() != 'nan' else None


def upsert_product(db, name, category, price, desc, img, colour, size, qty):
    existing = db.query(Product).filter(
        Product.product_name == name,
        Product.colour == colour,
    ).first()

    if existing:
        existing.price = price
        existing.description = desc
        existing.category = category
        if img:
            existing.image_url = img
        prod_id = existing.product_id
    else:
        new_prod = Product(
            product_name=name,
            category=category,
            price=price,
            description=desc,
            image_url=img,
            colour=colour,
        )
        db.add(new_prod)
        db.flush()
        prod_id = new_prod.product_id

    if size is not None and str(size).strip().upper() not in ('', 'NAN', 'NONE'):
        clean_size = str(size).strip().upper()
        inv = db.query(Inventory).filter(
            Inventory.product_id == prod_id,
            Inventory.size == clean_size,
        ).first()
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
                new_headers = [
                    f"{r0} {r1}" if (r0 and r1 and r0 != r1) else (r1 if r1 else r0)
                    for r0, r1 in zip(row0, row1)
                ]
                df = df_raw.iloc[2:].copy()
                df.columns = new_headers
            else:
                df = df_check
        except Exception as exc:
            print(f"❌ Error reading Excel: {exc}")
            return

        # --- Clean column prefixes ---
        print("--- 🧹 Cleaning Data Prefixes... ---")
        for col, prefix in {
            'Dress Name': 'Dress Name',
            'Colour': 'Colour',
            'Dress description': 'Dress description',
        }.items():
            if col in df.columns:
                df[col] = df[col].astype(str).apply(lambda x: clean_prefix(x, prefix))

        # --- Normalise column names ---
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

        # --- Forward-fill product fields across size rows ---
        # IMPORTANT: 'Full set Price' is intentionally EXCLUDED from this list.
        # Including it causes downstream products (which have no bundle) to
        # inherit the previous product's Full set Price via ffill, creating
        # spurious "Full Set" entries in the database.
        fill_cols = [c for c in df.columns if c in [
            'Dress Code', 'Dress Name', 'Colour',
            'Dress description', 'Unit Price (LKR)', 'image_url',
        ]]
        df[fill_cols] = df[fill_cols].ffill()

        print("--- 🔄 Syncing Individual Products... ---")

        # ------------------------------------------------------------------
        # SET REGISTRY
        # Groups components that share the same physical bundle so we create
        # ONE "Full Set" entry per bundle instead of one per component.
        #
        # Key:   normalised set-reference text extracted from the description
        #        (falls back to "__price_<N>__" when no reference is present)
        # Value: {price, img, colour, components: [{name, colour, img, sizes}]}
        # ------------------------------------------------------------------
        set_registry: dict = {}
        grouped = df.groupby(['Dress Name', 'Colour'])

        for (raw_name, colour), group in grouped:
            name = clean_name(str(raw_name).strip())
            colour = str(colour).strip()

            if not name or name.lower() in ('nan', ''):
                continue

            first = group.iloc[0]
            desc = clean_name(str(first.get('Dress description', '') or '').strip())
            img = _safe_img(first.get('image_url'))
            is_sold = any(is_sold_out(r) for _, r in group.iterrows())

            # Collect sizes and stock quantities for this product
            sizes: dict = {}
            for _, r in group.iterrows():
                sz = r.get('Quantity Size')
                if sz is None or (not isinstance(sz, str) and pd.isna(sz)):
                    continue
                sz = str(sz).strip().upper()
                if not sz or sz in ('NAN', ''):
                    continue
                qty_raw = r.get('Quantity for each', 0)
                qty = 0 if is_sold else int(qty_raw or 0)
                sizes[sz] = qty

            # 1. Individual item ─────────────────────────────────────────
            u_price = pd.to_numeric(first.get('Unit Price (LKR)'), errors='coerce')
            if not pd.isna(u_price) and u_price > 0:
                cat = detect_category(name, desc, is_set_bundle=False)
                upsert_product(db, name, cat, float(u_price), desc, img, colour, None, 0)
                for sz, qty in sizes.items():
                    upsert_product(db, name, cat, float(u_price), desc, img, colour, sz, qty)

            # 2. Register for Full Set deduplication ─────────────────────
            # NOTE: we read directly from the raw (non-ffilled) first row so
            # we only process products that explicitly declare a set price.
            s_price = pd.to_numeric(first.get('Full set Price'), errors='coerce')
            if not pd.isna(s_price) and s_price > 0:
                set_ref = extract_set_reference(desc)
                if not set_ref:
                    # Fallback: price-based key (works when descriptions don't
                    # embed a set reference — rare but possible)
                    set_ref = f"__price_{round(s_price)}__"

                if set_ref not in set_registry:
                    set_registry[set_ref] = {
                        "price": s_price,
                        "components": [],
                        "img": img,
                        "colour": colour,
                    }
                set_registry[set_ref]["components"].append({
                    "name": name,
                    "colour": colour,
                    "img": img,
                    "desc": desc,
                    "sizes": sizes,
                })

        # ------------------------------------------------------------------
        # Second pass: create ONE Full Set entry per unique bundle
        # ------------------------------------------------------------------
        print(f"--- 🎁 Creating {len(set_registry)} unique Full Set bundle(s)... ---")

        for set_ref, set_info in set_registry.items():
            components = set_info["components"]
            set_price = set_info["price"]

            # Derive a clean set name from common word prefix
            comp_names = [c["name"] for c in components]
            prefix = find_common_prefix(comp_names).strip()

            if len(prefix) >= 6:
                b_name = f"{prefix} - Full Set"
            else:
                # No meaningful common prefix → use the first component's name
                b_name = f"{comp_names[0]} - Full Set"

            b_colour = components[0]["colour"]
            b_img = _safe_img(components[0]["img"]) or _safe_img(set_info["img"])
            b_desc = (
                f"Complete co-ord set — includes: {', '.join(comp_names)}. "
                f"{components[0]['desc']}"
            )

            # Available sizes = intersection; quantity = minimum across components
            if len(components) == 1:
                common_sizes = components[0]["sizes"]
            else:
                common_keys = set(components[0]["sizes"].keys())
                for comp in components[1:]:
                    common_keys &= set(comp["sizes"].keys())
                common_sizes = {
                    sz: min(c["sizes"].get(sz, 0) for c in components)
                    for sz in common_keys
                }

            upsert_product(
                db, b_name, "Sets & Co-ords",
                float(set_price), b_desc, b_img, b_colour, None, 0,
            )
            for sz, qty in common_sizes.items():
                upsert_product(
                    db, b_name, "Sets & Co-ords",
                    float(set_price), b_desc, b_img, b_colour, sz, qty,
                )

        db.commit()
        print(
            f"✅ Database Sync Complete: "
            f"{len(grouped)} product groups processed, "
            f"{len(set_registry)} bundle(s) created."
        )

    except Exception as exc:
        print(f"❌ DB Sync Error: {exc}")
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    populate_initial_data()
