#!/bin/bash
# PostToolUse hook: auto-format Python files after Edit/Write
# Reads hook JSON from stdin, extracts file_path, runs `ruff format` only.
# Deliberately does NOT run `ruff check --fix`: the autofix strips an F401
# unused-import in the same Edit that adds it (before its use exists), which
# bit us repeatedly. Lint reporting is left to the `ruff-before-done` stop hook
# and the manual `ruff check .` gate before commit.

FILE_PATH=$(python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# Format only (cosmetic, non-destructive). No --fix.
ruff format "$FILE_PATH" 2>/dev/null

exit 0
