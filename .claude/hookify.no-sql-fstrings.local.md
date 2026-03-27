---
name: no-sql-fstrings
enabled: true
event: file
action: block
pattern: (execute|executemany)\s*\(\s*f["']
---

**SQL query built with f-string detected.**

Use parameterized queries with `?` placeholders: `conn.execute("SELECT * FROM t WHERE id=?", (val,))`. F-strings in SQL enable injection.
