---
name: eval-before-core
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: regex_match, pattern: core[/\\]inference\.py
  - field: content, operator: regex_match, pattern: (def _infer|def phase_|MIN_CONF|CLASH_BOUNDARY|PH5B_|ANOMALY_DROPOUT|PHASE4_FALLBACK)
---

**BLOCKED: Do not edit inference logic in `core/inference.py` directly.**

All inference changes MUST be prototyped and validated in `eval/inference.py` first. Never port changes to `core/inference.py` without the user's explicit approval. Ask before touching core.
