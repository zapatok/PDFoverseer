---
name: no-shell-true
enabled: true
event: file
action: block
pattern: shell\s*=\s*True
---

**Subprocess with `shell=True` detected.**

Use list form instead: `subprocess.run(["cmd", "arg1", "arg2"])`. `shell=True` enables command injection if any argument comes from user input.
