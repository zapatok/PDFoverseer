# Anti-colados Guard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect misfiled documents ("colados") in the counting corpus — whole foreign files by filename (all 20 siglas) and foreign page-runs inside compilations by form code (pagination siglas, opt-in) — surfacing each with a prefilled Incr-J reorg-op suggestion, **without ever changing a count by detection alone**.

**Architecture:** Pure detection helpers in a new `core/scanners/utils/colado_guard.py`; vertiente 1 hooks the pase-1 `SimpleFilenameScanner` (the single pase-1 path — both OCR scanners delegate `count()` to it) and persists via `apply_filename_result`; vertiente 2 (behind the §7 survey gate) extends the pagination engine with per-document segmentation and per-sigla `expected_codes`. Suspects live in cell state, are refreshed per-kind with evidence-based eviction, fold into the existing `all_reliable` derivation when `counted`, and surface in a DetailPanel panel with "Crear op de reorg" / "Descartar".

**Tech Stack:** Python 3.10 + FastAPI + PyMuPDF/Tesseract (existing engines only — no new OCR), React/Zustand/vitest, SQLite state JSON.

**Authority:** the spec `docs/superpowers/specs/2026-07-03-anti-colados-guard-design.md` **wins over this plan** on any discrepancy (per-project convention: verbose contracts copy verbatim spec→plan→code). Sections cited as §N below are spec sections.

**Project conventions that bind every task:** work directly on `po_overhaul` (no worktrees); NEVER `git add -A`/`git add .` (stage exact paths); corpus `A:\informe mensual` is READ-ONLY; never touch `data/overseer.db`; `ruff check .` = 0 before each commit; Spanish neutro in all UI copy; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**Hard invariant (test-enforced in Task 19):** counting output is byte-identical with the guard active. Detection writes flags/telemetry/suspects — never counts.

---

## Chunk 1: Fase V1 — vertiente filename, end-to-end

### Task 1: `siglas_suggested_by_filename` (the name-suggestion primitive)

**Files:**
- Modify: `core/scanners/utils/filename_glob.py` (add function after `extract_sigla`, ~line 119)
- Test: `tests/unit/scanners/test_filename_glob.py` (append)

**Why a new function (§3, verbatim rationale):** `_matches` answers "does this file belong to sigla X's *count*" and has the `count_scope == "folder"` escape — chps returns True for EVERY pdf, so using `_matches` here would make every file in the corpus "suggest" chps (false-positive storm) and make chps unable to flag anything (everything matches host). Vertiente 1 needs "which sigla does this NAME suggest": token/alias patterns only, `count_scope` ignored, full SET returned (the 2+ rule needs it).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/scanners/test_filename_glob.py`; the file already imports from `core.scanners.utils.filename_glob` — extend that import with `siglas_suggested_by_filename`)

```python
class TestSiglasSuggestedByFilename:
    """Vertiente-1 primitive (spec §3): token/alias matching only, count_scope ignored."""

    def test_single_foreign_token(self):
        assert siglas_suggested_by_filename("2026-05-04_odi_jhon.pdf") == {"odi"}

    def test_alias_cphs_suggests_chps(self):
        assert siglas_suggested_by_filename("2026-04-30_cphs_acta_reunion.pdf") >= {"chps"}

    def test_phrase_alias_suggests_revdocmaq(self):
        assert "revdocmaq" in siglas_suggested_by_filename(
            "REVISION_DOCUMENTACION_MAQUINARIA_AGUASAN.pdf"
        )

    def test_chps_real_files_suggest_nothing(self):
        # spec §3: crs.pdf / titan.pdf must suggest ∅ — NEVER "every PDF suggests chps".
        assert siglas_suggested_by_filename("crs.pdf") == set()
        assert siglas_suggested_by_filename("titan.pdf") == set()

    def test_multiple_siglas_returned_as_full_set(self):
        # cphs (alias de chps) + reunion both present → the SET carries both
        # (extract_sigla would collapse to one winner; the 2+ rule needs both).
        got = siglas_suggested_by_filename("2026-04-30_cphs_acta_reunion.pdf")
        assert got == {"chps", "reunion"}

    def test_non_pdf_returns_empty(self):
        assert siglas_suggested_by_filename("notas.txt") == set()

    def test_embedded_substring_does_not_match(self):
        # 'ext' inside 'extra' must not suggest ext (token boundaries).
        assert "ext" not in siglas_suggested_by_filename("2026-05_extra_material.pdf")
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/unit/scanners/test_filename_glob.py -q -k Suggested` → FAIL (ImportError).

- [ ] **Step 3: Implement** (in `filename_glob.py`, after `extract_sigla`):

```python
def siglas_suggested_by_filename(filename: str) -> set[str]:
    """Every sigla whose token/alias appears in the filename stem (anti-colados §3).

    The vertiente-1 question is "which sigla does this NAME suggest" — NOT
    ``_matches``'s "does this file belong to sigla X's count". This deliberately
    ignores ``count_scope``: the folder-scope escape (chps → every PDF) answers
    folder-membership and would poison name-suggestion both ways. Returns the
    full set — the caller's 2+ rule needs all matches, not one winner.

    Args:
        filename: PDF basename (any casing; non-.pdf yields the empty set).

    Returns:
        Set of sigla codes whose compiled token/alias patterns match the stem.
    """
    fn_lower = filename.lower()
    if not fn_lower.endswith(".pdf"):
        return set()
    stem = fn_lower[: -len(".pdf")]
    return {
        sigla
        for sigla, patterns in _SIGLA_PATTERNS.items()
        if any(p.search(stem) for p in patterns)
    }
```

- [ ] **Step 4: Run to verify pass** — same command → all pass. Then `ruff check core/ tests/`.
- [ ] **Step 5: Commit** — `git add core/scanners/utils/filename_glob.py tests/unit/scanners/test_filename_glob.py` + `feat(guard): siglas_suggested_by_filename primitive (anti-colados V1)`.

### Task 2: `core/scanners/utils/colado_guard.py` — pure detection + lifecycle helpers

**Files:**
- Create: `core/scanners/utils/colado_guard.py`
- Test: `tests/unit/scanners/utils/test_colado_guard.py` (new)

One responsibility: pure functions over filenames/state fragments. **No PDF/OCR I/O.** Complete module:

```python
"""Anti-colados guard — pure detection + suspect-lifecycle helpers (spec 2026-07-03).

Vertiente 1 (filename, all 20 siglas) ships first; vertiente 2 (form codes,
pagination opt-in) extends this module behind the §7 survey gate. Suspects are
plain dicts in cell state (JSON-persisted); ``ColadoSuspect`` is the typed
construction shape. Counts are NEVER derived here (§2.2).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core.scanners.utils.filename_glob import siglas_suggested_by_filename

KIND_FILENAME = "filename"
KIND_CODE = "code"

# reorg op types that suppress suspects (§5 dedupe table)
_OP_MOVE = "move_file"
_OP_EXTRACT = "extract_pages"


def suspect_id(kind: str, file: str, page_range: tuple[int, int] | None,
               suggested_sigla: str | None) -> str:
    """Deterministic id over the evidence (§5): addressing for dismiss only."""
    raw = f"{kind}|{file}|{page_range}|{suggested_sigla}"
    return "cs_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


@dataclass(frozen=True)
class ColadoSuspect:
    kind: str  # KIND_FILENAME | KIND_CODE
    file: str
    evidence: str  # matched foreign sigla(s) (filename) or dominant code (code)
    suggested_sigla: str | None  # None = ambiguous (2+ foreign matches)
    page_range: tuple[int, int] | None = None  # None = whole file
    counted: bool = False

    def to_dict(self) -> dict:
        return {
            "id": suspect_id(self.kind, self.file, self.page_range, self.suggested_sigla),
            "kind": self.kind,
            "file": self.file,
            "evidence": self.evidence,
            "suggested_sigla": self.suggested_sigla,
            "page_range": list(self.page_range) if self.page_range else None,
            "counted": self.counted,
        }


def find_foreign_filename_suspects(filenames: list[str], sigla_host: str) -> list[dict]:
    """Vertiente-1 rule (§3) over a folder's basenames.

    Suspect ⟺ the name suggests ≥1 foreign sigla AND does NOT suggest the host.
    Exactly one foreign → suggested; 2+ → suggested_sigla=None (operator picks).
    Host in set, or empty set (crs.pdf/titan.pdf) → silence.
    """
    out: list[dict] = []
    for name in sorted(set(filenames)):
        s = siglas_suggested_by_filename(name)
        if not s or sigla_host in s:
            continue
        suggested = next(iter(s)) if len(s) == 1 else None
        out.append(
            ColadoSuspect(
                kind=KIND_FILENAME,
                file=name,
                evidence=", ".join(sorted(s)),
                suggested_sigla=suggested,
            ).to_dict()
        )
    return out


def merge_suspects(
    existing: list[dict],
    kind: str,
    fresh: list[dict],
    present_files: set[str],
    scanned_files: set[str] | None = None,
) -> list[dict]:
    """Per-kind surgical refresh + evidence-based eviction (§5).

    - Entries of ``kind`` are replaced: all of them when ``scanned_files`` is
      None (pase-1 semantics: the fresh list covers the whole folder), else
      only those whose ``file`` is in ``scanned_files`` (OCR per-PDF semantics,
      vertiente 2).
    - Eviction (BOTH kinds, every refresh): any entry whose ``file`` is absent
      from ``present_files`` is dropped — the Incr-J evidence lifecycle mirror;
      without it a departed file's suspects would hold amber forever (§5).
    - Precedence: a KIND_FILENAME suspect for F suppresses KIND_CODE entries
      for F (whole-file suggestion subsumes ranges).
    """
    kept = [
        s for s in existing
        if s.get("kind") != kind or (scanned_files is not None and s.get("file") not in scanned_files)
    ]
    merged = kept + list(fresh)
    merged = [s for s in merged if s.get("file") in present_files]
    filename_files = {s["file"] for s in merged if s.get("kind") == KIND_FILENAME}
    return [
        s for s in merged
        if s.get("kind") != KIND_CODE or s.get("file") not in filename_files
    ]


def annotate_counted_filename(suspects: list[dict], cell: dict) -> list[dict]:
    """counted for KIND_FILENAME = live per-file contribution > 0 (§4.5).

    Same data ``compute_cell_count`` uses: ``per_file_overrides[f]`` if the key
    exists, else ``per_file.get(f, 0)``. Data-derived — NO cell-type taxonomy
    (the taxonomy lies: OCR cells fallback=1, anchors F8 0-covers, A7 1-page).
    KIND_CODE entries pass through untouched (their counted is set at scan
    time from segment data, vertiente 2).
    """
    per_file = cell.get("per_file") or {}
    overrides = cell.get("per_file_overrides") or {}

    def contribution(f: str) -> int:
        if f in overrides:
            return overrides[f] or 0
        return per_file.get(f, 0) or 0

    out = []
    for s in suspects:
        if s.get("kind") == KIND_FILENAME:
            out.append({**s, "counted": contribution(s["file"]) > 0})
        else:
            out.append(s)
    return out


def _ranges_overlap(a: list[int] | tuple[int, int], b: list[int] | tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _op_suppresses(suspect: dict, op: dict) -> bool:
    """§5 dedupe table row for ONE pending op on the same (cell, file)."""
    op_type = op.get("op_type")
    if op_type == _OP_MOVE:
        return True  # whole file already leaving → suppress everything on it
    if op_type == _OP_EXTRACT:
        if suspect.get("page_range") is None:
            return False  # a partial op never resolves a whole-file suspect
        op_range = (op.get("source") or {}).get("page_range")
        return bool(op_range) and _ranges_overlap(suspect["page_range"], op_range)
    return False  # rotate / split_in_place never suppress


def open_suspects(
    suspects: list[dict], reorg_ops: list[dict], hospital: str, sigla: str
) -> list[dict]:
    """Suspects minus the op-suppressed ones (§5). DERIVED, never persisted:
    deleting the op un-suppresses automatically. Ops participate only when
    ``status == "pending"`` AND their SOURCE CELL matches (hospital+sigla+file
    — never basename alone; the corpus repeats basenames across cells, F10).
    """
    relevant: dict[str, list[dict]] = {}
    for op in reorg_ops or []:
        src = op.get("source") or {}
        if (
            op.get("status") == "pending"
            and src.get("hospital") == hospital
            and src.get("sigla") == sigla
            and src.get("file")
        ):
            relevant.setdefault(src["file"], []).append(op)
    return [
        s for s in suspects or []
        if not any(_op_suppresses(s, op) for op in relevant.get(s.get("file"), []))
    ]


def has_open_counted_suspects(
    suspects: list[dict], reorg_ops: list[dict], hospital: str, sigla: str
) -> bool:
    """The all_reliable gate term (§4.5): any OPEN suspect with counted=True."""
    return any(s.get("counted") for s in open_suspects(suspects, reorg_ops, hospital, sigla))
```

- [ ] **Step 1: Write failing tests** — `tests/unit/scanners/utils/test_colado_guard.py`, table-driven, covering VERBATIM the §8 list: single-foreign / host-suppresses / empty-set silence / 2+ → `suggested_sigla None`; merge: per-kind replace (filename refresh leaves code entries), eviction of BOTH kinds on absent file, filename-over-code precedence on same file; annotate: override-0 counts as 0, per_file>0 → True, absent → False; dedupe table all 6 cells (move_file suppresses null-range and ranged; extract overlapping/non-overlapping; rotate/split never; `applied` op does NOT participate; other-cell same-basename op does NOT suppress); `has_open_counted_suspects` true/false; id determinism + stability.
- [ ] **Step 2: FAIL** (module missing) → **Step 3: implement module above** → **Step 4: pass + ruff** → **Step 5: Commit** `feat(guard): colado_guard pure detection + lifecycle helpers`.

### Task 3: telemetry + pase-1 scanner hook

**Files:**
- Modify: `core/scanners/base.py:29-33` (ScanTelemetry)
- Modify: `core/scanners/simple_factory.py` (count + _result)
- Test: `tests/unit/scanners/test_simple_factory.py` (append; tmp_path folders, no corpus)

- [ ] **Step 1: failing test** — build `tmp_path` folder for host `art` containing `2026-05-04_art_a.pdf`, `2026-05-04_odi_b.pdf`, `crs.pdf` (empty stub bytes ok — count() only opens matched files for page counts; the odi/crs files are unmatched for art). Assert `result.telemetry.colado_suspects` has exactly one entry (`file=="2026-05-04_odi_b.pdf"`, `suggested_sigla=="odi"`, `kind=="filename"`) and `set(result.telemetry.present_files) == {all three names}`. Second test: `folder_missing` → telemetry present with empty suspects + empty present_files.
- [ ] **Step 2: FAIL** → **Step 3: implement**:
  - `ScanTelemetry` gains `colado_suspects: list[dict] = field(default_factory=list)` and `present_files: list[str] = field(default_factory=list)` (frozen dataclass, defaulted → backward-compatible; AnchorsScanner's existing construction untouched).
  - `simple_factory.count()`: do ONE `all_pdfs = list(folder.rglob("*.pdf"))` right after the folder_missing gate and reuse it for the existing `path_by_name` comprehension (line 73 — replaces its own rglob; behavior-identical, single traversal). Compute `suspects = find_foreign_filename_suspects([p.name for p in all_pdfs], self.sigla)` and thread `telemetry=ScanTelemetry(colado_suspects=suspects, present_files=[p.name for p in all_pdfs])` through `_result(...)` (new keyword param, passed to `ScanResult(..., telemetry=telemetry)`). folder_missing branch passes `ScanTelemetry()` — empty telemetry evicts everything downstream (folder gone ⇒ files absent, evidence lifecycle).
- [ ] **Step 4: pass + ruff** → **Step 5: Commit** `feat(guard): pase-1 filename suspects in ScanTelemetry (single rglob)`.

### Task 4: persistence in `apply_filename_result` + the all_reliable AND

**Files:**
- Modify: `api/state.py:182-242` (`apply_filename_result`) — **BOTH branches**
- Test: `tests/unit/api/test_state.py` (append; existing file builds `SessionManager` on tmp DB — follow its fixtures)

Load-bearing nuance discovered in exploration: the `_cell_has_work` guard branch preserves per_file/near_matches to protect COUNTS — but suspects are telemetry, and files change under worked cells too. **Suspects refresh in BOTH branches; eviction runs in both.**

- [ ] **Step 1: failing tests** (manager-level, real tmp DB per project no-mock rule):
  1. fresh cell: apply a ScanResult whose telemetry carries one odi-suspect + present list → `cell["colado_suspects"]` persisted with `counted` annotated from the fresh per_file (unmatched foreign file in a token cell → `counted is False`).
  2. worked cell (set `ocr_count` first so `_cell_has_work` is True): re-apply with new telemetry → suspects still refreshed; pre-existing kind="code" entry for a file ABSENT from present_files is evicted; one for a PRESENT file survives.
  3. all_reliable AND (no-work branch): build a cell whose result is HIGH + per_file non-empty but telemetry carries a suspect with counted=True (simulate: per_file includes the foreign file with 1) → `all_reliable is False`; dismissing/evicting it (re-apply without the suspect) → True again.
  4. **chps folder-scope (§8 verbatim)**: host `chps` (count_scope="folder": every folder PDF counts, per_file carries them all), foreign `2026-05_odi_x.pdf` in its folder → suspect exists AND `counted is True` (its per_file contribution is 1) — the case that proves the Task-1 helper vs `_matches` split works end-to-end.
  5. **all_reliable downgrade in the HAS-WORK branch**: an OCR'd cell with baked `all_reliable=True`; a bulk re-scan's telemetry brings a NEW suspect whose file has per_file contribution >0 → after apply, `all_reliable is False`. (Without this the worked-cell branch would keep the green dot despite a counted suspect until some unrelated interactive write — §4.5 violation.)
- [ ] **Step 2: FAIL** → **Step 3: implement** in `apply_filename_result`. First, a small local helper computed ONCE at the top of the method (both branches need the merged+annotated suspects; suspects are telemetry, so they refresh even in the work-preserving branch):

```python
telemetry = result.telemetry
fresh = list(telemetry.colado_suspects) if telemetry else []
present = set(telemetry.present_files) if telemetry else set()
merged = merge_suspects(cell.get("colado_suspects") or [], KIND_FILENAME, fresh, present)
cell["colado_suspects"] = annotate_counted_filename(merged, cell)
blocked = has_open_counted_suspects(
    cell["colado_suspects"], state.get("reorg_ops") or [], hospital, sigla
)
```

  Compute this block right after `cell = state.setdefault(...)` and BEFORE the `if _cell_has_work(cell):` branch, so `cell["colado_suspects"]` is set once and both branches share it. Then:

  **NO-work branch** — replace the `all_reliable` assignment (line ~235) with the AND:

```python
cell["all_reliable"] = (
    result.confidence.value == "high" and bool(result.per_file) and not blocked
)
```

  **HAS-work branch** (line ~211) — the work-preserving branch does NOT recompute the positive readiness (that needs the folder / `compute_settled`, unavailable here), so apply a **one-directional downgrade only**: replace `cell.setdefault("all_reliable", False)` with

```python
cell.setdefault("all_reliable", False)
if blocked:
    cell["all_reliable"] = False  # a newly-discovered counted suspect kills the baked green
```

  (This is the fix for the class the manual review caught: without it, an OCR'd cell with `all_reliable=True` baked would keep its green dot when a bulk re-scan first surfaces a counted colado, until some unrelated interactive write happened to recompute — a §4.5 violation.)

  Import at top of state.py (NOT `open_suspects` — that one lives only in `_common.py`, importing it here would be an unused-import ruff F401):
  `from core.scanners.utils.colado_guard import KIND_FILENAME, annotate_counted_filename, has_open_counted_suspects, merge_suspects`.
- [ ] **Step 4: pass + ruff** → **Step 5: Commit** `feat(guard): persist pase-1 suspects (both rescan branches) + all_reliable AND`.

### Task 5: gate the single `refresh_all_reliable` chokepoint

**Files:**
- Modify: `api/routes/sessions/_common.py:266-286` (`refresh_all_reliable`)
- Test: `tests/unit/api/test_state.py` + re-run `tests/integration/test_write_responses_all_reliable.py`

**Enumeration result (verified against the tree, not left to the implementer):**
the only sites that ever bake `all_reliable=True` are `apply_filename_result`
(both branches — done in Task 4) and `set_all_reliable`, which is called
**exclusively** from `refresh_all_reliable`. `apply_per_file_ocr_result`
(~line 416) does NOT assign `all_reliable`; every OCR-completion path
recomputes through `refresh_all_reliable` instead (`scan.py:132` batch,
`scan.py:284` per-cell). So the interactive writes (override/per-file/worker/
note, `writes.py`) AND the OCR completions all funnel through this one
function — gating it here covers all of them. There is no other producer to
patch. (The `setdefault("all_reliable", False)` calls at `state.py:211/287`
only DEFAULT a missing field to False; they can never create a wrong green.)

- [ ] **Step 1: failing test** — a cell with a counted open suspect: `refresh_all_reliable` leaves `all_reliable` False even when `compute_settled` says True; after the suspect's file disappears + re-apply (eviction), refresh flips it True.
- [ ] **Step 2: FAIL** → **Step 3: implement** — in `refresh_all_reliable` (it already loads `state` + `cell`):

```python
blocked = has_open_counted_suspects(
    cell.get("colado_suspects") or [], state.get("reorg_ops") or [], hospital, sigla
)
mgr.set_all_reliable(
    session_id, hospital, sigla,
    compute_settled(cell, folder, pages=pages, count_type=count_type) and not blocked,
)
```

  Import `has_open_counted_suspects` into `_common.py` from `core.scanners.utils.colado_guard`.
- [ ] **Step 4: pass** (also re-run the whole `test_write_responses_all_reliable.py`) → **Step 5: Commit** `feat(guard): counted open suspects gate refresh_all_reliable (single chokepoint)`.

### Task 6: payload open-filter (derived dedupe) at the 4 serialization sites

**Files:**
- Modify: `api/routes/sessions/_common.py` (new `enrich_cell_colado_suspects` + `_cell_updated_event`)
- Modify: `api/routes/sessions/lifecycle.py:60-70` (GET map)
- Modify: `api/routes/sessions/writes.py:294-301` (reconcile return)
- Test: `tests/unit/api/test_routes_sessions.py` (append)

- [ ] **Step 1: failing test** — session with one suspect + one PENDING `move_file` op on the same (cell, file): GET payload's `colado_suspects` is `[]` (suppressed); delete the op (or craft state without it) → GET shows the suspect again (derived, §5).
- [ ] **Step 2: implement** in `_common.py`:

```python
def enrich_cell_colado_suspects(cell: dict, reorg_ops: list[dict], hospital: str, sigla: str) -> dict:
    """Payload view of suspects = OPEN list (§5 dedupe is derived, not state).

    Raw persisted suspects stay internal; every serialization of a cell to a
    client goes through here so the panel can never show a suspect an existing
    pending op already covers — and deleting that op un-suppresses with no
    extra bookkeeping.
    """
    raw = cell.get("colado_suspects") or []
    if not raw:
        return cell
    return {**cell, "colado_suspects": open_suspects(raw, reorg_ops, hospital, sigla)}
```

  Call sites (all four; each already has `state` in scope):
  1. `lifecycle.py` GET map (line ~66): wrap the existing enrich — `enrich_cell_colado_suspects(enrich_cell_worker_count(...), state.get("reorg_ops") or [], hosp, sigla)`.
  2. `_cell_updated_event` (`_common.py:316-341`): same wrap after the worker enrich.
  3. `writes.py` reconcile return (line ~297): wrap `enriched`.
  4. Task 7's dismiss response (below) returns the open list directly.
- [ ] **Step 3: pass + ruff** → **Step 4: Commit** `feat(guard): open-suspects payload filter at every cell serialization site`.

### Task 7: dismiss — manager method + route (M3)

**Files:**
- Modify: `api/state.py` (new method after `clear_near_matches`, template `api/state.py:454-499`)
- Modify: `api/routes/sessions/writes.py` (new route)
- Test: `tests/unit/api/test_lock_enforcement.py` pattern for the 409; new `tests/unit/api/test_colado_dismiss.py`

- [ ] **Step 1: failing tests** — dismiss removes exactly one suspect by id + recomputes all_reliable + broadcasts; **dismiss twice → second is 404** (§6/§8); dismissing while ANOTHER participant holds the cell → 409 with `lock_holder` (follow `test_lock_enforcement.py`'s two-participant fixture idiom); dismissal survives until the next pase-1 apply for the cell (then recomputed — the §5 documented behavior).
- [ ] **Step 2: implement manager** (M3 template verbatim from `clear_near_matches` — `@_synchronized`, `_editor_conflict` → `CellLockedError` first, agent auto-claim, then):

```python
@_synchronized
def dismiss_colado_suspect(
    self, session_id: str, hospital: str, sigla: str, suspect_id: str,
    *, participant_id: str | None = None,
) -> None:
    """Drop ONE suspect (operator says "es legítimo"). Removal lasts until the
    next scan refresh of its kind (§5 — no hidden permanent suppressions).
    Raises KeyError when the id is not present (route maps it to 404)."""
    holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
    if holder is not None:
        raise CellLockedError(hospital, sigla, holder)
    if is_agent(participant_id):
        self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
    state, _ = self._load_and_migrate(session_id)
    cell = (state.get("cells", {}).get(hospital, {}) or {}).get(sigla)
    suspects = (cell or {}).get("colado_suspects") or []
    if not any(s.get("id") == suspect_id for s in suspects):
        raise KeyError(suspect_id)
    cell["colado_suspects"] = [s for s in suspects if s.get("id") != suspect_id]
    update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

  Route in `writes.py` (mirror the reconcile route's shape): `POST /sessions/{session_id}/cells/{hospital}/{sigla}/colado-suspects/{suspect_id}/dismiss`, body `{participant_id: str | None}`; `KeyError → HTTPException(404, ...)`; on success `refresh_all_reliable(...)` (folder via `_find_category_folder`, `count_type=count_type_for(sigla)`), `_broadcast_cell_updated`, agent presence broadcast, and return `{"colado_suspects": <open list>, "all_reliable": cell["all_reliable"]}` (the F15 echo-drop rule: the response must carry what the dropped `cell_updated` would have).
- [ ] **Step 3: pass + ruff** → **Step 4: Commit** `feat(guard): dismiss endpoint (M3-gated, 404 on unknown id)`.

### Task 8: reorg create/delete refresh `all_reliable`

**Files:**
- Modify: `api/routes/sessions/reorg.py` (create + delete handlers, after the successful write)
- Test: `tests/unit/api/test_reorg_routes.py` (append)

Spec §4.5/§6: "crear la op restaura el verde sin re-scan" — the op suppresses the suspect (derived), but the persisted `all_reliable` only updates if these routes recompute it.

- [ ] **Step 1: failing test** — cell with counted open suspect (`all_reliable False`); POST a pending `move_file` op on that (cell, file) → cell's `all_reliable` True; DELETE the op → False again.
- [ ] **Step 2: implement** — in both handlers, after the manager write succeeds and before the response: resolve the SOURCE cell's folder and call `refresh_all_reliable(mgr, session_id, src.hospital, src.sigla, folder, count_type=count_type_for(src.sigla))`. (The routes already broadcast `session_refresh` → the frontend refetches, landing the new value.)
- [ ] **Step 3: pass + ruff** → **Step 4: Commit** `feat(guard): reorg op create/delete recompute all_reliable (green sin re-scan)`.

### Task 9: frontend — api, store, panel

**Files:**
- Modify: `frontend/src/lib/api.js` (add `dismissColadoSuspect(sessionId, h, s, suspectId, participantId)` — `jsonOrThrowStructured` POST like the other writes)
- Modify: `frontend/src/store/session.js` (new `dismissColadoSuspect` action)
- Create: `frontend/src/components/PosiblesColadosPanel.jsx`
- Modify: `frontend/src/components/DetailPanel.jsx` (render the panel)
- Test: `frontend/src/components/PosiblesColadosPanel.test.jsx`, `frontend/src/store/session.colado.test.js`

- [ ] **Step 1: store action** (failing vitest first, `session.lock.test.js` harness): on success merge `{colado_suspects, all_reliable}` from the response into the cell; 409 → lock toast + `refetchSession` (verbatim pattern); 404 → `refetchSession` + neutral toast `"Ese sospechoso ya no existe"`; generic → toast `"No se pudo descartar el sospechoso: ..."` (U2 pattern — NO sticky error).
- [ ] **Step 2: panel** — template `frontend/src/components/OrphanMarksPanel.jsx` (suspect tone, po-* tokens, shared `Badge`). Section title **"POSIBLES COLADOS"**. Per suspect row:
  - chip `Archivo` (`page_range == null`) or `Páginas X–Y` (kind chips share the Badge shape per the chip-consistency convention);
  - `file` (truncated, title attr), evidence (`token: odi` / `código: F-CRS-ART-01` — prefix by kind), suggested sigla via `sigla-labels.js` (or "— elige el destino" when null);
  - button **"Crear op de reorg"**: calls the EXISTING Incr-J create action (see the reorg actions in `session.js` ~line 759) with the §6 prefill: `op_type` = `move_file` (null range) / `extract_pages` (ranged), `source={hospital, sigla, file, page_range}`, `dest={same hospital, suggested_sigla}`, `doc_count` = **omit (backend `resolve_op_defaults`) when `counted`, explicit `0` when `!counted`** — the §6 divergence, comment it in the JSX; disabled with hint when `suggested_sigla == null`;
  - button **"Descartar"** → store action; microcopy under the list: *"Se vuelven a calcular en cada escaneo; descartar dura hasta el próximo escaneo de la celda."*
  - Cell locked by another (M3 read-only gating in DetailPanel) → both buttons disabled like every other control.
- [ ] **Step 3: DetailPanel** — render `<PosiblesColadosPanel/>` only when `cell.colado_suspects?.length > 0`, placed with the other advisory sections (immediately before the near-matches block); pass the lock flag the panel needs.
- [ ] **Step 4: vitest** — panel render (both kinds, ambiguous row disabled, dismiss wiring, locked state) + store action cases; `cd frontend && npm test -- --run` all green; `npm run build` OK.
- [ ] **Step 5: Commit** `feat(guard): POSIBLES COLADOS panel + dismiss/prefill actions`.

### Task 10: V1 docs + integration sweep

**Files:**
- Modify: `core/CLAUDE.md` (guard section under Scanner Architecture), `api/CLAUDE.md` (dismiss route row), `CLAUDE.md` Pending Work (V1 shipped, V2 gated)
- Test: full gates

- [ ] **Step 1:**整 docs (English, matching each file's tone; cite the spec path).
- [ ] **Step 2: gates** — `pytest -m "not slow" -q` (expect ≥785 passed + the new tests, 0 failed), `cd frontend && npm test -- --run`, `npm run build`, `ruff check .` = 0.
- [ ] **Step 3: Commit** `docs(guard): V1 vertiente filename shipped` → **this closes Chunk 1; V1 is shippable standalone.**

---

> **GATE RESULT (2026-07-04): ABORT vertiente 2.** The deep survey
> (`tools/survey_form_codes.py`) showed the form code is not a reliable
> foreign-sigla discriminator — the `F-CRS-LCH-NN` checklist family is shared
> across ~7 inspection siglas (documented collisions) and corner OCR is too
> noisy. Only ~3-4 siglas have distinct clean codes; the compilation-heavy
> inspection siglas (where interior colados live) are the undetectable LCH
> family. Daniel chose ABORT — V1 (filename) stands. **Chunk 3 below is NOT
> executed.** Full analysis:
> `docs/research/2026-07-04-anti-colados-v2-survey-abort.md`.

## Chunk 2: Gate — survey profundo de códigos (§7)

### Task 11: `tools/survey_form_codes.py` + the map for Daniel

**Files:**
- Create: `tools/survey_form_codes.py` (committed maintenance tool, A13-adjacent)
- Output: scratchpad JSON/markdown map (NOT committed — carries real filenames)

Read-only over `A:\informe mensual` (NEVER write there). Base: the session survey (scratchpad `survey_codes.py`) with these upgrades, all pinned:

- [ ] **Step 1: write the tool** — walk `ABRIL` + `MAYO` × `HPV/HRB/HLU/HLL`; resolve folders via `core.domain.folder_to_sigla`; **only PDFs with `page_count > 1`** (A7 files never reach vertiente 2); cap 8 PDFs × 8 pages per (sigla, hospital) — **HRB cap 16 PDFs** (Daniel: HRB is the hotspot); per page reuse the PRODUCTION extractor (`pagination_count._corner_text` + `extract_code`); aggregate `{sigla: Counter[normalized_code]}` using the Task-12 normalization (import it — if running before Task 12, inline the fold as a private copy marked TEMP); emit per sigla: raw codes, normalized forms, frequency, hospitals seen, and a PROPOSED `expected_codes` line; emit pairwise collision warnings post-normalization (prefix-of semantics, §4.2). CLI: `python tools/survey_form_codes.py [--months ABRIL MAYO] [--out <path>]`; `print()` allowed (CLI tool).
- [ ] **Step 2: run it** (venv `.venv-cuda`, `-X utf8`; expect several minutes) → save the map to the scratchpad.
- [ ] **Step 3: Commit the tool only** — `feat(tools): form-code survey (anti-colados V2 gate)`.
- [ ] **Step 4: STOP — controller gate.** Present Daniel the map + the proposed `expected_codes` per sigla + which siglas fall out. **Abort criterion (§7): <4 viable siglas or unresolved cross-hospital contradictions → V2 aborts, V1 stands.** Do not start Chunk 3 without his GO + the agreed data.

---

## Chunk 3: Fase V2 — vertiente form-code (behind the gate)

### Task 12: normalization + expected-code matching (pure)

**Files:**
- Modify: `core/scanners/utils/colado_guard.py` (add; keep the module pure)
- Test: `tests/unit/scanners/utils/test_colado_guard.py` (append)

- [ ] Implement + test (§4.2 verbatim): `normalize_code(raw) -> str` = uppercase → strip non-alphanumeric → fold with the `_DIGIT` map (import from `pagination_count`); `matches_expected(code, expected: list[str]) -> bool` — entries ending `*` are normalized-prefix matches, others normalized equality; `expected_collisions(by_sigla: dict[str, list[str]]) -> list[tuple]` — literal-vs-literal equality, prefix-vs-literal startswith, **prefix-vs-prefix = one is a PREFIX of the other (not substring — `FPETSCRS08` contains `PETSCRS` but no code starting with one starts with the other)**. Test the FECHA-31 noise (matches nothing), `F-CRS-ARTO1`→`F-CRS-ART-01` fold equality, `FPETS-CRS-08-00` under `F-PETS-CRS-08*`, irl `…ODI-01` vs odi `…ODI-03` distinct post-fold.
- [ ] Commit `feat(guard): code normalization + expected matching (V2)`.

### Task 13: engine segmentation (`DocSegment`)

**Files:**
- Modify: `core/scanners/utils/pagination_count.py`
- Test: `tests/unit/scanners/utils/test_pagination_count.py` (append — pure, no OCR)

- [ ] **Step 1: refactor without behavior change** — extract `counted_start_indices(reads, cover_code) -> list[int]` (0-based indices where `count_starts` counts); `count_starts` becomes `len(counted_start_indices(...))`. Existing tests must stay green UNCHANGED.
- [ ] **Step 2: add** `DocSegment` frozen dataclass `{page_start, page_end (1-based inclusive), counted_start_page: int | None, codes: dict[str, int]}` — the LONG field name is deliberate (§4.3: do not confuse with `page_start`, the range edge) — and pure `segment_documents(reads, cover_code) -> list[DocSegment]`: one segment per counted start; preamble pages attach to segment 0 (whose `counted_start_page` points at the counted start, not page 1); **no counted starts → single fallback segment covering the file with `counted_start_page=None`**; `codes` from `direct` reads only (recovered pages carry `code=None`). Wire `documents: list[DocSegment]` into `PaginationCountResult` (append field, default `()`/empty — existing constructions in tests keep working) and populate it in `count_documents_by_pagination`.
- [ ] Tests: interior boundaries, preamble, fallback, cover_code filtering parity (`len(segments) == count_starts(...)` property test across the existing fixtures' read-lists).
- [ ] Commit `feat(guard): per-document segmentation in the pagination engine`.

### Task 14: code-suspect detection rule (pure)

**Files:**
- Modify: `core/scanners/utils/colado_guard.py`
- Test: `tests/unit/scanners/utils/test_colado_guard.py` (append)

- [ ] `find_foreign_code_suspects(segments, pdf_name, total_pages, host_expected, expected_by_sigla) -> list[dict]` implementing §4.4 verbatim:
  - per page inside each segment: foreign ⟺ ≥1 read matches a foreign sigla's set AND none matches host's; unknown/no-read pages are NEUTRAL and **break runs** (two runs → two suspects; never a range spanning evidence-free pages);
  - maximal consecutive foreign runs → suspect `{kind: "code", file, page_range, evidence: dominant code, suggested_sigla}`; a run whose pages match 2+ foreign siglas → `suggested_sigla=None`;
  - **counted (§4.5): run covers its segment's `counted_start_page`, OR the segment is the fallback** — with the cover_code-absorbed-run test case (foreign run mid-segment in an irl-like host → `counted=False`);
  - move_file conversion: **only when the foreign runs cover ALL pages AND all suggest the SAME sigla** → collapse to ONE whole-file suspect (`page_range=None`); otherwise per-run `extract_pages`-shaped suspects — multi-sigla full coverage stays per-run (§4.4);
  - host with empty/missing `host_expected` → `[]` (vertiente 2 off).
- [ ] §8 cases as tests: mixto, desconocido, ruido FECHA, multi-ajena→None, absorbed-run counted=False, run-covers-start counted=True, whole-file single-sigla → move_file shape, whole-file multi-sigla → runs.
- [ ] Commit `feat(guard): foreign-code detection rule (V2)`.

### Task 15: `expected_codes` data + registry test + v7

**Files:**
- Modify: `core/scanners/patterns.py` (add `expected_codes` to the GATE-APPROVED siglas — the survey map is the authority; §4.1 provisional table is the shape reference: art `F-CRS-ART-01`, irl `F-CRS-ODI-01`, odi `F-CRS-ODI-03`, exc `F-CRS-LCH-31`, altura `F-PETS-CRS-01-01`, espacios `F-PETS-CRS-08*`; ext explicitly none)
- Modify: `core/utils.py` — `SCANNER_PATTERNS_VERSION` → `"v7-colado-guard"` (this task, not V1: V1 changed no patterns data; this one does)
- Test: `tests/unit/scanners/test_patterns_registry.py` (append)

- [ ] Registry tests: every `expected_codes` entry normalizes non-empty; **pairwise cross-sigla collision check via `expected_collisions` == []**; `expected_codes` only on `pagination` siglas.
- [ ] Commit `feat(guard): expected_codes registry (survey-approved) + v7-colado-guard`.

### Task 16: PaginationScanner + OCR-merge persistence

**Files:**
- Modify: `core/scanners/pagination_scanner.py` (`_count_one_pdf`), `core/scanners/ocr_scanner_base.py` (`_PdfOutcome` + telemetry aggregation)
- Modify: `api/state.py` (`apply_per_file_ocr_result` ~line 416: merge kind=code for the scanned PDF; the route side supplies present names)
- Modify: `api/routes/sessions/scan.py` (thread present_file_names + suspects through the existing per-file apply path; single-file OCR route too)
- Test: `tests/unit/scanners/test_pagination_scanner.py` (monkeypatched engine result carrying `documents`), `tests/unit/api/test_state.py` (merge semantics: per-PDF replace — `scanned_files={pdf}` —, eviction, filename-over-code precedence)

- [ ] `_count_one_pdf`: when `PATTERNS[self.sigla].get("expected_codes")` is set, build `expected_by_sigla` once (module-level lazy from PATTERNS) and compute suspects from `pag.documents`; attach to the `_PdfOutcome` (new field `colado_suspects: list[dict] = ()`); confidence: suspects do NOT change the low_trust computation (the amber comes from the all_reliable/`counted` path — §4.5 derived, not baked; leave the 4 existing low_trust triggers untouched).
- [ ] `OcrScannerBase`: aggregate per-PDF suspects into `ScanResult.telemetry.colado_suspects` (keep `present_files` empty here — the API side owns folder listing for eviction).
- [ ] `apply_per_file_ocr_result`: new optional params `colado_suspects: list[dict] | None`, `present_files: set[str] | None`; when given → `cell["colado_suspects"] = merge_suspects(existing, KIND_CODE, fresh, present_files, scanned_files={pdf_name})` (code-kind counted arrives pre-set from the scanner; `annotate_counted_filename` NOT applied here). scan.py threads both from the route context (it has the folder).
- [ ] Commit `feat(guard): code suspects through the OCR merge path`.

### Task 17: synthetic colado integration fixture

**Files:**
- Create: `tests/integration/test_colado_synthetic.py` (+ a fixture builder like `eval/pagination_count`'s synthetic PDFs — fitz-drawn pages, NEVER personal-data corpus slices)

- [ ] Build in tmp_path a synthetic "odi cell" PDF: 4 pages "Página 1..2 de 2" ×2 with drawn code `F-CRS-ODI-03`, then 2 interior pages "Página 1..2 de 2" with `F-CRS-ART-01` (the colado), then run the REAL `PaginationScanner.count_ocr` (real Tesseract on synthetic pages — mark `@pytest.mark.slow` if >5 s locally; measure first) and assert: count unchanged by detection; one kind=code suspect, `suggested_sigla=="art"`, correct range, `counted` per rule; end-to-end through a `TestClient` session: suspect in GET payload, dismiss 200/404, op create suppresses.
- [ ] Commit `test(guard): synthetic colado end-to-end`.

### Task 18: V2 frontend polish + docs

- [ ] Panel already renders kind=code rows (Task 9 built both) — verify copy for `Páginas X–Y` + `código:` evidence with a vitest case using a code suspect; fixtures README: update the andamios/herramientas_elec shadow caveat (§8: resolved only IF those siglas got expected_codes; else the caveat stands verbatim); `core/CLAUDE.md` V2 paragraph.
- [ ] Commit `docs(guard): V2 shipped notes + shadow-caveat status`.

### Task 19: cierre — OUTPUT GUARD + gates + push

- [ ] **OUTPUT GUARD (§2.2, hard):** on an ISOLATED COPY of the real DB (copy `data/overseer.db` to scratchpad; `OVERSEER_DB_PATH` env to the copy; `OVERSEER_OUTPUT_DIR` to scratchpad) run `python tools/dump_counts.py` before-checkout vs after (or vs the committed baseline pattern used in the audit round) → **diff EMPTY**. Real DB untouched (hash before/after).
- [ ] Full gates: `pytest -m "not slow" -q` 0 failed; slow suite `pytest -m slow -q` (ABRIL 80 cells) 0 failed; vitest all; `npm run build`; `ruff check .` 0.
- [ ] Update root `CLAUDE.md` (Pending Work: guard shipped; Project history entry), memory files per convention; **push `po_overhaul`** (round close).
- [ ] Tag suggestion for the controller: `anti-colados-v1` after Chunk 1 if V2 gate delays; `anti-colados-mvp` at full close.

---

## Execution notes for the controller (SDD)

- Implementer subagents: **Sonnet floor** (project rule), fresh per task, two-stage review (spec → quality) per task; holistic close per chunk. Reviewers receive the SPEC path + the chunk text — never session history.
- Tasks 1–3 are pure/mechanical (cheap model ok per SDD guidance, but never below Sonnet). Tasks 4–8 touch the manager/locks — standard care. Task 11's run + gate belongs to the CONTROLLER, not a subagent (talks to Daniel).
- Sequential execution only (single working tree — no parallel implementers).
- The spec's §8 test list is the acceptance checklist; every bullet must map to a test that exists by the end of its chunk.
