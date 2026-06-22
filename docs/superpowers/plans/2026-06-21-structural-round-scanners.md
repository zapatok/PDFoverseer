# Structural Round — Fase 0 + Fase 1 (Scanners) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement
> this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-run safety net for the OCR scanners' cancel contract + align migrated
siglas to the production scanner (Fase 0), then collapse the ~75% duplicated `count_ocr`
scaffolding of `AnchorsScanner` + `PaginationScanner` into a shared `OcrScannerBase`
(Template Method) **without changing any counting output** (Fase 1).

**Architecture:** Template Method. `OcrScannerBase.count_ocr` owns the outer harness (folder
guard, PDF enumeration, `only`/`skip` filtering, the per-PDF loop skeleton with cancel/emit
semantics, result assembly). Each subclass implements `_count_one_pdf(pdf)` (the per-PDF
page-count + A7 + engine + error fallback — **kept in the subclass module so the existing
monkeypatch test seam is untouched**) and `_precheck(...)` (anchors' "no flavors" short-circuit).

**Tech Stack:** Python 3.10+, pytest + monkeypatch, PyMuPDF, Tesseract. Source of truth for
the design: `docs/superpowers/specs/2026-06-21-structural-round-design.md` (Fase 0 + Fase 1).

**Hard constraint:** no change in counting output. The existing scanner unit tests
(`test_anchors_scanner.py`, `test_pagination_scanner.py`, the two `_progress.py` files) patch
`core.scanners.{anchors,pagination}_scanner.{get_page_count, <engine>}` on the **subclass
module namespace** — those patches MUST keep working (zero migration). Run them green after
every chunk.

---

## File Structure

- Create: `core/scanners/ocr_scanner_base.py` — `OcrScannerBase` + `_PdfOutcome`.
- Modify: `core/scanners/anchors_scanner.py` — `AnchorsScanner(OcrScannerBase)`: `_precheck` +
  `_count_one_pdf`, drop the harness + `_filename_glob`.
- Modify: `core/scanners/pagination_scanner.py` — `PaginationScanner(OcrScannerBase)`:
  `_count_one_pdf`, drop the harness.
- Modify (tests, Fase 0): `tests/unit/scanners/test_anchors_scanner.py`,
  `tests/unit/scanners/test_pagination_scanner.py` — add cancel-mid-PDF + pre-PDF-cancel tests.
- Modify (tests, Fase 0): the migrated-sigla `tests/unit/scanners/test_pattern_*.py` that still
  instantiate `AnchorsScanner` — re-point to `PaginationScanner`.

**Do NOT touch:** `core/scanners/base.py` (the `Scanner` Protocol — unchanged; subclasses still
satisfy it), `patterns.py` (no strategy/anchor change → no `SCANNER_PATTERNS_VERSION` bump),
the engines (`header_band_anchors.py`, `pagination_count.py` — Fase 2 territory).

---

## Chunk 1: Fase 0a — cancel-contract unit tests (always-run net)

**Why:** the existing scanner unit suites never fire `cancel.cancel()`, so the load-bearing
CancelledError contract (mid-PDF → `emit=False`, no `on_pdf` tick, re-raise; pre-PDF → no tick)
is unproven. Fase 1 moves that re-raise across the `_count_one_pdf` boundary — these tests are
the regression net for exactly that seam. Written against CURRENT code → green now → must stay
green after Fase 1.

**Files:**
- Modify: `tests/unit/scanners/test_anchors_scanner.py`
- Modify: `tests/unit/scanners/test_pagination_scanner.py`

- [ ] **Step 1: Write the failing-then-passing tests (anchors).** In
  `test_anchors_scanner.py`, following the file's existing stub conventions (a temp folder with
  a multi-page stub PDF, `monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count",
  …)` returning e.g. 3, and patching `core.scanners.anchors_scanner.count_covers_by_anchors`):

  - `test_count_ocr_cancel_mid_pdf_no_emit`: patch `count_covers_by_anchors` to a stub that
    raises `CancelledError`. Collect `on_pdf` calls into a list. Assert `count_ocr(...)` raises
    `CancelledError` **and** the `on_pdf` list is empty (the mid-PDF-cancelled file is NOT
    ticked).
  - `test_count_ocr_pre_pdf_cancel_no_emit`: pass a token with `.cancel()` already called;
    assert `count_ocr` raises `CancelledError` and `on_pdf` was never called.

  Use a 2-page stub so the A7 path is not taken (so the engine is actually reached). Mirror the
  fixture/temp-dir helper the file already uses (read the top of the file for the pattern).

- [ ] **Step 2: Run them — expect PASS against current code.**
  Run: `pytest tests/unit/scanners/test_anchors_scanner.py -v -k cancel`
  Expected: PASS (current code already implements the contract; these tests pin it).

- [ ] **Step 3: Mirror for pagination.** Add the same two tests to
  `test_pagination_scanner.py`, patching
  `core.scanners.pagination_scanner.count_documents_by_pagination` to raise `CancelledError`,
  and `core.scanners.pagination_scanner.get_page_count` → 3.

- [ ] **Step 4: Run pagination cancel tests — expect PASS.**
  Run: `pytest tests/unit/scanners/test_pagination_scanner.py -v -k cancel`
  Expected: PASS.

- [ ] **Step 5: Full scanner suite + ruff.**
  Run: `pytest tests/unit/scanners/ -q` (expect all green) and `ruff check tests/unit/scanners/`.

- [ ] **Step 6: Commit.**
  ```bash
  git add tests/unit/scanners/test_anchors_scanner.py tests/unit/scanners/test_pagination_scanner.py
  git commit -m "test(scanners): pin OCR cancel contract (mid-PDF + pre-PDF, no on_pdf tick)"
  ```

---

## Chunk 2: Fase 0b — align migrated-sigla fixture tests to PaginationScanner

**Why:** the 9 pagination-migrated siglas' `test_pattern_*.py` still instantiate
`AnchorsScanner` (testing the now-unused path). Re-point them to the production
`PaginationScanner`. These run only where the gitignored fixtures exist (Daniel's machine);
they skip in CI. Keep the 6 anchors siglas' tests on `AnchorsScanner`.

**Migrated → re-point to `PaginationScanner` (method `"pagination"`):** art, andamios, bodega,
caliente, exc, ext, herramientas_elec, irl_odi (odi + irl), altura. (insgral already uses
`PaginationScanner` — leave it as the reference.)
**Keep on `AnchorsScanner`:** charla, chintegral, chps, dif_pts, senal, maquinaria.

- [ ] **Step 1: Re-point each migrated `test_pattern_<sigla>.py`.** For each file in the
  migrated list: change the import + instantiation from `AnchorsScanner(sigla=…)` to
  `PaginationScanner(sigla=…)`, and the method assertion from `"header_band_anchors"` to
  `"pagination"`. Keep the `if not <fixture>.exists(): pytest.skip(...)` guard. Model the
  asserts on `test_pattern_insgral.py` (count == `gt["covers_expected"]`, method `"pagination"`,
  per_file entry, HIGH-confidence where the GT says all-direct).

- [ ] **Step 2: Drop now-stale `@pytest.mark.skip` where the skip reason was anchors-specific.**
  e.g. `test_pattern_art.py`'s skip cites the "truncated anchor set" postmortem — that premise
  doesn't apply to the pagination engine. Remove that decorator and rely on the fixture-presence
  `pytest.skip`. **Do not** unskip a test whose ground truth is genuinely uncertain — if a
  sigla's `ground_truth.json` lacks a clean single-fixture `covers_expected`, leave a precise
  skip with a fresh reason.

- [ ] **Step 3: Run on this machine (fixtures present).**
  Run: `pytest tests/unit/scanners/test_pattern_art.py tests/unit/scanners/test_pattern_irl_odi.py … -v`
  Expected: PASS where fixtures exist, SKIP where absent. **If a re-pointed test FAILS** (count
  mismatch), that is a real signal the fixture/GT doesn't match the pagination engine — do NOT
  fudge the assertion; leave the test skipped with an honest reason and report it to Daniel.

- [ ] **Step 4: ruff + commit.**
  ```bash
  git add tests/unit/scanners/test_pattern_*.py
  git commit -m "test(scanners): point migrated-sigla fixture tests at PaginationScanner (production path)"
  ```

---

## Chunk 3: Fase 1a — create `OcrScannerBase`

**Files:**
- Create: `core/scanners/ocr_scanner_base.py`
- Test: covered by the existing scanner suites once subclasses are ported (Chunks 4-5). This
  chunk adds the base but does not yet wire subclasses.

- [ ] **Step 1: Write the base module.** Create `core/scanners/ocr_scanner_base.py` with:

  - `from __future__ import annotations`, imports: `time`, `Callable`, `dataclass`, `Path`,
    `ConfidenceLevel`/`NearMatchEntry`/`ScanResult`/`ScanTelemetry` from `.base`,
    `CancellationToken`/`CancelledError` from `.cancellation`, `SimpleFilenameScanner` from
    `.simple_factory`, `enumerate_cell_pdfs` from `.utils.cell_enumeration`.
  - `@dataclass class _PdfOutcome:` fields exactly:
    `count: int | None`, `method: str`, `near_matches: list[dict]`, `low_trust: bool`,
    `a7: bool`, `error_msg: str | None`.
  - `@dataclass class OcrScannerBase:` with `sigla: str`; class attrs `METHOD: str` (override),
    `LOW_CONF_FLAG: str | None = None`.
    - `count(self, folder, *, override_method=None) -> ScanResult`: delegate to
      `SimpleFilenameScanner(sigla=self.sigla).count(folder, override_method=override_method)`.
    - `count_ocr(self, folder, *, cancel, on_pdf=None, only=None, skip=None, on_page=None) ->
      ScanResult`: the harness — verbatim equivalent of today's shared scaffolding:
      `cancel.check()`; `base = SimpleFilenameScanner(sigla=self.sigla).count(folder)`;
      `if "folder_missing" in base.flags: return base`; `pdfs = enumerate_cell_pdfs(folder)`;
      `only` filter; `skip` filter; `if not pdfs: return base`;
      `precheck = self._precheck(folder, pdfs, base, on_pdf); if precheck is not None: return precheck`;
      `start = time.perf_counter()`; init `total=0`, `per_file={}`, `flags=list(base.flags)`,
      `errors=[]`, `near_matches: list[NearMatchEntry]=[]`, `a7_used=False`,
      `low_confidence_files=[]`; the per-PDF loop (see Step 2); after the loop:
      `if a7_used: flags.append("a7_one_page_locked")`;
      `if low_confidence_files and self.LOW_CONF_FLAG: flags.append(self.LOW_CONF_FLAG)`;
      `duration_ms = int((time.perf_counter()-start)*1000)`;
      `confidence = ConfidenceLevel.HIGH if not errors and not low_confidence_files else ConfidenceLevel.LOW`;
      `return ScanResult(count=total, confidence=confidence, method=self.METHOD,
      breakdown=base.breakdown, flags=flags, errors=errors, duration_ms=duration_ms,
      files_scanned=len(pdfs), per_file=per_file, telemetry=ScanTelemetry(near_matches=near_matches) if near_matches else None)`.
    - `_precheck(self, folder, pdfs, base, on_pdf) -> ScanResult | None:` default `return None`.
    - `_count_one_pdf(self, pdf, *, cancel, on_page) -> _PdfOutcome:`
      `raise NotImplementedError` (abstract; subclass-module override).

- [ ] **Step 2: The per-PDF loop body (exact semantics).** Inside `count_ocr`:
  ```python
  for pdf in pdfs:
      cancel.check()                 # OUTSIDE try — pre-PDF cancel must not emit
      emit = True
      file_count: int | None = None
      file_method = "filename_glob"
      file_nms: list[dict] = []
      try:
          outcome = self._count_one_pdf(pdf, cancel=cancel, on_page=on_page)
          if outcome.error_msg:
              errors.append(outcome.error_msg)
          if outcome.count is not None:
              per_file[pdf.name] = outcome.count
              total += outcome.count
          if outcome.a7:
              a7_used = True
          for nm in outcome.near_matches:           # rebuild NearMatchEntry from the dict keys
              near_matches.append(NearMatchEntry(
                  pdf_name=nm["pdf_name"], page_index=nm["page_index"],
                  flavor_name=nm["flavor_name"],
                  matched_anchors=nm["matched_anchors"], missing_anchors=nm["missing_anchors"]))
          if outcome.low_trust:
              low_confidence_files.append(pdf.name)
          file_count, file_method, file_nms = outcome.count, outcome.method, outcome.near_matches
      except CancelledError:
          emit = False
          raise
      finally:
          if emit and on_pdf is not None:
              on_pdf(pdf.name, file_count, file_method, file_nms)
  ```
  Note: the `NearMatchEntry` rebuild reads the serialized dict keys the subclass produced
  (`pdf_name`/`page_index`/`flavor_name`/`matched_anchors`/`missing_anchors`) — lossless.

- [ ] **Step 3: Module docstring + ruff.** Add a module docstring explaining the Template
  Method split and the "I/O stays in the subclass module for the test-patch seam" rationale.
  Run: `ruff check core/scanners/ocr_scanner_base.py`. Expected: 0.

- [ ] **Step 4: Import smoke.**
  Run: `python -c "from core.scanners.ocr_scanner_base import OcrScannerBase, _PdfOutcome; print('ok')"`
  Expected: `ok`.

- [ ] **Step 5: Commit.**
  ```bash
  git add core/scanners/ocr_scanner_base.py
  git commit -m "feat(scanners): add OcrScannerBase Template Method harness"
  ```

---

## Chunk 4: Fase 1b — port `AnchorsScanner` onto the base

**Files:**
- Modify: `core/scanners/anchors_scanner.py`

- [ ] **Step 1: Rewrite `AnchorsScanner` as a subclass.** Keep the module-level imports the
  tests patch (`get_page_count`, `count_covers_by_anchors`, `PATTERNS`, `DEFAULT_TOP_FRACTION`,
  `PdfRenderError`, `SimpleFilenameScanner`, `CancellationToken`/`CancelledError`,
  `NearMatchEntry`) so monkeypatch targets stay valid. Define:
  ```python
  @dataclass
  class AnchorsScanner(OcrScannerBase):
      METHOD = "header_band_anchors"
      LOW_CONF_FLAG = None

      def _precheck(self, folder, pdfs, base, on_pdf):
          # today's "no flavors → filename_glob progress-only" short-circuit (anchors_scanner.py:102-113)
          pattern = PATTERNS.get(self.sigla)
          flavors = pattern.get("cover_flavors", []) if pattern is not None else []
          if not flavors:
              if on_pdf is not None:
                  base_pf = base.per_file or {}
                  for pdf in pdfs:
                      on_pdf(pdf.name, base_pf.get(pdf.name, 0), "filename_glob", [])
              return base
          return None

      def _count_one_pdf(self, pdf, *, cancel, on_page):
          try:
              page_count = get_page_count(pdf)
          except PdfRenderError as exc:
              return _PdfOutcome(None, "filename_glob", [], False, False, f"page_count_failed:{pdf.name}:{exc}")
          if page_count == 1:
              return _PdfOutcome(1, "filename_glob", [], False, a7=True, error_msg=None)
          pattern = PATTERNS.get(self.sigla)
          flavors = pattern.get("cover_flavors", [])
          top_fraction = pattern.get("top_fraction", DEFAULT_TOP_FRACTION)
          try:
              ocr = count_covers_by_anchors(pdf, flavors=flavors, top_fraction=top_fraction,
                                            cancel=cancel, on_page=on_page)
          except CancelledError:
              raise
          except (PdfRenderError, OSError, RuntimeError) as exc:
              return _PdfOutcome(1, "header_band_anchors", [], False, False, f"anchors_failed:{pdf.name}:{exc}")
          nms = [{"pdf_name": pdf.name, "page_index": nm.page_index, "flavor_name": nm.flavor_name,
                  "matched_anchors": list(nm.matched_anchors), "missing_anchors": list(nm.missing_anchors)}
                 for nm in ocr.near_matches]
          return _PdfOutcome(ocr.count, "header_band_anchors", nms, False, False, None)
  ```
  Remove the old `count_ocr` body and `_filename_glob` helper (now in the base). Keep `count`
  inherited from the base (delete the subclass override, which is identical) — OR keep a thin
  override only if a test patches it (it doesn't; delete it).
  **Behavioral note:** today the `top_fraction` is read once before the loop with the comment
  "pattern is non-None here"; `_precheck` guarantees flavors exist before any `_count_one_pdf`
  call, so `PATTERNS.get(self.sigla)` is non-None in `_count_one_pdf` — but guard defensively
  (`flavors = pattern.get("cover_flavors", []) if pattern else []`) to avoid an AttributeError
  under a test that patches PATTERNS oddly.

- [ ] **Step 2: Run the full anchors suite (the byte-identity proof).**
  Run: `pytest tests/unit/scanners/test_anchors_scanner.py tests/unit/scanners/test_anchors_scanner_progress.py -v`
  Expected: ALL PASS (including the Chunk-1 cancel tests). If any fail, the port changed
  behavior — fix until byte-identical. Do NOT edit the tests to match new behavior.

- [ ] **Step 3: ruff + import smoke.**
  Run: `ruff check core/scanners/anchors_scanner.py` (0) and
  `python -c "from core.scanners.anchors_scanner import AnchorsScanner; print(AnchorsScanner(sigla='art').METHOD)"`
  Expected: `header_band_anchors`.

- [ ] **Step 4: Commit.**
  ```bash
  git add core/scanners/anchors_scanner.py
  git commit -m "refactor(scanners): port AnchorsScanner onto OcrScannerBase (count-identical)"
  ```

---

## Chunk 5: Fase 1c — port `PaginationScanner` onto the base

**Files:**
- Modify: `core/scanners/pagination_scanner.py`

- [ ] **Step 1: Rewrite `PaginationScanner` as a subclass.** Keep the patched module-level
  imports (`get_page_count`, `count_documents_by_pagination`, `RECOVERY_LOW_CONF_RATIO`,
  `PATTERNS`, `PdfRenderError`, `CancelledError`). Define:
  ```python
  @dataclass
  class PaginationScanner(OcrScannerBase):
      METHOD = "pagination"
      LOW_CONF_FLAG = "pagination_low_confidence"

      def _count_one_pdf(self, pdf, *, cancel, on_page):
          try:
              pages = get_page_count(pdf)
          except PdfRenderError as exc:
              return _PdfOutcome(None, "filename_glob", [], False, False, f"page_count_failed:{pdf.name}:{exc}")
          if pages == 1:
              return _PdfOutcome(1, "filename_glob", [], False, a7=True, error_msg=None)
          cover_code = PATTERNS[self.sigla].get("cover_code")
          try:
              pag = count_documents_by_pagination(pdf, cancel=cancel, cover_code=cover_code, on_page=on_page)
          except CancelledError:
              raise
          except (PdfRenderError, OSError, RuntimeError) as exc:
              return _PdfOutcome(1, "pagination", [], True, False, f"pagination_failed:{pdf.name}:{exc}")
          pdf_count = pag.count if pag.count > 0 else 1
          low_trust = (pag.failed_reads > 0
                       or pag.recovered_reads / max(1, pag.pages_total) > RECOVERY_LOW_CONF_RATIO
                       or pag.cover_code_recovery)
          return _PdfOutcome(pdf_count, "pagination", [], bool(low_trust), False, None)
  ```
  No `_precheck` override (the base default returns None — pagination has no flavors
  short-circuit; `cover_code` is looked up inside `_count_one_pdf`). Remove the old `count_ocr`
  body and the `count` override (inherited).

- [ ] **Step 2: Run the full pagination suite.**
  Run: `pytest tests/unit/scanners/test_pagination_scanner.py tests/unit/scanners/test_pagination_scanner_progress.py -v`
  Expected: ALL PASS (incl. Chunk-1 cancel tests). Fix any drift in the port, never the tests.

- [ ] **Step 3: ruff + import smoke.**
  Run: `ruff check core/scanners/pagination_scanner.py` (0) and
  `python -c "from core.scanners.pagination_scanner import PaginationScanner; print(PaginationScanner(sigla='odi').METHOD)"`
  Expected: `pagination`.

- [ ] **Step 4: Commit.**
  ```bash
  git add core/scanners/pagination_scanner.py
  git commit -m "refactor(scanners): port PaginationScanner onto OcrScannerBase (count-identical)"
  ```

---

## Chunk 6: Fase 1 verification — full suite + registry + live read-only smoke

- [ ] **Step 1: Registry + completeness gate.** The scanner registry (`patterns.py`
  `register_defaults`) builds one scanner per sigla by `scan_strategy`. Confirm the class
  names/constructors are unchanged so registration is intact.
  Run: `pytest tests/unit/scanners/ -q` and any registry/completeness-gate test
  (e.g. `pytest -q -k "registry or completeness or patterns"`). Expected: all green.

- [ ] **Step 2: Full fast suite.**
  Run: `pytest -m "not slow" -q`
  Expected: **682 passed** baseline + the Chunk-1 cancel tests (4 new) + any re-pointed Fase 0b
  tests that now run = **≥682, 0 failed**. Record the exact number.

- [ ] **Step 3: ruff whole repo.**
  Run: `ruff check .` Expected: 0.

- [ ] **Step 4: Live read-only smoke (the output-identity proof).** With the real corpus
  present, run `count_ocr` for one **anchors** sigla cell and one **pagination** sigla cell and
  confirm the count + method + confidence match the pre-refactor values. `count_ocr` is
  read-only (never writes `overseer.db`). Example (adapt paths to a real month/cell):
  ```python
  from pathlib import Path
  from core.scanners.cancellation import CancellationToken
  from core.scanners.anchors_scanner import AnchorsScanner
  from core.scanners.pagination_scanner import PaginationScanner
  # anchors: pick a charla/chintegral/maquinaria cell folder; pagination: an odi/insgral cell.
  print(AnchorsScanner(sigla="charla").count_ocr(Path(r"A:\informe mensual\<MES>\<HOSP>\<...charla...>"), cancel=CancellationToken()).count)
  print(PaginationScanner(sigla="odi").count_ocr(Path(r"A:\informe mensual\<MES>\<HOSP>\<...odi...>"), cancel=CancellationToken()).count)
  ```
  Compare against the same call on the pre-Fase-1 commit (or a known-good count from the
  benchmark/history). **Any mismatch = stop and investigate.** Confirm `overseer.db` sha256
  unchanged afterward.

- [ ] **Step 5: Holistic review (subagent, Opus).** Dispatch a code-quality reviewer over the
  full Fase 0+1 diff (`git diff <pre-fase0>..HEAD -- core/scanners/ tests/unit/scanners/`):
  verify no behavioral drift, the harness matches both originals branch-for-branch, ruff/style
  clean, docstrings present. Fix any blocking finding + re-review.

- [ ] **Step 6: Update `core/CLAUDE.md` Scanner Architecture note** (if needed) to mention the
  `OcrScannerBase` Template Method (a one-line addition under "The scanner triad"). Commit:
  ```bash
  git add core/CLAUDE.md && git commit -m "docs(core): note OcrScannerBase in scanner architecture"
  ```

---

## Done criteria (Fase 0 + Fase 1)

- New cancel-contract unit tests green (always-run), migrated-sigla fixture tests point at
  `PaginationScanner`.
- `AnchorsScanner` + `PaginationScanner` both subclass `OcrScannerBase`; ~75% scaffolding
  de-duplicated; each scanner ≤ ~80 lines.
- Full fast suite 0-failed; ruff 0; live read-only smoke shows byte-identical counts; real
  `overseer.db` untouched.
- No `SCANNER_PATTERNS_VERSION` bump (no behavior change).
