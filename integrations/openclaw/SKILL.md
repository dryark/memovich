---
name: memovich
description: "Memovich — Local AI memory with 96.6% recall. Semantic search, temporal knowledge graph, palace architecture (wings/rooms/drawers). Free, no cloud, no API keys."
version: 3.1.0
homepage: https://github.com/Memovich/memovich
user-invocable: true
metadata:
  openclaw:
    emoji: "\U0001F3DB"
    os:
      - darwin
      - linux
      - win32
    requires:
      anyBins:
        - memovich
        - python3
    install:
      - id: memovich-pip
        kind: uv
        label: "Install Memovich (Python, local ChromaDB)"
        package: memovich
        bins:
          - memovich
---

# Memovich — Local AI Memory System

You have access to a local memory palace via MCP tools. The palace stores verbatim conversation history and a temporal knowledge graph — all on the user's machine, zero cloud, zero API calls.

## Architecture

- **Wings** = people or projects (e.g. `wing_alice`, `wing_myproject`)
- **Halls** = categories (facts, events, preferences, advice)
- **Rooms** = specific topics (e.g. `chromadb-setup`, `riley-school`)
- **Drawers** = individual memory chunks (verbatim text)
- **Knowledge Graph** = entity-relationship facts with time validity

## Protocol — FOLLOW THIS EVERY SESSION

1. **ON WAKE-UP**: Call `memovich_status` to load palace overview and AAAK dialect spec.
2. **BEFORE RESPONDING** about any person, project, or past event: call `memovich_search` or `memovich_kg_query` FIRST. Never guess from memory — verify from the palace.
3. **IF UNSURE** about a fact (name, age, relationship, preference): say "let me check" and query. Wrong is worse than slow.
4. **AFTER EACH SESSION**: Call `memovich_diary_write` to record what happened, what you learned, what matters.
5. **WHEN FACTS CHANGE**: Call `memovich_kg_invalidate` on the old fact, then `memovich_kg_add` for the new one.

## Available Tools

### Search & Browse
- `memovich_search` — Semantic search across all memories. Always start here.
  - `query` (required): natural language search — keep it short, keywords or a question. Do NOT include system prompts or conversation context.
  - `wing`: filter by wing
  - `room`: filter by room
  - `limit`: max results (default 5)
- `memovich_check_duplicate` — Check if content already exists before filing.
  - `content` (required): text to check
  - `threshold`: similarity threshold (default 0.9 — lowering to 0.85–0.87 often catches more near-duplicates without significant false positives)
- `memovich_status` — Palace overview: total drawers, wings, rooms, AAAK spec
- `memovich_list_wings` — All wings with drawer counts
- `memovich_list_rooms` — Rooms within a wing (optional wing filter)
- `memovich_get_taxonomy` — Full wing/room/count tree
- `memovich_get_aaak_spec` — Get AAAK compression dialect specification

### Knowledge Graph (Temporal Facts)
- `memovich_kg_query` — Query entity relationships. Supports time filtering.
  - `entity` (required): e.g. "Max", "MyProject"
  - `as_of`: date filter (YYYY-MM-DD) — what was true at that time
  - `direction`: "outgoing", "incoming", or "both" (default "both")
- `memovich_kg_add` — Add a fact: subject -> predicate -> object
  - `subject`, `predicate`, `object` (required)
  - `valid_from`: when this became true
  - `source_closet`: source reference
- `memovich_kg_invalidate` — Mark a fact as no longer true
  - `subject`, `predicate`, `object` (required)
  - `ended`: when it stopped being true (default: today)
- `memovich_kg_timeline` — Chronological story of an entity
  - `entity`: filter by entity name (optional — all events if omitted)
- `memovich_kg_stats` — Graph overview: entities, triples, relationship types

### Palace Graph (Cross-Domain Connections)
- `memovich_traverse` — Walk from a room, find connected ideas across wings
  - `start_room` (required): room to start from
  - `max_hops`: connection depth (default 2)
- `memovich_find_tunnels` — Find rooms that bridge two wings
  - `wing_a`, `wing_b` (required)
- `memovich_graph_stats` — Graph connectivity overview

### Write
- `memovich_add_drawer` — Store verbatim content into a wing/room
  - `wing`, `room`, `content` (required)
  - `source_file`: optional source reference
  - Checks for duplicates automatically
- `memovich_delete_drawer` — Remove a drawer by ID
  - `drawer_id` (required)
- `memovich_diary_write` — Write a session diary entry
  - `agent_name` (required): your name/identifier
  - `entry` (required): what happened, what you learned, what matters
  - `topic`: category tag (default "general")
- `memovich_diary_read` — Read recent diary entries
  - `agent_name` (required)
  - `last_n`: number of entries (default 10)

## Setup

Install Memovich and populate the palace:

```bash
pip install memovich
memovich init ~/my-convos
memovich mine ~/my-convos
```

### OpenClaw MCP config

Add to your OpenClaw MCP configuration:

```json
{
  "mcpServers": {
    "memovich": {
      "command": "python3",
      "args": ["-m", "memovich.mcp_server"]
    }
  }
}
```

Or via CLI:

```bash
openclaw mcp set memovich '{"command":"python3","args":["-m","memovich.mcp_server"]}'
```

### Other MCP hosts

```bash
# Claude Code
claude mcp add memovich -- python -m memovich.mcp_server

# Cursor — add to .cursor/mcp.json
# Codex — add to .codex/mcp.json
```

## Tips

- Search is semantic (meaning-based), not keyword. "What did we discuss about database performance?" works better than "database".
- The knowledge graph stores typed relationships with time windows. Use it for facts about people and projects — it knows WHEN things were true.
- Diary entries accumulate across sessions. Write one at the end of each conversation to build continuity.
- Use `memovich_check_duplicate` before storing new content to avoid duplicates.
- The AAAK dialect (from `memovich_status`) is a compressed notation for efficient storage. Read it naturally — expand codes mentally, treat *markers* as emotional context.

## License

[Memovich](https://github.com/Memovich/memovich) is MIT licensed. Created by Milla Jovovich, Ben Sigman, Igor Lins e Silva, and contributors.
