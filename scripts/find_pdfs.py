"""
Find PDF links in all HTML files and download them.
"""

import os
import re
import json
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
import urllib.request

SITE_DIR = os.path.expanduser("~/repos/hanak-search/site/www.hanak-nabytek.cz")
CATALOG_DIR = os.path.join(SITE_DIR, "catalogs")
BASE_DOMAIN = "www.hanak-nabytek.cz"


def find_pdf_links():
    """Scan all HTML files for PDF links."""
    pdf_urls = set()
    for html_file in Path(SITE_DIR).rglob("*.html"):
        try:
            with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower():
                    # Normalize URL
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = f"https://{BASE_DOMAIN}{href}"
                    elif not href.startswith("http"):
                        continue
                    pdf_urls.add(href)
        except Exception as e:
            print(f"  Error reading {html_file}: {e}")

    return sorted(pdf_urls)


def download_pdfs(urls):
    """Download PDFs to catalog dir."""
    os.makedirs(CATALOG_DIR, exist_ok=True)
    downloaded = []

    for url in urls:
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        out_path = os.path.join(CATALOG_DIR, filename)

        if os.path.exists(out_path):
            print(f"  ✅ Already exists: {filename}")
            downloaded.append({"url": url, "file": filename, "path": out_path})
            continue

        try:
            print(f"  ⬇️  Downloading: {filename}...")
            urllib.request.urlretrieve(url, out_path)
            downloaded.append({"url": url, "file": filename, "path": out_path})
            print(f"  ✅ {filename}")
        except Exception as e:
            print(f"  ❌ {filename}: {e}")

    return downloaded


def extract_pdf_text(pdf_path):
    """Extract text from PDF using pdftotext or Python fallback."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Fallback: try PyPDF2/pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except Exception:
        pass

    return ""


def main():
    print("=== Finding PDF links in HTML files ===")
    urls = find_pdf_links()
    print(f"Found {len(urls)} unique PDF URLs:")
    for u in urls:
        print(f"  {u}")

    if not urls:
        print("No PDFs found.")
        return

    print(f"\n=== Downloading PDFs ===")
    downloaded = download_pdfs(urls)

    print(f"\n=== Extracting text from PDFs ===")
    pdf_data = []
    for item in downloaded:
        text = extract_pdf_text(item["path"])
        if text:
            print(f"  ✅ {item['file']}: {len(text)} chars")
            pdf_data.append({
                "url": item["url"],
                "file": item["file"],
                "text": text[:5000],  # Limit for indexing
            })
        else:
            print(f"  ⚠️  {item['file']}: no text extracted")

    # Save for indexing
    out_path = os.path.join(os.path.expanduser("~/repos/hanak-search"), "pdf-catalog-text.json")
    with open(out_path, "w") as f:
        json.dump(pdf_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(pdf_data)} PDF texts to {out_path}")


if __name__ == "__main__":
    main()
