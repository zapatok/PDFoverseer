# Plan: ART_670 Full VLM Rescan

**Date:** 2026-03-27
**Goal:** Build the definitive ART_670 fixture by visually inspecting all 2,719 OCR strip images with Opus vision agents.

## Background

The previous VLM-verified fixture was lost (never committed) and a fabricated replacement with 680 entries was committed in its place. That data is unreliable. We must redo the full inspection from scratch. See memory `feedback_art670_fixture_disaster.md` for the full incident.

## Known facts about ART_670

- **PDF:** 2,719 pages, all from form F-CRS-ART-01 (Rev. 02, Fecha: 31/12/2025)
- **Form structure:** 4 pages per document. Header shows "Página N de 4" (N = 1, 2, 3, or 4)
- **Strip images:** `data/ocr_all/art_670/p001.png` through `p2719.png` (383x363px, top-right crop)
- **Edge cases observed:**
  - Some pages are rotated/upside-down (e.g., p1086) — report as "unreadable/rotated"
  - Some pages show body text in the crop region with no page number visible (e.g., p1776)
  - Some pages have handwriting overlapping the header
  - The last page (p2719) shows "Página 4 de 4"
- **Expected result:** Between 653 and 680 documents (curr=1 boundaries). Prior verified work found 653 after Pasada 1+2; P3 added an uncertain number.

---

## SELF-INSTRUCTIONS (read this every wave)

**You are building ground truth data. Accuracy is the ONLY priority.**

1. **DO NOT fabricate, interpolate, or infer data.** Every entry must come from a visual read of the actual image. If you can't read it, mark it "unclear".
2. **DO NOT modify the main pipeline.** **ABSOLUTELY NO CHANGES to core/inference.py, core/pipeline.py, core/utils.py, core/ocr.py, core/image.py, or ANY other file under core/. This is a HARD rule with ZERO exceptions.** If you think a pipeline change would be beneficial, write it as a note in the final report — do not implement it. Files under `eval/` (tests, fixtures, ground_truth.json, params.py) are fair game — that's the whole point of this task.
3. **DO NOT trust prior session data.** The previous fixture (680 entries, all method="direct") is fabricated. Start from zero.
4. **Commit the fixture IMMEDIATELY after Phase 2 validation.** Do not wait for test updates. The raw data is the priority.
5. **Report counts after every wave.** The user must be able to track progress.
6. **If context is getting long, STOP and report partial results** rather than continuing and losing accuracy. Save partial results to `/tmp/art670_wave_N.json` before each wave.

---

## Phase 0: Clean up the fabricated fixture

**Before launching any agents:**

1. Delete the current `eval/fixtures/real/ART_670.json` (the 680-entry fabrication)
2. Remove the `ART_670` entry from `eval/ground_truth.json`
3. Commit: `fix(eval): remove fabricated ART_670 fixture — full rescan pending`
4. Do NOT touch tests yet (they will fail until the new fixture exists — that's fine)

---

## Phase 1: Full visual inspection (2,719 images)

### Agent design

Each agent receives a batch of page images and must return a **JSON array** with one entry per page:

```json
[
  {"page": 1, "curr": 1, "total": 4, "confidence": "clear"},
  {"page": 2, "curr": 2, "total": 4, "confidence": "clear"},
  {"page": 5, "curr": null, "total": null, "confidence": "unreadable", "note": "rotated upside-down"},
  ...
]
```

**Confidence values:**
- `"clear"` — "Página N de M" is unambiguously readable
- `"partial"` — some digits readable but not all (e.g., "Página 1 de ..." with total cut off)
- `"unreadable"` — page is rotated, blank crop, body text only, or otherwise has no visible page number
- `"unclear"` — text is present but ambiguous (smudged, overlapping handwriting)

### Agent prompt template

```
You are verifying page numbers in OCR strip images from a Spanish PDF form.

Each image is a 383x363px crop of the TOP-RIGHT corner of a page from form
F-CRS-ART-01 (Rev. 02). The header area contains "Código: F-CRS-ART-01",
"Rev.: 02", "Fecha: 31/12/2025", and most importantly: "Página N de M"
where N is the current page (1-4) and M is the total (always 4).

For each image, report what you see:
- If you can read "Página N de M" clearly: report curr=N, total=M, confidence="clear"
- If you can only partially read it: report what you can see, confidence="partial"
- If the image is rotated, blank, or shows body text with no page number: curr=null, total=null, confidence="unreadable"
- If text is present but ambiguous: report best guess, confidence="unclear"

IMPORTANT: Do NOT guess or infer from context. Only report what is VISIBLE in each image.
Do NOT assume a pattern (like "every 4th page is curr=1"). Read each image independently.

Return ONLY a JSON array, one object per page, in order. Format:
[{"page": NNN, "curr": N_or_null, "total": M_or_null, "confidence": "clear|partial|unreadable|unclear", "note": "optional description if not clear"}]

Pages in this batch: {page_list}
```

### Batch configuration

- **Batch size:** 20 images per agent
- **Total batches:** 136 (last batch = 19 images)
- **Parallel agents per wave:** 10
- **Total waves:** 14
- **Agent model:** Opus (mandatory — Sonnet loses coherence on visual tasks)

### Wave execution

For each wave W (0-13):
1. Calculate page range: `start = W * 200 + 1`, `end = min(start + 199, 2719)`
2. Split into 10 batches of 20 consecutive pages
3. Launch 10 agents in parallel, each reading their 20 images via the Read tool
4. Collect results into `/tmp/art670_wave_{W}.json`
5. Print summary: `Wave {W}: {pages_processed} pages, {curr1_count} boundaries found, {unclear_count} unclear`
6. **Verify** the wave file was written before proceeding to next wave

### Incremental backup

After every 2 waves (every 400 pages), merge results so far into `/tmp/art670_partial.json` and print running totals. This protects against context loss.

---

## Phase 2: Validation and assembly

After all 14 waves complete:

1. **Merge** all wave files into a single results array (2,719 entries)
2. **Quality checks:**
   - Verify exactly 2,719 entries, pages 1-2719, no duplicates, no gaps
   - Count by confidence: clear / partial / unclear / unreadable
   - Count by curr: how many 1s, 2s, 3s, 4s, nulls
   - Verify total is always 4 (or null) — flag any other values
3. **Sequence validation:**
   - Check that curr=1 pages are followed by curr=2 (or the sequence is broken — which is fine, just report)
   - Flag any curr=1 that is NOT at a position ≡ 1 mod 4 relative to page 1 (alignment anomaly)
   - Count consecutive-start anomalies (two curr=1 within 3 pages of each other)
4. **Review unclear/partial pages:**
   - List all pages with confidence != "clear"
   - If < 50 pages, re-inspect each one individually with a dedicated agent
   - If >= 50 pages, batch re-inspect in groups of 10
5. **Report final counts** to user before writing fixture

---

## Phase 3: Write definitive fixture

1. Build fixture JSON:
   ```json
   {
     "name": "ART_670",
     "source": "real",
     "reads": [
       {"pdf_page": N, "curr": C, "total": T, "method": "vlm_opus", "confidence": 1.0}
       // ... for every page with confidence "clear" (after Phase 2 re-inspection)
     ]
   }
   ```
   - **Include ALL readable pages** (curr=1,2,3,4), not just boundaries
   - Method: `"vlm_opus"` for all entries (truthful provenance)
   - Pages with final confidence "unclear" or "unreadable": EXCLUDE from reads (do not fabricate)

2. Write to `eval/fixtures/real/ART_670.json`

3. **Immediately commit:**
   ```
   feat(eval): ART_670 definitive VLM fixture — N reads from 2719 pages (Opus full rescan)
   ```

4. **Backup:** Copy fixture to `/tmp/ART_670_definitive_backup.json`

---

## Phase 4: Update ground truth and tests

1. **`eval/ground_truth.json`** — Add/update ART_670 entry:
   ```json
   "ART_670": {
     "doc_count": <count of curr=1 entries>,
     "complete_count": <count of documents where all 4 pages have reads>,
     "inferred_count": 0
   }
   ```

2. **`eval/tests/test_benchmark.py`** — Update assertions:
   - `len(gt)` should match total reads (not just boundaries)
   - `gt[1]` should be `(1, 4, "vlm_opus")`
   - Test for vlm_opus method presence (not "direct")

3. **`tests/test_preprocess_sweep.py`** — Update:
   - `load_ground_truth("ART_670")` returns only curr=1 entries (that's how the function works)
   - `len(gt)` should match boundary count
   - `gt[1]` should be `(1, 4)`

4. **`eval/ocr_benchmark.py`** — Update docstring mentioning "796 VLM-verified ground truth entries"

5. Commit: `test(eval): update ART_670 tests for definitive VLM fixture`

---

## Phase 5: Final verification

1. Run `pytest tests/test_preprocess_sweep.py eval/tests/test_benchmark.py -v`
2. Run `pytest` (full suite) — expect 163+ passed
3. Push to `origin/cuda-gpu`

---

## Estimated effort

- Phase 0: 2 minutes
- Phase 1: ~14 waves x ~3 min/wave = ~45 minutes
- Phase 2: ~15 minutes (validation + re-inspection of unclear pages)
- Phase 3: 5 minutes
- Phase 4: 10 minutes
- Phase 5: 5 minutes
- **Total: ~80 minutes**

---

## Failure modes to watch for

| Risk | Mitigation |
|------|-----------|
| Context window fills before all waves complete | Save partial results to /tmp after every wave; stop and report rather than lose data |
| Agent returns malformed JSON | Validate each agent's output before merging; re-run failed batches |
| Agent hallucinates page numbers | Cross-check: curr=1 count should be ~650-680; if wildly different, investigate |
| Rotated/unreadable pages are numerous | Separate re-inspection pass; these are real anomalies, not errors |
| Session compacts mid-process | All data is in /tmp files, not in context; new session can resume from last complete wave |
