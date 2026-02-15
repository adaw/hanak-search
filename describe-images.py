#!/usr/bin/env python3 -u
"""Batch describe images using Ollama vision model."""
import json, base64, os, sys, time, subprocess, urllib.request, io
from PIL import Image

OLLAMA_URL = "http://100.124.94.31:11434/api/chat"
MODEL = "qwen2.5vl:7b"
PROMPT = "Popiš tento obrázek nábytku/interiéru česky. Zaměř se na: typ nábytku, materiály, barvy, styl designu, prostor (kuchyně/ložnice/obývák). Max 2-3 věty."
SITE_DIR = "site/www.hanak-nabytek.cz"
DESC_FILE = "image-descriptions.json"
BATCH_SIZE = 50
LOG_FILE = "/Users/lex/.openclaw/workspace/memory/2026-02-15.md"
RESIZE_PX = 512

def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def find_missing_images():
    with open(DESC_FILE) as f:
        existing = json.load(f)
    existing_keys = set(existing.keys())
    
    result = subprocess.run(
        ["find", SITE_DIR, "-type", "f", "(", "-name", "*.jpg", "-o", "-name", "*.jpeg", 
         "-o", "-name", "*.png", "-o", "-name", "*.webp", ")", "-size", "+20k"],
        capture_output=True, text=True
    )
    all_files = [l for l in result.stdout.strip().split("\n") if l]
    
    missing = []
    for fp in all_files:
        key = fp.replace("site/www.hanak-nabytek.cz", "")
        if key not in existing_keys:
            missing.append((fp, key))
    
    return missing, existing

def describe_image(filepath):
    img = Image.open(filepath)
    img.thumbnail((RESIZE_PX, RESIZE_PX))
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode()
    
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
        "stream": False,
        "options": {"num_predict": 200}
    })
    
    req = urllib.request.Request(OLLAMA_URL, data=payload.encode(), 
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data["message"]["content"]

def main():
    missing, existing = find_missing_images()
    total = len(missing)
    log(f"\n## Image descriptions batch - {time.strftime('%H:%M')}")
    log(f"- Missing: {total}, Existing: {len(existing)}")
    
    if total == 0:
        log("Nothing to do!")
        return
    
    done = 0
    errors = 0
    start = time.time()
    
    for i, (filepath, key) in enumerate(missing):
        t0 = time.time()
        try:
            desc = describe_image(filepath)
            existing[key] = desc
            done += 1
        except Exception as e:
            errors += 1
            dt = time.time() - t0
            log(f"  ❌ ({dt:.1f}s) {key[-60:]}: {e}")
        
        if (i + 1) % BATCH_SIZE == 0 or i == total - 1:
            with open(DESC_FILE, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            elapsed = time.time() - start
            rate = (done + errors) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate / 60 if rate > 0 else 0
            log(f"  ✅ {i+1}/{total}. +{done} ok, {errors} err. {rate:.1f} img/s, ETA: {eta:.0f}min")
    
    elapsed = time.time() - start
    log(f"- **Done!** +{done}, {errors} errors. Total: {len(existing)}. Time: {elapsed/60:.0f}min")

if __name__ == "__main__":
    main()
