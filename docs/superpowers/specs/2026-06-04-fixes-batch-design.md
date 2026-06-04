# Fixes batch — design (Excel #REF!, CPHS, sort retract, viewer nav, clear suspects, OCR preprocessing)

**Date:** 2026-06-04
**Branch:** `po_overhaul` (work directly — single live branch convention; push at end of round)
**Scope:** Six items Daniel reported in live review. Mix of Excel template, frontend, backend API, and OCR pipeline. Each is independent.

---

## E1 — Excel TOTAL #REF! (O11) + off-by-one (O12)

**Problem.** In the output `RESUMEN_<MES>.xlsx`, the TOTAL "Cantidad Realizada" column has two broken formulas, baked into the template `data/templates/RESUMEN_template_v1.xlsx`:
- `O11 = SUM(G11,I11,#REF!,M11)` — the K11 (Río Bueno cantidad, irl row) reference was lost to `#REF!`.
- `O12 = SUM(G12,I12,K11,M12)` — references **K11** instead of K12 (odi's total wrongly sums irl's Río Bueno).

All other rows (O10, O13–O28) are correct: `SUM(G,I,K,M)` for their row. The P (HH) column is intact.

**Design.** Surgical edit of the template via openpyxl (NOT a regenerate):
1. Back up the template first: `RESUMEN_template_v1.xlsx.bak-2026-06-04`.
2. `O11 → =SUM(G11,I11,K11,M11)`; `O12 → =SUM(G12,I12,K12,M12)`.
3. Verify by reloading and printing O10–O18.

The writer (`core/excel/writer.py`) fills the G/I/K/M data cells via named ranges and does not touch O/P (template formulas) — so fixing the template is sufficient and every future output inherits it. No writer change.

---

## E2 — chps → CPHS (display-only)

**Decision (Daniel):** correct only what the user sees; keep the internal key `chps`. The key is coupled to the upstream corpus (filename glob `^.*chps.*\.pdf$`, folder `18.-CHPS`) and to `historical_counts` rows — renaming it would mean a DB migration and upstream coupling, out of scope.

**The correct acronym is CPHS** (Comité Paritario de Higiene y Seguridad).

**Where the user sees the wrong form:**
- Frontend `SIGLA_LABELS.chps = "CHPS"` (sigla-labels.js:25) → shown in the DetailPanel header label and the CategoryRow tooltip.
- The raw key `chps` is rendered lowercase in two places: CategoryRow list (`{sigla}`) and the DetailPanel header mono (`{sigla}`).
- Excel: the visible row label text "CHPS — Comité Paritario…" in the template.

**Design.**
1. `SIGLA_LABELS.chps` → `"CPHS"` (sigla-labels.js).
2. Add a tiny display map for the raw-key rendering: `SIGLA_DISPLAY = { chps: "cphs" }` + helper `siglaDisplay(s) => SIGLA_DISPLAY[s] ?? s` in `sigla-labels.js`. Apply it where the raw key is shown to the user: CategoryRow list label and DetailPanel header mono. (Everything else — store keys, API, props — keeps `chps`.) The display value is **lowercase `cphs` by design**: the list renders every sigla as a lowercase code (irl, odi, art…), so the corrected code matches that style. The uppercase **CPHS** is the `SIGLA_LABELS` value (tooltip + DetailPanel header label), not the list code.
3. Excel template: change the visible CHPS label cell text to "CPHS — Comité Paritario de Higiene y Seguridad" (surgical openpyxl edit, same backup as E1). Also update `data/templates/build_template_v1.py` (label string at line ~84) so a future rebuild stays correct. The named ranges `HXX_chps_count` stay as-is (internal; the writer builds the name from the key `chps`).

**Non-goal:** renaming the internal key, the folder map, the glob, the named ranges, or migrating historical rows.

---

## E3 — Retract the FileList precedence sort (revert G3)

**Decision (Daniel):** the precedence sort shipped earlier today reorders rows on every action, which is disorienting — he wants the list to keep a **stable order** so that where he acts on a file, it stays put.

**Design.** Revert the G3 sort in `FileList.jsx`: drop `.sort(compareByOrigin)`, restore `const filtered = files.filter(...)`. Remove the now-unused `compareByOrigin` import. In `file-origin.js`, remove `compareByOrigin` + `ORIGIN_RANK` and their tests (dead after the retract); keep `fileCountDisplay` (G2 stays). The backend already returns files in a stable folder/filename order — that order is what the list shows.

**Keep:** G1 (alignment), G2 (pendiente "—" / revisar "0"), G4, G5 from this morning — only G3 is retracted.

---

## E4 — Viewer: navigate to the next (and previous) file

**Problem.** The PDF viewer (PDFLightbox) opens one file by `fileIndex`; there is no way to move to the next file in the list without closing and reopening.

**Design.** No new store action (the file count lives only in the component's local
`files` state, fetched via `getCellFiles`; the store has no count to clamp against).
- `PDFLightbox.jsx`: add **‹ Anterior** / **Siguiente ›** controls that call
  `openLightbox(hospital, sigla, clamp(fileIndex ± 1, 0, files.length - 1), mode)`
  directly, guarded on `files !== null` (prev disabled at index 0, next at the last).
- Add ←/→ key handlers for file step. Confirmed no collision: the viewer's existing
  keydown handler captures ArrowUp/ArrowDown (page nav), not ArrowLeft/ArrowRight.
- Changing `fileIndex` re-derives the PDF url (`api.cellPdfUrl`), which already resets
  the per-page viewer state — no extra reset needed.

Daniel asked for "next"; previous is the trivial symmetric companion and included for usability.

---

## E5 — Clear the near-match suspects list (total + individual)

**Problem.** The "Casi-matches" panel (candidates for a new flavor) accumulates in `cell.near_matches`. A long list (e.g. 60 entries) cannot be pruned; there is no way to dismiss reviewed/rejected candidates.

**Design.**
- **Backend.** `SessionManager.clear_near_matches(session_id, hospital, sigla, *, pdf_name=None, page_index=None)`:
  - if `pdf_name`/`page_index` given → remove that one entry from `cell["near_matches"]`;
  - else → set `cell["near_matches"] = []`.
  - Persist via the existing `update_session_state` (whole-state JSON write). Idempotent; no-op if the cell or list is absent.
  - Route: `POST /sessions/{id}/cells/{hospital}/{sigla}/near-matches/clear` with optional JSON body `{pdf_name, page_index}` (omit both = clear all). Mirrors the existing per-cell route shape in `routes/sessions.py`.
- **Frontend.**
  - `api.clearNearMatches(sessionId, hospital, sigla, entry?)`.
  - Store `clearNearMatches(...)`: calls the API, then updates the cell's `near_matches` in `session.cells[h][s]` (optimistic), so the DetailPanel re-renders without a full reload.
  - UI: a **"Limpiar todo"** button in the `NearMatchesSection` header (clears all) and a **"Descartar"** (X) action per `NearMatchRow` (clears that entry). Confirm-free — clearing only drops a maintenance hint, never a count.

---

## E6 — V4 image preprocessing in the anchor-band OCR

**Problem.** `count_covers_by_anchors` renders the top band and OCRs it **raw** (header_band_anchors.py:177-178) — no preprocessing. Degraded scans (andamios, ART, maquinaria) extract poorly → under-detection. The V4 pipeline already has a refined cascade, battle-tested on these same documents.

**The V4 cascade (today, inside ocr.py):**
- `_process_page`: `_render_clip` → `_deskew` (image.py) → `_tess_ocr`.
- `_tess_ocr` (ocr.py:80-96): for a color image, HSV blue-mask (`[90,50,50]`–`[150,255,255]`) → `cv2.inpaint(NS, radius 3)` → grayscale; then unsharp mask (GaussianBlur σ=1.0, addWeighted 1.3/−0.3); then Tesseract (`lang="eng"`).

**Design.** Extract the **image-cleaning** part (not the Tesseract call — the band uses `spa+eng`, V4 uses `eng`) into a shared, reusable function and apply it to the band:

1. `core/image.py`: new `clean_for_ocr(bgr: np.ndarray) -> np.ndarray` = the body of `_tess_ocr` lines 82-94 (color removal + inpaint + grayscale + unsharp), returning the cleaned grayscale array. Pure, no Tesseract.
2. `core/ocr.py`: `_tess_ocr` refactors to `gray = clean_for_ocr(bgr); return pytesseract.image_to_string(gray, lang="eng", config=TESS_CONFIG)`. **Behavior-preserving for V4** — same ops in the same order (the `len(bgr.shape)==2` gray guard moves into `clean_for_ocr`). The real-world guard is the E6 corpus before/after measurement; the unit test is a fixture-free `clean_for_ocr` check (below), not a rendered-text fixture.
3. `core/scanners/utils/header_band_anchors.py`: in `count_covers_by_anchors`, before the OCR, convert the rendered PIL band to BGR numpy, apply `_deskew` + `clean_for_ocr`, then OCR the cleaned array with `spa+eng`:
   ```python
   pil = render_page_region(pdf_path, page_idx, bbox=bbox, dpi=dpi)
   bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
   gray = clean_for_ocr(_deskew(bgr))
   text = pytesseract.image_to_string(gray, config="--psm 6 --oem 1", lang="spa+eng")
   ```

**Why low-risk on clean scans (Daniel's bar — "at least as good as now").** On a clean black-text band: the blue mask is empty → inpaint is a no-op; deskew only fires above 0.5° skew; unsharp sharpens (neutral-to-helpful). So clean cells should not regress; degraded cells should improve.

**Validation (mandatory — this touches calibrated OCR).** Before/after count comparison via a targeted harness on a small set, using the real corpus (read-only `A:/informe mensual`):
- **Degraded (expect ≥ today):** HPV/andamios, an ART cell, HRB/andamios.
- **Clean (expect == today):** a cell that counts correctly today via anchors (e.g. chintegral, odi).
- Record old vs new cover counts per cell. The bar: **no clean-cell regression**; any degraded-cell gain is a bonus. If a clean cell regresses, stop and surface it before shipping E6 (do not silently re-tune anchors — that is the OCR-refinement phase).

**Dependencies.** `cv2`, `numpy` already imported in the OCR path; `header_band_anchors.py` gains `cv2`/`numpy` imports. `clean_for_ocr` is GPU-free (pure OpenCV), safe in the Tesseract worker threads.

---

## Testing & sequencing

- **Unit (vitest):** keep `fileCountDisplay`; drop `compareByOrigin`/`ORIGIN_RANK` tests (E3). Lightbox step + clamp can have a small pure helper test (E4).
- **Unit (pytest):** `clear_near_matches` (all + individual + no-op) and its route (E5); `clean_for_ocr` on synthetic numpy arrays — color BGR → 2D grayscale of the same H×W, already-gray input handled by the guard, no crash (E6). No rendered-text/PDF fixture; the OCR behavior guard is the E6 corpus measurement.
- **Excel:** E1/E2 verified by reloading the template and asserting the O11/O12 formulas + the CPHS label string.
- **Full run at the end** (pytest + vitest + build), then a **live smoke** (chrome-devtools, ABRIL) of E2–E5, plus the **E6 before/after corpus measurement**.
- Atomic commits, one per item (E6 split: extract+refactor, apply-to-band, validation). English conventional-commit; Co-Authored-By "Claude Opus 4.8 <noreply@anthropic.com>". Push `po_overhaul` at the end.

## Files touched

| Item | Files |
|------|-------|
| E1 | `data/templates/RESUMEN_template_v1.xlsx` (+ `.bak`) |
| E2 | `frontend/src/lib/sigla-labels.js`, `frontend/src/components/CategoryRow.jsx`, `frontend/src/components/DetailPanel.jsx`, template label cell, `data/templates/build_template_v1.py` |
| E3 | `frontend/src/components/FileList.jsx`, `frontend/src/lib/file-origin.js`, `frontend/src/lib/__tests__/file-origin.test.js` |
| E4 | `frontend/src/store/session.js`, `frontend/src/components/PDFLightbox.jsx` |
| E5 | `api/state.py`, `api/routes/sessions.py`, `frontend/src/lib/api.js`, `frontend/src/store/session.js`, `frontend/src/components/DetailPanel.jsx` |
| E6 | `core/image.py`, `core/ocr.py`, `core/scanners/utils/header_band_anchors.py`, tests |
