#!/usr/bin/env python3
"""
layers.py — 4-Layer Memory Stack for memovich
===================================================

Load only what you need, when you need it.

    Layer 0: Identity       (~100 tokens)   — Always loaded. "Who am I?"
    Layer 1: Essential Story (~500-800)      — Always loaded. Top moments from the palace.
    Layer 2: On-Demand      (~200-500 each)  — Loaded when a topic/wing comes up.
    Layer 3: Deep Search    (unlimited)      — Full ChromaDB semantic search.

Wake-up cost: ~600-900 tokens (L0+L1). Leaves 95%+ of context free.

Reads directly from the configured vector store
and ~/.memovich/identity.txt.
"""

import os
import sys
from pathlib import Path
from collections import defaultdict

from .config import MemovichConfig
from .metadata_keys import NAMESPACE, SEGMENT
from .palace import get_collection as _get_collection
from .searcher import build_where_filter
from .tiers.loader import load_tier_preset


def _hot_window_tier(cfg: MemovichConfig):
    preset = load_tier_preset(cfg.tier_preset)
    for tier in preset.tiers:
        if tier.role == "hot_window":
            return tier
    raise RuntimeError(f"tier preset {cfg.tier_preset!r} missing hot_window tier")


# ---------------------------------------------------------------------------
# Layer 0 — Identity
# ---------------------------------------------------------------------------


class Layer0:
    """
    ~100 tokens. Always loaded.
    Reads from ~/.memovich/identity.txt — a plain-text file the user writes.

    Example identity.txt:
        I am Atlas, a personal AI assistant for Alice.
        Traits: warm, direct, remembers everything.
        People: Alice (creator), Bob (Alice's partner).
        Project: A journaling app that helps people process emotions.
    """

    def __init__(self, identity_path: str = None):
        if identity_path is None:
            identity_path = os.path.expanduser("~/.memovich/identity.txt")
        self.path = identity_path
        self._text = None

    def render(self) -> str:
        """Return the identity text, or a sensible default."""
        if self._text is not None:
            return self._text

        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self._text = f.read().strip()
        else:
            self._text = "## L0 — IDENTITY\nNo identity configured. Create ~/.memovich/identity.txt"

        return self._text

    def token_estimate(self) -> int:
        return len(self.render()) // 4


# ---------------------------------------------------------------------------
# Layer 1 — Essential Story (auto-generated from palace)
# ---------------------------------------------------------------------------


class Layer1:
    """
    ~500-800 tokens. Always loaded.
    Auto-generated from weighted chunks; grouping comes from the tier preset.
    """

    def __init__(self, palace_path: str = None, namespace: str = None):
        cfg = MemovichConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.namespace = namespace
        self._tier = _hot_window_tier(cfg)

    def generate(self) -> str:
        """Pull top chunks and format as compact L1 text."""
        try:
            col = _get_collection(self.palace_path, create=False)
        except Exception:
            return "## L1 — No memory store found. Run: memovich mine <dir>"

        max_scan = self._tier.max_scan or 2000
        max_drawers = self._tier.max_chunks or 15
        max_chars = self._tier.max_chars or 3200
        group_by = self._tier.group_by or "segment"
        group_key = NAMESPACE if group_by == "namespace" else SEGMENT

        _BATCH = 500
        docs, metas = [], []
        offset = 0
        while True:
            kwargs = {"include": ["documents", "metadatas"], "limit": _BATCH, "offset": offset}
            if self.namespace:
                kwargs["where"] = {NAMESPACE: self.namespace}
            try:
                batch = col.get(**kwargs)
            except Exception:
                break
            batch_docs = batch.get("documents", [])
            batch_metas = batch.get("metadatas", [])
            if not batch_docs:
                break
            docs.extend(batch_docs)
            metas.extend(batch_metas)
            offset += len(batch_docs)
            if len(batch_docs) < _BATCH or len(docs) >= max_scan:
                break

        if not docs:
            return "## L1 — No memories yet."

        scored = []
        for doc, meta in zip(docs, metas):
            importance = 3
            for key in ("importance", "emotional_weight", "weight"):
                val = meta.get(key)
                if val is not None:
                    try:
                        importance = float(val)
                    except (ValueError, TypeError):
                        pass
                    break
            scored.append((importance, meta, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_drawers]

        by_bucket = defaultdict(list)
        for imp, meta, doc in top:
            bucket = meta.get(group_key, "general")
            by_bucket[bucket].append((imp, meta, doc))

        lines = ["## L1 — ESSENTIAL STORY"]

        total_len = 0
        for bucket, entries in sorted(by_bucket.items()):
            hdr = f"\n[{bucket}]"
            lines.append(hdr)
            total_len += len(hdr)

            for imp, meta, doc in entries:
                source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""

                snippet = doc.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."

                entry_line = f"  - {snippet}"
                if source:
                    entry_line += f"  ({source})"

                if total_len + len(entry_line) > max_chars:
                    lines.append("  ... (more in L3 search)")
                    return "\n".join(lines)

                lines.append(entry_line)
                total_len += len(entry_line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layer 2 — On-Demand (wing/room filtered retrieval)
# ---------------------------------------------------------------------------


class Layer2:
    """
    ~200-500 tokens per retrieval.
    Loaded when a specific namespace/segment comes up in conversation.
    """

    def __init__(self, palace_path: str = None):
        cfg = MemovichConfig()
        self.palace_path = palace_path or cfg.palace_path

    def retrieve(self, namespace: str = None, segment: str = None, n_results: int = 10) -> str:
        """Retrieve chunks filtered by namespace and/or segment."""
        try:
            col = _get_collection(self.palace_path, create=False)
        except Exception:
            return "No memory store found."

        where = build_where_filter(namespace, segment)

        kwargs = {"include": ["documents", "metadatas"], "limit": n_results}
        if where:
            kwargs["where"] = where

        try:
            results = col.get(**kwargs)
        except Exception as e:
            return f"Retrieval error: {e}"

        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        if not docs:
            label = f"namespace={namespace}" if namespace else ""
            if segment:
                label += f" segment={segment}" if label else f"segment={segment}"
            return f"No chunks found for {label}."

        lines = [f"## L2 — ON-DEMAND ({len(docs)} chunks)"]
        for doc, meta in zip(docs[:n_results], metas[:n_results]):
            seg_name = meta.get(SEGMENT, "?")
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            entry = f"  [{seg_name}] {snippet}"
            if source:
                entry += f"  ({source})"
            lines.append(entry)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layer 3 — Deep Search (full semantic search via ChromaDB)
# ---------------------------------------------------------------------------


class Layer3:
    """
    Unlimited depth. Semantic search against the full vector store.
    """

    def __init__(self, palace_path: str = None):
        cfg = MemovichConfig()
        self.palace_path = palace_path or cfg.palace_path

    def search(
        self, query: str, namespace: str = None, segment: str = None, n_results: int = 5
    ) -> str:
        """Semantic search, returns compact result text."""
        try:
            col = _get_collection(self.palace_path, create=False)
        except Exception:
            return "No memory store found."

        where = build_where_filter(namespace, segment)

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception as e:
            return f"Search error: {e}"

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        if not docs:
            return "No results found."

        lines = [f'## L3 — SEARCH RESULTS for "{query}"']
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
            similarity = round(1 - dist, 3)
            ns_name = meta.get(NAMESPACE, "?")
            seg_name = meta.get(SEGMENT, "?")
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""

            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."

            lines.append(f"  [{i}] {ns_name}/{seg_name} (sim={similarity})")
            lines.append(f"      {snippet}")
            if source:
                lines.append(f"      src: {source}")

        return "\n".join(lines)

    def search_raw(
        self, query: str, namespace: str = None, segment: str = None, n_results: int = 5
    ) -> list:
        """Return raw dicts instead of formatted text."""
        try:
            col = _get_collection(self.palace_path, create=False)
        except Exception:
            return []

        where = build_where_filter(namespace, segment)

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception:
            return []

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append(
                {
                    "text": doc,
                    "namespace": meta.get(NAMESPACE, "unknown"),
                    "segment": meta.get(SEGMENT, "unknown"),
                    "source_file": Path(meta.get("source_file", "?")).name,
                    "similarity": round(1 - dist, 3),
                    "metadata": meta,
                }
            )
        return hits


# ---------------------------------------------------------------------------
# MemoryStack — unified interface
# ---------------------------------------------------------------------------


class MemoryStack:
    """
    The full 4-layer stack. One class, one palace, everything works.

        stack = MemoryStack()
        print(stack.wake_up())                # L0 + L1 (~600-900 tokens)
        print(stack.recall(namespace="my_app"))     # L2 on-demand
        print(stack.search("pricing change"))  # L3 deep search
    """

    def __init__(self, palace_path: str = None, identity_path: str = None):
        cfg = MemovichConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.identity_path = identity_path or os.path.expanduser("~/.memovich/identity.txt")

        self.l0 = Layer0(self.identity_path)
        self.l1 = Layer1(self.palace_path)
        self.l2 = Layer2(self.palace_path)
        self.l3 = Layer3(self.palace_path)

    def wake_up(self, namespace: str = None) -> str:
        """
        Generate wake-up text: L0 (identity) + L1 (essential story).
        Typically ~600-900 tokens. Inject into system prompt or first message.

        Args:
            namespace: Optional namespace filter for L1 (project-specific wake-up).
        """
        parts = []

        # L0: Identity
        parts.append(self.l0.render())
        parts.append("")

        # L1: Essential Story
        if namespace:
            self.l1.namespace = namespace
        parts.append(self.l1.generate())

        return "\n".join(parts)

    def recall(self, namespace: str = None, segment: str = None, n_results: int = 10) -> str:
        """On-demand L2 retrieval filtered by namespace/segment."""
        return self.l2.retrieve(namespace=namespace, segment=segment, n_results=n_results)

    def search(
        self, query: str, namespace: str = None, segment: str = None, n_results: int = 5
    ) -> str:
        """Deep L3 semantic search."""
        return self.l3.search(query, namespace=namespace, segment=segment, n_results=n_results)

    def status(self) -> dict:
        """Status of all layers."""
        result = {
            "palace_path": self.palace_path,
            "L0_identity": {
                "path": self.identity_path,
                "exists": os.path.exists(self.identity_path),
                "tokens": self.l0.token_estimate(),
            },
            "L1_essential": {
                "description": "Auto-generated from top palace drawers",
            },
            "L2_on_demand": {
                "description": "Namespace/segment filtered retrieval",
            },
            "L3_deep_search": {
                "description": "Full semantic vector search",
            },
        }

        # Count drawers
        try:
            col = _get_collection(self.palace_path, create=False)
            count = col.count()
            result["total_chunks"] = count
        except Exception:
            result["total_chunks"] = 0

        return result


# ---------------------------------------------------------------------------
# CLI (standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    def usage():
        print("layers.py — 4-Layer Memory Stack")
        print()
        print("Usage:")
        print("  python layers.py wake-up              Show L0 + L1")
        print("  python layers.py wake-up --namespace=NAME  Wake-up for a specific project")
        print("  python layers.py recall --namespace=NAME   On-demand L2 retrieval")
        print("  python layers.py search <query>       Deep L3 search")
        print("  python layers.py status               Show layer status")
        sys.exit(0)

    if len(sys.argv) < 2:
        usage()

    cmd = sys.argv[1]

    # Parse flags
    flags = {}
    positional = []
    for arg in sys.argv[2:]:
        if arg.startswith("--") and "=" in arg:
            key, val = arg.split("=", 1)
            flags[key.lstrip("-")] = val
        elif not arg.startswith("--"):
            positional.append(arg)

    palace_path = flags.get("palace")
    stack = MemoryStack(palace_path=palace_path)

    if cmd in ("wake-up", "wakeup"):
        namespace = flags.get("namespace")
        text = stack.wake_up(namespace=namespace)
        tokens = len(text) // 4
        print(f"Wake-up text (~{tokens} tokens):")
        print("=" * 50)
        print(text)

    elif cmd == "recall":
        namespace = flags.get("namespace")
        segment = flags.get("segment")
        text = stack.recall(namespace=namespace, segment=segment)
        print(text)

    elif cmd == "search":
        query = " ".join(positional) if positional else ""
        if not query:
            print("Usage: python layers.py search <query>")
            sys.exit(1)
        namespace = flags.get("namespace")
        segment = flags.get("segment")
        text = stack.search(query, namespace=namespace, segment=segment)
        print(text)

    elif cmd == "status":
        s = stack.status()
        print(json.dumps(s, indent=2))

    else:
        usage()
