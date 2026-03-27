---
name: constants-in-utils
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: not_contains, pattern: core/utils.py
  - field: file_path, operator: regex_match, pattern: ^(?!.*eval[/\\])
  - field: content, operator: regex_match, pattern: (DPI|CROP_X_START|CROP_Y_END|TESS_CONFIG|PARALLEL_WORKERS|BATCH_SIZE|MIN_CONF_FOR_NEW_DOC)\s*=
---

**Pipeline constants belong in `core/utils.py`.**

Do not redefine pipeline/inference constants outside their canonical location. Import them from `core.utils` instead.
