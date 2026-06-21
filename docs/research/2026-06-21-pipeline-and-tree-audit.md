# PDFoverseer — Pipeline + Tree Audit (pre-master-merge)

**Date:** 2026-06-21 · **Branch:** `po_overhaul` · **Goal:** leave the repo at its *peak*
before merging into `master`, **without deteriorating the current counting output.**

**Method:** four parallel read-only passes — the counting pipeline (`core/`, audited
directly), `api/` + `server.py` (Opus subagent), the project tree (`docs/`, `tools/`,
`vlm/`, `data/`, `models/`, `frontend/` — Explore subagent), and `eval/` + `tests/`
(Sonnet subagent). Baseline at audit time: suite **979 collected / 0 errors** (`-m "not
slow"`), git clean + fully pushed.

Every finding below has an ID, an **impact**, a **risk**, and an **output-safety** tag
(`SAFE` = behavior/count-preserving · `VERIFY` = could touch counts/Excel/UI, prove before
shipping). Nothing here proposes changing the counting *algorithm*; the count-defining
logic (`compute_cell_count`, `_sum_marks`, the scan merge, the `_cell_has_work`
clobber-guard, pagination recovery) was reviewed and is correct.

---

## 0. The one big decision — the V4 deferred cluster

After the 2026-06-21 pagination migration, the **V4 OCR+inference engine is unwired from
counting**. The only live remnant is `core/image.py` (used by the anchors E6 two-pass via
`header_band_anchors.py`). The dormant cluster:

| File | Lines | Note |
|---|---|---|
| `core/pipeline.py` | 419 | V4 engine (`analyze_pdf`) |
| `core/inference.py` | 604 | Dempster-Shafer inference |
| `core/ocr.py` | 115 | Tesseract+SR page processor (V4-only) |
| `core/scanners/utils/v4_count.py` | 104 | `count_documents_v4` adapter — **no live caller** |
| V4 half of `core/utils.py` | ~60 | `DPI`/`CROP_*`/`TESS_CONFIG`/`PARALLEL_WORKERS`/`BATCH_SIZE`/all `MIN_CONF/PHASE/PH5B/CLASH` consts/`_PAGE_PATTERNS`/`_to_int`/`_parse`/`Document`/`_PageRead` |
| `models/FSRCNN_x4.pb` | 41 KB | SR model (V4 CPU fallback) |
| tests | — | `test_v4_count.py`, `test_inference.py`, `test_image.py`*, `test_clean_for_ocr.py`* (*partly live) |

**A1 — `core/__init__.py` eagerly imports the whole V4 cluster.** It does `from .inference
…; from .pipeline import analyze_pdf …; from .utils import …`, and **nothing consumes those
exports** (`from core import …` appears nowhere). Because importing *any* `core.*` submodule
runs the package `__init__`, every app start eagerly loads `pipeline`→`ocr`→`inference`
(+cv2, torch-probe) for nothing. → **Impact: high (eager load + the cluster isn't actually
isolated). Risk: none. SAFE.** Emptying `core/__init__.py` is a free win **regardless of the
V4 disposition.**

**A2 — `models/EDSR_x4.pb` (38.6 MB) is referenced by no code at all** (grep: only a
CLAUDE.md/README structure comment). V4 uses `FSRCNN` or GPU bicubic, never EDSR. →
**Removable even if V4 stays. Impact: high (repo weight). Risk: none. SAFE.**

**Disposition options (your call):**
- **(rec) Quarantine** — empty `core/__init__.py` (A1), delete `EDSR_x4.pb` (A2), and leave
  the rest dormant but isolated. Reverses nothing; keeps the D10 fallback; biggest-weight
  item (EDSR) still goes. Cheapest, lowest-risk.
- **Remove** — also delete `pipeline.py`/`inference.py`/`ocr.py`/`v4_count.py` + their tests
  + `FSRCNN_x4.pb` + the V4 half of `utils.py`. Reverses the D10 "keep as fallback"
  decision; ~1,200 lines + recoverable from git/tags. Maximal slimming.
- **Keep as-is** — only do A1/A2; leave the cluster wired into `__init__`. (Not recommended:
  keeps the eager-load wart.)

---

## 1. Repo weight / tree hygiene

| ID | Item | Impact | Risk | Tag |
|---|---|---|---|---|
| T1 | `data/sessions.db` — **37.9 MB stale binary tracked in git** (already in `.gitignore:78`, never untracked; live DB is `overseer.db`, correctly ignored). `git rm --cached data/sessions.db`. | high (weight) | none | SAFE |
| T2 | `models/EDSR_x4.pb` (38.6 MB) — see A2. | high | none | SAFE |
| T3 | `tools/regex_pattern_test.py` — one-off ART_670 regex experiment reading a now-gone `data/ocr_all/all_index.csv`; no importer. | low | none | SAFE (delete/archive) |
| T4 | `README.md` (root) — still describes the pipeline as "V4 OCR + inference" primary; it's pagination-first now. | low | none | SAFE (doc) |

T1+T2 alone reclaim **~76 MB** — the bulk of repo bloat.

---

## 2. Dead code / dead surface

**core/ (all confirmed: no production caller; tests only)**

| ID | Symbol | Location |
|---|---|---|
| D1 | `scan_cell` | `core/orchestrator.py:144` (prod uses `scan_month`) |
| D2 | `sigla_to_folder`, `folder_to_sigla`, `_FOLDER_TO_SIGLA` | `core/domain.py:58/63` (prod uses `CATEGORY_FOLDERS[…]`) |
| D3 | `load_template`, `list_named_ranges` (+ `core/excel/__init__.py` re-export) | `core/excel/template.py:18/32` (writer uses `load_workbook`) |
| D4 | `get_counts_for_month` | `core/db/historical_repo.py:60` (history route uses `query_range`) |
| D5 | `render_page_image` | `core/scanners/utils/pdf_render.py:25` (prod uses `render_page_region`) |
| D6 | `make_simple_scanner` | `core/scanners/simple_factory.py:138` (registry builds `SimpleFilenameScanner` directly) |
| D7 | `recursive_glob` registry field — 13 entries in `patterns.py`, **never read** (cell_enumeration always rglobs; documented "informational only") | `core/scanners/patterns.py` |

**api/**

| ID | Symbol | Location |
|---|---|---|
| D8 | `SessionManager.apply_ocr_result` — self-deprecated (Incr 1A), no prod caller | `api/state.py:238` |
| D9 | `SessionManager.finalize` + `core/db/sessions_repo.finalize_session` — no route, no frontend caller (session finalization unreachable) | `api/state.py:732` |
| D10 | `apply_cell_result` deprecated alias (one prod caller, the `scan` route, can call `apply_filename_result`) | `api/state.py:721` |
| D11 | `api/routes/__init__.py` — stale (imports only 3 of 7 routers; nobody reads `__all__`) | `api/routes/__init__.py` |

All D1–D11 are **SAFE** (behavior-preserving); D1–D6/D8 each have tests that must be removed or migrated alongside.

---

## 3. Bugs

| ID | Severity | Finding | Tag |
|---|---|---|---|
| B1 | **correctness** | **`scan_file_ocr` bypasses the M3a/M3b cell lock** (`api/routes/sessions.py:852`). Single-file "Revisar OCR" calls `apply_per_file_ocr_result` with no lock/claim check, so it can clobber a cell another participant (human or Claude) holds — the exact collision M3a prevents. Fix at the route layer (claim/refuse before dispatch, mirroring `apply_ratio`). | VERIFY (gates a write) |
| B2 | low | `_apply_scan_event` mutates the orchestrator's `event["result"]` dict in place (`sessions.py:494`); fragile if ever fanned to two handlers. Copy-before-mutate. | SAFE |
| B3 | low | Lifespan shutdown waits on batch futures but **not** on `scan_file_ocr` dispatches (`main.py:50`) → narrow late-write-after-DB-close window (same class as the documented drain risk). | SAFE |
| B4 | cosmetic | Pase-1 `cell_skipped` WS events are computed + emitted but always dropped by the frontend (documented M3b limitation). Surface `resp.skipped` in `runScan`, or drop the dead emission. | SAFE |

**No bugs found in the counting algorithm.** B1 is the only finding with real correctness
weight; its fix changes *when a write is allowed*, so verify the single-user "Revisar OCR"
path still works.

---

## 4. Test / eval cleanup

**4a. Abandoned eval sub-projects** (no `core/`/`api/` import; postmortems declare them
shelved). Removing each dir + its eval tests touches zero production path.

| ID | Item | Status evidence |
|---|---|---|
| E1 | `eval/graph_inference/` (6 files + 3 result JSONs) + `eval/tests/test_graph_inference.py` | POSTMORTEM "shelved (not adopted)" |
| E2 | `eval/ocr_engines/` (~5 files) + `eval/tests/test_benchmark.py` | POSTMORTEM "EasyOCR/PaddleOCR eliminated, Tesseract sole engine" |
| E3 | `eval/pixel_density/` (35 files) + 11 `eval/tests/test_pd_*.py`/`test_scorer_*`/`test_bilateral_cosine`/`test_dit_embeddings` | Not on roadmap; **parked research** (branch `research/pixel-density` preserves it) — see caveat |
| E4 | `eval/tests/test_dit_embeddings.py:16` hardcodes a real corpus path (`A:/informe mensual/MARZO/rio_bueno/…ART PINGON…`). Skip-guarded (never runs), but a committed real path. Resolved by E3. | DATA-CONCERN |

**Caveat on E3:** pixel_density is *parked research*, not pure cruft (memory
`project_pixel_density_status`: ART/HLL solved, CH pending). It's safe to remove from
`po_overhaul` (recoverable from git + the research branch), but that's a judgment call —
hence a decision below.

**4b. Reverted-feature tests**

| ID | Item |
|---|---|
| E5 | `tests/test_vlm_*.py` (6 files) — VLM reverted 2026-03-30; import only `vlm.*`, zero production import. (Keep the `vlm/` package itself — intentional reference module — or retire it; the *tests* are dead either way.) |

**4c. Redundant / empty**

| ID | Item |
|---|---|
| E6 | `eval/tests/test_ocr_preprocess_new.py` — empty stub (2-line comment, 0 tests) |
| E7 | `eval/tests/test_preprocess.py` — duplicate of `test_ocr_preprocess.py` |

**4d. Stale skips & the coverage gap (most important test finding)**

| ID | Item | Tag |
|---|---|---|
| E8 | **Coverage gap:** the 9 pagination-migrated siglas (irl, odi, art, andamios, herramientas_elec, bodega, caliente, exc, ext) still have **anchor** fixture tests (`test_pattern_*` instantiate `AnchorsScanner`) — they test the *unused* path; **no `PaginationScanner` fixture test covers the production path** for them. The engine is covered generically (`test_pagination_count.py` pure fns + `test_pagination_scanner.py` contract + the real-corpus benchmark), so this is a *coverage* gap, not an output regression. Add per-sigla `PaginationScanner` fixture tests (or repoint existing ones). | VERIFY (harden) |
| E9 | 12 hard `@pytest.mark.skip` "awaiting fixture rebuild". 6 (charla/senal/maquinaria — still anchors) are legitimately pending. 6 (andamios/art/herramientas_elec — now pagination) have a **wrong premise**: the fix is a `PaginationScanner` replacement (folds into E8), not an anchor rebuild. | SAFE (cleanup) |

Removing 4a+4b+4c trims **~100–150 collected tests** with zero production impact. E8/E9 are
*additive* (restore real coverage of the migrated path).

---

## 5. Docs cleanup (archive, don't delete — historical record)

Move to a new `docs/archive/` (keep paths referenced by `CLAUDE.md`/memory in place):

| ID | Item | Why |
|---|---|---|
| C1 | `docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md` | superseded by the 2026-06-20 pagination spec |
| C2 | `docs/superpowers/{specs/2026-03-15-crop-selector-design.md, plans/2026-03-15-crop-selector.md, plans/2026-03-15-ocr-matcher.md}` | unmerged feature branches |
| C3 | `docs/superpowers/reports/2026-04-11-dit-*.md` (3) | DIT classifier experiments (with E3) |
| C4 | `docs/research/2026-04-01-pd-*.md`, `2026-04-06-scorer-forms-results.md` | pixel-density/scorer research (with E3) |

**Keep:** the VLM postmortem (CLAUDE.md Links), the anchor-truncation postmortem (memory),
and all shipped-milestone specs/plans (the record `CLAUDE.md` points to).

---

## 6. Performance opportunities

| ID | Item | Impact | Tag |
|---|---|---|---|
| P1 | **`AnchorsScanner` re-opens each PDF once per page** — `render_page_region` does `fitz.open` per call (`pdf_render.py:59`), so an N-page PDF = N+1 opens; the pagination engine opens once. Refactor `count_covers_by_anchors` to open the doc once. Affects the 6 anchor siglas on long compilations. | medium | VERIFY (anchors path) |
| P2 | Pase-1 double-opens every PDF: `simple_factory` builds a `pages` map *and* `flag_compilation_suspect` re-opens all PDFs. Compute page counts once, share. | low-med | VERIFY |
| P3 | api write-routes re-deserialize the full 72-cell session blob 2–3×/request (setter loads, then `get_session_state` read-back, then `_broadcast_cell_updated` reads again). Have setters return the cell. | medium | VERIFY (response/WS shape) |
| P4 | `output.py` walks `state["cells"]` + folders in 3 independent passes (`_build_cell_values`, `_build_worker_values`, history loop). Single pass. Infrequent (manual gen). | low | VERIFY |

All perf items touch read/merge paths → measure counts before/after.

---

## 7. Style / best-practices (all SAFE)

| ID | Item |
|---|---|
| S1 | Stale docstrings: `core/ocr.py:1` ("Tesseract + EasyOCR tier 3" — EasyOCR removed); `pagination_count.py:1` ("eval prototype" — it's the production engine); `simple_factory.py:1` ("FASE 2, 4 siglas"). |
| S2 | False `# noqa: F401 re-exported` comments on `CellLockedError`/`is_agent` in `api/state.py:13/15` (both used in-module). |
| S3 | `datetime.utcnow()` deprecated → `datetime.now(UTC)` (`api/routes/history.py:34`). |
| S4 | Mid-file imports w/ `# noqa: E402` not justified by `sys.path` (`sessions.py:69/849/1325`). |
| S5 | Inconsistent invalid-session-id status: 422 in `patch_worker_count`/`patch_note`, 400 everywhere else → route both through `_validate_session_id`. |
| S6 | Duplication: `_SESSION_ID_RE`+validator (×4 modules), `_informe_root`+`_MONTH_NAMES` (×2), marshal-to-loop helper (×3), the `if is_agent(): _broadcast_presence` tail (×7) → hoist into `api/routes/_common.py`. |
| S7 | `core/ocr.py` `on_log: callable` uses the builtin instead of `Callable`. |
| S8 | `base.py` `Scanner` Protocol declares only `count()`, not `count_ocr()` (orchestrator duck-types via `getattr`). Add an optional-OCR Protocol or document. |

---

## 8. Modularization

| ID | Item |
|---|---|
| M1 | `api/routes/sessions.py` (**1440 lines**) is a god-file → split: `routes/scan.py` (scan/cancel/progress), `routes/cells.py` (per-cell/file edits + apply-ratio + file serving), `routes/reorg.py`, `lib/counting.py` (pure `file_origin`/`compute_settled`/`cell_page_counts`/`refresh_all_reliable` — already imported by `output.py`), `routes/_common.py` (validators + shared consts). Mechanical move; full suite as guard. |
| M2 | The two scanners share **~75%** of their `count_ocr` scaffolding (enumerate→only/skip filter→A7→per-PDF try/finally→on_pdf→error-fallback→confidence). Extract a shared base/template-method; each scanner supplies only its per-PDF count fn + low-trust rule. |
| M3 | `core/orchestrator.py` (734) mixes 4 concerns (enumerate / pase-1 parallel / per-file OCR / pase-2 batch) + duplicates the `pdf_progress`+`file_result`+`cell_done` emission across the sync path and the drain thread. Optional split (`enumerate.py` / `scan_pase1.py` / `scan_pase2.py`). |
| M4 | `core/utils.py` interleaves live config with the dead V4 block → section or split (follows the V4 disposition). |
| M5 | `api/state.py` (855) — presence pass-throughs could move to a thin facade (lower priority than M1). |

---

## 9. Staged remediation plan (ordered safe → risky; each stage = suite green + commit)

**Stage 0 — baseline:** run the full suite (`pytest`) + `ruff check .` + `npm run build`;
record green. Snapshot a known cell-count set on a copy DB to diff against later (output guard).

**Stage 1 — zero-risk hygiene (SAFE, no logic):** T1 (untrack sessions.db), T2 (rm EDSR),
A1 (empty `core/__init__.py`), S1/S2/S3/S7 (docstrings/noqa/datetime), D11 (routes/__init__),
E6/E7 (empty+dup tests), T4 (README), D7 (recursive_glob). → suite green, commit per group.

**Stage 2 — dead-code removal (SAFE; remove symbol + its tests together):** D1–D6, D8–D10.

**Stage 3 — test/eval slimming (decision-gated — §10):** E1/E2 (clearly shelved), then
E3+E4+C3+C4 (pixel_density, if approved), E5 (vlm tests), E9 cleanup, docs archive C1/C2.

**Stage 4 — bug fixes:** B2/B3/B4 (SAFE) → then B1 (VERIFY: prove single-user Revisar-OCR
still works + no clobber).

**Stage 5 — coverage hardening:** E8 (PaginationScanner fixture tests for the 9 migrated
siglas) + fold in E9's 6 wrong-premise skips.

**Stage 6 — style/dedup (SAFE):** S4/S5/S6/S8.

**Stage 7 — modularization (mechanical, suite-guarded):** M1 (sessions split), M2 (scanner
base), then optionally M3/M4/M5.

**Stage 8 — perf (VERIFY each against counts):** P1, P2, P3, P4.

Stages 1–2 + 4(B2-B4) + 6 are pure wins. 3 is decision-gated. 5 restores coverage. 7 is the
"remodularize" Daniel asked about. 8 is opt-in.

---

## 10. Decisions needed from Daniel

1. **V4 disposition** — Quarantine (rec) / Remove / Keep-as-is. (§0)
2. **Parked research (pixel_density E3 + DIT docs C3/C4)** — remove from `po_overhaul`
   (git + research branch preserve it) / archive in-repo / keep. (§4a)
3. **Docs** — archive the superseded/unmerged set to `docs/archive/` (rec) / leave. (§5)
4. **Scope of execution now** — all stages / stop after the pure-win stages (1,2,4,6) and
   review before the structural ones (5,7) / a subset.

Everything else (bugs, dead helpers, perf, style, modularization) has a clear recommended
path and is gated on the suite staying green + no count drift.
