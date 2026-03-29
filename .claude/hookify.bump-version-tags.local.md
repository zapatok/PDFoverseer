---
name: bump-version-tags
enabled: true
event: file
action: block
conditions:
  - field: file_path, operator: regex_match, pattern: (core[/\\](pipeline|ocr|inference|image|utils|vlm_resolver|vlm_provider)\.py|vlm[/\\](client|parser|preprocess|benchmark)\.py|server\.py)
---

**BLOCKED — Version bump required before editing vital files.**

You are editing a vital pipeline file. Before this edit can proceed, you MUST:

1. **Choose which tag to bump** in `core/utils.py`:
   - `INFERENCE_ENGINE_VERSION` — inference logic, phases, gap-solver, D-S, period detection
   - `PAGE_PATTERN_VERSION` — regex patterns, `_parse()`, OCR digit normalization
   - `VLM_ENGINE_VERSION` — VLM resolver, provider, prompt, preprocessing
   - More than one if the change spans multiple areas

2. **Name the new version** (e.g. `s2t8-description`, `v2-description`, etc.)

3. **Edit `core/utils.py` FIRST** with the new version string

4. **Confirm to the user**: "Bumped [TAG]: old → new (reason)"

Only THEN retry the edit to the vital file.

Vital files: `core/{pipeline,ocr,inference,image,utils,vlm_resolver,vlm_provider}.py`, `vlm/{client,parser,preprocess,benchmark}.py`, `server.py`
