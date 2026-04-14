# MCP Integration — Claude Code

## Setup

Run the MCP server:

```bash
python -m memovich.mcp_server
```

Or add it to Claude Code:

```bash
claude mcp add memovich -- python -m memovich.mcp_server
```

## Available Tools

The server exposes the full Memovich MCP toolset. Common entry points include:

- **memovich_status** — palace stats (wings, rooms, drawer counts)
- **memovich_search** — semantic search across all memories
- **memovich_list_wings** — list all projects in the palace

## Usage in Claude Code

Once configured, Claude Code can search your memories directly during conversations.
