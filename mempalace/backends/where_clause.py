"""Map Chroma-style ``where`` filters to Postgres JSONB predicates."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def chroma_where_to_sql(where: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """
    Build ``(sql_fragment, params)`` for ``WHERE`` using ``metadata @> ...``.

    Supports ``{"key": value}``, ``{"$and": [...]}``, ``{"$or": [...]}`` (one level).
    Params are for psycopg ``%s`` placeholders in order of appearance.
    """
    params: List[Any] = []

    def walk(node: Any) -> str:
        if not isinstance(node, dict):
            raise ValueError(f"Invalid where clause: {node!r}")
        if "$and" in node:
            parts = [walk(sub) for sub in node["$and"]]
            return "(" + " AND ".join(parts) + ")"
        if "$or" in node:
            parts = [walk(sub) for sub in node["$or"]]
            return "(" + " OR ".join(parts) + ")"
        if len(node) != 1:
            raise ValueError(f"where dict must have one key or $and/$or: {node!r}")
        key, val = next(iter(node.items()))
        blob = json.dumps({key: val}, separators=(",", ":"), ensure_ascii=False)
        params.append(blob)
        return "metadata @> %s::jsonb"

    sql = walk(where)
    return sql, params
