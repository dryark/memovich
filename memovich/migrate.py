#!/usr/bin/env python3
"""
Legacy hooks for Chroma directory checks and repair confirmation.

Cross-version Chroma SQLite import was removed from this fork — use a
greenfield store with your configured ``vector_backend``.
"""

import os


def contains_palace_database(path: str) -> bool:
    """Return True when path looks like a ChromaDB data directory."""
    return os.path.isfile(os.path.join(path, "chroma.sqlite3"))


def confirm_destructive_action(
    operation_name: str, palace_path: str, assume_yes: bool = False
) -> bool:
    """Require confirmation before destructive palace operations."""
    if assume_yes:
        return True

    print(f"\n  {operation_name} will replace data in: {palace_path}")
    print("  A backup will be created first, then the store will be rebuilt.")
    try:
        answer = input("  Continue? [y/N]: ").strip().lower()
    except EOFError:
        print("  Aborted. Re-run with --yes to confirm destructive changes.")
        return False

    if answer not in {"y", "yes"}:
        print("  Aborted.")
        return False
    return True


def migrate(palace_path: str, dry_run: bool = False, confirm: bool = False) -> bool:
    """Removed: this fork does not import legacy palace databases."""
    del palace_path, dry_run, confirm
    print("\n  memovich migrate was removed in this fork.")
    print("  Configure vector_backend / Postgres DSN and re-ingest from source.")
    return False
