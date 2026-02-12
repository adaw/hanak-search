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

app = FastAPI(title="Hanak Search API", version="1.0.0")

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
):
    """Vector similarity search with instant results."""
    start = time.perf_counter()

    if collection.count() == 0:
        return SearchResponse(query=q, results=[], total=0, time_ms=0)

    # Embed query
    query_embedding = model.encode(q).tolist()

    # Search ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )

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
        search_results.append(SearchResult(
            title=meta.get("title", "Bez názvu"),
            url=meta.get("url", "#"),
            snippet=doc[:250] + "..." if len(doc) > 250 else doc,
            score=round(score, 4),
            category=meta.get("category", ""),
        ))

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
):
    """Fast typeahead suggestions — returns titles + URLs only."""
    start = time.perf_counter()

    if collection.count() == 0:
        return {"query": q, "suggestions": [], "time_ms": 0}

    query_embedding = model.encode(q).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(limit * 4, 30),  # fetch more candidates for re-ranking
        include=["metadatas", "distances"],
    )

    suggestions = []
    seen_titles = set()
    q_lower = q.lower()
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        score = 1 - dist
        if score < 0.2:
            continue
        title = meta.get("title", "")
        url = meta.get("url", "#")
        if title and title not in seen_titles:
            seen_titles.add(title)
            # Boost: prefix match in title or Czech content prioritized over foreign
            title_lower = title.lower()
            boost = 0.0
            if q_lower in title_lower:
                boost += 0.3
            if title_lower.startswith(q_lower):
                boost += 0.2
            # Deprioritize foreign language pages
            if any(f"/{lang}/" in url or url.startswith(f"/{lang}?") for lang in ("de", "fr", "en", "ru")):
                boost -= 0.15
            suggestions.append({
                "title": title,
                "url": url,
                "category": meta.get("category", ""),
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
