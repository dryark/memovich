#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the vector store.
Returns verbatim text — the actual words, never summaries.
"""

import logging
from pathlib import Path

from .metadata_keys import NAMESPACE, SEGMENT
from .palace import get_collection

logger = logging.getLogger("mempalace_mcp")


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no store found)."""


def build_where_filter(namespace: str = None, segment: str = None) -> dict:
    """Build metadata filter for namespace / segment (Chroma- and Postgres-compatible)."""
    if namespace and segment:
        return {"$and": [{NAMESPACE: namespace}, {SEGMENT: segment}]}
    if namespace:
        return {NAMESPACE: namespace}
    if segment:
        return {SEGMENT: segment}
    return {}


def search(
    query: str,
    palace_path: str,
    namespace: str = None,
    segment: str = None,
    n_results: int = 5,
):
    """
    Search the store. Returns verbatim chunk content.
    Optionally filter by namespace (project) or segment (aspect).
    """
    try:
        col = get_collection(palace_path, create=False)
    except Exception:
        print(f"\n  No memory store found at {palace_path}")
        print("  Run: mempalace init <dir> then mempalace mine <dir>")
        raise SearchError(f"No memory store found at {palace_path}")

    where = build_where_filter(namespace, segment)

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    if not docs:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if namespace:
        print(f"  Namespace: {namespace}")
    if segment:
        print(f"  Segment: {segment}")
    print(f"{'=' * 60}\n")

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        similarity = round(max(0.0, 1 - dist), 3)
        source = Path(meta.get("source_file", "?")).name
        ns_name = meta.get(NAMESPACE, "?")
        seg_name = meta.get(SEGMENT, "?")

        print(f"  [{i}] {ns_name} / {seg_name}")
        print(f"      Source: {source}")
        print(f"      Match:  {similarity}")
        print()
        for line in doc.strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str,
    palace_path: str,
    namespace: str = None,
    segment: str = None,
    n_results: int = 5,
    max_distance: float = 0.0,
) -> dict:
    """Programmatic search — returns a dict instead of printing.

    Used by the MCP server and other callers that need data.

    Args:
        query: Natural language search query.
        palace_path: Path to local storage root (Chroma dir or config palace_path).
        namespace: Optional namespace filter.
        segment: Optional segment filter.
        n_results: Max results to return.
        max_distance: Max cosine distance threshold. The collection uses
            cosine distance — 0 = identical, 2 = opposite.
            Results with distance > this value are filtered out. A value of
            0.0 disables filtering. Typical useful range: 0.3–1.0.
    """
    try:
        col = get_collection(palace_path, create=False)
    except Exception as e:
        logger.error("No memory store at %s: %s", palace_path, e)
        return {
            "error": "No memory store found",
            "hint": "Run: mempalace init <dir> && mempalace mine <dir>",
        }

    where = build_where_filter(namespace, segment)

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        if max_distance > 0.0 and dist > max_distance:
            continue
        hits.append(
            {
                "text": doc,
                "namespace": meta.get(NAMESPACE, "unknown"),
                "segment": meta.get(SEGMENT, "unknown"),
                "source_file": Path(meta.get("source_file", "?")).name,
                "similarity": round(max(0.0, 1 - dist), 3),
                "distance": round(dist, 4),
            }
        )

    return {
        "query": query,
        "filters": {"namespace": namespace, "segment": segment},
        "total_before_filter": len(docs),
        "results": hits,
    }
