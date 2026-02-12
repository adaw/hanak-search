"""
Take screenshots of important Hanak pages served locally via nginx.
Uses Playwright headless Chromium.
"""

import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8090"
SITE_DIR = os.path.expanduser("~/repos/hanak-search/site/www.hanak-nabytek.cz")
OUT_DIR = os.path.expanduser("~/repos/hanak-search/screenshots")

# Select important pages (skip oblibene/pridat, pagination, foreign langs, query strings)
def get_important_pages():
    pages = []
    for html_file in sorted(Path(SITE_DIR).rglob("*.html")):
        rel = str(html_file.relative_to(SITE_DIR))
        # Skip foreign languages, oblibene/pridat, query strings
        if any(f"/{lang}/" in f"/{rel}" for lang in ("de", "en", "fr", "ru", "sk")):
            continue
        if "oblibene/pridat" in rel:
            continue
        if "?" in rel:
            continue
        if "strana-" in rel:
            continue
        pages.append(rel)
    return pages


def url_to_filename(rel_path):
    """Convert relative path to a safe filename."""
    name = rel_path.replace("/", "__").replace(".html", "")
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return name + ".png"


def main():
    pages = get_important_pages()
    print(f"Found {len(pages)} pages to screenshot")

    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
        )
        page = context.new_page()

        for i, rel_path in enumerate(pages):
            url = f"{BASE_URL}/{rel_path}"
            filename = url_to_filename(rel_path)
            out_path = os.path.join(OUT_DIR, filename)

            try:
                page.goto(url, wait_until="load", timeout=10000)
                page.screenshot(path=out_path, full_page=False)
                web_url = "/" + rel_path.replace("index.html", "").rstrip("/")
                if web_url == "/":
                    web_url = "/"
                manifest[web_url] = filename
                print(f"  [{i+1}/{len(pages)}] ✅ {rel_path}")
            except Exception as e:
                print(f"  [{i+1}/{len(pages)}] ❌ {rel_path}: {e}")

        browser.close()

    # Save manifest
    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Done! {len(manifest)} screenshots saved to {OUT_DIR}")
    print(f"   Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
