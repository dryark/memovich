"""Tests for memovich.layers — Layer0, Layer1, Layer2, Layer3, MemoryStack."""

import os
from unittest.mock import MagicMock, patch

import pytest

from memovich.layers import Layer0, Layer1, Layer2, Layer3, MemoryStack


@pytest.fixture(autouse=True)
def _stub_tier_preset():
    """Avoid loading real YAML while MemovichConfig is mocked in unit tests."""
    hot = MagicMock()
    hot.role = "hot_window"
    hot.max_scan = 2000
    hot.max_chunks = 15
    hot.max_chars = 3200
    hot.group_by = "segment"
    preset = MagicMock()
    preset.tiers = [hot]
    with patch("memovich.layers.load_tier_preset", return_value=preset):
        yield


# ── Layer0 — with identity file ─────────────────────────────────────────


def test_layer0_reads_identity_file(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas, a personal AI assistant for Alice.")
    layer = Layer0(identity_path=str(identity_file))
    text = layer.render()
    assert "Atlas" in text
    assert "Alice" in text


def test_layer0_caches_text(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("Hello world")
    layer = Layer0(identity_path=str(identity_file))
    first = layer.render()
    identity_file.write_text("Changed content")
    second = layer.render()
    assert first == second
    assert second == "Hello world"


def test_layer0_missing_file_returns_default(tmp_path):
    missing = str(tmp_path / "nonexistent.txt")
    layer = Layer0(identity_path=missing)
    text = layer.render()
    assert "No identity configured" in text
    assert "identity.txt" in text


def test_layer0_token_estimate(tmp_path):
    identity_file = tmp_path / "identity.txt"
    content = "A" * 400
    identity_file.write_text(content)
    layer = Layer0(identity_path=str(identity_file))
    estimate = layer.token_estimate()
    assert estimate == 100


def test_layer0_token_estimate_empty(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("")
    layer = Layer0(identity_path=str(identity_file))
    assert layer.token_estimate() == 0


def test_layer0_strips_whitespace(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("  Hello world  \n\n")
    layer = Layer0(identity_path=str(identity_file))
    text = layer.render()
    assert text == "Hello world"


def test_layer0_default_path():
    layer = Layer0()
    expected = os.path.expanduser("~/.memovich/identity.txt")
    assert layer.path == expected


# ── Layer1 — mocked chromadb ────────────────────────────────────────────


def _mock_chromadb_for_layer(docs, metas, monkeypatch=None):
    """Return a mock collection whose get() returns docs/metas."""
    mock_col = MagicMock()
    # First batch returns data, second batch returns empty (end of pagination)
    mock_col.get.side_effect = [
        {"documents": docs, "metadatas": metas},
        {"documents": [], "metadatas": []},
    ]
    return mock_col


def test_layer1_no_palace():
    """Layer1 returns helpful message when no palace exists."""
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent/palace"
        layer = Layer1(palace_path="/nonexistent/palace")
        result = layer.generate()
    assert "No memory store found" in result or "No memories" in result


def test_layer1_generates_essential_story():
    docs = [
        "Important memory about project decisions",
        "Key architectural choice for the backend",
    ]
    metas = [
        {"segment": "decisions", "source_file": "meeting.txt", "importance": 5},
        {"segment": "architecture", "source_file": "design.txt", "importance": 4},
    ]
    mock_col = _mock_chromadb_for_layer(docs, metas)

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "ESSENTIAL STORY" in result
    assert "project decisions" in result


def test_layer1_empty_palace():
    mock_col = MagicMock()
    mock_col.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "No memories" in result


def test_layer1_with_namespace_filter():
    docs = ["Memory about project X"]
    metas = [{"segment": "general", "source_file": "x.txt", "importance": 3}]
    mock_col = _mock_chromadb_for_layer(docs, metas)

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake", namespace="project_x")
        result = layer.generate()

    assert "ESSENTIAL STORY" in result
    # Verify wing filter was passed
    call_kwargs = mock_col.get.call_args_list[0][1]
    assert call_kwargs.get("where") == {"namespace": "project_x"}


def test_layer1_truncates_long_snippets():
    docs = ["A" * 300]
    metas = [{"segment": "general", "source_file": "long.txt"}]
    mock_col = _mock_chromadb_for_layer(docs, metas)

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "..." in result


def test_layer1_respects_max_chars():
    """L1 stops adding entries once tier max_chars is reached."""
    docs = [f"Memory number {i} with substantial content padding here" for i in range(30)]
    metas = [{"segment": "general", "source_file": f"f{i}.txt", "importance": 5} for i in range(30)]
    mock_col = _mock_chromadb_for_layer(docs, metas)

    tier = MagicMock()
    tier.max_scan = 2000
    tier.max_chunks = 15
    tier.max_chars = 200
    tier.group_by = "segment"

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
        patch("memovich.layers._hot_window_tier", return_value=tier),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "more in L3 search" in result


def test_layer1_importance_from_various_keys():
    """Layer1 tries importance, emotional_weight, weight keys."""
    docs = ["mem1", "mem2", "mem3"]
    metas = [
        {"segment": "r", "emotional_weight": 5},
        {"segment": "r", "weight": 1},
        {"segment": "r"},  # no weight key, defaults to 3
    ]
    mock_col = _mock_chromadb_for_layer(docs, metas)

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "ESSENTIAL STORY" in result


def test_layer1_batch_exception_breaks():
    """If col.get raises on a batch, loop breaks gracefully."""
    mock_col = MagicMock()
    mock_col.get.side_effect = [
        {"documents": ["doc1"], "metadatas": [{"segment": "r"}]},
        RuntimeError("batch error"),
    ]
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer1(palace_path="/fake")
        result = layer.generate()

    assert "ESSENTIAL STORY" in result


# ── Layer2 — mocked chromadb ────────────────────────────────────────────


def test_layer2_no_palace():
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent/palace"
        layer = Layer2(palace_path="/nonexistent/palace")
        result = layer.retrieve(namespace="test")
    assert "No memory store found" in result


def test_layer2_retrieve_with_namespace():
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "documents": ["Some memory about the project"],
        "metadatas": [{"segment": "backend", "source_file": "notes.txt"}],
    }
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(namespace="project")

    assert "ON-DEMAND" in result
    assert "memory about the project" in result


def test_layer2_retrieve_with_room():
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "documents": ["Backend architecture notes"],
        "metadatas": [{"segment": "architecture", "source_file": "arch.txt"}],
    }
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(segment="architecture")

    assert "ON-DEMAND" in result


def test_layer2_retrieve_namespace_and_segment():
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "documents": ["Filtered result"],
        "metadatas": [{"segment": "backend", "source_file": "x.txt"}],
    }
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(namespace="proj", segment="backend")

    assert "ON-DEMAND" in result
    call_kwargs = mock_col.get.call_args[1]
    assert "$and" in call_kwargs.get("where", {})


def test_layer2_retrieve_empty():
    mock_col = MagicMock()
    mock_col.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(namespace="missing")

    assert "No chunks found" in result


def test_layer2_retrieve_no_filter():
    mock_col = MagicMock()
    mock_col.get.return_value = {"documents": [], "metadatas": []}
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        layer.retrieve()

    # No where filter should be passed
    call_kwargs = mock_col.get.call_args[1]
    assert "where" not in call_kwargs


def test_layer2_retrieve_error():
    mock_col = MagicMock()
    mock_col.get.side_effect = RuntimeError("db error")
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(namespace="test")

    assert "Retrieval error" in result


def test_layer2_truncates_long_snippets():
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "documents": ["B" * 400],
        "metadatas": [{"segment": "r", "source_file": "s.txt"}],
    }
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer2(palace_path="/fake")
        result = layer.retrieve(namespace="test")

    assert "..." in result


# ── Layer3 — mocked chromadb ────────────────────────────────────────────


def _mock_query_results(docs, metas, dists):
    return {
        "documents": [docs],
        "metadatas": [metas],
        "distances": [dists],
    }


def test_layer3_no_palace():
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent/palace"
        layer = Layer3(palace_path="/nonexistent/palace")
        result = layer.search("test query")
    assert "No memory store found" in result


def test_layer3_search_raw_no_palace():
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent/palace"
        layer = Layer3(palace_path="/nonexistent/palace")
        result = layer.search_raw("test query")
    assert result == []


def test_layer3_search_with_results():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["Found this important memory"],
        [{"namespace": "project", "segment": "backend", "source_file": "notes.txt"}],
        [0.2],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        result = layer.search("important")

    assert "SEARCH RESULTS" in result
    assert "important memory" in result
    assert "sim=0.8" in result


def test_layer3_search_no_results():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results([], [], [])
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        result = layer.search("nothing")

    assert "No results found" in result


def test_layer3_search_with_namespace_filter():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["result"],
        [{"namespace": "proj", "segment": "r"}],
        [0.1],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        layer.search("q", namespace="proj")

    call_kwargs = mock_col.query.call_args[1]
    assert call_kwargs["where"] == {"namespace": "proj"}


def test_layer3_search_with_room_filter():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["result"],
        [{"namespace": "w", "segment": "backend"}],
        [0.1],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        layer.search("q", segment="backend")

    call_kwargs = mock_col.query.call_args[1]
    assert call_kwargs["where"] == {"segment": "backend"}


def test_layer3_search_with_namespace_and_segment():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["result"],
        [{"namespace": "proj", "segment": "backend"}],
        [0.1],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        layer.search("q", namespace="proj", segment="backend")

    call_kwargs = mock_col.query.call_args[1]
    assert "$and" in call_kwargs["where"]


def test_layer3_search_error():
    mock_col = MagicMock()
    mock_col.query.side_effect = RuntimeError("search failed")
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        result = layer.search("q")

    assert "Search error" in result


def test_layer3_search_truncates_long_docs():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["C" * 400],
        [{"namespace": "w", "segment": "r", "source_file": "s.txt"}],
        [0.1],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        result = layer.search("q")

    assert "..." in result


def test_layer3_search_raw_returns_dicts():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["doc text"],
        [{"namespace": "proj", "segment": "backend", "source_file": "f.txt"}],
        [0.3],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        hits = layer.search_raw("q")

    assert len(hits) == 1
    assert hits[0]["text"] == "doc text"
    assert hits[0]["namespace"] == "proj"
    assert hits[0]["similarity"] == 0.7
    assert "metadata" in hits[0]


def test_layer3_search_raw_with_filters():
    mock_col = MagicMock()
    mock_col.query.return_value = _mock_query_results(
        ["doc"],
        [{"namespace": "w", "segment": "r"}],
        [0.1],
    )
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        layer.search_raw("q", namespace="w", segment="r")

    call_kwargs = mock_col.query.call_args[1]
    assert "$and" in call_kwargs["where"]


def test_layer3_search_raw_error():
    mock_col = MagicMock()
    mock_col.query.side_effect = RuntimeError("fail")
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        layer = Layer3(palace_path="/fake")
        result = layer.search_raw("q")

    assert result == []


# ── MemoryStack ─────────────────────────────────────────────────────────


def test_memory_stack_wake_up(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    with patch("memovich.layers.MemovichConfig") as mock_cfg:
        mock_cfg.return_value.palace_path = "/nonexistent"
        stack = MemoryStack(
            palace_path="/nonexistent",
            identity_path=str(identity_file),
        )
        result = stack.wake_up()

    assert "Atlas" in result
    # L1 will say no palace found
    assert "No palace" in result or "No memories" in result


def test_memory_stack_wake_up_with_namespace(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    with patch("memovich.layers.MemovichConfig") as mock_cfg:
        mock_cfg.return_value.palace_path = "/nonexistent"
        stack = MemoryStack(
            palace_path="/nonexistent",
            identity_path=str(identity_file),
        )
        result = stack.wake_up(namespace="my_project")

    assert stack.l1.namespace == "my_project"
    assert "Atlas" in result


def test_memory_stack_recall(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent"
        stack = MemoryStack(
            palace_path="/nonexistent",
            identity_path=str(identity_file),
        )
        result = stack.recall(namespace="test")

    assert "No memory store found" in result


def test_memory_stack_search(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", side_effect=Exception("missing")),
    ):
        mock_cfg.return_value.palace_path = "/nonexistent"
        stack = MemoryStack(
            palace_path="/nonexistent",
            identity_path=str(identity_file),
        )
        result = stack.search("test query")

    assert "No memory store found" in result


def test_memory_stack_status(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    with patch("memovich.layers.MemovichConfig") as mock_cfg:
        mock_cfg.return_value.palace_path = "/nonexistent"
        stack = MemoryStack(
            palace_path="/nonexistent",
            identity_path=str(identity_file),
        )
        result = stack.status()

    assert result["palace_path"] == "/nonexistent"
    assert result["total_chunks"] == 0
    assert "L0_identity" in result
    assert "L1_essential" in result
    assert "L2_on_demand" in result
    assert "L3_deep_search" in result


def test_memory_stack_status_with_palace(tmp_path):
    identity_file = tmp_path / "identity.txt"
    identity_file.write_text("I am Atlas.")

    mock_col = MagicMock()
    mock_col.count.return_value = 42
    with (
        patch("memovich.layers.MemovichConfig") as mock_cfg,
        patch("memovich.layers._get_collection", return_value=mock_col),
    ):
        mock_cfg.return_value.palace_path = "/fake"
        stack = MemoryStack(
            palace_path="/fake",
            identity_path=str(identity_file),
        )
        result = stack.status()

    assert result["total_chunks"] == 42
    assert result["L0_identity"]["exists"] is True
