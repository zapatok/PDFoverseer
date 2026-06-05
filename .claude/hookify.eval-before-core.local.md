---
name: eval-before-core
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: regex_match, pattern: core[/\\]inference\.py
  - field: content, operator: regex_match, pattern: (def _infer|def phase_|MIN_CONF|CLASH_BOUNDARY|PH5B_|ANOMALY_DROPOUT|PHASE4_FALLBACK)
---

**WARNING: Prototype inference changes in eval before editing `core/inference.py`.**

All inference changes should be prototyped and validated in `eval/inference_tuning/inference.py` first. Don't port changes to `core/inference.py` without the user's explicit approval — ask before touching core.
