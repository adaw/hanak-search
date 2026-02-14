#!/usr/bin/env python3
"""
Hanak Image Describer — uses Qwen2.5VL on Mac Studio (Ollama) to describe product images.
Focuses on PRIMARY objects (furniture, kitchen, etc.), not small details.

Usage:
    python3 describe-images.py [--limit N] [--output image-descriptions.json]
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://mac.local:11434")
MODEL = "qwen2.5vl:7b"
SITE_DIR = Path(__file__).parent / "site" / "www.hanak-nabytek.cz"
OUTPUT_FILE = Path(__file__).parent / "image-descriptions.json"

# Skip patterns — logos, icons, favicons, tiny UI elements
SKIP_PATTERNS = [
    "/themes/", "/favicon", "/logo", "/icon", "/flags/",
    "/typo3temp/", "/typo3conf/", "/_processed_/",
    "placeholder", "loading", "arrow", "close", "menu",
    "facebook", "instagram", "youtube", "linkedin", "twitter",
    "cookie", "gdpr", "banner",
]

# Only process these extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Minimum file size (skip tiny images — icons, spacers)
MIN_SIZE_KB = 30

PROMPT = """Popis tento obrázek nábytku/interiéru v 1-2 větách česky.
Zaměř se POUZE na hlavní předměty — jaký nábytek je na obrázku (kuchyně, postel, židle, skříň, stůl, dveře atd.).
Ignoruj drobné detaily jako zásuvky, kliky, dekorace.
Uveď barvu/materiál hlavního nábytku pokud je zřejmý.
Odpověz POUZE popisem, žádné úvody."""


def should_process(path: Path) -> bool:
    """Check if image should be processed."""
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return False
    if path.stat().st_size < MIN_SIZE_KB * 1024:
        return False
    path_str = str(path).lower()
    for pattern in SKIP_PATTERNS:
        if pattern in path_str:
            return False
    return True


def describe_image(image_path: Path) -> str | None:
    """Send image to Qwen2.5VL via Ollama and get description."""
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL,
                "prompt": PROMPT,
                "images": [image_data],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 150,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"  ❌ Error: {e}", file=sys.stderr)
        return None


def get_relative_url(image_path: Path) -> str:
    """Convert local path to relative URL."""
    try:
        return "/" + str(image_path.relative_to(SITE_DIR))
    except ValueError:
        return str(image_path)


def main():
    parser = argparse.ArgumentParser(description="Describe Hanak product images with Qwen2.5VL")
    parser.add_argument("--limit", type=int, default=0, help="Max images to process (0=all)")
    parser.add_argument("--output", default=str(OUTPUT_FILE), help="Output JSON file")
    parser.add_argument("--resume", action="store_true", help="Skip already described images")
    args = parser.parse_args()

    # Load existing descriptions if resuming
    existing = {}
    if args.resume and os.path.exists(args.output):
        with open(args.output) as f:
            existing = json.load(f)
        print(f"📂 Loaded {len(existing)} existing descriptions")

    # Find all processable images
    all_images = sorted(SITE_DIR.rglob("*"))
    images = [p for p in all_images if p.is_file() and should_process(p)]
    print(f"📸 Found {len(images)} images to describe (from {len(all_images)} total files)")

    if args.limit > 0:
        images = images[:args.limit]
        print(f"   Limiting to {args.limit}")

    # Check Ollama connectivity
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if MODEL not in models and f"{MODEL}:latest" not in models:
            print(f"⚠️  Model {MODEL} not found. Available: {models}")
            sys.exit(1)
        print(f"✅ Ollama connected, model {MODEL} ready")
    except Exception as e:
        print(f"❌ Cannot reach Ollama at {OLLAMA_URL}: {e}")
        sys.exit(1)

    # Process images
    descriptions = dict(existing)
    processed = 0
    skipped = 0
    start_time = time.time()

    for i, img_path in enumerate(images):
        url = get_relative_url(img_path)

        if args.resume and url in existing:
            skipped += 1
            continue

        print(f"[{i+1}/{len(images)}] {url} ({img_path.stat().st_size // 1024}KB)...", end=" ", flush=True)

        desc = describe_image(img_path)
        if desc:
            descriptions[url] = {
                "description": desc,
                "file_size_kb": img_path.stat().st_size // 1024,
                "path": str(img_path.relative_to(SITE_DIR)),
            }
            processed += 1
            print(f"✅ {desc[:80]}")
        else:
            print("⏭️ skipped")

        # Save periodically (every 10 images)
        if processed > 0 and processed % 10 == 0:
            with open(args.output, "w") as f:
                json.dump(descriptions, f, ensure_ascii=False, indent=2)
            elapsed = time.time() - start_time
            rate = processed / elapsed * 60
            print(f"   💾 Saved ({processed} done, {rate:.1f}/min)")

    # Final save
    with open(args.output, "w") as f:
        json.dump(descriptions, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"\n✅ Done! {processed} described, {skipped} skipped, {elapsed:.0f}s total")
    print(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
