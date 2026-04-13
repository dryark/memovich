"""In-memory vector collection for tests and zero-dependency runs."""

from __future__ import annotations

import math
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..embeddings import embed_texts
from .base import BaseCollection


def _normalize(vec: List[float]) -> List[float]:
    s = math.sqrt(sum(x * x for x in vec))
    if s <= 0:
        return vec
    return [x / s for x in vec]


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return 1.0 - float(dot)


def _meta_matches(meta: Dict[str, Any], where: Dict[str, Any]) -> bool:
    """Approximate Chroma where on a flat dict (no nested $or beyond one level)."""

    def match(node: Any) -> bool:
        if not isinstance(node, dict):
            return False
        if "$and" in node:
            return all(match(sub) for sub in node["$and"])
        if "$or" in node:
            return any(match(sub) for sub in node["$or"])
        for k, v in node.items():
            if meta.get(k) != v:
                return False
        return True

    return match(where)


class MemoryCollection(BaseCollection):
    def __init__(self, embed_fn: Callable[[Sequence[str]], List[List[float]]]):
        self._embed = embed_fn
        self._data: Dict[str, Dict[str, Any]] = {}

    def add(
        self,
        *,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        metadatas = metadatas or [{}] * len(ids)
        vecs = [_normalize(v) for v in self._embed(documents)]
        for i, doc_id in enumerate(ids):
            self._data[doc_id] = {
                "document": documents[i],
                "metadata": dict(metadatas[i] if i < len(metadatas) else {}),
                "embedding": vecs[i],
            }

    def upsert(self, *, documents, ids, metadatas=None):
        self.add(documents=documents, ids=ids, metadatas=metadatas)

    def query(self, **kwargs: Any) -> Dict[str, Any]:
        query_texts = kwargs.get("query_texts") or []
        n_results = int(kwargs.get("n_results", 10))
        where = kwargs.get("where")
        include = list(kwargs.get("include") or ["documents", "metadatas", "distances"])
        if not query_texts:
            out: Dict[str, Any] = {"ids": [[]], "distances": [[]]}
            if "documents" in include:
                out["documents"] = [[]]
            if "metadatas" in include:
                out["metadatas"] = [[]]
            return out

        qv = _normalize(self._embed([query_texts[0]])[0])
        scored: List[tuple] = []
        for doc_id, row in self._data.items():
            if where and not _meta_matches(row["metadata"], where):
                continue
            dist = _cosine_distance(qv, row["embedding"])
            scored.append((dist, doc_id, row))
        scored.sort(key=lambda x: x[0])
        scored = scored[:n_results]

        out_ids = [x[1] for x in scored]
        out_dist = [x[0] for x in scored]
        res: Dict[str, Any] = {"ids": [out_ids], "distances": [out_dist]}
        if "documents" in include:
            res["documents"] = [[x[2]["document"] for x in scored]]
        if "metadatas" in include:
            res["metadatas"] = [[dict(x[2]["metadata"]) for x in scored]]
        return res

    def get(self, **kwargs: Any) -> Dict[str, Any]:
        ids = kwargs.get("ids")
        where = kwargs.get("where")
        limit = kwargs.get("limit")
        offset = int(kwargs.get("offset") or 0)
        include = kwargs.get("include") or ["metadatas", "documents"]

        items = []
        if ids is not None:
            for doc_id in ids:
                if doc_id in self._data:
                    items.append((doc_id, self._data[doc_id]))
        else:
            for doc_id, row in sorted(self._data.items()):
                if where is None or _meta_matches(row["metadata"], where):
                    items.append((doc_id, row))
        items = items[offset:]
        if limit is not None:
            items = items[: int(limit)]

        out_ids = [x[0] for x in items]
        out_docs = [x[1]["document"] if "documents" in include else None for x in items]
        out_meta = [dict(x[1]["metadata"]) if "metadatas" in include else {} for x in items]
        return {"ids": out_ids, "documents": out_docs, "metadatas": out_meta}

    def delete(self, **kwargs: Any) -> None:
        ids = kwargs.get("ids")
        where = kwargs.get("where")
        if ids is not None:
            for i in ids:
                self._data.pop(i, None)
        elif where:
            to_del = [
                doc_id
                for doc_id, row in self._data.items()
                if _meta_matches(row["metadata"], where)
            ]
            for i in to_del:
                del self._data[i]
        else:
            self._data.clear()

    def count(self) -> int:
        return len(self._data)

    def update(
        self,
        *,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        for i, doc_id in enumerate(ids):
            if doc_id not in self._data:
                continue
            row = self._data[doc_id]
            if documents is not None:
                row["document"] = documents[i]
                row["embedding"] = _normalize(self._embed([row["document"]])[0])
            if metadatas is not None and i < len(metadatas):
                row["metadata"].update(metadatas[i])


class MemoryBackend:
    """In-process backend; collections are keyed by palace path + collection name."""

    def __init__(self, embed_fn: Optional[Callable[[Sequence[str]], List[List[float]]]] = None):
        self._embed_fn = embed_fn or embed_texts
        self._collections: Dict[tuple, MemoryCollection] = {}

    def get_collection(
        self, palace_path: str, collection_name: str, create: bool = False
    ) -> MemoryCollection:
        del create
        key = (os.path.abspath(palace_path), collection_name)
        if key not in self._collections:
            self._collections[key] = MemoryCollection(self._embed_fn)
        return self._collections[key]
