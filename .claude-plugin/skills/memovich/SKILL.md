---
name: memovich
description: Memovich — mine projects and conversations into a searchable memory palace. Use when asked about memovich, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Memovich

A searchable memory palace for AI — mine projects and conversations, then search them semantically.

## Prerequisites

Ensure `memovich` is installed:

```bash
memovich --version
```

If not installed:

```bash
pip install memovich
```

## Usage

Memovich provides dynamic instructions via the CLI. To get instructions for any operation:

```bash
memovich instructions <command>
```

Where `<command>` is one of: `help`, `init`, `mine`, `search`, `status`.

Run the appropriate instructions command, then follow the returned instructions step by step.
