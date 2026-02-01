import os
import pandas as pd
import cloudinary
import cloudinary.api
import re
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
# Ensure these are set in your .env or Railway Variables
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "dkftnrrjq"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

INPUT_EXCEL = "Pamorya_Stock(1).xlsx"
# We overwrite the file so the DB builder sees the changes
OUTPUT_EXCEL = "Pamorya_Stock(2).xlsx"


def clean_column_name(col_name):
    return re.sub(r'\s+', ' ', str(col_name)).strip()


def fetch_every_image():
    print("--- 1. Scanning ENTIRE Cloudinary Account... ---")
    all_resources = []
    next_cursor = None
    try:
        while True:
            response = cloudinary.api.resources(
                type="upload",
                max_results=500,
                next_cursor=next_cursor
            )
            batch = response.get('resources', [])
            all_resources.extend(batch)
            print(f"   -> Fetched batch of {len(batch)}... (Total: {len(all_resources)})")
            if 'next_cursor' in response:
                next_cursor = response['next_cursor']
            else:
                break
    except Exception as e:
        print(f"❌ Cloudinary Connection Error: {e}")
        print("   (Check your CLOUDINARY_API_KEY and SECRET in .env)")
        return []

    print(f"✅ Scan Complete. Found {len(all_resources)} total images.")
    return all_resources


def auto_link_images():
    # 1. Fetch Cloudinary Data
    resources = fetch_every_image()
    if not resources:
        return

    # 2. Map Clean Filenames -> URLs
    image_list = []
    for res in resources:
        full_id = res['public_id']
        filename = full_id.split('/')[-1].lower()  # e.g. "pwbw01_v1"
        image_list.append({
            "clean_name": filename,
            "url": res['secure_url']
        })

    # 3. Process Excel (Handle Double Headers)
    print("\n--- 2. Processing Excel... ---")
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(base_dir, INPUT_EXCEL)
        if not os.path.exists(excel_path):
            excel_path = INPUT_EXCEL  # Try relative

        df_raw = pd.read_excel(excel_path, header=None)
    except Exception as e:
        print(f"❌ Cannot read Excel: {e}")
        return

    # --- HEADER CLEANUP (Critical for your new file) ---
    row0 = df_raw.iloc[0].fillna('').astype(str).apply(clean_column_name)
    row1 = df_raw.iloc[1].fillna('').astype(str).apply(clean_column_name)
    new_headers = []
    for r0, r1 in zip(row0, row1):
        combined = f"{r0} {r1}" if (r0 and r1 and r0 != r1) else (r1 if r1 else r0)
        new_headers.append(combined)

    df = df_raw.iloc[2:].copy()
    df.columns = new_headers
    df.reset_index(drop=True, inplace=True)

    # Clean Columns for Matching
    col_map = {}
    for col in df.columns:
        c = col.lower()
        if "dress code" in c:
            col_map[col] = "Dress Code"
        elif "image" in c:
            col_map[col] = "image_url"
    df.rename(columns=col_map, inplace=True)

    if 'image_url' not in df.columns:
        df['image_url'] = ""

    count = 0
    print("\n--- 3. Matching Products ---")

    for index, row in df.iterrows():
        raw_code = str(row.get('Dress Code', ''))
        if raw_code == 'nan' or not raw_code.strip():
            continue

        code = raw_code.strip().lower()

        # FIND MATCHES (Starts with Code)
        matched_urls = []
        for img in image_list:
            # Match "pwbw01" against "pwbw01", "pwbw01_01", "pwbw01_v2"
            if img['clean_name'].startswith(code):
                remainder = img['clean_name'][len(code):]
                # Ensure boundary (pwbw01 should not match pwbw015)
                if not remainder or remainder[0] in ['_', '-', '.', ' ']:
                    matched_urls.append(img['url'])

        if matched_urls:
            unique_urls = sorted(list(set(matched_urls)))
            final_str = ",".join(unique_urls)
            # Write back to specific column
            df.at[index, 'image_url'] = final_str
            count += 1
            print(f"✅ {code.upper()}: Linked {len(unique_urls)} images.")

    # 4. Save (We construct a new DataFrame to preserve headers?)
    # Actually, simpler to just save this cleaned version for the DB builder
    df.to_excel(excel_path, index=False)
    print(f"\n🎉 SUCCESS: Updated {count} products in '{excel_path}'")


if __name__ == "__main__":
    auto_link_images()