"""Thin accessor to the shared ChromaDB used as the stateful memory layer.

Direct writes from the agents go through the MCP `commit_memory` /
`query_memory` tools; this module is kept for convenience and tests.
"""
from __future__ import annotations

from functools import lru_cache

from config import MEMORY_DIR


@lru_cache(maxsize=1)
def collection():
    import chromadb
    client = chromadb.PersistentClient(path=str(MEMORY_DIR))
    return client.get_or_create_collection("writers_room")
