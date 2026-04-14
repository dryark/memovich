#!/bin/bash
# Memovich PreCompact Hook — thin wrapper calling Python CLI
# All logic lives in memovich.hooks_cli for cross-harness extensibility
INPUT=$(cat)
echo "$INPUT" | python3 -m memovich hook run --hook precompact --harness claude-code
