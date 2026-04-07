#!/bin/bash
# PostToolUse hook: auto-format Python files after Edit/Write
# Reads hook JSON from stdin, extracts file_path, runs ruff format + check --fix

FILE_PATH=$(python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ -z "$FILE_PATH" || "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# Auto-fix lint issues, then format
ruff check --fix "$FILE_PATH" 2>/dev/null
ruff format "$FILE_PATH" 2>/dev/null

exit 0
