# Hanak Search

Vektorové vyhledávání pro hanak-nabytek.cz — showcase projekt CORE SYSTEMS.

## Architektura
- **site/** — kompletní mirror webu
- **api/** — Python FastAPI + ChromaDB vector search
- **search-ui/** — search overlay (typeahead, našeptávač)
- **docker-compose.yml** — one-command deploy

## Stack
- Nginx (static serving)
- FastAPI (search API)
- ChromaDB (vector embeddings)
- Sentence-transformers (multilingual embeddings)

