# Memovich

AI memory system. Store everything, find anything. Local, free, no API key.

---

## Slash Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| /memovich:init      | Install and set up Memovich   |
| /memovich:search    | Search your memories           |
| /memovich:mine      | Mine projects and conversations|
| /memovich:status    | Palace overview and stats      |
| /memovich:help      | This help message              |

---

## MCP Tools (19)

### Palace (read)
- memovich_status -- Palace status and stats
- memovich_list_wings -- List all wings
- memovich_list_rooms -- List rooms in a wing
- memovich_get_taxonomy -- Get the full taxonomy tree
- memovich_search -- Search memories by query
- memovich_check_duplicate -- Check if a memory already exists
- memovich_get_aaak_spec -- Get the AAAK specification

### Palace (write)
- memovich_add_drawer -- Add a new memory (drawer)
- memovich_delete_drawer -- Delete a memory (drawer)

### Knowledge Graph
- memovich_kg_query -- Query the knowledge graph
- memovich_kg_add -- Add a knowledge graph entry
- memovich_kg_invalidate -- Invalidate a knowledge graph entry
- memovich_kg_timeline -- View knowledge graph timeline
- memovich_kg_stats -- Knowledge graph statistics

### Navigation
- memovich_traverse -- Traverse the palace structure
- memovich_find_tunnels -- Find cross-wing connections
- memovich_graph_stats -- Graph connectivity statistics

### Agent Diary
- memovich_diary_write -- Write a diary entry
- memovich_diary_read -- Read diary entries

---

## CLI Commands

    memovich init <dir>                  Initialize a new palace
    memovich mine <dir>                  Mine a project (default mode)
    memovich mine <dir> --mode convos    Mine conversation exports
    memovich search "query"              Search your memories
    memovich split <dir>                 Split large transcript files
    memovich wake-up                     Load palace into context
    memovich compress                    Compress palace storage
    memovich status                      Show palace status
    memovich repair                      Rebuild vector index
    memovich mcp                         Show MCP setup command
    memovich hook run                    Run hook logic (for harness integration)
    memovich instructions <name>         Output skill instructions

---

## Auto-Save Hooks

- Stop hook -- Automatically saves memories every 15 messages. Counts human
  messages in the session transcript (skipping command-messages). When the
  threshold is reached, blocks the AI with a save instruction. Uses
  ~/.memovich/hook_state/ to track save points per session. If
  stop_hook_active is true, passes through to prevent infinite loops.

- PreCompact hook -- Emergency save before context compaction. Always blocks
  with a comprehensive save instruction because compaction means the AI is
  about to lose detailed context.

Hooks read JSON from stdin and output JSON to stdout. They can be invoked via:

    echo '{"session_id":"abc","stop_hook_active":false,"transcript_path":"..."}' | memovich hook run --hook stop --harness claude-code

---

## Architecture

    Wings (projects/people)
      +-- Rooms (topics)
            +-- Closets (summaries)
                  +-- Drawers (verbatim memories)

    Halls connect rooms within a wing.
    Tunnels connect rooms across wings.

The palace is stored locally using ChromaDB for vector search and SQLite for
metadata. No cloud services or API keys required.

---

## Getting Started

1. /memovich:init -- Set up your palace
2. /memovich:mine -- Mine a project or conversation
3. /memovich:search -- Find what you stored
