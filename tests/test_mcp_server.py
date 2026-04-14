"""
test_mcp_server.py — Tests for the MCP server tool handlers and dispatch.

Tests each tool handler directly (unit-level) and the handle_request
dispatch layer (integration-level). Uses isolated palace + KG fixtures
via monkeypatch to avoid touching real data.
"""

import json

import pytest


def _patch_mcp_server(monkeypatch, config, kg):
    """Patch the mcp_server module globals to use test fixtures."""
    from memovich import mcp_server

    monkeypatch.setattr(mcp_server, "_config", config)
    monkeypatch.setattr(mcp_server, "_kg", kg)


def _ensure_collection(palace_path, config, create=False):
    """Open the test palace collection via the configured vector backend."""
    from memovich.palace import get_collection

    return get_collection(palace_path, create=create, config=config)


# ── Protocol Layer ──────────────────────────────────────────────────────


class TestHandleRequest:
    def test_initialize(self):
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["serverInfo"]["name"] == "memovich"
        assert resp["id"] == 1

    def test_initialize_negotiates_client_version(self):
        from memovich.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
        assert resp["result"]["protocolVersion"] == "2025-11-25"

    def test_initialize_negotiates_older_supported_version(self):
        from memovich.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "2025-03-26"},
            }
        )
        assert resp["result"]["protocolVersion"] == "2025-03-26"

    def test_initialize_unknown_version_falls_back_to_latest(self):
        from memovich.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "initialize",
                "id": 1,
                "params": {"protocolVersion": "9999-12-31"},
            }
        )
        from memovich.mcp_server import SUPPORTED_PROTOCOL_VERSIONS

        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]

    def test_initialize_missing_version_uses_oldest(self):
        from memovich.mcp_server import handle_request, SUPPORTED_PROTOCOL_VERSIONS

        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        assert resp["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[-1]

    def test_notifications_initialized_returns_none(self):
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "notifications/initialized", "id": None, "params": {}})
        assert resp is None

    def test_ping_returns_empty_result(self):
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "ping", "id": 11, "params": {}})
        assert resp["id"] == 11
        assert resp["result"] == {}

    def test_tools_list(self):
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "memovich_status" in names
        assert "memovich_search" in names
        assert "memovich_add_chunk" in names
        assert "memovich_kg_add" in names

    def test_null_arguments_does_not_hang(self, monkeypatch, config, palace_path, seeded_kg):
        """Sending arguments: null should return a result, not hang (#394)."""
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import handle_request

        _ensure_collection(palace_path, config, create=True)
        resp = handle_request(
            {
                "method": "tools/call",
                "id": 10,
                "params": {"name": "memovich_status", "arguments": None},
            }
        )
        assert "error" not in resp
        assert resp["result"] is not None

    def test_unknown_tool(self):
        from memovich.mcp_server import handle_request

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 3,
                "params": {"name": "nonexistent_tool", "arguments": {}},
            }
        )
        assert resp["error"]["code"] == -32601

    def test_unknown_method(self):
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "unknown/method", "id": 4, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_any_notification_returns_none(self):
        """All notifications/* methods should return None (no response)."""
        from memovich.mcp_server import handle_request

        for method in [
            "notifications/initialized",
            "notifications/cancelled",
            "notifications/progress",
            "notifications/roots/list_changed",
        ]:
            resp = handle_request({"method": method, "params": {}})
            assert resp is None, f"{method} should return None"

    def test_unknown_method_no_id_returns_none(self):
        """Messages without id (notifications) must never get a response."""
        from memovich.mcp_server import handle_request

        resp = handle_request({"method": "unknown/thing", "params": {}})
        assert resp is None

    def test_malformed_method_none(self):
        """method=None or missing should not crash."""
        from memovich.mcp_server import handle_request

        # Explicit None
        resp = handle_request({"method": None, "params": {}})
        assert resp is None  # no id → no response

        # Missing method entirely
        resp = handle_request({"params": {}})
        assert resp is None

        # method=None with id → should return error, not crash
        resp = handle_request({"method": None, "id": 99, "params": {}})
        assert resp["error"]["code"] == -32601

    def test_tools_call_dispatches(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import handle_request

        # Create a collection so status works
        _ensure_collection(palace_path, config, create=True)

        resp = handle_request(
            {
                "method": "tools/call",
                "id": 5,
                "params": {"name": "memovich_status", "arguments": {}},
            }
        )
        assert "result" in resp
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "total_chunks" in content


# ── Read Tools ──────────────────────────────────────────────────────────


class TestReadTools:
    def test_status_empty_palace(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_status

        result = tool_status()
        assert result["total_chunks"] == 0
        assert result["namespaces"] == {}

    def test_status_with_data(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_status

        result = tool_status()
        assert result["total_chunks"] == 4
        assert "project" in result["namespaces"]
        assert "notes" in result["namespaces"]

    def test_list_namespaces(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_namespaces

        result = tool_list_namespaces()
        assert result["namespaces"]["project"] == 3
        assert result["namespaces"]["notes"] == 1

    def test_list_segments_all(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_segments

        result = tool_list_segments()
        assert "backend" in result["segments"]
        assert "frontend" in result["segments"]
        assert "planning" in result["segments"]

    def test_list_segments_filtered(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_segments

        result = tool_list_segments(namespace="project")
        assert "backend" in result["segments"]
        assert "planning" not in result["segments"]

    def test_get_taxonomy(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_get_taxonomy

        result = tool_get_taxonomy()
        assert result["taxonomy"]["project"]["backend"] == 2
        assert result["taxonomy"]["project"]["frontend"] == 1
        assert result["taxonomy"]["notes"]["planning"] == 1

    def test_no_palace_returns_error(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda create=False: None)
        from memovich.mcp_server import tool_status

        result = tool_status()
        assert "error" in result


# ── Search Tool ─────────────────────────────────────────────────────────


class TestSearchTool:
    def test_search_basic(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_search

        result = tool_search(query="JWT authentication tokens")
        assert "results" in result
        assert len(result["results"]) > 0
        # Top result should be the auth drawer
        top = result["results"][0]
        assert "JWT" in top["text"] or "authentication" in top["text"].lower()

    def test_search_with_namespace_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_search

        result = tool_search(query="planning", namespace="notes")
        assert all(r["namespace"] == "notes" for r in result["results"])

    def test_search_with_segment_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_search

        result = tool_search(query="database", segment="backend")
        assert all(r["segment"] == "backend" for r in result["results"])

    def test_search_min_similarity_backwards_compat(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        """Old min_similarity param still works via backwards-compat shim."""
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_search

        # Old name should work
        result = tool_search(query="JWT", min_similarity=1.5)
        assert "results" in result

        # Old name takes precedence when both provided
        result_strict = tool_search(query="JWT", max_distance=999.0, min_similarity=0.01)
        result_loose = tool_search(query="JWT", max_distance=0.01, min_similarity=999.0)
        assert len(result_strict["results"]) <= len(result_loose["results"])

    def test_list_segments_rejects_invalid_namespace(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda *args, **kwargs: pytest.fail())

        result = mcp_server.tool_list_segments(namespace="../etc/passwd")
        assert "error" in result

    def test_search_rejects_invalid_segment(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "search_memories", lambda *args, **kwargs: pytest.fail())

        result = mcp_server.tool_search(query="JWT", segment="../backend")
        assert "error" in result

    def test_list_chunks_rejects_invalid_namespace(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda *args, **kwargs: pytest.fail())

        result = mcp_server.tool_list_chunks(namespace="../notes")
        assert "error" in result

    def test_find_tunnels_rejects_invalid_namespace(self, monkeypatch, config, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda *args, **kwargs: pytest.fail())

        result = mcp_server.tool_find_tunnels(namespace_a="../project")
        assert "error" in result

    def test_wal_redacts_sensitive_fields(self, monkeypatch, config, kg, tmp_path):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        wal_file = tmp_path / "write_log.jsonl"
        monkeypatch.setattr(mcp_server, "_WAL_FILE", wal_file)

        mcp_server._wal_log(
            "test",
            {"content": "secret note", "query": "private search", "safe": "ok"},
        )

        entry = json.loads(wal_file.read_text().strip())
        assert entry["params"]["content"].startswith("[REDACTED")
        assert entry["params"]["query"].startswith("[REDACTED")
        assert entry["params"]["safe"] == "ok"


# ── Write Tools ─────────────────────────────────────────────────────────


class TestWriteTools:
    def test_add_chunk(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_add_chunk

        result = tool_add_chunk(
            namespace="test_namespace",
            segment="test_segment",
            content="This is a test memory about Python decorators and metaclasses.",
        )
        assert result["success"] is True
        assert result["namespace"] == "test_namespace"
        assert result["segment"] == "test_segment"
        assert result["chunk_id"].startswith("chunk_test_namespace_test_segment_")

    def test_add_chunk_duplicate_detection(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_add_chunk

        content = "This is a unique test memory about Rust ownership and borrowing."
        result1 = tool_add_chunk(namespace="w", segment="r", content=content)
        assert result1["success"] is True

        result2 = tool_add_chunk(namespace="w", segment="r", content=content)
        assert result2["success"] is True
        assert result2["reason"] == "already_exists"

    def test_add_chunk_shared_header_no_collision(self, monkeypatch, config, palace_path, kg):
        """Documents sharing a >100-char header must get distinct IDs (full-content hash)."""
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_add_chunk

        header = "# ACME Corp Knowledge Base\n**Project:** Alpha | **Team:** Backend | **Status:** Active\n\n"
        doc1 = (
            header
            + "Decision: Use PostgreSQL for primary storage. Rationale: ACID compliance required."
        )
        doc2 = header + "Decision: Use Redis for session caching. Rationale: sub-ms latency needed."

        result1 = tool_add_chunk(namespace="work", segment="decisions", content=doc1)
        result2 = tool_add_chunk(namespace="work", segment="decisions", content=doc2)

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["chunk_id"] != result2["chunk_id"], (
            "Documents with shared header but different content must have distinct chunk IDs"
        )

    def test_delete_chunk(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_delete_chunk

        result = tool_delete_chunk("chunk_proj_backend_aaa")
        assert result["success"] is True
        assert seeded_collection.count() == 3

    def test_delete_chunk_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_delete_chunk

        result = tool_delete_chunk("nonexistent_chunk")
        assert result["success"] is False

    def test_check_duplicate(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_check_duplicate

        # Exact match text from seeded_collection should be flagged
        result = tool_check_duplicate(
            "The authentication module uses JWT tokens for session management. "
            "Tokens expire after 24 hours. Refresh tokens are stored in HttpOnly cookies.",
            threshold=0.5,
        )
        assert result["is_duplicate"] is True

        # Unrelated content should not be flagged
        result = tool_check_duplicate(
            "Black holes emit Hawking radiation at the event horizon.",
            threshold=0.99,
        )
        assert result["is_duplicate"] is False

    def test_get_chunk(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_get_chunk

        result = tool_get_chunk("chunk_proj_backend_aaa")
        assert result["chunk_id"] == "chunk_proj_backend_aaa"
        assert result["namespace"] == "project"
        assert result["segment"] == "backend"
        assert "JWT tokens" in result["content"]

    def test_get_chunk_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_get_chunk

        result = tool_get_chunk("nonexistent_chunk")
        assert "error" in result

    def test_list_chunks(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_chunks

        result = tool_list_chunks()
        assert result["count"] == 4
        assert len(result["chunks"]) == 4

    def test_list_chunks_with_namespace_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_chunks

        result = tool_list_chunks(namespace="project")
        assert result["count"] == 3
        assert all(d["namespace"] == "project" for d in result["chunks"])

    def test_list_chunks_with_segment_filter(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_chunks

        result = tool_list_chunks(namespace="project", segment="backend")
        assert result["count"] == 2
        assert all(d["segment"] == "backend" for d in result["chunks"])

    def test_list_chunks_pagination(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_chunks

        result = tool_list_chunks(limit=2, offset=0)
        assert result["count"] == 2
        assert result["limit"] == 2
        assert result["offset"] == 0

    def test_list_chunks_negative_offset_clamped(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_list_chunks

        result = tool_list_chunks(offset=-5)
        assert result["offset"] == 0

    def test_update_chunk_content(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_get_chunk, tool_update_chunk

        result = tool_update_chunk("chunk_proj_backend_aaa", content="Updated content about auth.")
        assert result["success"] is True

        fetched = tool_get_chunk("chunk_proj_backend_aaa")
        assert fetched["content"] == "Updated content about auth."

    def test_update_chunk_namespace_and_segment(
        self, monkeypatch, config, palace_path, seeded_collection, kg
    ):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_update_chunk

        result = tool_update_chunk(
            "chunk_proj_backend_aaa", namespace="new_namespace", segment="new_segment"
        )
        assert result["success"] is True
        assert result["namespace"] == "new_namespace"
        assert result["segment"] == "new_segment"

    def test_update_chunk_not_found(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_update_chunk

        result = tool_update_chunk("nonexistent_chunk", content="hello")
        assert result["success"] is False

    def test_update_chunk_noop(self, monkeypatch, config, palace_path, seeded_collection, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_update_chunk

        result = tool_update_chunk("chunk_proj_backend_aaa")
        assert result["success"] is True
        assert result.get("noop") is True


# ── KG Tools ────────────────────────────────────────────────────────────


class TestKGTools:
    def test_kg_add(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich.mcp_server import tool_kg_add

        result = tool_kg_add(
            subject="Alice",
            predicate="likes",
            object="coffee",
            valid_from="2025-01-01",
        )
        assert result["success"] is True

    def test_kg_query(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import tool_kg_query

        result = tool_kg_query(entity="Max")
        assert result["count"] > 0

    def test_kg_invalidate(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import tool_kg_invalidate

        result = tool_kg_invalidate(
            subject="Max",
            predicate="does",
            object="chess",
            ended="2026-03-01",
        )
        assert result["success"] is True

    def test_kg_timeline(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import tool_kg_timeline

        result = tool_kg_timeline(entity="Alice")
        assert result["count"] > 0

    def test_kg_stats(self, monkeypatch, config, palace_path, seeded_kg):
        _patch_mcp_server(monkeypatch, config, seeded_kg)
        from memovich.mcp_server import tool_kg_stats

        result = tool_kg_stats()
        assert result["entities"] >= 4


# ── Diary Tools ─────────────────────────────────────────────────────────


class TestDiaryTools:
    def test_diary_write_and_read(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_diary_write, tool_diary_read

        w = tool_diary_write(
            agent_name="TestAgent",
            entry="Today we discussed authentication patterns.",
            topic="architecture",
        )
        assert w["success"] is True
        assert w["agent"] == "TestAgent"

        r = tool_diary_read(agent_name="TestAgent")
        assert r["total"] == 1
        assert r["entries"][0]["topic"] == "architecture"
        assert "authentication" in r["entries"][0]["content"]

    def test_diary_read_empty(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich.mcp_server import tool_diary_read

        r = tool_diary_read(agent_name="Nobody")
        assert r["entries"] == []


# ── Cache invalidation (storage signature) ────────────────────────────


class TestCacheInvalidation:
    """Tests for _get_collection refresh when storage signature changes."""

    def test_storage_signature_change_refreshes_cache(self, monkeypatch, config, palace_path, kg):
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        _n = [0]

        def fake_sig(c):
            _n[0] += 1
            return ("memory", 0, float(_n[0]))

        monkeypatch.setattr(mcp_server, "storage_signature_for_config", fake_sig)

        _ensure_collection(palace_path, config, create=True)
        mcp_server._get_collection()
        assert mcp_server._storage_sig == ("memory", 0, 1.0)

        mcp_server._get_collection()
        assert mcp_server._storage_sig == ("memory", 0, 2.0)

    def test_reconnect_reports_failure_when_no_palace(self, monkeypatch, config, kg):
        """tool_reconnect should report failure when no collection is available."""
        _patch_mcp_server(monkeypatch, config, kg)
        from memovich import mcp_server

        monkeypatch.setattr(mcp_server, "_get_collection", lambda create=False: None)

        result = mcp_server.tool_reconnect()
        assert result["success"] is False
        assert "No palace found" in result["message"]
        assert result["chunks"] == 0

    def test_reconnect_reports_success(self, monkeypatch, config, palace_path, kg):
        """tool_reconnect should report success with chunk count."""
        _patch_mcp_server(monkeypatch, config, kg)
        _ensure_collection(palace_path, config, create=True)
        from memovich import mcp_server

        result = mcp_server.tool_reconnect()
        assert result["success"] is True
        assert "Reconnected" in result["message"]
        assert isinstance(result["chunks"], int)
