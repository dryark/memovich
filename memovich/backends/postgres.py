"""Postgres + pgvector storage backend."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

import psycopg
from pgvector.psycopg import register_vector

from ..embeddings import EMBEDDING_DIMENSION, embed_texts
from .base import BaseCollection
from .where_clause import chroma_where_to_sql

logger = logging.getLogger(__name__)

_SAFE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_table_name(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid Postgres table name: {name!r}")
    return name


def _json_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not meta:
        return {}
    out = {}
    for k, v in meta.items():
        if v is None:
            continue
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


class PostgresCollection(BaseCollection):
    """pgvector-backed collection with a Chroma-like API."""

    def __init__(
        self,
        conn: psycopg.Connection,
        table_name: str,
        embed_fn: Callable[[Sequence[str]], List[List[float]]],
    ):
        _validate_table_name(table_name)
        self._conn = conn
        self._table = table_name
        self._embed = embed_fn

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding vector({EMBEDDING_DIMENSION}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            try:
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._table}_embedding_hnsw
                    ON {self._table}
                    USING hnsw (embedding vector_cosine_ops)
                    """
                )
            except Exception:
                logger.warning("Could not create HNSW index (pgvector version may be old).")

    def add(
        self,
        *,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        metadatas = metadatas or [{}] * len(ids)
        vectors = self._embed(documents)
        with self._conn.cursor() as cur:
            for i, doc_id in enumerate(ids):
                meta = _json_meta(metadatas[i] if i < len(metadatas) else {})
                emb = vectors[i]
                if len(emb) != EMBEDDING_DIMENSION:
                    raise ValueError(f"Embedding dim {len(emb)} != expected {EMBEDDING_DIMENSION}")
                cur.execute(
                    f"""
                    INSERT INTO {self._table} (id, document, metadata, embedding)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                    (doc_id, documents[i], json.dumps(meta), emb),
                )

    def upsert(
        self,
        *,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
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

        qvec = self._embed([query_texts[0]])[0]
        where_sql, where_params = ("TRUE", [])
        if where:
            where_sql, where_params = chroma_where_to_sql(where)

        parts = ["id"]
        if "distances" in include:
            parts.append("(embedding <=> %s::vector) AS dist")
        if "documents" in include:
            parts.append("document")
        if "metadatas" in include:
            parts.append("metadata")

        select_sql = ", ".join(parts)
        params: List[Any] = []
        if "distances" in include:
            params.append(qvec)
        params.extend(where_params)
        sql = (
            f"SELECT {select_sql} FROM {self._table} WHERE ({where_sql}) "
            "ORDER BY embedding <=> %s::vector ASC LIMIT %s"
        )
        params.extend([qvec, n_results])

        out_ids: List[str] = []
        out_dist: List[float] = []
        out_docs: List[str] = []
        out_meta: List[Dict[str, Any]] = []

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                idx = 0
                out_ids.append(row[idx])
                idx += 1
                if "distances" in include:
                    out_dist.append(float(row[idx]))
                    idx += 1
                if "documents" in include:
                    out_docs.append(row[idx] or "")
                    idx += 1
                if "metadatas" in include:
                    raw = row[idx]
                    out_meta.append(dict(raw) if raw is not None else {})
                    idx += 1

        res: Dict[str, Any] = {
            "ids": [out_ids],
            "distances": [out_dist] if "distances" in include else [[]],
        }
        if "documents" in include:
            res["documents"] = [out_docs]
        if "metadatas" in include:
            res["metadatas"] = [out_meta]
        return res

    def get(self, **kwargs: Any) -> Dict[str, Any]:
        ids = kwargs.get("ids")
        where = kwargs.get("where")
        limit = kwargs.get("limit")
        offset = int(kwargs.get("offset") or 0)
        include = kwargs.get("include") or ["metadatas", "documents"]

        cols = ["id"]
        if "documents" in include:
            cols.append("document")
        if "metadatas" in include:
            cols.append("metadata")
        select_sql = ", ".join(cols)

        where_sql = "TRUE"
        params: List[Any] = []
        if ids is not None:
            where_sql = "id = ANY(%s)"
            params.append(ids)
        elif where:
            wsql, wparams = chroma_where_to_sql(where)
            where_sql = wsql
            params.extend(wparams)

        sql = f"SELECT {select_sql} FROM {self._table} WHERE {where_sql} ORDER BY id"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            params.extend([int(limit), offset])
        elif offset:
            sql += " OFFSET %s"
            params.append(offset)

        out_ids: List[str] = []
        out_docs: List[Optional[str]] = []
        out_meta: List[Dict[str, Any]] = []

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                idx = 0
                out_ids.append(row[idx])
                idx += 1
                if "documents" in include:
                    out_docs.append(row[idx])
                    idx += 1
                else:
                    out_docs.append(None)
                if "metadatas" in include:
                    raw = row[idx]
                    out_meta.append(dict(raw) if raw is not None else {})
                else:
                    out_meta.append({})

        return {"ids": out_ids, "documents": out_docs, "metadatas": out_meta}

    def delete(self, **kwargs: Any) -> None:
        ids = kwargs.get("ids")
        where = kwargs.get("where")
        with self._conn.cursor() as cur:
            if ids is not None:
                cur.execute(f"DELETE FROM {self._table} WHERE id = ANY(%s)", (ids,))
            elif where:
                wsql, wparams = chroma_where_to_sql(where)
                cur.execute(f"DELETE FROM {self._table} WHERE {wsql}", wparams)
            else:
                cur.execute(f"DELETE FROM {self._table}")

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._table}")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def update(
        self,
        *,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if not ids:
            return
        with self._conn.cursor() as cur:
            for i, doc_id in enumerate(ids):
                cur.execute(
                    f"SELECT document, metadata FROM {self._table} WHERE id = %s", (doc_id,)
                )
                row = cur.fetchone()
                if not row:
                    continue
                old_doc, old_meta = row[0], dict(row[1] or {})
                new_doc = old_doc if documents is None else documents[i]
                if metadatas is not None and i < len(metadatas):
                    merged = dict(old_meta)
                    merged.update(_json_meta(metadatas[i]))
                    new_meta = merged
                else:
                    new_meta = old_meta
                new_meta = _json_meta(new_meta)
                vectors = self._embed([new_doc])
                emb = vectors[0]
                cur.execute(
                    f"""
                    UPDATE {self._table}
                    SET document = %s, metadata = %s::jsonb, embedding = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_doc, json.dumps(new_meta), emb, doc_id),
                )


class PostgresBackend:
    """Factory for pgvector-backed storage."""

    def __init__(
        self,
        dsn: str,
        table_name: str = "memovich_chunks",
        embed_fn: Optional[Callable[[Sequence[str]], List[List[float]]]] = None,
    ):
        self.dsn = dsn
        self.table_name = _validate_table_name(table_name)
        self._embed_fn = embed_fn or embed_texts
        self._conn: Optional[psycopg.Connection] = None

    def _physical_table(self, collection_name: str) -> str:
        """Primary collection uses ``table_name``; auxiliary collections get a suffix."""
        if not collection_name or collection_name == "memovich_chunks":
            return self.table_name
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", collection_name)
        return _validate_table_name(f"{self.table_name}_{safe}")

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.dsn, autocommit=True)
            register_vector(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def get_collection(
        self, palace_path: str, collection_name: str, create: bool = False
    ) -> PostgresCollection:
        del palace_path  # unused; storage is DSN-bound
        physical = self._physical_table(collection_name)
        conn = self._connection()
        col = PostgresCollection(conn, physical, self._embed_fn)
        if create:
            col._ensure_schema()
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = current_schema() AND table_name = %s
                    """,
                    (physical,),
                )
                if cur.fetchone() is None:
                    raise FileNotFoundError(
                        f"Postgres table {physical!r} does not exist "
                        "(run init / first ingest with create=True)"
                    )
        return col
