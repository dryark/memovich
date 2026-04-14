# Memovich

### An AI memory system.

This system uses tiered memory organization.

**Raw verbatim storage** — Memovich stores your exchanges in a vector store without summarization or extraction.

**AAAK** — A crappy abbreviation system that is legacy from Memovich. Will be stripped out.

## Quick Start

```bash
pip install memovich

# Init
memovich init ~/projects/myapp

# Mine
memovich mine ~/projects/myapp                    # projects — code, docs, notes
memovich mine ~/chats/ --mode convos              # convos — Claude, ChatGPT, Slack exports
memovich mine ~/chats/ --mode convos --extract general  # general — classifies into decisions, milestones, problems

# Search
memovich search "why did we switch to GraphQL"

# Status
memovich status
```

Three mining modes: **projects** (code and docs), **convos** (conversation exports), and **general** (auto-classifies into decisions, preferences, milestones, problems, and emotional context).

## How To Use It

After the one-time setup ( install -> init -> mine ), you don't run Memovich commands manually. Your AI uses it for you. There are two ways, depending on which AI you use.

### With Claude Code

Native marketplace install:

```bash
claude plugin marketplace add dryark/memovich
claude plugin install --scope user memovich
```

Restart Claude Code, then type `/skills` to verify "memovich" appears.

### With Claude, ChatGPT, Cursor, Gemini (MCP-compatible tools)

```bash
# Connect Memovich once
claude mcp add memovich -- python -m memovich.mcp_server
```

Now your AI has 19 tools available through MCP. Ask it anything:

> *"What did we decide about auth last month?"*

Claude calls `memovich_search` automatically, gets verbatim results, and answers you. You never type `memovich search` again. The AI handles it.

Memovich also works natively with **Gemini CLI** (which handles the server and save hooks automatically) — see the [Gemini CLI Integration Guide](examples/gemini_cli_setup.md).

### With local models (Llama, Mistral, or any offline LLM)

Local models generally don't speak MCP yet. Two approaches:

**1. Wake-up command** — load your world into the model's context:

```bash
memovich wake-up > context.txt
# Paste context.txt into your local model's system prompt
```

This gives your local model ~170 tokens of critical facts (in AAAK if you prefer) before you ask a single question.

**2. CLI search** — query on demand, feed results into your prompt:

```bash
memovich search "auth decisions" > results.txt
# Include results.txt in your prompt
```

Or use the Python API:

```python
from memovich.searcher import search_memories
results = search_memories("auth decisions", palace_path="~/.memovich/palace")
# Inject into your local model's context
```

Either way — the stack runs offline. Vector store on your machine, Llama on your machine, shitacular AAAK for compression.

## Real-World Examples

### Solo developer across multiple projects

```bash
# Mine each project's conversations
memovich mine ~/chats/orion/  --mode convos --wing orion
memovich mine ~/chats/nova/   --mode convos --wing nova
memovich mine ~/chats/helios/ --mode convos --wing helios

# Six months later: "why did I use Postgres here?"
memovich search "database decision" --wing orion
# -> "Chose Postgres over SQLite because Orion needs concurrent writes
#    and the dataset will exceed 10GB. Decided 2025-11-03."

# Cross-project search
memovich search "rate limiting approach"
# → finds your approach in Orion AND Nova, shows the differences
```

### Team lead managing a product

```bash
# Mine Slack exports and AI conversations
memovich mine ~/exports/slack/ --mode convos --wing driftwood
memovich mine ~/.claude/projects/ --mode convos

# "What did Soren work on last sprint?"
memovich search "Soren sprint" --wing driftwood
# → 14 closets: OAuth refactor, dark mode, component library migration

# "Who decided to use Clerk?"
memovich search "Clerk decision" --wing driftwood
# → "Kai recommended Clerk over Auth0 — pricing + developer experience.
#    Team agreed 2026-01-15. Maya handling the migration."
```

### Before mining: split mega-files

Some transcript exports concatenate multiple sessions into one huge file:

```bash
memovich split ~/chats/                      # split into per-session files
memovich split ~/chats/ --dry-run            # preview first
memovich split ~/chats/ --min-sessions 3     # only split files with 3+ sessions
```

## Knowledge Graph

Temporal entity-relationship triples

```python
from memovich.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_triple("Kai", "works_on", "Orion", valid_from="2025-06-01")
kg.add_triple("Maya", "assigned_to", "auth-migration", valid_from="2026-01-15")
kg.add_triple("Maya", "completed", "auth-migration", valid_from="2026-02-01")

# What's Kai working on?
kg.query_entity("Kai")
# -> [Kai -> works_on -> Orion (current), Kai -> recommended -> Clerk (2026-01)]

# What was true in January?
kg.query_entity("Maya", as_of="2026-01-20")
# -> [Maya -> assigned_to -> auth-migration (active)]

# Timeline
kg.timeline("Orion")
# -> chronological story of the project
```

Facts have validity windows. When something stops being true, invalidate it:

```python
kg.invalidate("Kai", "works_on", "Orion", ended="2026-03-01")
```

Now queries for Kai's current work won't return Orion. Historical queries still will.

## Specialist Agents

Create agents that focus on specific areas. Each agent gets its own wing and diary in the palace — not in one giant global instructions file. Add 50 agents, your config stays the same size.

```
~/.memovich/agents/
  ├── reviewer.json       # code quality, patterns, bugs
  ├── architect.json      # design decisions, tradeoffs
  └── ops.json            # deploys, incidents, infra
```

Your agent instructions just need one line:

```
You have Memovich agents. Run memovich_list_agents to see them.
```

The AI discovers its agents from the palace at runtime. Each agent:

- **Has a focus** — what it pays attention to
- **Keeps a diary** — written in AAAK, persists across sessions
- **Builds expertise** — reads its own history to stay sharp in its domain

```
# Agent writes to its diary after a code review
memovich_diary_write("reviewer",
    "PR#42|auth.bypass.found|missing.middleware.check|pattern:3rd.time.this.quarter|★★★★")

# Agent reads back its history
memovich_diary_read("reviewer", last_n=10)
# -> last 10 findings
```

Each agent is a lens on your data. The reviewer remembers every bug pattern it's seen. The architect remembers every design decision. The ops agent remembers every incident. They don't share a scratchpad. They each maintain their own memory.

## MCP Server

```bash
# Via plugin (recommended)
claude plugin marketplace add dryark/memovich
claude plugin install --scope user memovich

# Or manually
claude mcp add memovich -- python -m memovich.mcp_server
```

### 19 Tools

**Palace (read)**

| Tool | What |
|------|------|
| `memovich_status` | Palace overview + AAAK spec + memory protocol |
| `memovich_list_wings` | Wings with counts |
| `memovich_list_rooms` | Rooms within a wing |
| `memovich_get_taxonomy` | Full wing → room → count tree |
| `memovich_search` | Semantic search with wing/room filters |
| `memovich_check_duplicate` | Check before filing |
| `memovich_get_aaak_spec` | AAAK dialect reference |

**Palace (write)**

| Tool | What |
|------|------|
| `memovich_add_drawer` | File verbatim content |
| `memovich_delete_drawer` | Remove by ID |

**Knowledge Graph**

| Tool | What |
|------|------|
| `memovich_kg_query` | Entity relationships with time filtering |
| `memovich_kg_add` | Add facts |
| `memovich_kg_invalidate` | Mark facts as ended |
| `memovich_kg_timeline` | Chronological entity story |
| `memovich_kg_stats` | Graph overview |

**Navigation**

| Tool | What |
|------|------|
| `memovich_traverse` | Walk the graph from a room across wings |
| `memovich_find_tunnels` | Find rooms bridging two wings |
| `memovich_graph_stats` | Graph connectivity overview |

**Agent Diary**

| Tool | What |
|------|------|
| `memovich_diary_write` | Write AAAK diary entry |
| `memovich_diary_read` | Read recent diary entries |

The AI learns AAAK and the memory protocol automatically from the `memovich_status` response. No manual configuration.

## Auto-Save Hooks

Two hooks for Claude Code that automatically save memories during work:

**Save Hook** — every 15 messages, triggers a structured save. Topics, decisions, quotes, code changes. Also regenerates the critical facts layer.

**PreCompact Hook** — fires before context compression. Emergency save before the window shrinks.

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/memovich/hooks/memovich_save_hook.sh"}]}],
    "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/memovich/hooks/memovich_precompact_hook.sh"}]}]
  }
}
```

**Optional auto-ingest:** Set the `MEMOVICH_DIR` environment variable to a directory path and the hooks will automatically run `memovich mine` on that directory during each save trigger (background on stop, synchronous on precompact).

## All Commands

```bash
# Setup
memovich init <dir>                              # guided onboarding + AAAK bootstrap

# Mining
memovich mine <dir>                              # mine project files
memovich mine <dir> --mode convos                # mine conversation exports
memovich mine <dir> --mode convos --wing myapp   # tag with a wing name

# Splitting
memovich split <dir>                             # split concatenated transcripts
memovich split <dir> --dry-run                   # preview

# Search
memovich search "query"                          # search everything
memovich search "query" --wing myapp             # within a wing
memovich search "query" --room auth-migration    # within a room

# Memory stack
memovich wake-up                                 # load L0 + L1 context
memovich wake-up --wing driftwood                # project-specific

# Compression
memovich compress --wing myapp                   # AAAK compress

# Status
memovich status                                  # palace overview

# MCP
memovich mcp                                     # show MCP setup command
```

All commands accept `--palace <path>` to override the default location.

## Configuration

### Global (`~/.memovich/config.json`)

```json
{
  "palace_path": "/custom/path/to/palace",
  "collection_name": "memovich_drawers",
  "people_map": {"Kai": "KAI", "Priya": "PRI"}
}
```

### Wing config (`~/.memovich/wing_config.json`)

Generated by `memovich init`. Maps your people and projects to wings:

```json
{
  "default_wing": "wing_general",
  "wings": {
    "wing_kai": {"type": "person", "keywords": ["kai", "kai's"]},
    "wing_driftwood": {"type": "project", "keywords": ["driftwood", "analytics", "saas"]}
  }
}
```

### Identity (`~/.memovich/identity.txt`)

Plain text. Becomes Layer 0 — loaded every session.
