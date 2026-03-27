---
name: no-bare-except
enabled: true
event: file
pattern: except\s*:
action: block
---

**No bare `except:` clauses.**

Catch specific exception types: `except ValueError`, `except OSError`, or `except Exception` at minimum. Bare except catches KeyboardInterrupt and SystemExit which masks real problems.
