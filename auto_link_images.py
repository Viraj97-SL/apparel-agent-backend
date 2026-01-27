import os
import pandas as pd
import cloudinary
import cloudinary.api
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "YOUR_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY", "YOUR_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", "YOUR_API_SECRET")
)

INPUT_EXCEL = "Pamorya Stock(1).xlsx"
OUTPUT_EXCEL = "Pamorya Stock(1).xlsx"


def fetch_every_image():
    print("--- 1. Scanning ENTIRE Cloudinary Account... ---")
    all_resources = []
    next_cursor = None

    # We remove the 'prefix' parameter to find images in Root AND Folders
    while True:
        try:
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
            print(f"❌ Connection Error: {e}")
            break

    print(f"✅ Scan Complete. Found {len(all_resources)} total images.")

    # Debug: Print first 3 files to verify we are seeing them
    if all_resources:
        print(f"   (Example file found: {all_resources[0]['public_id']})")

    return all_resources


def auto_link_images_v3():
    # 1. Fetch Everything
    resources = fetch_every_image()

    # 2. Map Clean Filenames -> URLs
    # We store multiple entries to handle folders:
    # 'PWBW01_v1' -> URL
    # 'apparel/PWBW01_v1' -> URL
    image_list = []
    for res in resources:
        full_id = res['public_id']
        filename = full_id.split('/')[-1].lower()  # Just the end part: "pwbw01_v1lxc3"
        image_list.append({
            "clean_name": filename,
            "url": res['secure_url']
        })

    # 3. Process Excel
    print("\n--- 2. Processing Excel... ---")
    try:
        df = pd.read_excel(INPUT_EXCEL)
    except:
        print(f"❌ Cannot find {INPUT_EXCEL}")
        return

    if 'image_url' not in df.columns:
        df['image_url'] = ""

    count = 0
    print("\n--- 3. Matching Products ---")

    for index, row in df.iterrows():
        raw_code = str(row['Dress Code'])
        if raw_code == 'nan' or not raw_code.strip():
            continue

        code = raw_code.strip().lower()  # e.g., "pwbw01"

        # FIND MATCHES
        # We look for the code at the START of the filename
        matched_urls = []
        for img in image_list:
            # Check if "pwbw01_v1lxc3" starts with "pwbw01"
            if img['clean_name'].startswith(code):
                # Safety: Ensure next char is not a letter/number (avoids PWBW01 matching PWBW015)
                remainder = img['clean_name'][len(code):]
                if not remainder or remainder[0] in ['_', '-', '.', ' ']:
                    matched_urls.append(img['url'])

        if matched_urls:
            # Remove duplicates and sort
            unique_urls = sorted(list(set(matched_urls)))
            final_str = ",".join(unique_urls)
            df.at[index, 'image_url'] = final_string = final_str
            count += 1
            print(f"✅ {code.upper()}: Linked {len(unique_urls)} images.")
        else:
            print(f"⚠️ {code.upper()}: No match (Checked {len(image_list)} files)")

    # 4. Save
    df.to_excel(OUTPUT_EXCEL, index=False)
    print(f"\n🎉 SUCCESS: Updated {count} products in '{OUTPUT_EXCEL}'")


if __name__ == "__main__":
    auto_link_images_v3()