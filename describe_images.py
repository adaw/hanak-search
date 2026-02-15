#!/usr/bin/env python3
"""Describe images for hanak-nabytek.cz using Ollama vision model."""
import json, os, base64, glob, time, sys, subprocess, tempfile

REPO = "/Users/lex/repos/hanak-search"
JSON_FILE = os.path.join(REPO, "image-descriptions.json")
SITE_DIR = os.path.join(REPO, "site/www.hanak-nabytek.cz")
OLLAMA_URL = "http://100.124.94.31:11434/api/chat"
MODEL = "qwen2.5vl:7b"
PROMPT = "Popiš tento obrázek nábytku/interiéru česky. Zaměř se na: typ nábytku, materiály, barvy, styl designu, prostor. Max 2-3 věty."
BATCH_SIZE = 10
MAX_FILE_SIZE = 5 * 1024 * 1024
MIN_FILE_SIZE = 20 * 1024

with open(JSON_FILE) as f:
    descriptions = json.load(f)
print(f"Existing: {len(descriptions)}", flush=True)

extensions = ("*.jpg", "*.jpeg", "*.png", "*.webp")
all_images = []
for ext in extensions:
    all_images.extend(glob.glob(os.path.join(SITE_DIR, "**", ext), recursive=True))

todo = []
for img in sorted(all_images):
    rel_full = os.path.relpath(img, REPO)
    idx = rel_full.find("/fileadmin/")
    if idx == -1:
        continue
    rel = rel_full[idx:]
    size = os.path.getsize(img)
    if size < MIN_FILE_SIZE or size > MAX_FILE_SIZE:
        continue
    if rel not in descriptions:
        todo.append((img, rel, size))

print(f"Todo: {len(todo)}", flush=True)

count = 0
errors = 0
start = time.time()

def describe_image(img_path):
    """Call Ollama via curl to avoid Python requests hanging."""
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
        "stream": False,
        "keep_alive": "2h",
        "options": {"num_ctx": 8192}
    })
    
    # Write payload to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "120", "-X", "POST", OLLAMA_URL,
             "-H", "Content-Type: application/json", "-d", f"@{tmp_path}"],
            capture_output=True, text=True, timeout=130
        )
        resp = json.loads(result.stdout)
        return resp["message"]["content"].strip()
    finally:
        os.unlink(tmp_path)

for img_path, rel_path, fsize in todo:
    t0 = time.time()
    try:
        desc = describe_image(img_path)
        descriptions[rel_path] = desc
        count += 1
        
        dt = time.time() - t0
        elapsed = time.time() - start
        eta_min = (len(todo) - count) * (elapsed / count) / 60
        print(f"[{count}/{len(todo)}] {dt:.0f}s {fsize//1024}KB eta:{eta_min:.0f}m | {os.path.basename(rel_path)}", flush=True)
        
        if count % BATCH_SIZE == 0:
            with open(JSON_FILE, "w") as f:
                json.dump(descriptions, f, ensure_ascii=False, indent=2)
            print(f"  >> SAVED ({len(descriptions)} total)", flush=True)
    
    except KeyboardInterrupt:
        print("Interrupted!", flush=True)
        break
    except Exception as e:
        errors += 1
        dt = time.time() - t0
        print(f"  ERR [{errors}] {dt:.0f}s {os.path.basename(rel_path)}: {e}", flush=True)
        if errors > 50:
            print("Too many errors, stopping.", flush=True)
            break
        continue

with open(JSON_FILE, "w") as f:
    json.dump(descriptions, f, ensure_ascii=False, indent=2)

elapsed = time.time() - start
print(f"\nDone: {count} ok, {errors} err, {elapsed:.0f}s", flush=True)
print(f"Total: {len(descriptions)}", flush=True)
