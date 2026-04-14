"""Tests for memovich.migrate helpers."""

import os

from memovich.migrate import contains_palace_database, migrate


def test_contains_palace_database_false(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert contains_palace_database(str(d)) is False


def test_contains_palace_database_true(tmp_path):
    d = tmp_path / "palace"
    d.mkdir()
    (d / "chroma.sqlite3").write_text("x")
    assert contains_palace_database(str(d)) is True


def test_migrate_is_noop(capsys):
    assert migrate(os.path.join("tmp", "any"), dry_run=True, confirm=True) is False
    out = capsys.readouterr().out
    assert "removed" in out.lower()
