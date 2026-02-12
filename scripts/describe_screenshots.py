"""
Generate text descriptions for screenshots using vision model on Mac Studio.
Falls back to HTML-based descriptions if vision unavailable.
"""

import json
import os
import re
import base64
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

SCREENSHOTS_DIR = os.path.expanduser("~/repos/hanak-search/screenshots")
DESCRIPTIONS_DIR = os.path.expanduser("~/repos/hanak-search/descriptions")
SITE_DIR = os.path.expanduser("~/repos/hanak-search/site/www.hanak-nabytek.cz")
MANIFEST_PATH = os.path.join(SCREENSHOTS_DIR, "manifest.json")

# LM Studio on Mac Studio for vision (or fallback to HTML analysis)
LM_STUDIO_URL = "http://100.124.94.31:1234/v1/chat/completions"


def describe_from_html(url_path):
    """Generate description from HTML content analysis."""
    # Convert URL path to file path
    rel_path = url_path.lstrip("/")
    if not rel_path or rel_path == "/":
        rel_path = "index.html"
    elif not rel_path.endswith(".html"):
        rel_path = rel_path.rstrip("/") + "/index.html"

    filepath = os.path.join(SITE_DIR, rel_path)
    if not os.path.exists(filepath):
        # Try with .html
        filepath = os.path.join(SITE_DIR, rel_path.rstrip("/") + ".html")
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "lxml")
    except Exception:
        return None

    # Extract structural info
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:5]

    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        meta_desc = meta["content"]

    # Count images
    images = soup.find_all("img")
    img_count = len(images)

    # Find links/navigation
    nav_links = []
    for nav in soup.find_all(["nav", "ul"]):
        for a in nav.find_all("a", href=True)[:10]:
            text = a.get_text(strip=True)
            if text and len(text) < 50:
                nav_links.append(text)

    # Determine page type
    page_type = "obecná stránka"
    url_lower = url_path.lower()
    if url_lower in ("/", "/index.html"):
        page_type = "domovská stránka (homepage)"
    elif "/nabytek/kuchyne" in url_lower:
        page_type = "kategorie - kuchyně"
    elif "/nabytek/koupelny" in url_lower:
        page_type = "kategorie - koupelny"
    elif "/nabytek/" in url_lower and "/detail/" in url_lower:
        page_type = "detail produktu"
    elif "/nabytek/" in url_lower:
        page_type = "kategorie nábytku"
    elif "/realizace/detail/" in url_lower:
        page_type = "detail realizace"
    elif "/realizace" in url_lower:
        page_type = "přehled realizací"
    elif "/aktualne/detail/" in url_lower:
        page_type = "článek/aktualita"
    elif "/aktualne" in url_lower:
        page_type = "přehled aktualit"
    elif "/kontakt" in url_lower:
        page_type = "kontaktní stránka"
    elif "/katalogy" in url_lower:
        page_type = "katalogy ke stažení"
    elif "/proc-hanak" in url_lower:
        page_type = "o firmě / proč Hanák"
    elif "/studia" in url_lower:
        page_type = "studia / showroomy"
    elif "/kariera" in url_lower:
        page_type = "kariéra"

    # Build description
    parts = [f"Typ stránky: {page_type}"]
    if title:
        parts.append(f"Titulek: {title}")
    if meta_desc:
        parts.append(f"Popis: {meta_desc}")
    if h1s:
        parts.append(f"Hlavní nadpis: {', '.join(h1s[:3])}")
    if h2s:
        parts.append(f"Sekce: {', '.join(h2s)}")
    parts.append(f"Počet obrázků: {img_count}")
    if nav_links:
        parts.append(f"Navigace obsahuje: {', '.join(nav_links[:8])}")

    # Overall layout guess
    if img_count > 5:
        parts.append("Layout: galerie/grid s mnoha obrázky")
    elif img_count > 0:
        parts.append("Layout: textová stránka s obrázky")
    else:
        parts.append("Layout: převážně textová stránka")

    return "\n".join(parts)


def main():
    print("=== Generating page descriptions ===")

    if not os.path.exists(MANIFEST_PATH):
        print("No manifest.json found. Run take_screenshots.py first.")
        return

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    os.makedirs(DESCRIPTIONS_DIR, exist_ok=True)

    descriptions = {}
    for url_path, screenshot_file in manifest.items():
        desc = describe_from_html(url_path)
        if desc:
            # Save .txt file
            txt_name = screenshot_file.replace(".png", ".txt")
            txt_path = os.path.join(DESCRIPTIONS_DIR, txt_name)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(desc)
            descriptions[url_path] = {
                "screenshot": screenshot_file,
                "description_file": txt_name,
                "description": desc,
            }
            print(f"  ✅ {url_path}")
        else:
            print(f"  ⚠️  {url_path}: no description generated")

    # Save summary
    summary_path = os.path.join(DESCRIPTIONS_DIR, "descriptions.json")
    with open(summary_path, "w") as f:
        json.dump(descriptions, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Generated {len(descriptions)} descriptions")


if __name__ == "__main__":
    main()
