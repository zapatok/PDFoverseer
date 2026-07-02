# Deep-Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every finding of the 2026-07-02 deep audit (`docs/research/2026-07-02-deep-audit.md`) — count integrity (bug #2, reorg locks, negative clamps), scan robustness, honest confidence, corpus matching, UX consistency, test hardening, and the docs sweep — without deteriorating the counting output.

**Architecture:** Work **directly on `po_overhaul`** (project convention — NO worktree), one fase = one reviewable cluster of commits, suite green after every task. All VERIFY-tagged fases run under an **output guard**: a baseline dump of every cell's effective count taken on a **copy DB** before the fase, re-dumped after, diff must contain only the enumerated intended changes. The real `overseer.db` and the corpus (`A:\informe mensual`) are never touched by tests or smokes (autouse write-guard fixture already enforces the corpus).

**Tech Stack:** Python 3.10 / FastAPI / PyMuPDF / pytest · React 18 + Vite + zustand v5 / vitest · SQLite (WAL).

**Decisions locked by Daniel (2026-07-02):** F1 = full reconciliation (consistency layer + migrate/discard UI) · F7+F8 = both go honest-LOW · E8 = migrate the 8 fixture files to `PaginationScanner` and delete the 6 wrong-premise skips · READMEs = thin pointers to the module CLAUDE.md files. Corpus facts baked in: 18 duplicate-basename groups exist (all in pre-normalization FEBRERO) → warning-flag only; chps files are named `..._cphs_...` (ABRIL) and `crs.pdf`/`titan.pdf` (MAYO) → chps needs folder-membership counting, not just an alias.

**Conventions that bind every task:** ruff 0 before each commit (hook auto-formats) · no bare `except` · Python 3.10+ typing · frontend uses `po-*` tokens only · Spanish-neutro microcopy (no voseo) · conventional commits `type(scope): message` · `SCANNER_PATTERNS_VERSION` bump when scanner matching semantics change (Fase 5 does).

**Reference:** finding IDs (F/U/PF/D/QA-…) refer to `docs/research/2026-07-02-deep-audit.md`. Read the finding before starting its task — evidence and failure scenarios live there, this plan does not repeat them.

---

## Chunk 1: Fases 0–2 (trivials · count integrity · bug #2)

### Fase 0 — Same-day trivials (SAFE)

#### Task 0.1: `openpyxl` into requirements [QA-25] + drop dead pins [QA-26, QA-27]

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-gpu.txt`

- [ ] **Step 1:** In `requirements.txt`, append `openpyxl==3.1.5` (the file is NOT alphabetized — just add it after `numpy==2.2.6`). Add a comment line above `anthropic==0.86.0`: `# anthropic + requests: used only by the opt-in vlm/ module (QA-27)`.
- [ ] **Step 2:** In `requirements-gpu.txt`, read the file first: delete the `transformers>=4.40,<5` line (line 3) AND its DiT-rationale comment lines (7-8, NON-adjacent) — but KEEP the easyocr/torch rationale lines sitting between them (lines 4-6).
- [ ] **Step 3:** Verify: `python -c "import openpyxl; print(openpyxl.__version__)"` → `3.1.5` (already installed; the pin now matches). `grep -rn "import transformers\|from transformers" --include=*.py .` → no hits.
- [ ] **Step 4:** Commit: `fix(packaging): pin openpyxl (Excel writer dep was missing); drop dead transformers pin`

#### Task 0.2: Canonical SIGLAS in the reorg destination picker [F11]

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx:26-32`
- Test: `frontend/src/components/` (covered by existing vitest suite compiling the import)

- [ ] **Step 1:** Delete the local `const HOSPITALS = [...]` and `const SIGLAS = [...]` (lines 26-32). Add `import { SIGLAS } from "../lib/sigla-labels";` and `const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];`… **no** — HOSPITALS has no canonical frontend export; check first: `grep -rn "HPV" frontend/src/lib/`. If no canonical list exists, create `export const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];` in `frontend/src/lib/sigla-labels.js` and import both from there (single source).
- [ ] **Step 2:** `grep -rn '"reunion"' frontend/src --include=*.jsx` — confirm no other hardcoded sigla list remains in components.
- [ ] **Step 3:** Run: `cd frontend && npx vitest run` → 237 passed. `npm run build` → OK.
- [ ] **Step 4:** Commit: `fix(web): reorg destination picker uses the canonical 20-sigla list (was stale 18)`

#### Task 0.3: Rename the drifted slow test [QA-4]

**Files:**
- Modify: `tests/integration/test_abril_full_corpus.py:16`

- [ ] **Step 1:** Rename `test_abril_full_corpus_yields_72_cells` → `test_abril_full_corpus_yields_80_cells`.
- [ ] **Step 2:** `python -m pytest tests/integration/test_abril_full_corpus.py --collect-only -q` → collects with the new name.
- [ ] **Step 3:** Commit: `test: rename abril full-corpus test to match its 80-cell assertion`

---

### Fase 1 — Count integrity (VERIFY: run the output guard)

#### Task 1.0: Output-guard baseline (prerequisite for every VERIFY fase)

**Files:**
- Create: `tools/dump_counts.py`

- [ ] **Step 1:** Write `tools/dump_counts.py` — a read-only CLI that, given `--db <path>`, loads every session via `SessionManager`, and prints JSON `{session_id: {"HOSP|sigla": {"count": compute_cell_count(cell, count_type_for(sigla), present=None), "worker": compute_worker_count(cell, None)}}}`. Use `OVERSEER_DB_PATH` override via env var, never the default path implicitly:

```python
"""Dump every cell's effective counts as JSON — the audit-remediation output guard."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.state import SessionManager  # noqa: E402
from core.cell_count import compute_cell_count, compute_worker_count  # noqa: E402
from core.db.connection import open_connection  # noqa: E402
from core.scanners.patterns import count_type_for  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to a COPY of overseer.db")
    args = ap.parse_args()
    conn = open_connection(Path(args.db))
    rows = conn.execute("SELECT session_id FROM sessions ORDER BY session_id").fetchall()
    os.environ["OVERSEER_DB_PATH"] = args.db
    mgr = SessionManager(conn)
    out: dict = {}
    for (sid,) in (tuple(r) for r in rows):
        state = mgr.get_session_state(sid)
        cells = {}
        for hosp, sigla_map in state.get("cells", {}).items():
            for sigla, cell in sigla_map.items():
                cells[f"{hosp}|{sigla}"] = {
                    "count": compute_cell_count(cell, count_type_for(sigla)),
                    "worker": compute_worker_count(cell),
                }
        out[sid] = cells
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
```

  (Adjust the `SessionManager(conn)` constructor call to its real signature — check `api/state.py` `__init__` — before running.)
- [ ] **Step 2:** `Copy-Item data/overseer.db "$env:TEMP/audit_guard.db"` then `python tools/dump_counts.py --db "$env:TEMP/audit_guard.db" > "$env:TEMP/counts_baseline.json"`. Keep this file for every later diff.
- [ ] **Step 3:** Commit: `chore(tools): add dump_counts.py output guard for the remediation round`

**Guard protocol (referenced as "OUTPUT GUARD" below):** after finishing a VERIFY fase, refresh the copy DB from the same original snapshot, re-run the migrations/paths the fase touched if applicable, dump again, `git diff --no-index` the two JSONs. **Allowed diffs are enumerated per fase**; anything else = stop and investigate.

#### Task 1.1: Clamp effective counts at 0 in both languages [F5-clamp]

**Files:**
- Modify: `core/cell_count.py:107-108,126`
- Modify: `frontend/src/lib/cellCount.js:64-66`, `frontend/src/lib/worker-count.js:48-53`
- Modify: `tests/fixtures/cell_count_cases.json` (+ its loader test auto-picks cases)
- Test: `tests/unit/api/test_cell_count.py` (or wherever `compute_cell_count` unit tests live — locate with `grep -rl "compute_cell_count" tests/unit`), `frontend/src/lib/cellCount.test.js`, `frontend/src/lib/worker-count.test.js`

- [ ] **Step 1 (failing tests):** Add cross-language fixture cases to `cell_count_cases.json`: `{cell: {filename_count: 2, reorg_doc_delta: -5}, count_type: "documents", expected: 0}` and a checks case with negative worker delta. Add JS unit tests: `computeCellCount({filename_count: 2, reorg_doc_delta: -5}) === 0`, `cellWorkerCount({worker_marks: {}, reorg_worker_delta: -3}, null) === 0`. Add the mirror pytest cases.
- [ ] **Step 2:** Run both suites; the new cases FAIL (current result −3/−5).
- [ ] **Step 3:** Implement: Python `compute_cell_count` → `return max(0, base + (cell.get("reorg_doc_delta") or 0))`; `compute_worker_count` → `return max(0, _sum_marks(...) + (...))`. JS `computeCellCount` → `Math.max(0, _baseCount(...) + (cell?.reorg_doc_delta ?? 0))`; `cellWorkerCount` → `Math.max(0, ...)`.
- [ ] **Step 4:** `python -m pytest tests/ -k "cell_count" -q` PASS · `npx vitest run` PASS.
- [ ] **Step 5:** Commit: `fix(count): clamp effective cell/worker counts at 0 in both languages (F5)`

#### Task 1.2: Reject negative inputs at every entry [F5-validation]

**Files:**
- Modify: `frontend/src/components/InlineEditCount.jsx:54-76`
- Modify: `api/routes/sessions/writes.py` (`PerFileOverrideRequest`, ~line 81)
- Modify: `api/routes/sessions/reorg.py:39-48` (`ReorgOpCreate`)
- Modify: `api/reorg.py:74-81` (`validate_op`)
- Test: `frontend/src/lib/override-input.test.js` siblings; `tests/unit/api/test_reorg.py`; the per-file override route test file (locate: `grep -rl "per-file" tests/unit/api`)

- [ ] **Step 1 (failing tests):** pytest — POST per-file override with `count=-1` expects 400/422; `validate_op` with `move_file` + `doc_count=5` on a file whose `src_cell` contribution is 1 expects an error string. vitest — simulate InlineEditCount commit path with `"-5"` (extract the guard into a pure helper if needed; simplest: test via the existing component test pattern or add `min` + guard and assert in a DOM test that `onCommit` is not called).
- [ ] **Step 2:** Implement:
  - `InlineEditCount.jsx`: `min={0}` on the input; Enter handler condition becomes `if (!Number.isNaN(v) && v >= 0 && (max === null || v <= max))`.
  - `PerFileOverrideRequest`: `count: int = Field(ge=0)` (import `Field` from pydantic).
  - `ReorgOpCreate`: `doc_count: int | None = Field(default=None, ge=0)`, same for `worker_count`.
  - `validate_op`: replace the `move_file` upper bound — add a `src_contribution: int | None = None` kwarg; when not None and `ot == "move_file"` and `dc > src_contribution`: error `"doc_count excede la contribución actual del archivo"`. In `create_reorg_op` (reorg.py route), compute `contribution = (src_cell.get("per_file_overrides") or {}).get(file, (src_cell.get("per_file") or {}).get(file, 1))` and pass it.
- [ ] **Step 3:** Run the touched test files + full fast suite: `python -m pytest -m "not slow" -q` → 701+new passed. vitest + `npm run build`.
- [ ] **Step 4:** Commit: `fix(validation): reject negative counts at every write entry; cap reorg doc_count by real contribution (F5)`

#### Task 1.3: Validate hospital/sigla on cell routes; history iterates the canonical grid [F13, D5]

**Files:**
- Modify: `api/routes/sessions/_common.py` (add validator)
- Modify: `api/routes/sessions/writes.py`, `api/routes/sessions/files.py`, `api/routes/sessions/scan.py` (apply-ratio + scan_file_ocr), `api/routes/sessions/reorg.py` (source/dest cells)
- Modify: `api/routes/output.py:237-259`
- Test: `tests/unit/api/test_routes_sessions.py` (new cases), `tests/unit/api/test_routes_output.py`

- [ ] **Step 1 (failing tests):** POST override to `/cells/BOGUS/odi/...` expects **400** (today: phantom cell + 200/500); POST worker-count to `/cells/HPV/FAKE/...` expects 400. Output test: a state blob containing a phantom cell (`cells["HPV"]["zzz"]`) must NOT produce a `historical_counts` row for `zzz`.
- [ ] **Step 2:** Implement `_validate_cell_coords(hospital, sigla)` in `_common.py` raising `HTTPException(400, f"Unknown hospital/sigla: {hospital}/{sigla}")` when `hospital not in HOSPITALS or sigla not in SIGLAS` (import from `core.domain`). Call it first in every route that takes `{hospital}/{sigla}` path params (grep: `hospital: str, sigla: str` across `api/routes/sessions/`). In `create_reorg_op`, validate both `source` and `dest` coords with it (replaces the ad-hoc KeyError → 404 mapping for unknown sigla).
- [ ] **Step 3:** In `output.py`'s history loop, iterate `for sigla, cell in hosp_cells.items(): if sigla not in SIGLAS: continue` (cheap skip; the canonical grid is already the Excel path's frame). While in the file [D5]: change `confidence=cell.get("confidence", "high")` → `cell.get("confidence") or "low"`.
- [ ] **Step 4:** Full fast suite + guard: **OUTPUT GUARD diff must be empty** (validation only rejects new bad input; D5 changes only history confidence strings for never-counted cells — enumerate those rows as allowed if the dump includes confidence; it doesn't → empty diff expected).
- [ ] **Step 5:** Commit: `fix(api): validate hospital/sigla on all cell routes; history skips phantom siglas; honest low confidence for never-counted history rows (F13, D5)`

#### Task 1.4: Reorg endpoints honor the M3 locks, frontend threads participant_id [F3]

**Files:**
- Modify: `api/routes/sessions/reorg.py` (both routes)
- Modify: `frontend/src/lib/api.js` (`createReorgOp`, `deleteReorgOp`)
- Modify: `frontend/src/store/session.js` (reorg actions: 409 → toast + refetch, mirroring `saveOverride`)
- Modify: `frontend/src/components/DetailPanel.jsx:486-493` + `frontend/src/components/ReorganizacionPanel.jsx` (accept `locked`, disable delete buttons)
- Test: `tests/unit/api/test_reorg_routes.py`; `frontend/src/components/ReorganizacionPanel.test.jsx`

- [ ] **Step 1 (failing tests):** pytest — with a presence registry where participant P1 focus-claimed `HRB|odi`: `POST /reorg/ops` (participant_id=P2, dest=HRB|odi) → **409** `cell_locked`; same for source-held; `DELETE /reorg/ops/{id}?participant_id=P2` on an op touching a P1-held cell → 409; `participant_id=None` (legacy) → 200 (inert, like every other write). Follow the existing M3a route-test pattern (`grep -rn "cell_locked" tests/unit/api` for the fixture recipe).
- [ ] **Step 2:** Implement backend: add `participant_id: str | None = None` to `ReorgOpCreate`; in `create_reorg_op`, after resolving the op and before `add_reorg_op`:

```python
for cell_key in ((src["hospital"], src["sigla"]), (op["dest"]["hospital"], op["dest"]["sigla"])):
    if is_agent(body.participant_id):
        holder = mgr.agent_claim_cell(session_id, *cell_key)
        if holder is not None:
            raise CellLockedError(cell_key[0], cell_key[1], holder)
    else:
        mgr.check_cell_lock(session_id, cell_key[0], cell_key[1], body.participant_id)
```

  (imports: `from api.presence import CellLockedError, is_agent` — mirror `apply_ratio` in `scan.py:84-89`). For `delete_reorg_op`: accept `participant_id: str | None = None` as a **query param**, look up the op (`next(o for o in state["reorg_ops"] if o["id"] == op_id)`) before deleting, and gate on its source+dest cells the same way.
- [ ] **Step 3:** Frontend — follow the file's established convention (`api.js` never calls `getParticipantId` itself; the **store** supplies it, as with all 8 existing write methods): `api.js` — `createReorgOp(sessionId, op, participantId)` includes `participant_id: participantId ?? null` in the body; `deleteReorgOp(sessionId, opId, participantId)` appends `?participant_id=` when set. Both switch to `jsonOrThrowStructured`. The store's reorg actions pass `getParticipantId()` (already imported in `session.js`) and catch the structured 409 → `toast.error(\`Celda bloqueada por ${err.body?.lock_holder?.name ?? "otro participante"}\`)` + `refetchSession(sessionId)` (copy the `saveOverride` 409 branch shape). `DetailPanel` passes `locked={Boolean(lockHolder)}` to `ReorganizacionPanel`; the panel disables its delete buttons when `locked` (keep Export enabled — session-wide).
- [ ] **Step 4:** Suites + build. **OUTPUT GUARD: empty diff** (gating only).
- [ ] **Step 5:** Commit: `fix(reorg): create/delete ops honor the M3 per-cell locks on source+dest; UI threads participant_id and disables delete under lock (F3)`

#### Task 1.5: Atomic reorg refresh — kill the get-then-set race [F4]

**Files:**
- Modify: `api/state.py` (new `@_synchronized` method `recompute_reorg_deltas`)
- Modify: `api/routes/sessions/_common.py:190-248` (`refresh_reorg_deltas` becomes a thin wrapper)
- Test: `tests/unit/api/test_state.py` (new), `tests/unit/api/test_reorg_routes.py` (existing keep passing)

- [ ] **Step 1 (failing test):** two-thread test: seed a session with op A; start T1 = `mgr.recompute_reorg_deltas(sid)` while T2 = `mgr.add_reorg_op(sid, opB)` + `mgr.recompute_reorg_deltas(sid)`; join; assert **both ops** persist in `state["reorg_ops"]` and both deltas applied. (With the current route-level helper this is racy-flaky; with the atomic method it must be deterministic — write the test against the *new* manager method.)
- [ ] **Step 2:** Implement `SessionManager.recompute_reorg_deltas(session_id, *, check_applied=False)`: move the body of `_common.refresh_reorg_deltas` inside the manager under `@_synchronized`, loading state ONCE via `self._load_and_migrate`, mutating `ops`/deltas, and persisting via one `update_session_state`. For `check_applied`, the on-disk presence check needs only **names**: replace `set(cell_page_counts(folder))` with `{p.name for p in folder.rglob("*.pdf")}` (no PDF opens inside the lock). `_find_category_folder` import: module-level in `state.py` (already imports from core elsewhere — keep import-cycle-free: `core.orchestrator` does not import `api.*`, safe).
- [ ] **Step 3:** Rewrite `_common.refresh_reorg_deltas(mgr, session_id, *, check_applied=False)` → `mgr.recompute_reorg_deltas(session_id, check_applied=check_applied)` (keep the wrapper so the 3 call sites don't churn). Delete the stale "safe because single writer" docstring; document the atomicity.
- [ ] **Step 4:** Move the **overlap re-validation** inside the lock: in `create_reorg_op`, pass the validated op into a new atomic `mgr.add_reorg_op_validated(session_id, op)` that re-runs *only* the overlap check (`_ranges_overlap` against fresh `state["reorg_ops"]`, extract that loop from `validate_op` into a small pure helper in `api/reorg.py`) and raises `ValueError` → route maps to 400. Page-bounds validation stays outside (needs PDF page counts).
- [ ] **Step 5:** Fast suite + **OUTPUT GUARD: empty diff**.
- [ ] **Step 6:** Commit: `fix(reorg): atomic recompute of reorg deltas + in-lock overlap check (F4 race)`

---

### Fase 2 — Bug #2: one worker-total derivation + orphan-marks reconciliation [F1]

**Design (locked):** (a) the backend becomes the ONLY producer of a cell's worker total: every cell payload (GET session, `cell_updated`, PATCH response) carries `worker_count` computed with the **present-files filter**; (b) the frontend deletes its unfiltered fallback; (c) orphan marks get a visible reconciliation UI (migrate / discard) so counted work survives corpus reorganizations. Present-files = **names only** (`rglob` listing, no PDF opens) — cheap enough for GET session.

#### Task 2.1: Backend worker_count enrichment everywhere

**Files:**
- Modify: `api/routes/sessions/_common.py` (new helpers `present_file_names(folder)`, `enrich_cell_worker_count(cell, month_root, hospital, sigla)`; use in `_cell_updated_event`)
- Modify: `api/routes/sessions/lifecycle.py:28-38` (GET session enriches all worker/checks cells)
- Modify: `api/routes/sessions/writes.py:207-221` (patch_worker_count response uses the shared helper — delete its bespoke `cell_page_counts`-based computation: names suffice)
- Test: `tests/unit/api/test_routes_sessions.py`, `tests/unit/api/test_cell_files_endpoint.py` (adjust snapshots if they assert exact cell keys)

- [ ] **Step 1 (failing tests):** GET `/sessions/{id}` → every cell whose sigla has `count_type in {"documents_workers", "checks"}` includes `worker_count` (int, present-filtered: seed a cell with marks for an absent file → expect the orphan excluded). A `cell_updated` event payload includes `worker_count`.
- [ ] **Step 2:** Implement:

```python
def present_file_names(folder: Path) -> set[str]:
    """Names of the PDFs currently in a cell folder (no opens — cheap)."""
    if not folder.exists():
        return set()
    return {p.name for p in folder.rglob("*.pdf")}


def enrich_cell_worker_count(cell: dict, month_root: Path, hospital: str, sigla: str) -> dict:
    """Return a copy of ``cell`` with the canonical present-filtered worker_count.

    The frontend must never derive this total (bug #2, F1): one producer, one filter.
    Only worker/checks siglas get the field; document siglas stay untouched.
    """
    if count_type_for(sigla) not in ("documents_workers", "checks"):
        return cell
    folder = _find_category_folder(month_root / hospital, sigla)
    present = present_file_names(folder)
    return {**cell, "worker_count": compute_worker_count(cell, present)}
```

  Wire it: `_cell_updated_event` returns `{... "cell": enrich_cell_worker_count(cell, month_root, hospital, sigla)}` (month_root from the state it already loads); GET session route maps over `state["cells"]` enriching worker/checks cells (build the response copy — do NOT persist the enriched field into state); `patch_worker_count` response uses it. Note `compute_worker_count` import already exists in `writes.py`/`output.py`; add to `_common.py`.
- [ ] **Step 3:** Excel path sanity: `output.py` `_build_worker_values` keeps its own (page-count-based) present set — switch it to `present_file_names` too (names are all `_sum_marks` needs; drops a full-folder PDF-open pass — part of PF2).
- [ ] **Step 4:** Fast suite. **OUTPUT GUARD: empty diff** (the dump uses `compute_worker_count(cell, None)` — unchanged; the Excel worker values switch from page-keys to name-keys, same sets).
- [ ] **Step 5:** Commit: `feat(api): canonical present-filtered worker_count on every cell payload (F1 consistency layer)`

#### Task 2.2: Frontend consumes the canonical total; unfiltered fallback dies

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx:159-166`
- Modify: `frontend/src/lib/worker-count.js` (align/delegate), `frontend/src/lib/cellCount.js` (export `_sumMarks` already exported)
- Modify: `frontend/src/components/FileList.jsx:65`, `frontend/src/components/WorkerCountViewer.jsx:154` (stop nulling `worker_count`; recompute locally with the real file list instead)
- Test: `frontend/src/lib/worker-count.test.js`, `frontend/src/components/` store tests

- [ ] **Step 1 (failing tests):** vitest — `cellWorkerCount({worker_marks: {"gone.pdf": [{page:1,count:9}]}, per_file: {"real.pdf": 1}}, null)` must now equal **0** (legacy per_file filter, mirroring Python), not 9. DetailPanel-level: with `cell.worker_count === 4` present → total 4; with it absent → falls back to the *filtered* derivation.
- [ ] **Step 2:** Implement: `worker-count.js` — reimplement `cellWorkerCount(cell, fileNames)` as `Math.max(0, _sumMarks(cell, fileNames) + (cell?.reorg_worker_delta ?? 0))` importing `_sumMarks` from `./cellCount` (kills the duplicate, divergent summer; keep `computeWorkerCount` only if the viewer still needs a marks-only helper — it passes real fileNames, so migrate it to `_sumMarks`-shape or leave with a comment that `null` is forbidden there). `DetailPanel` total: `cell.worker_count ?? cellWorkerCount(cell, null)` (fallback now faithful). In FileList/WorkerCountViewer optimistic updates, replace `worker_count: null` with `worker_count: cellWorkerCount(nextCell, files.map(f => f.name))` so the displayed total stays canonical between save round-trips.
- [ ] **Step 3:** vitest + build. Cross-language: add a fixture case (orphan marks + non-empty per_file, legacy null filter) to `cell_count_cases.json` if the cross-language runner covers worker counts; if it doesn't, add the pair of unit tests (py+js) with identical inputs/outputs and a comment cross-referencing them.
- [ ] **Step 4:** Commit: `fix(web): one worker-total derivation — canonical backend worker_count + faithful filtered fallback (F1)`

#### Task 2.3: Orphan-marks reconciliation — backend

**Files:**
- Modify: `api/state.py` (new `@_synchronized reconcile_worker_marks`)
- Modify: `api/routes/sessions/writes.py` (new route)
- Test: `tests/unit/api/test_state.py`, `tests/unit/api/test_routes_sessions.py`

- [ ] **Step 1 (failing tests):** manager: `reconcile_worker_marks(sid, h, s, action="migrate", from_file="old.pdf", to_file="new.pdf")` moves the marks list (append to any existing `new.pdf` marks), deletes the `old.pdf` key, persists; `action="discard"` deletes the key; unknown `from_file` → `KeyError`; lock held by another → `CellLockedError`; route: `POST /sessions/{id}/cells/{h}/{s}/worker-marks/reconcile` body `{action, from_file, to_file?, participant_id?}` → 200 with the enriched cell; `migrate` without `to_file` → 400; 409 on lock.
- [ ] **Step 2:** Implement manager method (mirror `apply_worker_count`'s lock/agent-claim preamble verbatim; body: mutate `cell["worker_marks"]`; on migrate, `cell["worker_marks"].setdefault(to_file, []).extend(marks)` keeping each mark's `page`/`count` as-is — pages are historical evidence, not viewer anchors, after a merge). Route: validate action ∈ {"migrate","discard"}, `_validate_cell_coords`, call manager, `_broadcast_cell_updated`, return the enriched cell.
- [ ] **Step 3:** Fast suite. Commit: `feat(api): worker-marks reconcile endpoint — migrate/discard orphan marks under the M3 lock (F1)`

#### Task 2.4: Orphan-marks reconciliation — UI

**Files:**
- Create: `frontend/src/components/OrphanMarksPanel.jsx`
- Modify: `frontend/src/components/DetailPanel.jsx` (render inside the worker-count section when orphans exist)
- Modify: `frontend/src/lib/api.js` (`reconcileWorkerMarks`), `frontend/src/store/session.js` (action with 409 handling)
- Test: `frontend/src/components/OrphanMarksPanel.test.jsx`

- [ ] **Step 1 (failing test):** render OrphanMarksPanel with `cell.worker_marks = {"gone.pdf": [{page:1,count:7},{page:3,count:5}]}` and `files = ["real.pdf"]` → shows `gone.pdf` with subtotal 12, a destination `<select>` listing `real.pdf`, buttons **Migrar** and **Descartar**; with no orphans → renders nothing.
- [ ] **Step 2:** Implement. Orphans computed client-side: `Object.keys(worker_marks).filter(f => !fileSet.has(f))`. Visual: suspect-tone notice (existing `po-suspect-*` tokens, same shape as the lock notice), microcopy: *"N marcas pertenecen a archivos que ya no están en la carpeta."* per-file row: `gone.pdf — 12 marcas` + `[Migrar a <select>] [Descartar]`. Actions call the store; store calls `api.reconcileWorkerMarks(...)` with `participant_id`, merges the returned enriched cell, 409 → toast + refetch (copy `saveWorkerCount`'s 409 branch shape — it already toasts + refetches, `session.js:592-605`). Confirm-before-discard: reuse the existing `Dialog` primitive with "Se descartarán N marcas de X.pdf. Esta acción no se puede deshacer."
- [ ] **Step 3:** DetailPanel: file names come from the FileList fetch it already coordinates via `filesTick` — if DetailPanel doesn't hold them, fetch via the existing `api.getCellFiles` in the panel effect (cheap, cached by tick) or lift the names from FileList's store slice; pick whichever the current wiring makes smaller. The panel only renders for `showsWorkerCounter(countType)` cells.
- [ ] **Step 4:** vitest + build + fast pytest suite.
- [ ] **Step 5:** Commit: `feat(web): orphan worker-marks panel — migrate or discard counted work after corpus reorganizations (F1)`

#### Task 2.5: Fase-2 live verification (copy DB)

- [ ] **Step 1:** Start an isolated backend on a **copy** DB (`OVERSEER_DB_PATH=<temp copy>`, `OVERSEER_OUTPUT_DIR=<temp dir>`, port 8010 — the established smoke recipe). In Brave (chrome-devtools MCP): open MAYO, pick a charla/chintegral cell with marks, verify DetailPanel total == PATCH total; simulate an orphan (copy-DB state edit: rename a marks key to `gone.pdf`) → panel appears, **Migrar** moves the subtotal to a real file and the total is unchanged; **Descartar** (on another orphan) drops the total accordingly; generate the RESUMEN on the copy → the HH cell now matches the UI total.
- [ ] **Step 2:** **OUTPUT GUARD (amended expectations):** document-count diffs = none; worker diffs = only cells where you migrated/discarded during the smoke (copy DB only). Real `overseer.db` untouched (hash-compare).
- [ ] **Step 3:** Commit any smoke-found fixes; tag nothing yet.

---

## Chunk 2: Fases 3–5 (scan robustness · honest confidence · corpus matching)

### Fase 3 — Scan robustness (SAFE)

#### Task 3.1: Cancel-with-queued-cells ends as a real `scan_cancelled`; drain never leaks [F2]

**Files:**
- Modify: `core/orchestrator/ocr_scan.py:310-357`
- Test: `tests/unit/test_orchestrator_scan.py` (new)

- [ ] **Step 1 (failing test):** monkeypatch `concurrent.futures.ProcessPoolExecutor` → `ThreadPoolExecutor` (the in-function `from concurrent.futures import ProcessPoolExecutor` resolves at call time, so patch the attribute on the `concurrent.futures` module) with `max_workers=1`; submit 4 synthetic cells whose worker blocks on a `threading.Event` for the first cell and sets `cancel` before releasing; assert `scan_cells_ocr` **returns** (no exception), the events sink received exactly one terminal event and it is `scan_cancelled`, and no `cell_error` events were fabricated. Also assert the drain thread finished: patch `threading.Thread` to capture the instance and check `not thread.is_alive()` after return.
- [ ] **Step 2:** Implement in `ocr_scan.py`:
  - Wrap the result consumption: `try: h, s, result, err = fut.result() except futures.CancelledError: cancelled += 1; scanned += 1; on_progress({"type": "scan_progress", ...}); continue` (import `concurrent.futures as futures` inside the function like its siblings).
  - Wrap pool block + drain-stop in `try/finally`: the `progress_q.put({"type": _DRAIN_STOP})` + `drain_thread.join(timeout=5.0)` + the is_alive warning move into `finally`.
- [ ] **Step 3:** Full fast suite (the synthetic-event scan tests must stay green).
- [ ] **Step 4:** Commit: `fix(orchestrator): cancelled queued futures end the batch as scan_cancelled; drain thread stopped via finally (F2)`

#### Task 3.2: Single-file OCR is cancellable [U6]

**Files:**
- Modify: `api/routes/sessions/scan.py:551-628` (register a handle; reuse the existing `/cancel`)
- Modify: `api/batch.py` (only if `make_handle` needs a variant — check first; likely reusable with `total=1`)
- Modify: `frontend/src/components/FileViewerProgress.jsx` or the lightbox's scan UI (add a Cancelar button calling the existing `api.cancelScan`)
- Test: `tests/unit/api/test_scan_file_ocr.py` (locate the B1 tests: `grep -rl "scan-ocr" tests/unit/api` and extend)

- [ ] **Step 1 (failing test):** POST single-file scan-ocr → `app.state.batches[session_id]` exists while running (reuse the batch-dedup slot so batch-vs-file scans also exclude each other — assert a concurrent batch POST 409s); POST `/cancel` sets the handle's event → the `scan_one_file_ocr` run observes `cancel_token.cancelled` and the route broadcasts `file_scan_error` with `error: "cancelled"` (or a dedicated `file_scan_cancelled` — pick `file_scan_error` + message to avoid a new frontend event type).
- [ ] **Step 2:** Implement: `handle = make_handle(session_id=session_id, total=1)`; same `setdefault` dedup as `scan_ocr` (409 `another batch is already running`); `cancel_token = CancellationToken.from_event(handle.cancel_event)`; pop the handle in `_run`'s `finally`. Frontend: show a small "Cancelar" button next to the per-file progress; on `file_scan_error` with cancelled message, toast neutral "Escaneo cancelado".
- [ ] **Step 3:** Suite + vitest + build. Commit: `feat(scan): single-file OCR is cancellable and mutually exclusive with batch scans (U6)`

#### Task 3.3: Retry doesn't double-tick progress [U9] + unify the on_page contract [U7]

**Files:**
- Modify: `core/orchestrator/ocr_worker.py:138-150` (retry) · `core/scanners/utils/pagination_count.py:205-206` · `core/orchestrator/ocr_scan.py:70-80` (adapter)
- Test: `tests/unit/test_orchestrator_scan.py`, `eval/tests/test_pagination_count.py` (on_page assertions)

- [ ] **Step 1 (failing tests):** (a) a worker whose `count_ocr` raises once then succeeds over 3 PDFs must emit exactly 3 `pdf_done` events *that the drain counts* — assert the route-visible `pdf_progress.done` never exceeds `total` **before** the clamp (expose by asserting the number of `pdf_done` events per filename == 1 after a retry — de-dup by `(cell, pdf_name)`); (b) pagination engine `on_page` receives `(page_idx_0based, total)` **before-page semantics** identical to anchors — pick ONE contract: **anchors' `(0-based idx, total) before processing`** (smaller change: pagination's `on_page(pi + 1, n)` → `on_page(pi, n)` moved to loop top) and assert `file_page_progress` for a 5-page PDF emits pages 1..5, never 6.
- [ ] **Step 2:** Implement: pagination `on_page(pi, n)` called before `_corner_text`; document the contract in `OcrScannerBase.count_ocr` docstring ("on_page(idx_0based, total), called before each page"). Retry de-dup: in `_ocr_worker`, track `ticked: set[str]` across attempts; wrap `pdf_cb` so a name already ticked re-emits `file_result` (merge is idempotent) but NOT another queue `pdf_done`… simpler and honest: suppress duplicate `pdf_done` *events* per filename via the wrapper (one line: `if name in ticked: return` before the queue put, add after the merge-relevant emit — file_result rides the same event, so instead emit a distinct `{"type": "pdf_done", "duplicate": True}`? NO — keep it minimal: skip the entire duplicate emission; attempt-2 merges land via its final per-PDF events only for files NOT ticked in attempt 1; files already ticked were already merged with identical values).
- [ ] **Step 3:** Suite. Commit: `fix(scan): per-PDF progress ticks once across retries; unified 0-based before-page on_page contract (U9, U7)`

#### Task 3.4: Shutdown awaits single-file dispatches [U11] + ghost presence on month switch [U10]

**Files:**
- Modify: `api/main.py:51-62` · `api/routes/sessions/scan.py` (single-file handle from Task 3.2 already lands in `app.state.batches` → U11 is largely FREE after 3.2 — verify then simplify) · `frontend/src/store/session.js:60-100`
- Test: existing lifespan test file (`grep -rl "lifespan" tests`), `frontend/src/store/session.presence.test.js`

- [ ] **Step 1:** Verify U11 is closed by Task 3.2 (single-file scans now registered in `app.state.batches`, which shutdown already drains). Add a regression test: lifespan shutdown with an in-flight single-file scan → `fut.result` awaited (mock-free: use the TestClient `with` teardown + a slow synthetic scan).
- [ ] **Step 2 (U10):** in `openMonth`, before reconnecting to a *different* session: `api.beaconLeave(oldSessionId, participantId)` (or call the dead `leavePresence` action and un-dead it). vitest: switching months emits a leave for the old session.
- [ ] **Step 3:** Commit: `fix(presence): leave old session on month switch; shutdown drains single-file scans (U10, U11)`

---

### Fase 4 — Honest confidence (VERIFY: benchmark + enumerated flips)

#### Task 4.1: Recovered document-starts force LOW [F7]

**Files:**
- Modify: `core/scanners/utils/pagination_count.py` (result field) · `core/scanners/pagination_scanner.py:84-91`
- Test: `eval/tests/test_pagination_count.py`, `tests/unit/scanners/test_pagination_scanner.py`

- [ ] **Step 1 (failing tests):** pure: `recover_sequence([(2,2,None),(None,None,None),(1,2,None)], 2)` recovers index 1 as `curr==1`; new `PaginationCountResult.recovered_start_count == 1` for that shape; scanner: a monkeypatched engine result with `recovered_start_count=1`, `failed_reads=0`, recovery ratio < 30% → `_PdfOutcome.low_trust is True` → cell confidence LOW + `pagination_low_confidence` flag.
- [ ] **Step 2:** Implement: `count_starts` already has the reads; compute `recovered_start_count = sum(1 for r in reads if r.curr == 1 and r.status == "recovered")` in `count_documents_by_pagination` (respecting cover_code: with cover_code set, recovered starts are never counted — keep the field raw and let the scanner ignore it when `cover_code` is set, since `cover_code_recovery` already forces LOW there). Scanner low_trust gains `or (cover_code is None and pag.recovered_start_count > 0)`.
- [ ] **Step 3:** Re-run the real-corpus pagination benchmark (slow, manual): `python -m pytest eval/tests/test_pagination_benchmark.py -m slow -q` (or its documented invocation — see `docs/research/2026-06-21-pagination-benchmark-results.md`). **Acceptance: zero count changes; only confidence flips, and only on PDFs with recovered starts.** Record the flipped set in the commit body.
- [ ] **Step 4:** Commit: `fix(pagination): a recovered document-start forces LOW confidence — review-routing for the mixed-totals overcount edge (F7)`

#### Task 4.2: Anchors 0-covers on a multi-page PDF is low-trust [F8]

**Files:**
- Modify: `core/scanners/anchors_scanner.py:64-120` (post-engine branch) · possibly `LOW_CONF_FLAG` class attr
- Test: `tests/unit/scanners/test_anchors_scanner.py` (or the generic scanner test file — locate by `grep -rl "AnchorsScanner" tests/unit/scanners | head -3`)

- [ ] **Step 1 (failing test):** monkeypatched `count_covers_by_anchors` returning `count=0` for a 5-page PDF → `_PdfOutcome(0, "header_band_anchors", low_trust=True)` → cell LOW + a `anchors_zero_covers` entry in flags; a 0 on a **1-page** PDF is impossible (A7 short-circuits) — no test needed; a legit multi-page with covers > 0 stays HIGH.
- [ ] **Step 2:** Implement: set `LOW_CONF_FLAG = "anchors_low_confidence"` on `AnchorsScanner` (it was `None`); in `_count_one_pdf`, after the engine call: `low_trust = ocr.count == 0` (pages > 1 is guaranteed at that point); return it in the outcome. Count stays 0 — honest number, amber dot.
- [ ] **Step 3:** **Enumerated flips:** run the fast suite + inspect ABRIL/MAYO copy-DB cells with anchors siglas: senal cells with 0/18 must flip green→amber. Nothing else changes (OUTPUT GUARD: count diff empty; the dump doesn't include confidence — verify flips manually in the UI smoke of Task 6.6).
- [ ] **Step 4:** Commit: `fix(anchors): zero covers on a multi-page PDF is low-trust — senal 0/18 stops reading as listo (F8)`

#### Task 4.3: Merge-time lock re-check on single-file OCR [F12]

**Files:**
- Modify: `api/routes/sessions/scan.py` (`scan_file_ocr.on_progress`)
- Test: the B1 test file (extend)

- [ ] **Step 1 (failing test):** dispatch single-file OCR as P1 (who holds the cell); before the synthetic `file_scan_done` fires, expire P1's lease and focus-claim as P2 → the merge must NOT apply; a `file_scan_error` (message "cell_locked") is broadcast instead.
- [ ] **Step 2:** Implement in `on_progress`'s `file_scan_done` branch: wrap the merge in `try: mgr.check_cell_lock(session_id, hospital, sigla, participant_id); mgr.apply_per_file_ocr_result(...) except CellLockedError: _safe_bc({type: "file_scan_error", ..., error: "cell_locked"}); return`.
- [ ] **Step 3:** Suite. Commit: `fix(scan): re-check the M3 lock at merge time for single-file OCR (F12)`

---

### Fase 5 — Corpus matching (VERIFY + `SCANNER_PATTERNS_VERSION` bump)

#### Task 5.1: Per-sigla filename token aliases; revdocmaq matches its real names [F6]

**Files:**
- Modify: `core/scanners/utils/filename_glob.py:21-69`
- Modify: `core/scanners/patterns.py:839-847` (delete the misleading `filename_glob` claim in revdocmaq's comment; see also Task 5.4)
- Modify: `core/utils.py` (`SCANNER_PATTERNS_VERSION` v5 → `"v6-token-aliases"` — single bump covers all of Fase 5; do it in THIS task, first edit)
- Test: `tests/unit/scanners/test_filename_glob.py`, `tests/unit/scanners/utils/test_filename_glob_lax.py`

- [ ] **Step 1 (failing tests):**

```python
@pytest.mark.parametrize("filename,expected", [
    ("REVISION_DOCUMENTACION_MAQUINARIA_AGUASAN.pdf", "revdocmaq"),
    ("2026-06-01_revision_documentacion_titan.pdf", "revdocmaq"),
    ("2026-04-30_cphs_acta_reunion.pdf", "chps"),          # real ABRIL file (F14 alias half)
    ("maquinaria_inspeccion_04.pdf", "maquinaria"),         # no regression
    ("2026-04_chps_acta_reunion.pdf", "chps"),              # earliest-match still holds
])
def test_extract_sigla_aliases(filename, expected):
    assert extract_sigla(filename) == expected
```

- [ ] **Step 2:** Implement `_SIGLA_TOKEN_ALIASES: dict[str, tuple[str, ...]]` in `filename_glob.py`:

```python
# Extra filename tokens that resolve to a sigla, beyond its literal name.
# Phrases use [_\-.\s]+ between words so both "revision_documentacion" and
# "revision documentacion" match. Mirrors domain._SIGLA_FOLDER_ALIASES in spirit.
_SIGLA_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "chps": (r"cphs",),
    "revdocmaq": (r"revision[_\-.\s]+documentacion",),
}
```

  Build `_SIGLA_PATTERNS` as a dict of **lists**: the literal token plus each alias, all wrapped in `_TOKEN_SEP + ... + _TOKEN_END`. `extract_sigla` collects the earliest match across all patterns of each sigla (tie-break unchanged: earliest position, then longest **matched text**, replacing `-len(sigla)` with `-match_length` so the phrase alias wins ties correctly).
- [ ] **Step 3:** Run the two test files + full fast suite (the lax-matching regression tests must stay green — 17 historical cases).
- [ ] **Step 4:** Commit: `feat(scan): per-sigla filename token aliases — revdocmaq real names + cphs spelling (F6, F14a); SCANNER_PATTERNS_VERSION v6`

#### Task 5.2: chps counts by folder membership [F14]

**Files:**
- Modify: `core/scanners/patterns.py` (`SiglaPattern` gains `count_scope: NotRequired[Literal["token", "folder"]]`; chps entry sets `"count_scope": "folder"`)
- Modify: `core/scanners/utils/filename_glob.py` (`count_pdfs_by_sigla` honors it) · `core/scanners/simple_factory.py:64-71` (`path_by_name` predicate honors it)
- Test: `tests/unit/scanners/test_filename_glob.py`, `tests/unit/scanners/test_simple_factory.py`

- [ ] **Step 1 (failing test):** a tmp folder with `crs.pdf`, `titan.pdf`, `2026-04-30_cphs_acta_reunion.pdf` → `count_pdfs_by_sigla(folder, sigla="chps")` returns count=3, `matched_filenames` = all three, no `some_files_unrecognized` flag; for `sigla="charla"` (scope token) behavior unchanged.
- [ ] **Step 2:** Implement: `count_pdfs_by_sigla` looks up `PATTERNS.get(sigla, {}).get("count_scope", "token")`; scope `"folder"` → `matched = pdfs` (every PDF in the resolved category folder belongs to the category; the folder IS the classifier). Keep flags logic (`no_matching_sigla_in_folder` can no longer fire for folder-scope). `simple_factory.path_by_name` uses the same predicate (extract a tiny shared `_matches(sigla, name)` helper in `filename_glob.py` so the two stay in lock-step).
- [ ] **Step 3:** **Enumerated output change:** chps cells in ABRIL (1 file) and MAYO (2 files) go from 0 → their real file counts. chps is **excluded from the Excel** (`EXCEL_EXCLUDED_SIGLAS`), so the RESUMEN is untouched; UI + `historical_counts` change for chps only. Run OUTPUT GUARD on the copy DB after a pase-1 re-scan of a copy session: diff must show **only** `*|chps` count rows.
- [ ] **Step 4:** Commit: `feat(scan): chps counts by folder membership — its real files carry no sigla token (F14); Excel-neutral by exclusion`

#### Task 5.3: Duplicate-basename detection [F10]

**Files:**
- Modify: `core/scanners/utils/cell_enumeration.py` (new `find_duplicate_basenames(folder) -> dict[str, int]`)
- Modify: `core/scanners/simple_factory.py` (append flag `duplicate_basenames` when non-empty)
- Modify: `frontend/src/lib/method-info.js` or the flags surface (`grep -rn "compilation_suspect" frontend/src` and mirror how that flag renders) — show "N nombres duplicados en subcarpetas — los conteos por archivo pueden solaparse"
- Test: `tests/unit/scanners/test_simple_factory.py`, plus a unit for the helper

- [ ] **Step 1 (failing test):** tmp folder `A/x.pdf` + `B/x.pdf` → helper returns `{"x.pdf": 2}`; `SimpleFilenameScanner.count` flags `duplicate_basenames`; a flat folder → no flag.
- [ ] **Step 2:** Implement (names from the same `rglob` already performed — thread through, don't re-walk). Frontend: render the flag in the cell's flags UI with suspect tone.
- [ ] **Step 3:** Suite + OUTPUT GUARD (flags only — counts unchanged; the FEBRERO duplicates are in a pre-normalization month PDFoverseer doesn't open, but the guard proves ABRIL/MAYO neutrality).
- [ ] **Step 4:** Commit: `feat(scan): surface duplicate PDF basenames per cell — the name-keyed model can undercount silently (F10)`

#### Task 5.4: Retire the dead `filename_glob` registry field [D8, F6 tail]

**Files:**
- Modify: `core/scanners/patterns.py` (delete `filename_glob` from `SiglaPattern` + all 20 entries; update the module docstring; same for `recursive_glob` — **decision**: keep `recursive_glob` (documented informational) but move its "informational only" note into `SiglaPattern`'s docstring prominently; `filename_glob` goes because it actively misleads)
- Test: `tests/unit/scanners/test_patterns_registry.py` (drop any assertion on the field)

- [ ] **Step 1:** `grep -rn "filename_glob" core/ tests/ tools/ | grep -v '"filename_glob"' | grep -v method` — confirm the only consumers are the registry entries themselves and the *method-name string* (unrelated). Delete the field from the TypedDict + entries; fix `test_patterns_registry` expectations.
- [ ] **Step 2:** Fast suite green. Commit: `refactor(patterns): drop the dead filename_glob registry field — pase-1 matches by sigla tokens (+aliases), the field only misled (D8)`

---

## Chunk 3: Fases 6–7 (frontend consistency/UX · test hardening)

### Fase 6 — Frontend consistency + UX polish

#### Task 6.1: Mirror semantics — align Python's legacy fallback to `??` [F9] + delete the writer's dead legacy branch [D4]

**Files:**
- Modify: `core/cell_count.py:72` · `core/excel/writer.py:31-33`
- Modify: `tests/fixtures/cell_count_cases.json` (+ py/js loaders pick it up)
- Test: cross-language fixture test + `tests/unit/excel/test_writer.py` (locate: `grep -rl "resolve_cell_value" tests`)

- [ ] **Step 1 (failing tests):** fixture case `{cell: {ocr_count: 0, filename_count: 5, per_file: {}}, expected: 0}` — JS already passes, Python fails (returns 5). Writer test: `resolve_cell_value({"user_override": 0, "count": 7})` must return `0` after the change (today the dead branch would return 7 if such a cell existed).
- [ ] **Step 2:** Implement: `_base_count` fallback →

```python
    if cell.get("ocr_count") is not None:
        return cell["ocr_count"]
    if cell.get("filename_count") is not None:
        return cell["filename_count"]
    return 0
```

  Delete `resolve_cell_value`'s `if value == 0 and cell.get("count") is not None: return cell["count"]` (v1→v2 migration pops `count` before any state reaches the writer).
- [ ] **Step 3:** **OUTPUT GUARD: empty diff expected** (post-1A cells all have per_file; if the guard shows a diff, a real legacy cell exists — STOP, list it, decide with Daniel whether its ocr_count=0 was a real zero).
- [ ] **Step 4:** Commit: `fix(count): ocr_count=0 is information, not absence — align Python fallback to the JS ?? semantics; drop the writer's unreachable legacy branch (F9, D4)`

#### Task 6.2: `cell_updated` respects pending saves [F15]

**Files:**
- Modify: `frontend/src/store/session.js:862-879`
- Test: `frontend/src/store/session.cellUpdated.test.js`

- [ ] **Step 1 (failing test):** with `_pendingSave` holding a key for `HPV|odi`, a `cell_updated` for that cell does NOT clobber the optimistically-set field; after the pending save resolves, state converges to the server value; a `cell_updated` for a cell with no pending save replaces wholesale (existing behavior test stays green).
- [ ] **Step 2:** Implement: in the `cell_updated` case, `const hasPending = [...prev._pendingSave.keys()].some(k => k.startsWith(`${event.hospital}|${event.sigla}`));` — if `hasPending`, skip the replace (the POST resolution + its own refetch path reconciles); else replace as today.
- [ ] **Step 3:** vitest. Commit: `fix(web): cell_updated snapshots defer to in-flight local saves (F15)`

#### Task 6.3: Per-file editor parity in the lightbox [U1] + error-path revert [U2] + checks read-only per-file [U3]

**Files:**
- Modify: `frontend/src/components/PDFLightbox.jsx:305-355` · `frontend/src/store/session.js:428-438` · `frontend/src/components/FileList.jsx:356-378`
- Test: component/store tests alongside

- [ ] **Step 1 (failing test, U2):** store test (pattern: `session.lock.test.js`): mock `api.patchPerFileOverride` to reject with a generic (non-409) error → `savePerFileOverride` must bump `filesTick` and must NOT set the global `error` field; assert a toast was emitted (mock `sonner`). Run → FAIL (today: no tick bump, sticky global error).
- [ ] **Step 2:** Implement U2 — in `savePerFileOverride`'s generic catch: bump `filesTick` (re-fetch server truth) + `toast.error(...)`; stop setting the sticky global `error` for this per-cell failure. Test passes.
- [ ] **Step 3 (failing test, U3):** FileList-level render test if the harness allows mocking its files fetch cheaply (check for an existing FileList test first: `Glob frontend/src/components/FileList*.test.jsx`); if none exists and scaffolding one exceeds ~30 lines of mocks, implement U3 test-after via the pure gate: extract `perFileCountEditable(countType)` into `lib/cell-status.js` (unit-testable: `false` for `"checks"`, `true` otherwise) and have FileList consume it.
- [ ] **Step 4:** Implement U3 — FileList renders the per-file count as plain text (no editor) when `!perFileCountEditable(countType)` (maquinaria/checks: the tally comes from marks; a per-file override is persisted-but-ignored today. documents_workers keeps the editor — its cell number IS documents).
- [ ] **Step 5:** Implement U1 — pass `disabled={isLocked}` + `max={isCappedCountType(scanInfo?.count_type) ? (currentFile?.page_count ?? null) : null}` to the lightbox `InlineEditCount` (mirror FileList's props at `FileList.jsx:362-364`). No new unit test: rendering PDFLightbox requires pdf.js scaffolding; the lock/cap behavior is asserted in the Task 6.6 smoke checklist (lightbox editor disabled under lock, over-cap rejected) and the props are one-line mirrors of FileList's tested wiring.
- [ ] **Step 6:** vitest + build. Commit: `fix(web): lightbox per-file editor gains lock+cap parity; per-file save errors revert visibly; checks cells drop the inert per-file editor (U1-U3)`

#### Task 6.4: Small-batch: tooltip honesty [U4] + speech cleanup [U12] + store selectors [PF4]

> U5 was **withdrawn** during plan review: `saveWorkerCount`'s 409 branch already calls
> `refetchSession` (`store/session.js:604`). No change needed — do not hunt for it.

**Files:**
- Create: `frontend/src/components/HospitalCard.test.jsx` (U4 test)
- Modify: `frontend/src/components/HospitalCard.jsx:64` · `frontend/src/hooks/useSpeechNumber.js:60-65` · `frontend/src/App.jsx:12`, `frontend/src/views/MonthOverview.jsx:17-22`, `frontend/src/views/HospitalDetail.jsx:14`

- [ ] **Step 1 (failing test, U4):** render `HospitalCard` with a cell shaped `{per_file: {"a.pdf": 2}, per_file_overrides: {"a.pdf": 5}, reorg_doc_delta: 1}` → the dot tooltip for that sigla must read **6** (`computeCellCount`), not 0 (the current `user_override ?? ocr_count ?? filename_count ?? 0` cascade). Follow the rendering pattern of an existing component test (e.g. `ReorganizacionPanel.test.jsx` + the per-file `@vitest-environment jsdom` pragma).
- [ ] **Step 2:** Run it → FAIL (tooltip shows 0).
- [ ] **Step 3:** Implement U4 — tooltip value → `computeCellCount(cells?.[s], countTypeFor(s))` (import `computeCellCount` from `../lib/cellCount`, `countTypeFor` from `../lib/sigla-info`; copy CategoryRow's usage). Test passes.
- [ ] **Step 4:** U12 — null `rec.onresult` in the cleanup alongside `onend`. No new test: the fix removes a post-unmount no-op callback; observable behavior is unchanged by design — covered by the existing `useSpeechNumber` suite staying green.
- [ ] **Step 5:** PF4 — replace the bare `useSessionStore()` destructures with field selectors (`useSessionStore((s) => s.view)` etc. — one selector per field, primitives only, NO object literals: the Zustand-v5 footgun rule). No new test: pure subscription-granularity refactor; the render-behavior guard is the full vitest suite + the Step-6 jank eyeball.
- [ ] **Step 6:** vitest + build + eyeball a scan in the dev server (no jank regression, no React #185 in console). Commit: `fix(web): honest card tooltips, speech cleanup, field selectors on root views (U4, U12, PF4)`

#### Task 6.5: Friendly error when the RESUMEN is open in Excel [U8]

**Files:**
- Modify: `core/excel/writer.py:90-100` or `api/routes/output.py:227-231`
- Test: `tests/unit/excel/test_writer.py`

- [ ] **Step 1 (failing test):** monkeypatch `Path.rename`/`Path.replace` to raise `PermissionError` → `generate` route returns **409** with detail `"El archivo RESUMEN está abierto en Excel — ciérralo y vuelve a generar"` (writer raises a typed `OutputLockedError`; route maps it).
- [ ] **Step 2:** Implement: wrap the bak/rename dance in `try/except PermissionError as exc: raise OutputLockedError(...) from exc` (new exception class in `writer.py`); handler in `output.py` (or a FastAPI exception handler in `main.py` — smaller: catch in the route). Frontend: the existing error toast surfaces `detail` — verify the message reads correctly.
- [ ] **Step 3:** Suite. Commit: `fix(output): friendly 409 when the RESUMEN xlsx is locked by Excel (U8)`

#### Task 6.6: Fase 4+6 UI smoke (copy DB)

- [ ] **Step 1:** Isolated backend on copy DB (:8010 recipe). Verify: senal cell shows **amber** with 0 (F8); a maquinaria cell's per-file counts are read-only (U3); lightbox editor disabled under a simulated second-participant lock (U1); tooltip on a reorg-adjusted cell matches its row count (U4). Console clean.
- [ ] **Step 2:** Commit smoke fixes if any.

---

### Fase 7 — Test hardening (SAFE)

#### Task 7.1: E8 — migrate the 8 per-sigla fixture files to PaginationScanner; delete the 6 wrong-premise skips [QA-1, QA-2]

**Files:**
- Modify: `tests/unit/scanners/test_pattern_art.py`, `test_pattern_andamios.py`, `test_pattern_herramientas_elec.py`, `test_pattern_irl_odi.py`, `test_pattern_exc.py`, `test_pattern_ext.py`, `test_pattern_caliente.py`, `test_pattern_bodega.py`

- [ ] **Step 1:** Read `tests/unit/scanners/test_pattern_altura.py` — it is the reference pattern (pure `PaginationScanner`, fixture-gated with the `pytest.skip("fixture not present")` guard). Read `tests/fixtures/scanners/README.md` for the fixture conventions.
- [ ] **Step 2:** For each of the 8 files: replace `AnchorsScanner` instantiation with `PaginationScanner`; keep the fixture-PDF paths + ground-truth counts (the GT is method-agnostic: N documents in the fixture); **irl** keeps its `cover_code` semantics (assert appendix page-1s aren't counted — the fixture GT already encodes this). Delete the 6 `@pytest.mark.skip("...anchor set...awaiting fixture rebuild...")` tests in art/andamios/herramientas_elec outright.
- [ ] **Step 3:** `python -m pytest tests/unit/scanners -q` — migrated tests pass where fixtures exist locally, skip-guard where they don't; **0 hard skips remain** with the wrong-premise reason (`python -m pytest -m "not slow" -rs -q 2>&1 | Select-String "anchor set"` → 6 remaining, all charla/senal/maquinaria).
- [ ] **Step 4:** Commit: `test(scanners): per-sigla fixtures exercise the production PaginationScanner path; drop the 6 wrong-premise skips (E8/E9 debt)`

#### Task 7.2: Guard the real-corpus test files [QA-3]

**Files:**
- Modify: `tests/unit/test_orchestrator.py`, `tests/unit/test_orchestrator_scan.py`, `tests/unit/scanners/test_simple_factory.py`, `tests/unit/scanners/test_filename_glob.py`, `tests/unit/scanners/test_page_count_heuristic.py`, `tests/unit/api/test_clear_near_matches.py`, `tests/unit/api/test_routes_output.py`, `tests/unit/api/test_routes_sessions.py`, `tests/unit/api/test_routes_months.py`, `tests/unit/api/test_state.py`

- [ ] **Step 1:** In each file, find the `A:/informe mensual/ABRIL` (or sibling) constant; add at module level:

```python
ABRIL = Path("A:/informe mensual/ABRIL")
pytestmark_corpus = pytest.mark.skipif(not ABRIL.exists(), reason="live corpus not present")
```

  and apply to the tests that actually touch the corpus (`@pytestmark_corpus` per test, or module `pytestmark` where the whole file depends on it). Do NOT convert them to `slow` — they're fast when the corpus exists; the criterion is presence, not runtime. Where an assertion doesn't truly need the real corpus (e.g. pure-logic tests that just happened to point there), switch to `tmp_path` synthetic folders instead — judge per test, prefer synthetic.
- [ ] **Step 2:** Verify both ways: `python -m pytest -m "not slow" -q` (corpus present → same pass count) and simulate absence: `$env:INFORME_MENSUAL_ROOT='C:\nonexistent'; python -m pytest tests/unit/api/test_routes_months.py -q` — hmm, the guard is path-based not env-based; simulate by running one guarded test with the constant monkeypatched — simplest honest check: temporarily rename nothing, just assert via `--collect-only` that the marks exist. Keep it pragmatic: the skipif expression is self-evidently correct once in place.
- [ ] **Step 3:** Commit: `test: real-corpus tests skip cleanly when A:/informe mensual is absent (QA-3)`

#### Task 7.3: sigla-labels completeness gate [QA-5] + fix/retire the broken capture tools [QA-6, QA-7]

**Files:**
- Create: `frontend/src/lib/sigla-labels.test.js`
- Modify: `tools/capture_failures.py:86-96`, `tools/capture_all.py:54-60` (or delete both — decision below)

- [ ] **Step 1:** vitest: every `SIGLAS` entry has a non-empty `SIGLA_LABELS` string; `siglaDisplay("chps") === "cphs"`; `siglaDisplay("art") === "art"`.
- [ ] **Step 2:** Tools decision: these capture OCR-failure crops for the V4 engine — **quarantined territory**. Default: **fix the imports minimally** (both `capture_pdf` functions: drop `EASYOCR_DPI`/`_init_easyocr`/`_upsample_4x`-if-gone; import `DPI`, `_parse` from `core.utils`, `_tess_ocr`/`_setup_sr` equivalents from `core.ocr` — read `core/ocr.py` first and map names; if the mapping is not 1:1 within 15 minutes, DELETE both tools instead and note it in the commit body — they are V4-era, unreferenced, and git preserves them).
- [ ] **Step 3:** `python -c "import tools.capture_failures, tools.capture_all"` (or confirm deletion). vitest green. Commit: `test(web): sigla-labels completeness gate; fix/retire V4-era capture tools' dead imports (QA-5..7)`

---

## Chunk 4: Fases 8–9 + cierre (docs · perf opt-in · close-out)

### Fase 8 — Docs & hygiene sweep (SAFE)

#### Task 8.1: The "18→20" + stale-architecture sweep in code-adjacent docs [QA-8, QA-9, D1, D2, D3, QA-22]

**Files:**
- Modify: `core/domain.py:13,104` · `core/scanners/patterns.py:4,877` + `count_type_for` docstring · `core/scanners/simple_factory.py:3` · `api/routes/siglas.py:18-21` · `api/routes/months.py:83` · `api/reorg.py:3` · `core/CLAUDE.md` · `api/CLAUDE.md` · `README.md:47-48` · `data/templates/README.md:86`

- [ ] **Step 1:** `grep -rn "18 sigla\|18 categor\|18 cells\|las 18\|all 18\|11 pagination\|× 18" --include=*.py --include=*.md .` — fix every hit to the current truth: **20 siglas · 2 none / 6 anchors / 12 pagination**. Fix `folder_to_sigla`'s example (`'13.-Revision Documentacion Maquinaria' -> 'revdocmaq'`; use `'99.-Categoria Inventada'` as the unmodeled example). Fix `api/reorg.py:3` → `api/routes/sessions/reorg.py`.
- [ ] **Step 2:** `core/CLAUDE.md`: rewrite the V4 intro paragraph (V4 is quarantined/deferred, NOT "reached via PaginationScanner"); update the Scanner Architecture distribution + "all 20 SIGLAS"; note `count_scope: folder` (chps) + token aliases from Fase 5. `api/CLAUDE.md`: 20 cells, sessions package layout.
- [ ] **Step 3:** Commit: `docs: sweep the 18→20 drift + stale V4 framing across code-adjacent docs (QA-8/9, D1-D3)`

#### Task 8.2: Root CLAUDE.md accuracy [QA-10, QA-11, QA-12, QA-13, QA-14]

**Files:**
- Modify: `CLAUDE.md` (root)

- [ ] **Step 1:** Rewrite line 3 + Tech Stack: lead with the real pipeline (pase-1 filename/token glob + pase-2 pagination-first OCR with anchors for template siglas; V4 quarantined as deferred fallback). Fix the structure tree (`core/` one-liner; drop `EDSR_x4.pb`). Add `npm run build` + `npm test` rows to Key Commands. Replace the frozen "Pending Work" with the actual open list (deferred structural items, the perf backlog, senal OCR follow-up, Incr-J paso-1 consumer) or a one-liner pointing at the newest Project History entry + this plan. Remove/repoint the dead `eval/pixel_density/README.md` link.
- [ ] **Step 2:** Commit: `docs: root CLAUDE.md reflects the pagination-first reality (QA-10..14)`

#### Task 8.3: Module READMEs become thin pointers [QA-15..21, QA-23, QA-24; decision locked]

**Files:**
- Modify: `core/README.md`, `api/README.md`, `tools/README.md`, `vlm/README.md:8`, `frontend/README.md`, `eval/CLAUDE.md`

- [ ] **Step 1:** `core/README.md` + `api/README.md`: replace wholesale with ~15-line files: one-paragraph module purpose, current file list (one line each), and "**Architecture and conventions live in `<module>/CLAUDE.md`** — this file intentionally defers to it." Delete every stale claim (the `core/__init__` export block especially — QA-16). `tools/README.md`: drop `regex_pattern_test.py`, add one line per existing script (incl. the QA-6/7 status/outcome). `vlm/README.md`: fix the spec link → the postmortem. `frontend/README.md`: replace boilerplate with 5 lines pointing at root README + the `po-*` token convention. `eval/CLAUDE.md`: add the 2 missing rows.
- [ ] **Step 2:** Commit: `docs: module READMEs become thin pointers to their CLAUDE.md (QA-15..24) — drift can't re-accumulate`

#### Task 8.4: api hygiene leftovers [D6, D7]

**Files:**
- Modify: `api/routes/sessions/writes.py:86-135` · `api/state.py`
- Test: existing suites

- [ ] **Step 1:** D6 — `patch_per_file_override`: add `_validate_session_id(session_id)` first; replace `mgr._load_and_migrate(session_id)` with `mgr.get_session_state(session_id)`.
- [ ] **Step 2:** D7 — delete `SessionManager.apply_ocr_result` + `SessionManager.finalize` + `core/db/sessions_repo.finalize_session` **and their tests** (prior-audit D8/D9, twice-deferred; `grep -rn "apply_ocr_result\|finalize_session\|\.finalize(" --include=*.py` to catch every reference; keep `finalize_cell_ocr` — different method).
- [ ] **Step 3:** Fast suite green (expect the deleted tests to reduce the count — note the new number). Commit: `chore(api): validate+sync patch_per_file_override; remove the twice-deferred dead finalize/apply_ocr_result surface (D6, D7)`

#### Task 8.5: D9 — flavorStub/constants leftovers

- [ ] **Step 1:** `grep -rn "flavorStub" frontend/src --include=*.js*` — if only its own test imports it, delete both; else leave with a comment. Same check for unused `constants.js` exports (`grep` each export name).
- [ ] **Step 2:** vitest + build. Commit: `chore(web): prune dead lib leftovers (D9)` (skip the commit if nothing was deletable).

---

### Fase 9 — Perf, measure-first (opt-in; PF1-PF3)

**Gate:** only enter this fase if the Fase-2/6 smokes showed noticeable save latency on big cells, OR Daniel opts in. PF was declined once (2026-06-22) as marginal — PF1 (interactive) is the new evidence; measure before building.

#### Task 9.1: Measure

- [ ] **Step 1:** With the dev backend on the copy DB, time `PATCH /cells/HPV/charla/override` (the ≤pages validation walk) 5× and `POST /output` 3× (PowerShell `Measure-Command`). Record in the plan-execution notes. **If the p50 override save is < 300 ms, STOP here** — mark Fase 9 as measured-and-declined with the numbers.

#### Task 9.2: Page-count memo (only if 9.1 shows pain)

**Files:**
- Modify: `api/routes/sessions/_common.py` (`cell_page_counts` gains a `(folder, max_mtime, file_count)`-keyed process-local memo)
- Test: unit test for invalidation (touch a file → recompute)

- [ ] **Step 1 (failing test):** two calls on an unchanged folder → 1 walk (monkeypatch-count `fitz.open` calls); modify a file's mtime → recompute.
- [ ] **Step 2:** Implement a small module-level `dict[Path, tuple[key, dict]]` memo; key = `(count, max(st_mtime of pdfs))` gathered from a names-only walk (cheap) — full open only on key change. Thread-safety: guard with a `threading.Lock` (it's called from route threads + drain).
- [ ] **Step 3:** OUTPUT GUARD empty; re-measure (Task 9.1 numbers halve or better on repeat saves). Commit: `perf(api): mtime-keyed memo for cell_page_counts — interactive saves stop re-opening every PDF (PF1-PF3)`

---

### Cierre de ronda

- [ ] **Step 1:** Full gates: `python -m pytest -m "not slow" -q` (record the final count) · `python -m pytest -m slow -q` (ABRIL corpus, 80 cells) · `cd frontend && npx vitest run && npm run build` · `ruff check .` → 0.
- [ ] **Step 2:** Final OUTPUT GUARD run against the original baseline; the union of allowed diffs = exactly: chps counts (F14), worker totals on smoke-reconciled copy cells (F1, copy only), nothing else. Real `overseer.db`: verify **data** (session counts spot-check), not just hash.
- [ ] **Step 3:** Live smoke on the real stack (read-only paths): open MAYO, confirm 20 categories, senal amber, chps showing its files + count, orphan panel absent on healthy cells.
- [ ] **Step 4:** Tag `audit-remediation-2026-07` on the final commit; push `po_overhaul`.
- [ ] **Step 5:** Ask Daniel: FF-merge `master` to the tag now (convention: re-merge at milestone) — his call.
- [ ] **Step 6:** Update `CLAUDE.md` Project History with the round entry + write the session memory file (per the established milestone-memory pattern).

---

## Execution notes for the next session

- **Order matters:** Fase 1 before Fase 2 (Task 1.0's OUTPUT-GUARD baseline must exist before ANY VERIFY work, and 2.1's guard run assumes the F5 clamps already landed; Task 2.3's lock preamble mirrors the pre-existing `apply_worker_count` pattern, not Fase-1 work). Task 3.2 before 3.4 (U11 falls out of it). Fase 5 bumps `SCANNER_PATTERNS_VERSION` once (Task 5.1, first edit) — note this is a **manual convention step**: the `bump-version-tags` hookify rule does NOT cover `core/scanners/*`, so no hook will remind you.
- **Subagent guidance (if using superpowers:subagent-driven-development):** minimum model Sonnet (project rule); implementer per task, two-stage review per fase; **never `git add -A`** (stage explicit paths — `observations.txt` lives untracked in the repo root); verify subagent commits exist before moving on (past incident: silent mid-task stop).
- **Blast-radius reminders:** anything touching `core/cell_count.py`, `cellCount.js`, `worker-count.js`, `output.py`, or `filename_glob.py` is count-defining — the OUTPUT GUARD is not optional there. The corpus root is read-only; smokes run on copy DBs with `OVERSEER_OUTPUT_DIR` isolated (2026-06-23 lesson).
- **Deliberately OUT of scope** (unchanged decisions): V4 removal (stays quarantined), pixel-density revival, VLM, the sessions/state god-file split beyond what tasks touch, old P1/P2/P3 perf items beyond PF1-PF3, **PF5** (anchors two-pass OCR cost — documented tradeoff, do not touch without a benchmark), lock-lending UX (§8 of the multiplayer spec).
