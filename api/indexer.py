"""
Hanak Indexer — Parse scraped HTML pages and index into ChromaDB.
Run: python3 indexer.py /path/to/site/www.hanak-nabytek.cz
"""

import os
import sys
import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup
import chromadb
from sentence_transformers import SentenceTransformer

CHROMADB_PATH = os.environ.get("CHROMADB_PATH", "./chromadb_data")
SITE_DIR = sys.argv[1] if len(sys.argv) > 1 else "../site/www.hanak-nabytek.cz"
BATCH_SIZE = 50


def extract_text_from_html(filepath: str) -> dict | None:
    """Parse HTML file and extract meaningful text content."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "lxml")
    except Exception as e:
        print(f"  ⚠️ Error reading {filepath}: {e}")
        return None

    # Filter: only Czech pages
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "") if html_tag else ""
    if lang and not lang.startswith("cs"):
        return None

    # Remove script/style/nav/footer
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # Meta description
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        meta_desc = meta["content"].strip()

    # OG image for thumbnails
    og_image = ""
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        og_image = og["content"].strip()

    # First big image as fallback thumbnail
    first_image = ""
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        # Skip tiny icons, logos, spacers
        if any(skip in src.lower() for skip in ["icon", "logo", "spacer", "pixel", "blank", ".svg", "data:image"]):
            continue
        # Prefer fileadmin images (product photos)
        if "fileadmin" in src or src.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            # Normalize relative paths to absolute
            if src.startswith("../") or src.startswith("./"):
                # Resolve relative to the HTML file's directory
                file_dir = os.path.dirname(os.path.relpath(filepath, SITE_DIR))
                resolved = os.path.normpath(os.path.join(file_dir, src))
                first_image = "/" + resolved.replace("\\", "/")
            elif not src.startswith("/") and not src.startswith("http"):
                first_image = "/" + src
            else:
                first_image = src
            break

    # Main content text
    main = soup.find("main") or soup.find("article") or soup.find("div", {"class": re.compile(r"content|main|body", re.I)})
    if main:
        text = main.get_text(separator=" ", strip=True)
    else:
        text = soup.get_text(separator=" ", strip=True)

    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) < 50:
        return None

    # Determine category from URL path
    rel_path = os.path.relpath(filepath, SITE_DIR)
    url = "/" + rel_path.replace("index.html", "").rstrip("/")
    if url == "/":
        url = "/"
    
    category = ""
    parts = rel_path.split("/")
    if len(parts) > 1:
        category = parts[0].replace("-", " ").title()

    # Create chunks for long pages (max ~500 chars per chunk)
    chunks = []
    if len(text) > 600:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > 500 and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    else:
        chunks = [text]

    return {
        "title": title or os.path.basename(filepath),
        "url": url,
        "meta_desc": meta_desc,
        "og_image": og_image,
        "first_image": first_image,
        "text": text,
        "chunks": chunks,
        "category": category,
    }


def main():
    print(f"=== Hanak Indexer ===")
    print(f"Site: {SITE_DIR}")
    print(f"ChromaDB: {CHROMADB_PATH}")

    # Find all HTML files
    html_files = list(Path(SITE_DIR).rglob("*.html"))
    print(f"Found {len(html_files)} HTML files")

    # Parse all pages
    pages = []
    for f in html_files:
        result = extract_text_from_html(str(f))
        if result:
            pages.append(result)

    print(f"Parsed {len(pages)} pages with content")

    if not pages:
        print("No pages to index!")
        return

    # Load model
    print("Loading embedding model...")
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # Setup ChromaDB
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    
    # Delete existing collection if exists
    try:
        client.delete_collection("hanak_pages")
    except Exception:
        pass
    
    collection = client.create_collection(
        "hanak_pages",
        metadata={"hnsw:space": "cosine"}
    )

    # Load image descriptions if available
    image_desc_path = None
    for candidate in [
        os.path.join(os.path.dirname(SITE_DIR), "image-descriptions-quality.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "image-descriptions-quality.json"),
        "/app/image-descriptions-quality.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "image-descriptions-quality.json"),
        os.path.join(os.path.dirname(SITE_DIR), "image-descriptions.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "image-descriptions.json"),
        "/app/image-descriptions.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "image-descriptions.json"),
    ]:
        if os.path.exists(candidate):
            image_desc_path = candidate
            break
    image_descs = []
    if image_desc_path and os.path.exists(image_desc_path):
        import json
        with open(image_desc_path) as f:
            raw = json.load(f)
        # Support both dict-keyed-by-path and list-of-dicts formats
        if isinstance(raw, dict):
            image_descs = []
            for img_path, info in raw.items():
                filename = os.path.basename(img_path)
                if isinstance(info, str):
                    desc = info
                    path = img_path
                elif isinstance(info, dict):
                    desc = info.get("description", "")
                    path = info.get("path", img_path)
                else:
                    continue
                image_descs.append({
                    "filename": filename,
                    "description": desc,
                    "path": path,
                })
        else:
            image_descs = raw
        print(f"Loaded {len(image_descs)} image descriptions")

    # Index all chunks
    total_chunks = 0
    all_docs = []
    all_ids = []
    all_metas = []

    # Add image descriptions as searchable chunks
    for img in image_descs:
        filename = img.get("filename", "unknown")
        img_path = img.get("path", filename)
        doc_id = hashlib.md5(f"img_{img_path}".encode()).hexdigest()
        category = "Obrázek"
        url = img.get("path", f"/fileadmin/user_upload/{filename}")
        if not url.startswith("/"):
            url = "/" + url
        title = f"Obrázek: {filename.replace('.jpg','').replace('.png','').replace('-',' ').replace('_',' ')}"
        desc = img.get("description", "")
        if not desc:
            continue
        
        all_docs.append(desc)
        all_ids.append(doc_id)
        all_metas.append({
            "title": title,
            "url": url,
            "category": category,
            "chunk_index": 0,
            "meta_desc": desc[:500],
            "og_image": url,
            "source_type": "image",
        })
        total_chunks += 1

    for page in pages:
        for i, chunk in enumerate(page["chunks"]):
            doc_id = hashlib.md5(f"{page['url']}_{i}".encode()).hexdigest()
            all_docs.append(chunk)
            all_ids.append(doc_id)
            all_metas.append({
                "title": page["title"],
                "url": page["url"],
                "category": page["category"],
                "chunk_index": i,
                "meta_desc": page["meta_desc"][:500] if page["meta_desc"] else "",
                "og_image": page.get("og_image", ""),
                "first_image": page.get("first_image", ""),
            })
            total_chunks += 1

    # Deduplicate by ID
    seen_ids = set()
    deduped = []
    for idx in range(len(all_ids)):
        if all_ids[idx] not in seen_ids:
            seen_ids.add(all_ids[idx])
            deduped.append(idx)
    if len(deduped) < len(all_ids):
        print(f"Removed {len(all_ids) - len(deduped)} duplicate IDs")
        all_docs = [all_docs[i] for i in deduped]
        all_ids = [all_ids[i] for i in deduped]
        all_metas = [all_metas[i] for i in deduped]
        total_chunks = len(all_ids)

    print(f"Embedding {total_chunks} chunks...")

    # Batch embed and insert
    for i in range(0, len(all_docs), BATCH_SIZE):
        batch_docs = all_docs[i:i+BATCH_SIZE]
        batch_ids = all_ids[i:i+BATCH_SIZE]
        batch_metas = all_metas[i:i+BATCH_SIZE]

        embeddings = model.encode(batch_docs).tolist()

        collection.add(
            documents=batch_docs,
            embeddings=embeddings,
            metadatas=batch_metas,
            ids=batch_ids,
        )
        
        progress = min(i + BATCH_SIZE, len(all_docs))
        print(f"  Indexed {progress}/{total_chunks} chunks")

    print(f"\n✅ Done! {total_chunks} chunks indexed from {len(pages)} pages")
    print(f"   ChromaDB: {CHROMADB_PATH}")


if __name__ == "__main__":
    main()
