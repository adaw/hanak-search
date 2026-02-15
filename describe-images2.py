#!/usr/bin/env python3
"""Batch describe images using Ollama vision model via curl."""
import json, base64, io, time, subprocess, sys, os
from PIL import Image

OLLAMA_URL = "http://100.124.94.31:11434/api/chat"
PROMPT = "Popiš tento obrázek nábytku/interiéru česky. Zaměř se na: typ nábytku, materiály, barvy, styl designu, prostor (kuchyně/ložnice/obývák). Max 2-3 věty."
SITE_DIR = "site/www.hanak-nabytek.cz"
DESC_FILE = "image-descriptions.json"

with open(DESC_FILE) as f:
    existing = json.load(f)
existing_keys = set(existing.keys())

result = subprocess.run(
    ["find", SITE_DIR, "-type", "f", "(", "-name", "*.jpg", "-o", "-name", "*.jpeg",
     "-o", "-name", "*.png", "-o", "-name", "*.webp", ")", "-size", "+20k"],
    capture_output=True, text=True
)
all_files = [l for l in result.stdout.strip().split("\n") if l]
missing = [(fp, fp.replace("site/www.hanak-nabytek.cz", "")) for fp in all_files if fp.replace("site/www.hanak-nabytek.cz", "") not in existing_keys]

total = len(missing)
print(f"Missing: {total}", flush=True)

done = 0
errors = 0
start = time.time()

for i, (fp, key) in enumerate(missing):
    try:
        img = Image.open(fp)
        img.thumbnail((512, 512))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = json.dumps({
            "model": "qwen2.5vl:7b",
            "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
            "stream": False,
            "options": {"num_predict": 150}
        })

        # Use curl with hard timeout
        r = subprocess.run(
            ["curl", "-s", "-m", "30", "-X", "POST", OLLAMA_URL,
             "-H", "Content-Type: application/json", "-d", "@-"],
            input=payload.encode(), capture_output=True, timeout=35
        )
        if r.returncode != 0:
            errors += 1
            continue

        data = json.loads(r.stdout)
        existing[key] = data["message"]["content"]
        done += 1
    except subprocess.TimeoutExpired:
        errors += 1
        print(f"TIMEOUT: {key[-50:]}", flush=True)
    except Exception as e:
        errors += 1
        print(f"ERR: {key[-50:]}: {e}", flush=True)

    if (i + 1) % 50 == 0 or i == total - 1:
        with open(DESC_FILE, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        elapsed = time.time() - start
        rate = (done + errors) / elapsed
        eta = (total - i - 1) / rate / 60 if rate > 0 else 0
        print(f"{i+1}/{total}: +{done} ok, {errors} err, {rate:.1f}/s, ETA:{eta:.0f}m", flush=True)

elapsed = time.time() - start
print(f"DONE: +{done}, {errors} err, {elapsed/60:.0f}min. Total: {len(existing)}", flush=True)
