#!/bin/bash
# PostCompact hook: re-inject critical project rules after context compaction
# Output goes to Claude as a system message

cat "$CLAUDE_PROJECT_DIR/.claude/context-essentials.txt" 2>/dev/null || cat "$(dirname "$0")/../context-essentials.txt" 2>/dev/null

exit 0
