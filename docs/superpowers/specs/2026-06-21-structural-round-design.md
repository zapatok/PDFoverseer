# Structural Round (pre-master peak) — Design Spec

**Date:** 2026-06-21
**Branch:** `po_overhaul`
**Status:** design → review → plan → SDD execution

> Companion to the audit report `docs/research/2026-06-21-pipeline-and-tree-audit.md`.
> That report enumerated the findings (IDs `T*/D*/B*/E*/C*/P*/S*/M*`) and Daniel gated
> the cleanup into two parts: the **pure-win round** (shipped, tag-less, `1bfc170..1032936`)
> and this **structural round** (the deferred, higher-risk items). This spec designs the
> structural round.

---

## Goal

Leave the counting pipeline and the API/orchestration layer at their **peak** before
merging `po_overhaul` into `master`: remove the structural debt the audit surfaced
(scanner duplication, three god-files, N+1 PDF opens, blob re-deserialization) **without
deteriorating the counting output** and **without regressing the multiplayer lock model**.

## Hard constraint (non-negotiable)

**No change in counting output.** Every refactor in this round is behavior-preserving for
the count derivation. The verification strategy (§8) exists to prove this: the existing
suite + a new coverage net (Fase 0) + a live read-only smoke on a real cell after each
counting-touching phase. If any count drifts, the change is wrong, not the test.

## Scope

In scope (Daniel's gate, 2026-06-21): **Fases 0–3**.

- **Fase 0** — coverage net: `PaginationScanner` fixture tests (safety net for the refactors).
- **Fase 1** — extract `OcrScannerBase` (Template Method) from the two OCR scanners.
- **Fase 2** — perf: N+1 `fitz.open` (anchors engine), pase-1 double-open, session-blob
  re-deserialization in write routes.
- **Fase 3** — modularize the three god-files: `api/state.py`, `core/orchestrator.py`,
  `api/routes/sessions.py`.

**Explicitly OUT of scope** (its own focused task, Daniel's gate):

- **B1** — `scan_file_ocr` bypasses the M3a/M3b cell lock. This is a *behavior change*
  (correctness fix), not a refactor, and needs a full-stack M3-extension + a 2-context
  browser smoke. Deferred.
- Aggressive dead-helper pruning beyond the deprecated D8/D10 seams that *move* during
  Fase 1/3. The audit established the rest (`sigla_to_folder`, `load_template`,
  `apply_ocr_result`, `apply_cell_result`, …) are tested public API or load-bearing test
  seams — not harmful dead code. Leave them.

---

## Invariants that MUST survive (the refactor contract)

Every phase is checked against these. They are the reason the round is risky.

1. **Counting output is byte-identical.** Same `ScanResult.count`, `per_file`, `method`,
   `confidence`, `flags`, `telemetry` for the same inputs. Proven by: the Fase 0 net + the
   unchanged scanner unit/progress/fixture tests + a live read-only smoke. (The
   `eval/pagination_count/` benchmark uses its own *eval* engine copy, not the production
   `pagination_count.py`, so it corroborates but does not by itself prove harness identity.)
2. **Single `RLock`, one object.** `SessionManager` stays one instance with one `self._lock`.
   The `@_synchronized` decorator keeps wrapping every public mutator. Mixins are *code
   organization only* — they do not introduce a second lock or a second object.
3. **TOCTOU-safe check-then-write.** The non-decorated helpers (`_editor_conflict`,
   `_load_and_migrate`) keep being called *from inside* already-`@_synchronized` methods,
   so check+write stay atomic under the one lock. No helper that callers rely on for
   atomicity becomes `@_synchronized` (which would re-enter) or moves outside the lock.
4. **M3a/M3b lock semantics unchanged.** `participant_id` threading, `CellLockedError`→409,
   `agent_claim_cell`, `presence_lock_holder`, the read-only gating contract — all identical.
5. **Windows `spawn` safety.** The OCR worker (`_ocr_worker`, `_init_ocr_worker`) and the
   per-subprocess module globals (`_WORKER_EVENT`, `_WORKER_PROGRESS_Q`) stay **co-located in
   one module**. The initializer sets the module global in the re-imported worker process;
   splitting them across modules would set the global in the wrong module object.
6. **Import surfaces preserved.** `api.state`, `core.orchestrator`, `api.routes.sessions`
   keep exporting the names their consumers import today. Each god-file becomes a package whose
   `__init__.py` re-exports the public surface, so no importer edits are needed beyond the
   package itself. **The grep that builds each `__init__` re-export list MUST be exhaustive and
   INCLUDE `_`-prefixed names** — tests and sibling route modules import several private helpers
   directly (enumerated per-file in Fase 3 below). A missing name silently breaks an importer at
   collection time; the full suite is the backstop, but the grep is the design step.
7. **Broadcast-on-write (M1) unchanged.** The `_emit` / `asyncio.run_coroutine_threadsafe`
   bridge and the per-write `cell_updated` / `presence` / `session_refresh` broadcasts keep
   firing from the same points with the same payloads.
8. **`SCANNER_PATTERNS_VERSION` only bumps on a real behavior change.** Refactors do not bump
   it (no anchor-set / strategy change). The hookify `bump-version-tags` BLOCK rule targets
   `core/{pipeline,ocr,inference,image}.py` + `vlm/*` — none of which this round edits.

---

## Fase 0 — Coverage net (safety first)

**Why first:** the 9 pagination-migrated siglas' per-sigla fixture tests still instantiate
`AnchorsScanner` (they test the *unused* path). Before refactoring the scanners, add tests
that exercise the **production** path (`PaginationScanner`) so a regression in Fase 1/2 is
caught by a red test, not by drifting a real count.

**Design:**

- Add `PaginationScanner` fixture tests covering the migrated siglas (art, irl, odi, ext,
  bodega, caliente, exc, herramientas_elec, art, andamios, altura, insgral) against the
  existing synthetic-PDF fixtures under `tests/fixtures/scanners/` (and/or
  `eval/pagination_count/` fixtures — synthetic only, **never** real-corpus slices, per the
  fixture rules).
- Assert the full `ScanResult` contract that matters for counting: `count`, `per_file`,
  `method == "pagination"`, `confidence` (HIGH vs LOW on recovery/cover_code), the
  `a7_one_page_locked` / `pagination_low_confidence` flags.
- Fold in the 6 wrong-premise `@skip`s the audit found where they now have a correct
  premise under `PaginationScanner`.
- Keep the existing `AnchorsScanner` tests for the 6 siglas that stayed on anchors
  (charla/chintegral/dif_pts/senal/chps/maquinaria) — those are the live anchors path.

**Risk:** none (pure test addition). **Verification:** new tests green; suite count rises.

---

## Fase 1 — `OcrScannerBase` (Template Method)

**Finding (confirmed by reading both scanners):** `AnchorsScanner.count_ocr` and
`PaginationScanner.count_ocr` share ~75% identical scaffolding — the *harness*:

- `cancel.check()` → filename-glob base → `folder_missing` short-circuit → `enumerate_cell_pdfs`
  → `only`/`skip` filtering → empty short-circuit → `time.perf_counter()` start;
- the per-PDF loop: pre-`try` `cancel.check()`, `emit` flag, per-file `(count, method, nms)`
  capture, `get_page_count` with `PdfRenderError`→error+continue, `page_count == 1`→A7
  trivial+continue, engine call with `CancelledError` re-raise + `(PdfRenderError, OSError,
  RuntimeError)`→fallback, accumulation into `total`/`per_file`, `except CancelledError:
  emit=False; raise`, `finally: if emit and on_pdf: on_pdf(...)`;
- result assembly: `a7_one_page_locked` flag, `duration_ms`, confidence, `ScanResult(...)`.

The **variation** is small and isolates cleanly:

| Aspect | `AnchorsScanner` | `PaginationScanner` |
|---|---|---|
| `METHOD` | `"header_band_anchors"` | `"pagination"` |
| pre-loop guard | "no flavors → filename_glob progress-only" short-circuit | (none; looks up `cover_code`) |
| per-multipage engine | `count_covers_by_anchors` → `.count` + `.near_matches` | `count_documents_by_pagination` → `.count`/`.failed_reads`/`.recovered_reads`/`.pages_total`/`.cover_code_recovery`, degenerate-0→1 |
| per-PDF error fallback | count 1, method `header_band_anchors`, **not** low-trust | count 1, method `pagination`, **low-trust** |
| low-trust signal | never (no `low_confidence_files`) | `failed_reads>0 or recovered/pages>RATIO or cover_code_recovery` |
| extra flag | none | `"pagination_low_confidence"` when any low-trust file |
| telemetry | near-match entries | none |

**Key correctness finding:** the overall confidence rule can be **unified** —
`HIGH if not errors and not low_confidence_files else LOW`. For anchors, `low_confidence_files`
is always empty, so this reduces to `HIGH if not errors`, which is **byte-identical** to
today's anchors behavior. So the base needs no confidence hook.

### CRITICAL — keep the test-patch seam in the subclass module (blocking review finding)

The existing scanner tests monkeypatch `get_page_count` **and** the engines on the
**concrete scanner module namespace**, e.g. `monkeypatch.setattr("core.scanners.
anchors_scanner.get_page_count", …)` (17 refs), `"…anchors_scanner.count_covers_by_anchors"`,
`"core.scanners.pagination_scanner.get_page_count"` (20 refs),
`"…pagination_scanner.count_documents_by_pagination"`, plus the `_progress` tests (3+3). Python
binds these names at the *calling module*. If the `get_page_count(pdf)` call (or an engine call)
moves into `core/scanners/ocr_scanner_base.py`, those patches stop affecting it — the tests
then run real PyMuPDF I/O against stub `b"%PDF-1.4\n"` bytes → every PDF errors → **silent
in-test count drift in the very tests that are the safety net.**

**Therefore the decomposition keeps ALL per-PDF I/O calls (`get_page_count`, the engine) in the
subclass module** via `_count_one_pdf`. The base owns only the outer harness + loop skeleton +
result assembly — none of which any test patches by module path. **Net result: zero test
migration; the existing scanner suite is byte-identical and green before and after.** The price
is ~6 duplicated lines (the page-count read + A7 1-page branch) per subclass — a deliberate
trade to keep the safety net untouched.

**Design — `core/scanners/ocr_scanner_base.py`:**

```python
@dataclass
class _PdfOutcome:
    count: int | None            # None → unreadable: ticked via on_pdf, NOT merged
    method: str                  # per-file method for on_pdf / merge
    near_matches: list[dict]     # [] for pagination
    low_trust: bool              # pagination low-trust; anchors always False
    a7: bool                     # 1-page trivial → base sets the a7_one_page_locked flag
    error_msg: str | None         # appended to errors[] when set

class OcrScannerBase:
    sigla: str
    METHOD: str                  # class attr: result-level method name
    LOW_CONF_FLAG: str | None    # class attr: extra flag on any low-trust file (None = skip)

    def count(self, folder, *, override_method=None) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder, override_method=override_method)

    def count_ocr(self, folder, *, cancel, on_pdf=None, only=None, skip=None, on_page=None) -> ScanResult:
        # identical OUTER harness (cancel.check, filename base, folder_missing guard,
        # enumerate_cell_pdfs, only/skip filtering, empty guard, perf_counter start)
        precheck = self._precheck(folder, pdfs, base, on_pdf)   # hook: anchors flavors short-circuit; pagination → None
        if precheck is not None:
            return precheck
        for pdf in pdfs:
            cancel.check()                 # OUTSIDE try — a pre-PDF cancel must not emit on_pdf
            emit = True
            file_count, file_method, file_nms = None, "filename_glob", []
            try:
                outcome = self._count_one_pdf(pdf, cancel=cancel, on_page=on_page)
                if outcome.error_msg:        errors.append(outcome.error_msg)
                if outcome.count is not None: per_file[pdf.name] = outcome.count; total += outcome.count
                if outcome.a7:               a7_used = True
                if outcome.near_matches:     telemetry_nms.extend(...)   # NearMatchEntry rebuild
                if outcome.low_trust:        low_confidence_files.append(pdf.name)
                file_count, file_method, file_nms = outcome.count, outcome.method, outcome.near_matches
            except CancelledError:
                emit = False; raise
            finally:
                if emit and on_pdf is not None:
                    on_pdf(pdf.name, file_count, file_method, file_nms)
        # identical result assembly using METHOD / LOW_CONF_FLAG / unified confidence + telemetry

    def _precheck(self, folder, pdfs, base, on_pdf) -> ScanResult | None: ...   # default: None
    def _count_one_pdf(self, pdf, *, cancel, on_page) -> _PdfOutcome: ...        # abstract; lives in subclass module
```

- `AnchorsScanner(OcrScannerBase)` (in `anchors_scanner.py`): `METHOD="header_band_anchors"`,
  `LOW_CONF_FLAG=None`; `_precheck` = the flavors-empty short-circuit; `_count_one_pdf` does
  `get_page_count(pdf)` (PdfRenderError → `_PdfOutcome(count=None, method="filename_glob",
  error_msg="page_count_failed:…")`), A7 1-page → `_PdfOutcome(1, "filename_glob", [], False,
  a7=True, None)`, else `count_covers_by_anchors(...)` (success → count + serialized
  near-matches, `low_trust=False`; engine error → `_PdfOutcome(1, "header_band_anchors", [],
  **low_trust=False**, False, error_msg="anchors_failed:…")`).
- `PaginationScanner(OcrScannerBase)` (in `pagination_scanner.py`): `METHOD="pagination"`,
  `LOW_CONF_FLAG="pagination_low_confidence"`; `_count_one_pdf` does `get_page_count(pdf)`
  (same error outcome), A7 same, else `count_documents_by_pagination(...)` (degenerate-0→1;
  low-trust rule; engine error → `_PdfOutcome(1, "pagination", [], **low_trust=True**, False,
  error_msg="pagination_failed:…")`). `cover_code` looked up inside (cheap dict get).

**`CancelledError` placement (load-bearing):** `_count_one_pdf` catches only
`(PdfRenderError, OSError, RuntimeError)` for its engine fallback and **re-raises
`CancelledError`**, so the base loop's `except CancelledError: emit=False; raise` fires (no
`on_pdf` tick for an aborted PDF). The pre-PDF `cancel.check()` stays in the base loop
*outside* the try. The cancel contract is part of the count semantics.

**Risk:** medium. The per-PDF body and the loop skeleton are subtle (the `finally` runs through
the early returns; the `emit` flag; A7; the None-count "ticked but not merged" case). But the
test-patch seam stays in the subclass modules (above) → the existing scanner suite proves
identity. **Verification:** Fase 0 net + the unchanged existing anchors/pagination unit +
progress tests + the per-sigla fixture tests + a live read-only smoke on one anchors cell and
one pagination cell → counts byte-identical. (The `eval/pagination_count/` benchmark uses its
own *eval* engine copy, not the production `pagination_count.py`, so it is corroboration, not a
byte-identity proof of the refactored harness — the unit/fixture tests + smoke do the proving.)

**D8/D10 retirement:** `_filename_glob` (anchors private helper) collapses into the base.
Any deprecated seam that *moves here* is removed in passing; nothing else is pruned.

---

## Fase 2 — Performance (count-identical)

Three independent, perf-only changes. Each must produce identical pixels/counts/state.

**2a — N+1 `fitz.open` in the anchors engine ONLY (confirmed; pagination is already single-open).**
`header_band_anchors.count_covers_by_anchors` calls `get_page_count(pdf_path)` (1 `fitz.open`,
`pdf_render.py:19`) then loops `render_page_region(pdf_path, page_idx, ...)` which does
`fitz.open(pdf_path)` **per page** (`pdf_render.py:59`). A P-page PDF opens the file `1+P`
times. **Fix:** open the doc **once** and render each region against the open `doc`/`page`.
Options (decided in the plan): add `render_page_region_from_doc(doc, page_idx, ...)` + open
once in `count_covers_by_anchors`, OR a context-manager `open_pdf(pdf_path)` that yields a doc
the region renders reuse. Same pixmap math → identical OCR input → identical count.

**Scope correction (review):** the **pagination** engine
(`pagination_count.count_documents_by_pagination`) already opens once
(`pagination_count.py:195`, `with fitz.open(pdf_path) as doc:` → `doc[pi]` per page). So 2a is
the anchors engine alone, which now serves only **6** siglas (charla/chintegral/dif_pts/senal/
chps/maquinaria) — the win is real but smaller than "the primary engine." Secondary, in the
same family as 2b: both scanners read `get_page_count(pdf)` in `_count_one_pdf` AND the anchors
engine reads `get_page_count` *again* internally (`header_band_anchors.py:192`) — a per-PDF
double-open. The plan may pass the already-known page count into the engine to drop the second
read (per-PDF, not per-page — minor; include only if clean).

**2b — pase-1 double-open.** Confirm in the plan whether the filename pase (`scan_cell` /
`count_pdfs_by_sigla`) opens each PDF twice (e.g. existence + page count). If so, single-open.
Pase-1 is a ~4 s bulk pass, so the win is modest — include only if the change is clean.

**2c — session-blob re-deserialization in write routes (confirmed pattern).**
A single write (e.g. `patch_override`) deserializes the full session JSON multiple times per
request: the manager method `_load_and_migrate` does `json.loads(rec.state_json)` +
`json.dumps(state)` (`state.py:157-173`), and the route additionally reads state to build its
response and to run `refresh_all_reliable` / `refresh_reorg_deltas` (each a `get_session_state`
→ another `json.loads`). **Fix (conservative):** have the lock-guarded mutator return the
updated `state`/cell snapshot so the route builds its response without a second
deserialize, and batch the `refresh_*` reads. **Constraint:** the response snapshot must come
from *inside* the lock (the value just written) — do not add an unlocked re-read that could
observe a concurrent write (would reopen a TOCTOU the M3a model closed). If returning state
from the mutator complicates the lock contract, defer 2c rather than risk it.

**Risk:** 2a/2b low (perf-only, count-identical); 2c medium (touches the read-after-write
path near the lock). **Verification:** suite + a timing sanity check (anchors cell scan
wall-time before/after) + live smoke. 2c additionally verified by the M3a lock smoke.

---

## Fase 3 — Modularize the three god-files

Each god-file becomes a **package** that re-exports its current public surface from
`__init__.py`. Consumers' imports do not change. Done as `git mv` of the file into the new
package then splitting, so history is preserved.

### 3a — `api/state.py` (855) → `api/state/` package, via **mixins**

The riskiest split (the lock model). The safe pattern: split `SessionManager`'s methods into
**mixin classes** recombined into one `SessionManager` — still one object, one `self._lock`.

Method inventory → mixin assignment (line refs from the 2026-06-21 map):

- `_base.py` — `_SessionManagerBase.__init__` (101), `_load_and_migrate` (157, non-decorated),
  the `_synchronized` decorator (80), shared attrs (`_conn`, `_lock`, `_presence`).
- `derive.py` — module-level pure fns `_cell_has_work` (32), `compute_worker_count` (62).
- `lifecycle.py` — `LifecycleMixin`: `open_session` (106), `get_session_state` (139),
  `finalize` (732).
- `scan_apply.py` — `ScanApplyMixin`: `apply_filename_result` (176), `apply_ocr_result` (238),
  `finalize_cell_ocr` (299), `apply_per_file_ocr_result` (469), `apply_cell_result` (721).
- `writes.py` — `WriteMixin` (the `participant_id` lock seam): `apply_user_override` (345),
  `set_note` (392), `apply_per_file_override` (430), `clear_near_matches` (509),
  `apply_worker_count` (556), `apply_confirmed` (600), `set_all_reliable` (640).
- `reorg.py` — `ReorgMixin`: `add_reorg_op` (648), `delete_reorg_op` (670),
  `set_reorg_state` (689).
- `locks.py` — `LockMixin`: `_editor_conflict` (808, non-decorated, TOCTOU-safe),
  `check_cell_lock` (826), `agent_claim_cell` (771), `agent_leave` (796),
  `presence_lock_holder` (763).
- `presence.py` — `PresenceMixin`: `presence_heartbeat` (743), `presence_focus` (751),
  `presence_leave` (755), `presence_snapshot` (759). **(Naming: this mixin is distinct from
  the existing `api/presence.py` `PresenceRegistry` module — do not confuse them.)**
- `__init__.py` — `class SessionManager(LifecycleMixin, ScanApplyMixin, WriteMixin,
  ReorgMixin, LockMixin, PresenceMixin, _SessionManagerBase)`, plus re-exports. **Known
  consumers (review grep — extend in the plan):** `SessionManager`, `compute_worker_count`,
  `_cell_has_work`, `_synchronized`, `CellLockedError`, `is_agent`, **and the re-exported count
  helpers `compute_cell_count` + `_sum_marks`** (today `state.py:17-20` carries them as
  `# noqa: F401 re-exported`; `api/routes/output.py:14` imports `compute_cell_count`, plus
  `tests/test_compute_cell_count.py`, `tests/test_cell_count_cross_language.py`,
  `tests/unit/api/test_state.py`). Dropping `compute_cell_count` would break a count-path
  consumer (`output.py`) — it MUST stay in the package surface.

**Why mixins are safe here:** the composed class is one object; `self._lock` is one
attribute; `@_synchronized` reads `self._lock` at call time, so a decorated method works in
any mixin; cross-mixin calls (`self._editor_conflict`, `self._load_and_migrate`,
`self._presence.*`) resolve via MRO on the same `self`. MRO puts mixins before `_base`, so
`_base.__init__` runs once. **No second lock, no second object → invariants 2/3/4 hold by
construction.** The full suite exercises every method → a misplaced/dropped method fails red.

**Split risks:** a method assigned to the wrong mixin that another mixin calls (still works
via MRO, but keep cohesive); the `__init__` re-export list must be exhaustive (grep
consumers); `CellLockedError`/`is_agent` are imported *into* `state` from `api.presence` and
re-used — preserve those imports + re-exports.

### 3b — `core/orchestrator.py` (734) → `core/orchestration/` package (4 concerns)

- `enumeration.py` — `CellInventory` (22), `MonthInventory` (31), `_find_category_folder`
  (38), `enumerate_month` (64).
- `filename_scan.py` — pase-1: `scan_cell` (144), `_scan_cell_worker` (160), `scan_month` (178).
- `ocr_worker.py` — **co-located for spawn safety (invariant 5):** `_WORKER_EVENT` (222),
  `_WORKER_PROGRESS_Q` (223), `_init_ocr_worker` (226), `_eta_ms` (235), `_ocr_worker` (247)
  +inner `_finish`, `_serialize_near_matches` (356), `_cell_done_meta` (372).
- `ocr_scan.py` — pase-2 orchestration: `scan_one_file_ocr` (390) +inner `_on_page`,
  `scan_cells_ocr` (476) +inner `_drain`.
- `__init__.py` — re-export the public surface **plus the private names other modules/tests
  import** (review grep): `scan_month`, `scan_cells_ocr`, `scan_one_file_ocr`,
  `enumerate_month`, `CellInventory`, `MonthInventory`, **`_find_category_folder`** (imported by
  `api/routes/sessions.py:858`, `api/routes/output.py:18`, `tools/audit_sigla_page_ranges.py`),
  **`_ocr_worker`** (imported by `tests/unit/test_orchestrator_ocr_anchors.py`), **`scan_cell`**
  (imported by `tests/unit/test_orchestrator_scan.py`). **Keep `__init__.py` import-only** (no
  heavy work / cycles): under Windows spawn the child re-imports the package via
  `core.orchestration.ocr_worker`, so `__init__` runs per spawned worker.

**Split risks:** the multiprocessing `Pool` must reference `_ocr_worker`/`_init_ocr_worker`
by an importable module-level name (keep them module-level, not closures); confirm the pool
construction still imports the worker from `ocr_worker.py` correctly under Windows spawn (a
live OCR smoke is the proof). `_WORKER_*` globals are set in the worker process via the
initializer — they MUST live in the same module that `_ocr_worker` reads them from.

### 3c — `api/routes/sessions.py` (1447) → `api/routes/sessions/` package (route groups)

- `_common.py` — shared helpers + constants + DI: `_validate_session_id` (46), `file_origin`
  (79), `cell_page_counts` (106), `compute_settled` (123), `_informe_root` (159),
  `_resolve_month_dir` (163), `get_manager` (179), `refresh_all_reliable` (184),
  `refresh_reorg_deltas` (207), `_is_capped_sigla` (268), `_cell_total_pages` (272),
  constants (`_DISPATCH_POOL`, `_SESSION_ID_RE`, `_MONTH_NAMES`, `_MAX_REASONABLE_COUNT`,
  `_OCR_METHODS`).
- `scan.py` — scan orchestration routes + their helpers: `scan` (397), `scan_ocr` (695),
  `scan_file_ocr` (861), `cancel` (849), `apply_ratio` (283, RN write), and the scan-event/
  broadcast/progress helpers `_skip_files` (454), `_apply_scan_event` (466),
  `_cell_updated_event` (525), `_scan_followup_event` (548), `_handle_scan_progress` (558),
  `_broadcast_cell_updated` (643), `_broadcast_presence` (652), `_broadcast_session_refresh`
  (669), `_meta_result` (674). **(Keep the M1 broadcast helpers with the scan routes —
  invariant 7.)**
- `lifecycle.py` — `create` (370), `get` (384).
- `writes.py` — single-cell writes: `patch_override` (935), `patch_per_file_override` (987),
  `clear_near_matches` (1047), `patch_worker_count` (1082), `patch_note` (1138),
  `patch_confirm` (1185). (Pydantic models for these go here.)
- `files.py` — `get_cell_files` (1219), `get_cell_pdf` (1290).
- `reorg.py` — `create_reorg_op` (1359), `delete_reorg_op` (1398), `export_reorg_manifest`
  (1419) + reorg pydantic models.
- `__init__.py` — builds the combined `router` (`include_router` of each submodule's router)
  and re-exports the names imported elsewhere. **Review grep (extend in the plan) — several are
  private helpers pulled by tests:** `router`, `get_manager`, `file_origin`, `compute_settled`,
  `cell_page_counts`, `refresh_all_reliable`, `refresh_reorg_deltas`, `_skip_files`,
  `_apply_scan_event`, `_cell_updated_event`, `_scan_followup_event`, `_handle_scan_progress`
  (consumers incl. `tests/…/test_scan_event_merge.py`, `test_multiplayer_sync.py`,
  `test_file_origin.py`, `test_compute_settled*.py`, `test_reorg_routes.py`).
- **`_DISPATCH_POOL`** (`sessions.py:37`, a module-level `ThreadPoolExecutor`) is shared mutable
  state used by the scan routes — it must live in **one** module (`_common.py`) and be imported,
  never duplicated, or two pools would exist.

**Split risks:** helpers shared across route groups live only in `_common.py` (one home);
`apply_ratio` is a write route but uses the scan lock-gate path — keep it where its
dependencies are cleanest (scan group, since it calls scanner methods under the
editor-exclusivity gate); the `router` registration in `server.py` / `api/routes/__init__.py`
must still find `router`; pydantic models moved with their routes must not be imported by
name from the old flat path elsewhere (grep).

---

## §8 Verification strategy (per phase)

For **every** phase, in order:

1. `pytest -m "not slow"` (the full fast suite incl. eval/tests) → 0 failed. Baseline before
   this round: **682 passed / 51 skipped**. Each phase only *adds* (Fase 0) or holds the count.
2. `ruff check .` → **0** (whole repo).
3. For phases touching counting (0/1/2) or the frontend contract: `cd frontend && npm run build`
   (no frontend change expected, but the build is cheap insurance) — actually only needed if a
   route contract changes; the refactor must not change any contract, so build is a final-gate
   check, not per-phase.
4. **Live read-only smoke** after Fase 1 and Fase 2 (the counting-touching ones): run
   `count_ocr` on one **anchors** cell and one **pagination** cell against the real corpus
   (read-only — `count_ocr` never writes), assert the count matches the pre-refactor count.
   Run **fully isolated** (copy DB / no writes to `overseer.db`); verify `overseer.db`
   byte-identical (sha256) after.
5. After Fase 3a (state mixins): the M3a/M3b **lock smoke** (the lock invariants are what's at
   risk) — at minimum the API-level lock tests in the suite; a 2-context browser smoke is
   ideal but, like the M3 milestones, may be run manually.
6. After Fase 3b: a **live OCR scan smoke** (proves Windows spawn still wires the worker).

**Subagent-driven execution (Daniel's process gate):** each phase = a plan; each plan chunk
= fresh implementer subagent + two-stage review (spec compliance, then code quality), all
**≥ Sonnet** (never Haiku), holistic review at phase end. Atomic conventional commits, one
concern per commit. Push at round close.

## §9 Sequencing & commit discipline

Strict order (each gates the next): **Fase 0 → Fase 1 → Fase 2 → Fase 3a → Fase 3b → Fase 3c.**
Fase 0 first (net). Scanners (1, 2a) before the API/orchestrator splits so the counting core
is settled before the larger mechanical moves. 3a (state, highest risk) before 3b/3c so the
lock model is proven early. Each phase is independently shippable + verifiable; if any phase
fails its gate, stop and surface rather than pushing forward.

## §10 Out of scope (recap)

- **B1** (`scan_file_ocr` lock bypass) — separate full-stack task.
- Aggressive dead-helper prune — the audit established these are tested API / test seams.
- Any anchor-set / `scan_strategy` / pattern change — this round is structure only.
- VLM — stays out of the pipeline (postmortem).
- V4 — stays the deferred fallback (D10), unwired, untouched.
