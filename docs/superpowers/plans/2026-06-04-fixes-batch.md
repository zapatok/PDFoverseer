# Fixes batch — implementation plan

> Execute in-session. Tests written alongside each task; full run (pytest + vitest + build) + live smoke + E6 corpus measurement at the end. Checkbox steps.

**Goal:** Ship six independent fixes/features: Excel TOTAL #REF!, chps→CPHS (display), retract FileList sort, viewer next/prev file, clear near-match suspects, V4 preprocessing in the anchor-band OCR.

**Spec:** `docs/superpowers/specs/2026-06-04-fixes-batch-design.md`
**Branch:** `po_overhaul` (work directly; push at end).
**Co-Author (verbatim):** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

Order: E3 (revert) → E1 (Excel) → E2 (CPHS) → E4 (viewer) → E5 (clear suspects) → E6 (preprocessing) → verify.

---

## Task E3: retract the FileList precedence sort

**Files:** `frontend/src/components/FileList.jsx`, `frontend/src/lib/file-origin.js`, `frontend/src/lib/__tests__/file-origin.test.js`

- [ ] **Step 1:** In FileList.jsx, restore the stable order — change
  ```js
  const filtered = files
    .filter((f) => f.name.toLowerCase().includes(search.toLowerCase()))
    .sort(compareByOrigin);
  ```
  back to
  ```js
  const filtered = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()),
  );
  ```
  and change the import to `import { fileCountDisplay } from "../lib/file-origin";` (drop `compareByOrigin`).
- [ ] **Step 2:** In `file-origin.js`, delete `ORIGIN_RANK` and `compareByOrigin` (keep `fileCountDisplay`). In `file-origin.test.js`, delete the `ORIGIN_RANK` and `compareByOrigin` describe blocks (keep `fileCountDisplay`).
- [ ] **Step 3: Commit** — `revert(frontend): drop FileList precedence sort; keep stable order`

---

## Task E1: fix Excel TOTAL #REF! (O11) + off-by-one (O12)

**Files:** `data/templates/RESUMEN_template_v1.xlsx` (+ dated `.bak`)

- [ ] **Step 1:** Back up + fix via a one-off script (run with the venv python). Back up first, fix O11/O12, verify:

```python
# .tmp_excel_fix.py
import shutil, openpyxl
from pathlib import Path
tpl = Path("data/templates/RESUMEN_template_v1.xlsx")
shutil.copy2(tpl, tpl.parent / "RESUMEN_template_v1.xlsx.bak-2026-06-04")
wb = openpyxl.load_workbook(tpl)
ws = wb.active
ws["O11"] = "=SUM(G11,I11,K11,M11)"
ws["O12"] = "=SUM(G12,I12,K12,M12)"
wb.save(tpl)
# verify
wb2 = openpyxl.load_workbook(tpl)
for r in (10, 11, 12, 13):
    print(r, wb2.active[f"O{r}"].value)
```
Expected: O11=`=SUM(G11,I11,K11,M11)`, O12=`=SUM(G12,I12,K12,M12)`, O10/O13 unchanged.

- [ ] **Step 2:** Delete `.tmp_excel_fix.py`. (The `.bak` stays as the dated backup.)
- [ ] **Step 3: Commit** — `fix(excel): repair TOTAL Cantidad Realizada O11 #REF! + O12 off-by-one`
  (commit the template; the `.bak` is gitignored or added — check `.gitignore`; if untracked, do not commit it.)

---

## Task E2: chps → CPHS (display-only)

**Files:** `frontend/src/lib/sigla-labels.js`, `frontend/src/components/CategoryRow.jsx`, `frontend/src/components/DetailPanel.jsx`, the template label cell, `data/templates/build_template_v1.py`

- [ ] **Step 1:** `sigla-labels.js`: `chps: "CHPS"` → `chps: "CPHS"`. Add:
  ```js
  // Display override for the lowercase raw-key code shown in the list/header.
  // Internal key stays "chps" (glob/folder/DB); only the visible code changes.
  export const SIGLA_DISPLAY = { chps: "cphs" };
  export const siglaDisplay = (s) => SIGLA_DISPLAY[s] ?? s;
  ```
- [ ] **Step 2:** `CategoryRow.jsx`: import `siglaDisplay`; render `{siglaDisplay(sigla)}` in the mono span (line ~56).
- [ ] **Step 3:** `DetailPanel.jsx`: import `siglaDisplay`; render `{siglaDisplay(sigla)}` in the header mono span (line ~191).
- [ ] **Step 4:** Excel template label. Locate the "CHPS" text cell and change to CPHS (same backup as E1, or a fresh one if E1 already ran — re-use the `.bak`):
  ```python
  # .tmp_cphs_label.py
  import openpyxl
  from pathlib import Path
  tpl = Path("data/templates/RESUMEN_template_v1.xlsx")
  wb = openpyxl.load_workbook(tpl)
  ws = wb.active
  for row in ws.iter_rows():
      for c in row:
          if isinstance(c.value, str) and "CHPS" in c.value:
              print("found", c.coordinate, repr(c.value))
              c.value = c.value.replace("CHPS", "CPHS")
  wb.save(tpl)
  ```
  Run, confirm it reports the CHPS label cell(s) and rewrites to CPHS. Delete the script.
- [ ] **Step 5:** `build_template_v1.py` line ~84: change the label string "CHPS — Comité Paritario…" → "CPHS — Comité Paritario…" so a future rebuild stays correct. (No rebuild now.)
- [ ] **Step 6: Commit** — `fix(cphs): correct CHPS→CPHS in app labels and Excel (display-only)`

---

## Task E4: viewer next/previous file

**Files:** `frontend/src/components/PDFLightbox.jsx`

- [ ] **Step 1:** Read PDFLightbox.jsx to confirm it holds the cell's `files` in local state and has `hospital/sigla/fileIndex/mode` from the `lightbox` store slice.
- [ ] **Step 2:** Add a `step(delta)` helper inside the component:
  ```js
  const step = (delta) => {
    if (!files) return;
    const next = Math.min(Math.max(fileIndex + delta, 0), files.length - 1);
    if (next !== fileIndex) openLightbox(hospital, sigla, next, mode);
  };
  ```
- [ ] **Step 3:** Add **‹ Anterior** / **Siguiente ›** buttons (lucide ChevronLeft/ChevronRight), `disabled` at the ends, plus a filename position indicator ("N de M") if it fits the header.
- [ ] **Step 4:** Add a keydown effect for ArrowLeft/ArrowRight → `step(-1)/step(+1)` (confirm it does not shadow the viewer's ArrowUp/ArrowDown page nav; only Left/Right).
- [ ] **Step 5: Commit** — `feat(frontend): step to next/previous file in the PDF viewer`

---

## Task E5: clear near-match suspects (total + individual)

**Files:** `api/state.py`, `api/routes/sessions.py`, `frontend/src/lib/api.js`, `frontend/src/store/session.js`, `frontend/src/components/DetailPanel.jsx`

- [ ] **Step 1 (test first):** add `tests/unit/api/test_clear_near_matches.py` — seed a cell with 3 near_matches via the manager; assert clear-one removes exactly that entry; clear-all empties the list; no-op on absent cell/list.
- [ ] **Step 2:** `api/state.py`: `clear_near_matches(self, session_id, hospital, sigla, *, pdf_name=None, page_index=None)`:
  ```python
  state = self.get_session_state(session_id)
  cell = (state.get("cells", {}).get(hospital, {}) or {}).get(sigla)
  if not cell or not cell.get("near_matches"):
      return
  if pdf_name is None and page_index is None:
      cell["near_matches"] = []
  else:
      cell["near_matches"] = [
          nm for nm in cell["near_matches"]
          if not (nm.get("pdf_name") == pdf_name and nm.get("page_index") == page_index)
      ]
  update_session_state(self._conn, session_id, state_json=json.dumps(state))
  ```
- [ ] **Step 3:** `api/routes/sessions.py`: route mirroring the per-cell shape:
  ```python
  @router.post("/{session_id}/cells/{hospital}/{sigla}/near-matches/clear")
  def clear_near_matches(session_id, hospital, sigla, body: ClearNearMatchBody | None = None,
                         manager: SessionManager = Depends(get_manager)):
      manager.clear_near_matches(session_id, hospital, sigla,
                                 pdf_name=body.pdf_name if body else None,
                                 page_index=body.page_index if body else None)
      return {"ok": True}
  ```
  with a small `ClearNearMatchBody(BaseModel)` (`pdf_name: str | None = None`, `page_index: int | None = None`). Validate session_id like the sibling routes.
- [ ] **Step 4:** `frontend/src/lib/api.js`: `clearNearMatches(sessionId, hospital, sigla, entry)` → POST with optional `{pdf_name, page_index}`.
- [ ] **Step 5:** `frontend/src/store/session.js`: `clearNearMatches(sessionId, hospital, sigla, entry)` action — call the API, then update `session.cells[hospital][sigla].near_matches` in place (remove one or empty all) so the panel re-renders.
- [ ] **Step 6:** `DetailPanel.jsx`: "Limpiar todo" button in the `NearMatchesSection` header; a "Descartar" (X) icon-button per `NearMatchRow`. Wire both to the store action.
- [ ] **Step 7: Commit** — `feat(suspects): clear near-match list, all or individually`

---

## Task E6: V4 preprocessing in the anchor-band OCR

**Files:** `core/image.py`, `core/ocr.py`, `core/scanners/utils/header_band_anchors.py`, `tests/unit/test_clean_for_ocr.py`

- [ ] **Step 1 (test first):** `tests/unit/test_clean_for_ocr.py`:
  ```python
  import numpy as np
  from core.image import clean_for_ocr
  def test_color_input_returns_2d_gray_same_hw():
      bgr = np.full((40, 120, 3), 200, np.uint8)
      out = clean_for_ocr(bgr)
      assert out.ndim == 2 and out.shape == (40, 120) and out.dtype == np.uint8
  def test_gray_input_passthrough_guard():
      gray = np.full((30, 90), 180, np.uint8)
      out = clean_for_ocr(gray)
      assert out.ndim == 2 and out.shape == (30, 90)
  ```
- [ ] **Step 2:** `core/image.py`: add `clean_for_ocr(bgr: np.ndarray) -> np.ndarray` = the body of `_tess_ocr` lines 82-94 (gray guard + HSV blue-mask + inpaint + grayscale + unsharp), returning `gray`. Google-style docstring.
- [ ] **Step 3:** `core/ocr.py`: `_tess_ocr` → `gray = clean_for_ocr(bgr); return pytesseract.image_to_string(gray, lang="eng", config=TESS_CONFIG).strip()`. Import `clean_for_ocr` from `core.image` (extend the existing import). Behavior unchanged.
- [ ] **Step 4:** `core/scanners/utils/header_band_anchors.py`: import `cv2`, `numpy as np`, and `from core.image import _deskew, clean_for_ocr`. Replace the OCR lines:
  ```python
  pil = render_page_region(pdf_path, page_idx, bbox=bbox, dpi=dpi)
  bgr = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)
  gray = clean_for_ocr(_deskew(bgr))
  text = pytesseract.image_to_string(gray, config="--psm 6 --oem 1", lang="spa+eng")
  ```
  Keep the `on_page`/`cancel` hooks intact.
- [ ] **Step 5: Commit** — `feat(ocr): apply V4 preprocessing cascade to the anchor-band OCR`

---

## Task E7: verification (all at the end)

- [ ] **Step 1:** `pytest -q` (expect green; the ~12 env-only FileNotFoundError from gitignored `data/samples` are baseline, not regressions). Include the new E5/E6 tests.
- [ ] **Step 2:** `cd frontend && npm run test -- --run` (vitest; file-origin reduced to `fileCountDisplay`) + `npm run build`.
- [ ] **Step 3 — E6 corpus measurement (the real OCR guard).** Throwaway script `.tmp_e6_measure.py`: run `count_covers_by_anchors` (or `AnchorsScanner`) on a small set from the read-only corpus — a clean cell (e.g. HRB/chintegral or an odi) and degraded cells (HPV/andamios, an ART cell) — capping PDFs/pages for speed. Run it on the **pre-E6 code** first (git stash the E6 commits or checkout the band file) to record the baseline, then on the post-E6 code; compare cover counts. **Bar: clean cells unchanged; degraded cells ≥ baseline.** If a clean cell drops, STOP and surface before shipping E6 — do not re-tune anchors here. Delete the script after.
- [ ] **Step 4 — live smoke (chrome-devtools, ABRIL):**
  - E3: FileList keeps stable order; editing a row leaves it in place.
  - E2: list/header show "cphs"; DetailPanel label and (when regenerated) Excel show "CPHS".
  - E4: open viewer, step next/prev with buttons + ←/→; ends disabled.
  - E5: a cell with near_matches — "Descartar" removes one, "Limpiar todo" empties.
  - (E1 verified by reopening the template / a freshly generated Excel: O11/O12 sum correctly.)
- [ ] **Step 5:** `git push origin po_overhaul`. Report verified facts + the E6 before/after numbers.
