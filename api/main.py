"""
Hanak Search API — Vector search for hanak-nabytek.cz
FastAPI + ChromaDB + sentence-transformers
"""

import os
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

import unicodedata
import re

def _strip_diacritics(text: str) -> str:
    """Remove diacritics for fuzzy Czech matching (kuchyne → kuchyne, kuchyně → kuchyne)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))

# Czech diacritics restoration — common words without diacritics mapped to correct form
_CZECH_DIACRITICS_MAP = {
    "zidle": "židle", "zidli": "židli", "zidlicka": "židlička",
    "kuchyne": "kuchyně", "kuchyni": "kuchyni", "kuchynsky": "kuchyňský",
    "dvere": "dveře", "dveri": "dveří",
    "loznice": "ložnice", "loznici": "ložnici",
    "skrin": "skříň", "skrine": "skříně", "skrini": "skříní", "skrinek": "skříněk",
    "nabytek": "nábytek", "nabytku": "nábytku",
    "postel": "postel", "postele": "postele",
    "stul": "stůl", "stolu": "stolu", "stolni": "stolní",
    "police": "police", "policky": "poličky",
    "satna": "šatna", "satni": "šatní", "satny": "šatny",
    "obyvaci": "obývací", "obyvak": "obývák",
    "jidelni": "jídelní", "jidelna": "jídelna",
    "ulozny": "úložný", "ulozne": "úložné",
    "osvetlen": "osvětlení", "osvetleni": "osvětlení",
    "pracovni": "pracovní", "kancelar": "kancelář", "kancelari": "kanceláři",
    "realizace": "realizace", "interier": "interiér", "interiery": "interiéry",
    "luxusni": "luxusní", "moderni": "moderní", "designovy": "designový",
    "vestav": "vestavěný", "vestaveny": "vestavěný", "vestavene": "vestavěné",
    "predsin": "předsíň", "predsine": "předsíně", "predsini": "předsíní",
    "koupelna": "koupelna", "koupelny": "koupelny",
    "barovy": "barový", "barova": "barová",
    "dreveny": "dřevěný", "drevene": "dřevěné", "drevo": "dřevo",
    "zelezny": "železný",
    "sedy": "šedý", "sede": "šedé", "seda": "šedá",
    "bily": "bílý", "bile": "bílé", "bila": "bílá",
    "cerny": "černý", "cerne": "černé", "cerna": "černá",
}

def _restore_diacritics(query: str) -> str:
    """Try to restore Czech diacritics in a query without them.
    Returns the original query if it already has diacritics or no match found."""
    words = query.lower().split()
    restored = []
    changed = False
    for w in words:
        if w in _CZECH_DIACRITICS_MAP:
            restored.append(_CZECH_DIACRITICS_MAP[w])
            changed = True
        else:
            restored.append(w)
    return ' '.join(restored) if changed else query

def _normalize_query(query: str) -> tuple[str, str]:
    """Returns (primary_query, fallback_query_or_None).
    If query has no diacritics and we can restore them, primary=restored, fallback=original.
    Otherwise primary=original, fallback=None."""
    stripped = _strip_diacritics(query)
    if stripped.lower() == query.lower():
        # No diacritics in input — try to restore
        restored = _restore_diacritics(query)
        if restored != query:
            return restored, query
    return query, None

app = FastAPI(title="Hanak Search API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Global state
model = None
collection = None

CHROMADB_PATH = os.environ.get("CHROMADB_PATH", "./chromadb_data")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float
    category: str = ""
    image: str = ""


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    time_ms: float


@app.on_event("startup")
async def startup():
    global model, collection
    print("Loading embedding model...")
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    try:
        collection = client.get_collection("hanak_pages")
        print(f"Collection loaded: {collection.count()} documents")
    except Exception:
        collection = client.get_or_create_collection(
            "hanak_pages",
            metadata={"hnsw:space": "cosine"}
        )
        print("Empty collection created — run indexer first")


@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    types: str = Query("text,image,document", description="Comma-separated content types to include"),
):
    """Vector similarity search with instant results."""
    start = time.perf_counter()

    if collection.count() == 0:
        return SearchResponse(query=q, results=[], total=0, time_ms=0)

    # Normalize query — restore diacritics if missing
    primary_q, fallback_q = _normalize_query(q)

    # Embed primary query (with restored diacritics)
    query_embedding = model.encode(primary_q).tolist()

    # Search ChromaDB
    fetch_n = limit * 2 if fallback_q else limit
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=fetch_n,
        include=["documents", "metadatas", "distances"],
    )

    # If we have a fallback (original without diacritics), merge results
    if fallback_q:
        fallback_embedding = model.encode(fallback_q).tolist()
        fallback_results = collection.query(
            query_embeddings=[fallback_embedding],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )
        # Merge: add fallback results not already in primary
        seen_ids = set(results["ids"][0]) if results["ids"] else set()
        for j in range(len(fallback_results["ids"][0])):
            rid = fallback_results["ids"][0][j]
            if rid not in seen_ids:
                results["ids"][0].append(rid)
                results["documents"][0].append(fallback_results["documents"][0][j])
                results["metadatas"][0].append(fallback_results["metadatas"][0][j])
                results["distances"][0].append(fallback_results["distances"][0][j])
                seen_ids.add(rid)

    # Parse requested types
    requested_types = set(t.strip() for t in types.split(",") if t.strip())

    # Format results
    search_results = []
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        score = 1 - dist  # cosine distance → similarity
        if score < 0.15:  # threshold
            continue

        # Determine content type for filtering
        source_type = meta.get("source_type", "html")
        cat = meta.get("category", "")
        if cat == "Obrázek":
            content_type = "image"
        elif source_type == "pdf":
            content_type = "document"
        else:
            content_type = "text"

        if content_type not in requested_types:
            continue

        title = meta.get("title", "Bez názvu")
        url = meta.get("url", "#")
        # Boosting (same logic as suggest)
        q_lower = q.lower()
        q_norm = _strip_diacritics(q_lower)
        title_norm = _strip_diacritics(title.lower())
        boost = 0.0
        if q_norm in title_norm:
            boost += 0.3
        if q_lower in title.lower():
            boost += 0.1
        if title_norm.startswith(q_norm):
            boost += 0.2
        url_slug = _strip_diacritics(url.lower().rsplit('/', 1)[-1].replace('.html', ''))
        if q_norm == url_slug:
            boost += 0.35
        url_depth = url.strip('/').count('/')
        if url_depth <= 1 and q_norm in title_norm:
            boost += 0.15
        # Get best thumbnail: og_image > first_image > image description path
        image_url = meta.get("og_image", "")
        if not image_url:
            image_url = meta.get("first_image", "")
        if not image_url and cat == "Obrázek":
            image_url = url  # For image results, the URL IS the image

        search_results.append(SearchResult(
            title=title,
            url=url,
            snippet=doc[:250] + "..." if len(doc) > 250 else doc,
            score=round(score + boost, 4),
            category=meta.get("category", ""),
            image=image_url,
        ))

    # Re-sort by boosted score
    search_results.sort(key=lambda x: x.score, reverse=True)
    search_results = search_results[:limit]

    elapsed = (time.perf_counter() - start) * 1000

    return SearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
        time_ms=round(elapsed, 1),
    )


@app.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=15),
    types: str = Query("text,image,document", description="Comma-separated content types to include"),
):
    """Fast typeahead suggestions — returns titles + URLs only."""
    start = time.perf_counter()

    if collection.count() == 0:
        return {"query": q, "suggestions": [], "time_ms": 0}

    # Normalize query — restore diacritics if missing
    primary_q, fallback_q = _normalize_query(q)

    query_embedding = model.encode(primary_q).tolist()
    fetch_n = min(limit * 4, 30)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=fetch_n,
        include=["metadatas", "distances"],
    )

    # Merge fallback results if available
    if fallback_q:
        fallback_embedding = model.encode(fallback_q).tolist()
        fb = collection.query(
            query_embeddings=[fallback_embedding],
            n_results=fetch_n,
            include=["metadatas", "distances"],
        )
        seen_ids = set(results["ids"][0]) if results["ids"] else set()
        for j in range(len(fb["ids"][0])):
            rid = fb["ids"][0][j]
            if rid not in seen_ids:
                results["ids"][0].append(rid)
                results["metadatas"][0].append(fb["metadatas"][0][j])
                results["distances"][0].append(fb["distances"][0][j])
                seen_ids.add(rid)

    requested_types = set(t.strip() for t in types.split(",") if t.strip())

    suggestions = []
    seen_titles = set()
    q_lower = primary_q.lower()
    q_norm = _strip_diacritics(q_lower)
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        score = 1 - dist
        if score < 0.2:
            continue

        # Filter by content type
        source_type = meta.get("source_type", "html")
        cat = meta.get("category", "")
        if cat == "Obrázek":
            content_type = "image"
        elif source_type == "pdf":
            content_type = "document"
        else:
            content_type = "text"
        if content_type not in requested_types:
            continue

        title = meta.get("title", "")
        url = meta.get("url", "#")
        if title and title not in seen_titles:
            seen_titles.add(title)
            title_lower = title.lower()
            title_norm = _strip_diacritics(title_lower)
            boost = 0.0
            # Exact diacritics-insensitive match in title
            if q_norm in title_norm:
                boost += 0.3
            if q_lower in title_lower:
                boost += 0.1  # extra for exact diacritics match
            if title_norm.startswith(q_norm):
                boost += 0.2
            # URL slug match (e.g. "kuchyne" → /nabytek/kuchyne.html)
            url_slug = _strip_diacritics(url.lower().rsplit('/', 1)[-1].replace('.html', ''))
            if q_norm == url_slug:
                boost += 0.35  # strong boost for exact slug match
            # Primary category page boost (short URL = main page)
            url_depth = url.strip('/').count('/')
            if url_depth <= 1 and q_norm in title_norm:
                boost += 0.15
            # Deprioritize foreign language pages
            if any(f"/{lang}/" in url or url.startswith(f"/{lang}?") for lang in ("de", "fr", "en", "ru")):
                boost -= 0.15
            # Best thumbnail: og_image > first_image > URL for image results
            image_url = meta.get("og_image", "")
            if not image_url:
                image_url = meta.get("first_image", "")
            if not image_url and content_type == "image":
                image_url = url
            suggestions.append({
                "title": title,
                "url": url,
                "category": meta.get("category", ""),
                "image": image_url,
                "score": round(score + boost, 4),
            })

    # Re-sort by boosted score
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    suggestions = suggestions[:limit]

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "query": q,
        "suggestions": suggestions,
        "time_ms": round(elapsed, 1),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "documents": collection.count() if collection else 0,
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
    }
