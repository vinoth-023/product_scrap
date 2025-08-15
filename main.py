import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import io
import os
import requests

# --- Streamlit Setup ---
st.set_page_config(page_title="Amazon Lentil Scraper", layout="wide")
st.title("🛒 Amazon Lentil Product Scraper")
st.markdown("**Paste Amazon URL** or **Upload HTML file** to extract product data.")

url = st.text_input("🔗 Paste Amazon Search URL")
uploaded_file = st.file_uploader("📂 OR Upload saved Amazon HTML file", type=["html"])

# --- Helper: Extract Pack Size ---
def extract_pack_size(text):
    match = re.search(r'(\d+\.?\d*\s?(g|kg|ml|l|L|GM|KG|G))', text, re.IGNORECASE)
    return match.group(1) if match else "N/A"

# --- Helper: Extract Brand Name ---
def extract_brand_name(item, title_text):
    brand_tag = item.select_one("h5.s-line-clamp-1")
    if brand_tag and brand_tag.text.strip():
        return brand_tag.text.strip()

    common_keywords = ["dal", "masoor", "toor", "moong", "urad", "chana", "lentil", "split"]
    words = title_text.split()
    for i, word in enumerate(words):
        if word.lower() in common_keywords:
            return " ".join(words[:i]) if i > 0 else "N/A"
    return words[0] if words else "N/A"

# --- Scraper from HTML content ---
def scrape_html_content(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for item in soup.select('div[data-component-type="s-search-result"]'):
        title = item.select_one("h2 span")
        price_whole = item.select_one(".a-price-whole")
        price_fraction = item.select_one(".a-price-fraction")
        image = item.select_one("img.s-image")

        title_text = title.get_text(strip=True) if title else "N/A"
        brand = extract_brand_name(item, title_text)

        if "Amazon Brand - " in title_text:
            title_text = title_text.replace("Amazon Brand - ", "").strip()
        if "Amazon Brand - " in brand:
            brand = brand.replace("Amazon Brand - ", "").strip()

        pack_size = extract_pack_size(title_text)

        price = (
            f"₹{price_whole.text.strip()}.{price_fraction.text.strip()}"
            if price_whole and price_fraction else (
                f"₹{price_whole.text.strip()}" if price_whole else "N/A"
            )
        )

        img_url = image["src"] if image else "N/A"

        products.append({
            "Product Name": title_text,
            "Brand Name": brand,
            "Pack Size": pack_size,
            "Price": price,
            "Image URL": img_url
        })

    return pd.DataFrame(products)

# --- Scrape Live Pages via Selenium ---
def scrape_amazon_live(base_url, max_pages=5):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)

    all_products = []

    for page in range(1, max_pages + 1):
        if "&page=" in base_url:
            paged_url = re.sub(r"&page=\d+", f"&page={page}", base_url)
        else:
            paged_url = f"{base_url}&page={page}"

        st.info(f"📄 Scraping page {page}...")
        driver.get(paged_url)
        time.sleep(5)
        html = driver.page_source
        page_df = scrape_html_content(html)

        if not page_df.empty:
            all_products.extend(page_df.to_dict(orient="records"))
        else:
            st.warning(f"⚠️ No products found on page {page}, stopping.")
            break

    driver.quit()
    return pd.DataFrame(all_products)

# --- Clean filename ---
def clean_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name)  # Remove illegal chars
    name = re.sub(r"\s+", "_", name)  # Replace spaces with _
    return name.strip()[:80]

# --- Scrape Button ---
if st.button("🔍 Scrape Now"):
    df = None
    try:
        if url and "amazon" in url:
            st.info("⏳ Scraping up to 5 pages from live Amazon site...")
            df = scrape_amazon_live(url, max_pages=5)
            st.success(f"✅ Scraped {len(df)} products from live URL.")
        elif uploaded_file:
            html = uploaded_file.read().decode("utf-8")
            df = scrape_html_content(html)
            st.success(f"✅ Scraped {len(df)} products from uploaded file.")
        else:
            st.warning("⚠️ Please enter a URL or upload a file.")

        if df is not None and not df.empty:
            st.dataframe(df)

            # --- Excel Download ---
            towrite = io.BytesIO()
            df.to_excel(towrite, index=False, engine='openpyxl')
            towrite.seek(0)
            st.download_button(
                "📥 Download as Excel",
                data=towrite,
                file_name="amazon_lentils.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # --- Image Download ---
            if st.button("📸 Download All Images"):
                try:
                    folder_path = "product_images"
                    os.makedirs(folder_path, exist_ok=True)

                    for _, row in df.iterrows():
                        img_url = row["Image URL"]
                        if img_url == "N/A":
                            continue
                        product_name = clean_filename(row["Product Name"])
                        img_path = os.path.join(folder_path, f"{product_name}.jpg")

                        try:
                            response = requests.get(img_url, timeout=10)
                            if response.status_code == 200:
                                with open(img_path, "wb") as f:
                                    f.write(response.content)
                        except Exception:
                            st.warning(f"⚠️ Failed to download image for: {row['Product Name']}")

                    st.success(f"✅ Downloaded all images to: `{folder_path}`")
                except Exception as e:
                    st.error(f"❌ Error downloading images: {e}")

        else:
            st.warning("No products found.")
    except Exception as e:
        st.error(f"❌ Error occurred: {e}")
