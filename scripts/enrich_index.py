"""
Enrich ChromaDB index with visual descriptions and PDF catalog text.
Adds new documents to existing collection without deleting.
"""

import os
import sys
import json
import hashlib
import chromadb
from sentence_transformers import SentenceTransformer

CHROMADB_PATH = os.environ.get("CHROMADB_PATH", os.path.expanduser("~/repos/hanak-search/chromadb_data"))
DESCRIPTIONS_PATH = os.path.expanduser("~/repos/hanak-search/descriptions/descriptions.json")
PDF_TEXT_PATH = os.path.expanduser("~/repos/hanak-search/pdf-catalog-text.json")
BATCH_SIZE = 50


def main():
    print("=== Enriching ChromaDB index ===")

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_collection("hanak_pages")
    print(f"Current collection size: {collection.count()}")

    all_docs = []
    all_ids = []
    all_metas = []

    # Add visual descriptions
    if os.path.exists(DESCRIPTIONS_PATH):
        with open(DESCRIPTIONS_PATH) as f:
            descriptions = json.load(f)
        print(f"Adding {len(descriptions)} visual descriptions...")
        for url, info in descriptions.items():
            doc_id = hashlib.md5(f"visual_{url}".encode()).hexdigest()
            desc = info["description"]
            all_docs.append(desc)
            all_ids.append(doc_id)
            all_metas.append({
                "title": f"Vizuální popis: {url}",
                "url": url,
                "category": "Vizuální popis",
                "chunk_index": 0,
                "meta_desc": desc[:500],
                "og_image": "",
            })

    # Add PDF catalog text
    if os.path.exists(PDF_TEXT_PATH):
        with open(PDF_TEXT_PATH) as f:
            pdfs = json.load(f)
        print(f"Adding {len(pdfs)} PDF catalog texts...")
        for pdf in pdfs:
            # Chunk PDF text
            text = pdf["text"]
            chunks = []
            if len(text) > 600:
                for i in range(0, len(text), 500):
                    chunk = text[i:i+500].strip()
                    if chunk:
                        chunks.append(chunk)
            else:
                chunks = [text]

            for ci, chunk in enumerate(chunks):
                doc_id = hashlib.md5(f"pdf_{pdf['file']}_{ci}".encode()).hexdigest()
                all_docs.append(chunk)
                all_ids.append(doc_id)
                all_metas.append({
                    "title": f"Katalog: {pdf['file']}",
                    "url": pdf.get("url", f"/catalogs/{pdf['file']}"),
                    "category": "PDF Katalog",
                    "chunk_index": ci,
                    "meta_desc": chunk[:500],
                    "og_image": "",
                })

    if not all_docs:
        print("Nothing to add.")
        return

    print(f"Embedding {len(all_docs)} new chunks...")
    for i in range(0, len(all_docs), BATCH_SIZE):
        batch_docs = all_docs[i:i+BATCH_SIZE]
        batch_ids = all_ids[i:i+BATCH_SIZE]
        batch_metas = all_metas[i:i+BATCH_SIZE]
        embeddings = model.encode(batch_docs).tolist()
        collection.upsert(
            documents=batch_docs,
            embeddings=embeddings,
            metadatas=batch_metas,
            ids=batch_ids,
        )
        print(f"  Upserted {min(i+BATCH_SIZE, len(all_docs))}/{len(all_docs)}")

    print(f"\n✅ Done! Collection now has {collection.count()} documents")


if __name__ == "__main__":
    main()
