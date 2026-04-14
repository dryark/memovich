"""
palace.py — Shared storage path helpers and vector collection access.

Consolidates collection access patterns used by miners and the MCP server.
"""

import os

from .backends.factory import create_backend, invalidate_backend_cache

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    "coverage",
    ".memovich",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    ".eggs",
    "htmlcov",
    "target",
}


def chroma_data_signature(palace_path: str) -> tuple:
    """Return (inode, mtime) for chroma.sqlite3, or (0, 0.0) if missing."""
    db_path = os.path.join(palace_path, "chroma.sqlite3")
    try:
        st = os.stat(db_path)
        inode, mtime = st.st_ino, st.st_mtime
    except OSError:
        return (0, 0.0)
    return (inode, mtime)


def storage_signature_for_config(config) -> tuple:
    """MCP cache invalidation: Chroma uses DB file identity; others rely on reconnect."""
    if config.vector_backend == "chroma":
        inode, mtime = chroma_data_signature(config.palace_path)
        if inode != 0 and mtime != 0.0:
            return ("chroma", inode, mtime)
    return (config.vector_backend, 0, 0.0)


def get_collection(
    palace_path: str = None,
    collection_name: str = None,
    create: bool = True,
    config=None,
):
    """Get the chunk collection for the configured vector backend."""
    from .config import MemovichConfig

    cfg = config or MemovichConfig()
    path = palace_path if palace_path is not None else cfg.palace_path
    name = collection_name if collection_name is not None else cfg.collection_name
    backend = create_backend(cfg)
    return backend.get_collection(path, name, create=create)


def invalidate_vector_backend_cache() -> None:
    """Drop cached backend connections (used by MCP reconnect)."""
    invalidate_backend_cache()


def file_already_mined(collection, source_file: str, check_mtime: bool = False) -> bool:
    """Check if a file has already been filed.

    When check_mtime=True (used by project miner), returns False if the file
    has been modified since it was last mined, so it gets re-mined.
    When check_mtime=False (used by convo miner), just checks existence.
    """
    try:
        results = collection.get(where={"source_file": source_file}, limit=1)
        if not results.get("ids"):
            return False
        if check_mtime:
            stored_meta = results.get("metadatas", [{}])[0]
            stored_mtime = stored_meta.get("source_mtime")
            if stored_mtime is None:
                return False
            current_mtime = os.path.getmtime(source_file)
            return abs(float(stored_mtime) - current_mtime) < 0.001
        return True
    except Exception:
        return False
