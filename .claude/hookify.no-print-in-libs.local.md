---
name: no-print-in-libs
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: regex_match, pattern: (core|api|vlm|eval)[/\\]
  - field: content, operator: regex_match, pattern: \bprint\(
---

**No `print()` in library code.**

Use `logging.getLogger(__name__)` instead. `print()` is only allowed in CLI entry points (`server.py`) and standalone tools (`tools/`).
