# Structural Round — Fase 3 (Modularization) Implementation Plan

> **For agentic workers:** implement via superpowers:subagent-driven-development where
> infra allows; otherwise execute directly with the same TDD/verification discipline.
> Design source of truth: `docs/superpowers/specs/2026-06-21-structural-round-design.md` §3.

**Goal:** Split the three god-files into focused packages **without changing any behavior** —
counting output, the M3 lock model, Windows-spawn wiring, and every import surface stay
identical. Each package re-exports its current public surface (incl. `_`-prefixed names tests
import) so no consumer edits are needed.

**Order (revised from spec):** **3b (orchestrator) → 3c (sessions) → 3a (state)**. Rationale:
3b/3c split genuinely separable functions/routes (clean, lower risk) and validate the
package-shim pattern; 3a (`SessionManager`, one cohesive single-lock class) gets its design
finalized last after re-reading the full file (mixin-split vs conservative helper-extraction).

**Hard invariants (per phase):** full fast suite 0-failed; ruff 0; import surface preserved
(grep incl. `_`-names); for 3b a live OCR multi-worker spawn smoke; for 3a the M3 lock tests.

---

## Fase 3b — `core/orchestrator.py` (734) → `core/orchestrator/` package

**Decision:** make `core/orchestrator/` a **package with the same name** (not `orchestration/`)
so `from core.orchestrator import X` is byte-identical — no shim, no consumer edits.

**Modules (acyclic: enumeration ← filename_scan; ocr_worker ← ocr_scan):**
- `enumeration.py` — `CellInventory`, `MonthInventory`, `_find_category_folder`,
  `enumerate_month` (imports `core.domain`).
- `filename_scan.py` — pase-1: `scan_cell`, `_scan_cell_worker`, `scan_month` (imports
  `CellInventory`/`MonthInventory` from `.enumeration`; `ScanResult` under `TYPE_CHECKING`;
  os/ProcessPoolExecutor/scanner_registry stay local imports).
- `ocr_worker.py` — **spawn-critical, co-located:** `_WORKER_EVENT`, `_WORKER_PROGRESS_Q`,
  `_init_ocr_worker`, `_eta_ms`, `_ocr_worker` (+inner `_finish`/`pdf_cb`),
  `_serialize_near_matches`, `_cell_done_meta`. Needs `import time`, `from pathlib import
  Path`, `Callable`, `Any`; local imports of scanner_registry/CancellationToken/
  enumerate_cell_pdfs/OCR_RETRY_* unchanged.
- `ocr_scan.py` — pase-2: `scan_one_file_ocr` (+inner `_on_page`), `scan_cells_ocr`
  (+inner `_emit_pdf`/`_drain`). Imports `_cell_done_meta`/`_eta_ms`/`_init_ocr_worker`/
  `_ocr_worker`/`_serialize_near_matches` from `.ocr_worker`; `logger`; local imports of
  mp/queue/threading/futures/cancellation/enumerate/pdf_render unchanged.
- `__init__.py` — **import-only** (spawn children re-run it). Re-export: `CellInventory`,
  `MonthInventory`, `_find_category_folder`, `enumerate_month`, `scan_cell`,
  `_scan_cell_worker`, `scan_month`, `scan_cells_ocr`, `scan_one_file_ocr`, `_init_ocr_worker`,
  `_eta_ms`, `_ocr_worker`, `_serialize_near_matches`, `_cell_done_meta` + `__all__`.

**Spawn safety (invariant 5):** `_init_ocr_worker` sets the module globals via `global` in
`ocr_worker.py`; `_ocr_worker` reads them from the same module → co-located → correct. The
pool (in `ocr_scan.py`) pickles `_ocr_worker`/`_init_ocr_worker` by qualname
`core.orchestrator.ocr_worker.*`; the child imports that module (running the import-only
`__init__`). No cycles, no heavy import (`core/__init__` is the quarantined docstring-only).

**Test seam migration (only one file):** `tests/test_ocr_worker_retry.py` patches
`orchestrator._WORKER_EVENT` (no-op None→None, but fragile) and `orchestrator.time.sleep`
(needs `orchestrator.time` to exist). Repoint it: `from core.orchestrator import ocr_worker`
and `monkeypatch.setattr(ocr_worker, "_WORKER_EVENT", None)` +
`monkeypatch.setattr(ocr_worker.time, "sleep", ...)` + call `ocr_worker._ocr_worker(...)`.
All other tests import re-exported functions or patch scanner/pdf_render source modules — no
change. `test_orchestrator_ocr_anchors.py` patches `AnchorsScanner.count_ocr` (the class) —
unaffected.

**Steps:**
- [ ] Create the 4 submodules + `__init__.py` (extract exact code, verbatim bodies).
- [ ] `git rm core/orchestrator.py` (the package dir replaces it).
- [ ] Migrate `tests/test_ocr_worker_retry.py` to the `ocr_worker` namespace.
- [ ] `python -c "from core.orchestrator import enumerate_month, scan_month, scan_cells_ocr, scan_one_file_ocr, _ocr_worker, _find_category_folder, CellInventory, MonthInventory; print('ok')"`.
- [ ] `pytest tests/unit/test_orchestrator*.py tests/test_ocr_worker_retry.py tests/unit/api/test_scan_event_merge.py -q` → green.
- [ ] Full fast suite + `ruff check .` → 0.
- [ ] **Live OCR multi-worker spawn smoke:** run `scan_cells_ocr` on one small real cell with
  `max_workers=2` (real ProcessPoolExecutor) and confirm it completes with a non-empty result
  + `scan_complete` event (proves the spawn wiring survives the split). Read-only; restore any
  DB. Then commit.

---

## Fase 3c — `api/routes/sessions.py` (1447) → `api/routes/sessions/` package

**Decision:** package named `sessions/` replacing the module; `__init__.py` builds the combined
`router` and re-exports the helpers consumers import.

**Modules (per spec §3c map):** `_common.py` (shared helpers + constants + DI + the single
`_DISPATCH_POOL`), `lifecycle.py` (create/get), `scan.py` (scan/scan_ocr/scan_file_ocr/cancel/
apply_ratio + all scan-event/broadcast/progress helpers — keep M1 broadcasts here),
`writes.py` (the 6 single-cell patch routes + their models), `files.py` (cell files/pdf),
`reorg.py` (reorg ops/export + models). Each submodule defines its own `APIRouter()`;
`__init__.py` `include_router`s them into one `router`.

**Import surface (per Opus review grep — exhaustive, incl. private):** `__init__` re-exports
`router`, `get_manager`, `file_origin`, `compute_settled`, `cell_page_counts`,
`refresh_all_reliable`, `refresh_reorg_deltas`, `_skip_files`, `_apply_scan_event`,
`_cell_updated_event`, `_scan_followup_event`, `_handle_scan_progress`, `_validate_session_id`
(+ any others a final grep surfaces). `_DISPATCH_POOL` lives once in `_common.py`.

**Steps:** create submodules; `git rm` the old file; exhaustive grep of importers (tests +
`output.py`/`months.py`/`history.py` etc.) → ensure each name is re-exported; verify
`server.py`/`api/routes/__init__.py` still find `router`; full suite + ruff; commit.
(Detailed steps finalized at execution time after a fresh read of the file.)

---

## Fase 3a — `api/state.py` (855): finalize design, then execute

**Open decision (resolve after re-reading the full file):** the spec drafted a **mixin-split**
(`LifecycleMixin`/`WriteMixin`/…) recomposed into one `SessionManager`. But `SessionManager` is
a single cohesive stateful class whose methods all share `self._lock`/`self._conn`/
`self._presence` and call each other — mixins that can't stand alone may add indirection that
*obscures* the lock invariants rather than clarifying them. Evaluate two options:

- **(A) Conservative (favored unless the class is truly unmanageable):** extract only the pure,
  stateless helpers (`compute_worker_count`, `_cell_has_work`, count-derivation re-exports) into
  `api/state/derive.py`, keep `SessionManager` as one cohesive class in `api/state/__init__.py`
  (or keep `api/state.py` as a module and just move the pure helpers). Lowest risk to the lock
  model; modest file reduction.
- **(B) Full mixin-split (spec §3a):** only if (A) leaves the class still unwieldy AND the
  mixin boundaries are clean. Preserve: one object, one `RLock`; `_editor_conflict`/
  `_load_and_migrate` stay **non-decorated** (TOCTOU seam); `__init__` runs once (MRO:
  mixins before base).

**Either way — import surface:** `api.state` must keep re-exporting `SessionManager`,
`compute_worker_count`, `_cell_has_work`, `_synchronized`, `CellLockedError`, `is_agent`,
**`compute_cell_count`, `_sum_marks`** (used by `output.py` + tests).

**Verification (3a):** full suite + the M3 lock tests + a live API lock smoke if feasible.

---

## Round close (after 3b+3c+3a)
Full `pytest -m "not slow"` 0-failed; `ruff check .` 0; `cd frontend && npm run build` OK;
live read-only scanner smoke (anchors + pagination cell) byte-identical vs pre-round; push.
