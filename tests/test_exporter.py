import os
import shutil
import tempfile
from pathlib import Path

import yaml

from memovich.miner import mine
from memovich.exporter import export_palace


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_palace(tmpdir):
    """Create a small palace with chunks across two namespaces for testing."""
    project_a = Path(tmpdir) / "project_a"
    project_b = Path(tmpdir) / "project_b"
    palace_path = str(Path(tmpdir) / "palace")

    # Project A: namespace=alpha, segments=backend,frontend
    os.makedirs(project_a / "backend")
    os.makedirs(project_a / "frontend")
    write_file(project_a / "backend" / "server.py", "def serve():\n    return 'ok'\n" * 20)
    write_file(project_a / "frontend" / "app.js", "function render() { return 'hi'; }\n" * 20)
    with open(project_a / "memovich.yaml", "w") as f:
        yaml.dump(
            {
                "namespace": "alpha",
                "segments": [
                    {"name": "backend", "description": "Backend code"},
                    {"name": "frontend", "description": "Frontend code"},
                ],
            },
            f,
        )

    # Project B: namespace=beta, segments=docs
    os.makedirs(project_b / "docs")
    write_file(project_b / "docs" / "guide.md", "# Guide\n\nThis explains things.\n" * 20)
    with open(project_b / "memovich.yaml", "w") as f:
        yaml.dump(
            {
                "namespace": "beta",
                "segments": [{"name": "docs", "description": "Documentation"}],
            },
            f,
        )

    mine(str(project_a), palace_path)
    mine(str(project_b), palace_path)

    return palace_path


def test_export_creates_structure():
    tmpdir = tempfile.mkdtemp()
    try:
        palace_path = _setup_palace(tmpdir)
        output_dir = os.path.join(tmpdir, "export")

        stats = export_palace(palace_path, output_dir)

        assert stats["namespaces"] == 2
        assert stats["segments"] >= 2
        assert stats["chunks"] >= 3

        # Directory structure
        assert os.path.isfile(os.path.join(output_dir, "index.md"))
        assert os.path.isdir(os.path.join(output_dir, "alpha"))
        assert os.path.isdir(os.path.join(output_dir, "beta"))

        # Room files exist
        assert os.path.isfile(os.path.join(output_dir, "alpha", "backend.md"))
        assert os.path.isfile(os.path.join(output_dir, "alpha", "frontend.md"))
        assert os.path.isfile(os.path.join(output_dir, "beta", "docs.md"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_markdown_content():
    tmpdir = tempfile.mkdtemp()
    try:
        palace_path = _setup_palace(tmpdir)
        output_dir = os.path.join(tmpdir, "export")

        export_palace(palace_path, output_dir)

        # Check that room files contain expected markdown elements
        backend_md = Path(output_dir) / "alpha" / "backend.md"
        content = backend_md.read_text(encoding="utf-8")

        assert content.startswith("# alpha / backend\n")
        assert "## chunk_" in content
        assert "| Field | Value |" in content
        assert "| Source |" in content
        assert "| Filed |" in content
        assert "| Added by |" in content
        assert "---" in content
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_index_content():
    tmpdir = tempfile.mkdtemp()
    try:
        palace_path = _setup_palace(tmpdir)
        output_dir = os.path.join(tmpdir, "export")

        export_palace(palace_path, output_dir)

        index_md = Path(output_dir) / "index.md"
        content = index_md.read_text(encoding="utf-8")

        assert "# Memory export" in content
        assert "| Namespace | Segments | Chunks |" in content
        assert "[alpha](alpha/)" in content
        assert "[beta](beta/)" in content
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_empty_palace():
    tmpdir = tempfile.mkdtemp()
    try:
        palace_path = os.path.join(tmpdir, "empty_palace")
        output_dir = os.path.join(tmpdir, "export")

        stats = export_palace(palace_path, output_dir)

        assert stats == {"namespaces": 0, "segments": 0, "chunks": 0}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
