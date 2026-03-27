---
name: no-db-mocking
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: regex_match, pattern: tests?[/\\]
  - field: content, operator: regex_match, pattern: (patch|Mock|MagicMock).*(\bsqlite3\b|api\.database|database\.)
---

**Database mocking detected in tests.**

Project convention: do not mock the database. Use real SQLite with fixtures instead. Mocked tests can pass while production breaks.
