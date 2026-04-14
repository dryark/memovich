"""Construct vector storage backends from configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Tuple

if TYPE_CHECKING:
    from ..config import MemovichConfig

_backend_cache: Dict[Tuple[Any, ...], Any] = {}


def _backend_key(cfg: "MemovichConfig") -> Tuple[Any, ...]:
    return (
        cfg.vector_backend,
        cfg.postgres_dsn or "",
        cfg.postgres_table or "",
    )


def create_backend(cfg: "MemovichConfig"):
    """Return a cached backend instance for this config."""
    key = _backend_key(cfg)
    if key in _backend_cache:
        return _backend_cache[key]

    kind = cfg.vector_backend
    if kind == "postgres":
        from .postgres import PostgresBackend

        inst = PostgresBackend(dsn=cfg.postgres_dsn, table_name=cfg.postgres_table)
    elif kind == "chroma":
        try:
            from .chroma import ChromaBackend
        except ImportError as e:
            raise ImportError(
                "vector_backend=chroma requires the chroma extra: pip install 'memovich[chroma]'"
            ) from e

        inst = ChromaBackend()
    elif kind == "memory":
        from .memory import MemoryBackend

        inst = MemoryBackend()
    else:
        raise ValueError(f"Unknown vector_backend: {kind!r}")

    _backend_cache[key] = inst
    return inst


def invalidate_backend_cache() -> None:
    """Close and drop cached backends (e.g. MCP reconnect)."""
    global _backend_cache
    for inst in _backend_cache.values():
        close = getattr(inst, "close", None)
        if callable(close):
            close()
    _backend_cache.clear()
