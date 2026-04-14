"""Tests for memovich.palace_graph — graph traversal layer.

All vector access is mocked — no real database needed.
"""

from unittest.mock import MagicMock, patch


def _make_fake_collection(metadatas, ids=None):
    """Create a mock collection that returns the given metadata in batches."""
    if ids is None:
        ids = [f"id_{i}" for i in range(len(metadatas))]

    col = MagicMock()
    col.count.return_value = len(metadatas)

    def fake_get(limit=1000, offset=0, include=None):
        batch_meta = metadatas[offset : offset + limit]
        batch_ids = ids[offset : offset + limit]
        return {"ids": batch_ids, "metadatas": batch_meta}

    col.get.side_effect = fake_get
    return col


# Patch chromadb at import time so palace_graph can be imported
with patch.dict("sys.modules", {"chromadb": MagicMock()}):
    from memovich.palace_graph import (
        _fuzzy_match,
        build_graph,
        find_tunnels,
        graph_stats,
        traverse,
    )


class TestBuildGraph:
    def test_empty_collection(self):
        col = _make_fake_collection([])
        nodes, edges = build_graph(col=col)
        assert nodes == {}
        assert edges == []

    def test_falsy_collection(self):
        """When col is explicitly falsy, build_graph returns empty."""
        nodes, edges = build_graph(col=0)
        assert nodes == {}
        assert edges == []

    def test_single_namespace_no_edges(self):
        col = _make_fake_collection(
            [
                {
                    "segment": "auth",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-01",
                },
                {
                    "segment": "auth",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-02",
                },
            ]
        )
        nodes, edges = build_graph(col=col)
        assert "auth" in nodes
        assert nodes["auth"]["count"] == 2
        assert edges == []

    def test_multi_namespace_creates_edges(self):
        col = _make_fake_collection(
            [
                {
                    "segment": "chromadb",
                    "namespace": "ns_code",
                    "hall": "databases",
                    "date": "2026-01-01",
                },
                {
                    "segment": "chromadb",
                    "namespace": "ns_project",
                    "hall": "databases",
                    "date": "2026-01-02",
                },
            ]
        )
        nodes, edges = build_graph(col=col)
        assert "chromadb" in nodes
        assert len(edges) == 1
        assert edges[0]["namespace_a"] == "ns_code"
        assert edges[0]["namespace_b"] == "ns_project"
        assert edges[0]["hall"] == "databases"

    def test_general_segment_excluded(self):
        col = _make_fake_collection(
            [
                {"segment": "general", "namespace": "ns_code", "hall": "misc", "date": ""},
            ]
        )
        nodes, edges = build_graph(col=col)
        assert "general" not in nodes

    def test_missing_namespace_excluded(self):
        col = _make_fake_collection(
            [
                {"segment": "orphan", "namespace": "", "hall": "misc", "date": ""},
            ]
        )
        nodes, edges = build_graph(col=col)
        assert "orphan" not in nodes

    def test_dates_capped_at_five(self):
        col = _make_fake_collection(
            [
                {"segment": "busy", "namespace": "w", "hall": "h", "date": f"2026-01-{i:02d}"}
                for i in range(1, 10)
            ]
        )
        nodes, _ = build_graph(col=col)
        assert len(nodes["busy"]["dates"]) <= 5


class TestTraverse:
    def _build_col(self):
        return _make_fake_collection(
            [
                {
                    "segment": "auth",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-01",
                },
                {
                    "segment": "login",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-01",
                },
                {"segment": "deploy", "namespace": "ns_ops", "hall": "infra", "date": "2026-01-01"},
            ]
        )

    def test_traverse_known_segment(self):
        col = self._build_col()
        result = traverse("auth", col=col)
        assert isinstance(result, list)
        segments = [r["segment"] for r in result]
        assert "auth" in segments
        assert "login" in segments

    def test_traverse_unknown_segment(self):
        col = self._build_col()
        result = traverse("nonexistent", col=col)
        assert isinstance(result, dict)
        assert "error" in result
        assert "suggestions" in result

    def test_traverse_max_hops(self):
        col = self._build_col()
        result = traverse("auth", col=col, max_hops=0)
        assert len(result) == 1
        assert result[0]["segment"] == "auth"


class TestFindTunnels:
    def _build_tunnel_col(self):
        return _make_fake_collection(
            [
                {"segment": "chromadb", "namespace": "ns_code", "hall": "db", "date": "2026-01-01"},
                {
                    "segment": "chromadb",
                    "namespace": "ns_project",
                    "hall": "db",
                    "date": "2026-01-02",
                },
                {
                    "segment": "auth",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-01",
                },
            ]
        )

    def test_find_all_tunnels(self):
        col = self._build_tunnel_col()
        tunnels = find_tunnels(col=col)
        assert len(tunnels) == 1
        assert tunnels[0]["segment"] == "chromadb"

    def test_find_tunnels_with_namespace_filter(self):
        col = self._build_tunnel_col()
        tunnels = find_tunnels(namespace_a="ns_code", col=col)
        assert len(tunnels) == 1

    def test_find_tunnels_no_match(self):
        col = self._build_tunnel_col()
        tunnels = find_tunnels(namespace_a="ns_nonexistent", col=col)
        assert tunnels == []

    def test_find_tunnels_both_namespaces(self):
        col = self._build_tunnel_col()
        tunnels = find_tunnels(namespace_a="ns_code", namespace_b="ns_project", col=col)
        assert len(tunnels) == 1
        assert tunnels[0]["segment"] == "chromadb"


class TestGraphStats:
    def test_empty_graph(self):
        col = _make_fake_collection([])
        stats = graph_stats(col=col)
        assert stats["total_segments"] == 0
        assert stats["tunnel_segments"] == 0
        assert stats["total_edges"] == 0

    def test_stats_with_data(self):
        col = _make_fake_collection(
            [
                {"segment": "chromadb", "namespace": "ns_code", "hall": "db", "date": "2026-01-01"},
                {
                    "segment": "chromadb",
                    "namespace": "ns_project",
                    "hall": "db",
                    "date": "2026-01-02",
                },
                {
                    "segment": "auth",
                    "namespace": "ns_code",
                    "hall": "security",
                    "date": "2026-01-01",
                },
            ]
        )
        stats = graph_stats(col=col)
        assert stats["total_segments"] == 2
        assert stats["tunnel_segments"] == 1
        assert stats["total_edges"] == 1
        assert "ns_code" in stats["segments_per_namespace"]


class TestFuzzyMatch:
    def test_exact_substring(self):
        nodes = {"chromadb-setup": {}, "other": {}}
        assert "chromadb-setup" in _fuzzy_match("chromadb", nodes)

    def test_hyphen_token(self):
        nodes = {"my-topic-here": {}}
        assert "my-topic-here" in _fuzzy_match("topic", nodes)
