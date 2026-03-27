---
name: bump-version-tags
enabled: true
event: file
action: warn
conditions:
  - field: file_path, operator: regex_match, pattern: core[/\\]
  - field: content, operator: regex_match, pattern: (_parse|_PAGE_PATTERNS|PAGE_PATTERN|_infer|phase_|dempster_shafer)
---

**Did you bump the version tags?**

After any change to OCR patterns or inference logic, you MUST update:
- `PAGE_PATTERN_VERSION` in `core/utils.py` (for regex/parse changes)
- `INFERENCE_ENGINE_VERSION` in `core/utils.py` (for inference changes)
- The `[REG:]` tag in the `[AI:]` telemetry log reflects these versions.
