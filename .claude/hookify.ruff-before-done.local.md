---
name: ruff-before-done
enabled: true
event: stop
pattern: .*
action: warn
---

**Run `ruff check .` before finishing.**

Project requires 0 ruff violations before committing. Run `ruff check .` and fix any issues before you stop.
