# Conteo-session fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four app defects surfaced by the 2026-07-08/09 counting session — the wrong `irl` cover_code (4 sites), silent unknown-key acceptance on every write endpoint, the `≤ pages` cap that cannot express 2-docs-per-page, and two presence gaps.

**Architecture:** Spec `docs/superpowers/specs/2026-07-09-conteo-session-fixes-design.md` is the authority — do not re-litigate its decisions. Four independent fixes, one chunk each: (1) a value flip + its 3 documentation/eval echoes + version bump; (2) `extra="forbid"` on every request model, converting the 3 raw-dict bodies to `Any`-typed models so 400 semantics never shift to 422; (3) an `allow_over_pages` write-time flag + a client-side `over_cap` confirmation (the cap is enforced client-side today — the backend 422 is unreachable from the UI); (4) a presence GET + agent-kind heartbeat.

**Tech Stack:** FastAPI + Pydantic v2 (`model_config = ConfigDict(extra="forbid")`), pytest (`tests/integration/` uses the `client` + `session_with_pending_cell` fixtures), React/Zustand, vitest.

**No counting change:** nothing here alters `compute_cell_count`, Excel, or history. After the final task, `python tools/dump_counts.py` (or the equivalent used in prior rounds) against the real DB must show zero row changes.

**Conventions that bind every task:** `ruff check .` must be 0 before each commit; conventional commits in English; work directly on `po_overhaul`; never `git add -A` — stage named paths only.

---

## Chunk 1: irl cover_code (spec §1)

### Task 1: Flip the buggy value in all 4 sites + version bump

**Files:**
- Modify: `tests/unit/scanners/test_patterns_registry.py:113-116`
- Modify: `core/scanners/patterns.py` (irl entry ~line 725-729; `SiglaPattern` docstring ~line 48-49)
- Modify: `tests/unit/scanners/test_pattern_irl_odi.py:24-32` (docstring only)
- Modify: `eval/pagination_count/samples.py:86`
- Modify: `core/utils.py:56-68` (`SCANNER_PATTERNS_VERSION`)

- [ ] **Step 1: Write the failing test (flip the assertion to the CORRECT value)**

In `tests/unit/scanners/test_patterns_registry.py`, the test currently pins the bug:

```python
def test_irl_pagination_has_cover_code():
    """IRL counts only its F-CRS-ODI-01 covers (ignores appendix page-1s)."""
    assert PATTERNS["irl"]["scan_strategy"] == "pagination"
    assert PATTERNS["irl"].get("cover_code") == "F-CRS-ODI-01"
```

Replace with:

```python
def test_irl_pagination_has_cover_code():
    """IRL counts only its F-CRS-IRL-01 covers (ignores appendix page-1s).

    Regression pin for the 2026-07-09 fix: the entry shipped with odi's code
    (F-CRS-ODI-01) by mistake — a pase-2 run on irl matched no covers.
    """
    assert PATTERNS["irl"]["scan_strategy"] == "pagination"
    assert PATTERNS["irl"].get("cover_code") == "F-CRS-IRL-01"
```

- [ ] **Step 2: Run it to verify it fails against the current bug**

Run: `pytest tests/unit/scanners/test_patterns_registry.py::test_irl_pagination_has_cover_code -v`
Expected: FAIL — `assert 'F-CRS-ODI-01' == 'F-CRS-IRL-01'`

- [ ] **Step 3: Fix the value + the three echoes**

`core/scanners/patterns.py`, irl entry — change value and comment:

```python
    "irl": {
        "scan_strategy": "pagination",  # v4: migrated — packet covers via cover_code
        "cover_code": "F-CRS-IRL-01",  # count only IRL form covers, not appendix page-1s
        "cover_flavors": _IRL_ANCHORS,
    },
```

`core/scanners/patterns.py`, `SiglaPattern` docstring (~line 48-49) — the worked
example must use the corrected code:

```python
    `cover_code`: pagination only — count only covers whose form code contains
        this substring (e.g. ``"F-CRS-IRL-01"`` for IRL). When absent, every
```

`tests/unit/scanners/test_pattern_irl_odi.py` — docstring of
`test_irl_count_ocr_smoke` (doc-only; the test skips without its gitignored
fixture). Change the sentence `IRL's patterns.py entry sets
cover_code='F-CRS-ODI-01'` → `cover_code='F-CRS-IRL-01'`.

`eval/pagination_count/samples.py:86` — the IRL `Sample` is consumed live by
`eval/pagination_count/benchmark.py`; change `cover_code="F-CRS-ODI-01"` →
`cover_code="F-CRS-IRL-01"` (one line, keep the rest of the `Sample` intact).

- [ ] **Step 4: Bump `SCANNER_PATTERNS_VERSION`**

`core/utils.py` — append one changelog comment line and change the string:

```python
SCANNER_PATTERNS_VERSION = (
    # v2: pase-1 honest confidence + page-count for FIXED_PAGE_SIGLAS
    # v3: count_type por sigla (documents/documents_workers/checks) — Incr. 1A
    # v4: pagination-first engine — migrated odi/ext/bodega/caliente/exc/
    #     herramientas_elec/art/andamios + irl(cover_code) anchors→pagination.
    #     Anchor flavors kept on migrated siglas for one-line reversibility.
    # v5: + revdocmaq (none) + espacios (pagination, F-PETS-CRS-08-01) → 20 siglas.
    # v6: Fase 5 corpus matching — per-sigla filename token aliases (chps
    #     "cphs" + revdocmaq "revision"+"documentacion" phrase, F6/F14a); chps
    #     counts by folder membership instead of by token (F14); duplicate
    #     PDF basename detection surfaced as a flag (F10).
    # v7: irl cover_code corrected F-CRS-ODI-01 → F-CRS-IRL-01 (2026-07-09
    #     counting session found the real cover header; ODI's code matched 0).
    "v7-irl-cover"
)
```

- [ ] **Step 5: Run the affected tests + full fast suite**

Run: `pytest tests/unit/scanners/ -v` → all pass (the smoke test may SKIP without its fixture — that is fine).
Run: `pytest -m "not slow" -q` → same pass count as before this task, 0 failures.
Run: `ruff check .` → 0.

- [ ] **Step 6: Over-match verification (spec §1 implementation check)**

**Do NOT reach for `benchmark.py` here** — it has no CLI filter (no argparse
at all) and `extract_sample()` hardcodes the MAYO month folder, so it can
never read the JUNIO/HRB packet this check targets. Write a scratch script
(scratchpad, not the repo) calling the engine directly:

```python
import sys
sys.path.insert(0, "a:/PROJECTS/PDFoverseer")
from pathlib import Path
from core.scanners.cancellation import CancellationToken
from core.scanners.utils.pagination_count import count_documents_by_pagination

pdf = next(Path(r"A:/informe mensual/JUNIO/HRB/2.-Induccion IRL").rglob("*.pdf"))
# cancel is a REQUIRED keyword-only arg (pagination_count.py:198) — the idiom
# comes from tests/unit/scanners/utils/test_pagination_count.py.
result = count_documents_by_pagination(pdf, cancel=CancellationToken(), cover_code="F-CRS-IRL-01")
print(pdf.name, result)
```

(Adapt the folder name / return-shape handling to reality — check
`core/scanners/utils/pagination_count.py` for what it returns, and the
CancellationToken import path against the test file's actual import.) Expected: **1 document** per IRL packet (one cover), not 0 (old
bug) and not >1 (would mean appendix pages carry the substring — if so, STOP
and surface to Daniel before committing). Optionally also run the fixed
MAYO-based benchmark end-to-end (`python eval/pagination_count/benchmark.py`,
its documented invocation) and confirm the irl row still reads 1/1.

- [ ] **Step 7: Commit**

```bash
git add core/scanners/patterns.py core/utils.py tests/unit/scanners/test_patterns_registry.py tests/unit/scanners/test_pattern_irl_odi.py eval/pagination_count/samples.py
git commit -m "fix(scanners): irl cover_code F-CRS-ODI-01 -> F-CRS-IRL-01 (v7)

The irl pattern shipped with odi's form code, so a pase-2 pagination run
matched no covers. Fixes the value plus its three echoes (registry test
assertion, SiglaPattern docstring example, irl_odi smoke docstring) and
the live-consumed eval Sample. SCANNER_PATTERNS_VERSION -> v7-irl-cover."
```

---

## Chunk 2: extra="forbid" on every write model (spec §2)

### Task 2: writes.py — 7 models + OverridePatch conversion

**Files:**
- Modify: `api/routes/sessions/writes.py`
- Test: `tests/integration/test_forbid_extra_keys.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_forbid_extra_keys.py`. It reuses the
`client` + `session_with_pending_cell` fixtures from
`tests/integration/conftest.py` (same as `test_override_cap.py`):

```python
"""Integration: unknown JSON keys on write endpoints must 422, not be
silently ignored (spec 2026-07-09-conteo-session-fixes §2). Regression for
the note-wipe incident: {note, note_status} returned 200 and cleared text."""

from __future__ import annotations


def test_note_unknown_keys_422_and_note_preserved(client, session_with_pending_cell):
    """The incident repro: wrong keys must 422 and NOT clear the stored note."""
    sid, hosp, sigla = session_with_pending_cell
    url = f"/api/sessions/{sid}/cells/{hosp}/{sigla}/note"
    r = client.patch(url, json={"text": "nota real", "status": "por_resolver"})
    assert r.status_code == 200, r.text

    r = client.patch(url, json={"note": "x", "note_status": "resuelto"})
    assert r.status_code == 422, r.text

    state = client.get(f"/api/sessions/{sid}").json()
    cell = state["cells"][hosp][sigla]
    assert cell.get("note") == "nota real"
    assert cell.get("note_status") == "por_resolver"


def test_cell_override_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override",
        json={"value": 3, "bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_cell_override_bad_value_keeps_400(client, session_with_pending_cell):
    """Behavior preservation: hand-rolled value validation still 400s."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override",
        json={"value": "doce"},
    )
    assert r.status_code == 400, r.text


def test_per_file_override_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 1, "bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_confirm_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(  # the confirm route is PATCH (writes.py:371)
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/confirm",
        json={"confirmed": True, "bogus": 1},
    )
    assert r.status_code == 422, r.text
```

Note for the implementer: add analogous
one-liner tests for `worker-count`, near-match clear, reconcile-marks and
dismiss-colado **iff** their happy-path fixtures are cheap to reach with
`session_with_pending_cell`; otherwise the model-level guarantee (`extra=
"forbid"` present on the class) plus these five is sufficient coverage —
do not build elaborate fixtures just for a 422 check.

- [ ] **Step 2: Run to verify the 422 tests fail today (200/ignored)**

Run: `pytest tests/integration/test_forbid_extra_keys.py -v`
Expected: the unknown-key tests FAIL (endpoints return 200 today); `bad_value_keeps_400` PASSES (already the behavior).

- [ ] **Step 3: Implement in `writes.py`**

Import `ConfigDict`:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Add to **each** of the 7 existing models (`PerFileOverrideRequest`,
`ClearNearMatchBody`, `WorkerCountPatch`, `ReconcileWorkerMarksBody`,
`NotePatch`, `ConfirmRequest`, `DismissColadoBody`) as the first class line:

```python
    model_config = ConfigDict(extra="forbid")
```

Convert `patch_override`'s raw dict. Add the model (near the other models):

```python
class OverridePatch(BaseModel):
    """Cell-override body. `value` stays Any: the endpoint's hand-rolled
    validation must keep returning 400 (not Pydantic 422) for bad types."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    manual: bool = False
    participant_id: str | None = None
```

(`from typing import Any, Literal` — extend the existing import.) Change the
signature and the three reads:

```python
def patch_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: OverridePatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
```

and inside: `value = body.value`, `manual = bool(body.manual)`,
`participant_id = body.participant_id`. Everything else in the function body
is untouched (the manual isinstance/range checks keep their 400s). Remove
`Body` from the fastapi import **only if** no other route in the file still
uses it.

Accepted micro-change (call it out in the commit body, nothing else): the
typed `manual: bool` means a non-boolish `manual` value now 422s instead of
being truthiness-coerced — no known caller sends one (api.js sends literal
`true` or omits it).

- [ ] **Step 4: Run the new tests + the full fast suite**

Run: `pytest tests/integration/test_forbid_extra_keys.py -v` → all PASS.
Run: `pytest -m "not slow" -q` → 0 failures (proves no legitimate caller sent extra keys).
Run: `ruff check .` → 0.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions/writes.py tests/integration/test_forbid_extra_keys.py
git commit -m "fix(api): forbid unknown JSON keys on the writes.py surface

extra='forbid' on the 7 request models + patch_override's raw dict
becomes OverridePatch (value stays Any so the hand-rolled 400 semantics
don't shift to 422). Regression-pins the note-wipe incident: wrong keys
now 422 and the stored note survives."
```

### Task 3: scan.py + reorg.py + presence.py models

**Files:**
- Modify: `api/routes/sessions/scan.py`
- Modify: `api/routes/sessions/reorg.py`
- Modify: `api/routes/presence.py`
- Test: `tests/integration/test_forbid_extra_keys.py` (extend)

- [ ] **Step 1: Write the failing tests (extend the same file)**

```python
def test_presence_heartbeat_unknown_key_422(client, session_with_pending_cell):
    sid, _, _ = session_with_pending_cell
    r = client.post(
        f"/api/sessions/{sid}/presence/heartbeat",
        json={"participant_id": "p1", "name": "Ana", "color": "#fff", "bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_scan_unknown_key_422(client, session_with_pending_cell):
    sid, _, _ = session_with_pending_cell
    r = client.post(f"/api/sessions/{sid}/scan", json={"scope": "all", "bogus": 1})
    assert r.status_code == 422, r.text


def test_reorg_create_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    # source MUST carry hospital/sigla (ReorgSource requires them, no default)
    # or the request 422s TODAY for missing fields — which would make this
    # test pass without exercising the extra="forbid" guard at all.
    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "rotate",
            "source": {
                "hospital": hosp,
                "sigla": sigla,
                "file": "2026-04-15_odi_big.pdf",
                "bogus": 1,
            },
            "dest": {"hospital": hosp, "sigla": sigla},
            "rotation_deg": 90,
        },
    )
    assert r.status_code == 422, r.text
    # Belt-and-suspenders: the 422 must be about the unknown key, not a
    # missing required field.
    assert "bogus" in r.text
```

Implementer note: check `scan`'s current happy-path body/response in
`scan.py:146` first — if `scan` kicks off real work on the fixture session,
the unknown-key request must still be cheap because validation rejects it
**before** the handler runs. Add a `scan_ocr` unknown-key test only if a
cheap fixture exists (it streams work otherwise; the model guard is the same
one line).

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/integration/test_forbid_extra_keys.py -v`
Expected: new tests FAIL (200/400-but-not-422 today).

- [ ] **Step 3: Implement**

- `scan.py`: add `model_config = ConfigDict(extra="forbid")` to
  `ApplyRatioRequest` and `ScanFileOcrRequest`. Convert the two raw dicts,
  preserving today's manual validation (the OverridePatch trick):

```python
class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Any = "all"


class ScanOcrRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cells: Any = None
    participant_id: str | None = None
```

Before writing these, read the two handlers (`scan.py:146`, `scan.py:390`)
and mirror **exactly** the keys they read from the dict today (`body.get(...)`
calls) as `Any`-typed fields with the same defaults — then swap `body["x"]`/
`body.get("x")` reads for attribute access. If `scan_ocr` reads keys other
than `cells`/`participant_id`, add them as fields; do not drop any.

- `reorg.py`: add the config line to `ReorgOpCreate`, `ReorgSource`,
  `ReorgDest` (they stay otherwise untouched — nested `source.bogus` now 422s
  via `ReorgSource`).
- `api/routes/presence.py`: add the config line to `HeartbeatBody`,
  `FocusBody`, `LeaveBody`.

- [ ] **Step 4: Grep the test tree for intentional extra-key posts**

Run: `grep -rn "json={" tests/ | grep -iv forbid | wc -l` then targeted checks:
any test that posts a key not in the target model will now fail — the fast
suite run in the next step is the real gate; investigate any new failure as a
possible intentional-extra-key test and fix the test (not the model).

- [ ] **Step 5: Run the suite**

Run: `pytest tests/integration/test_forbid_extra_keys.py -v` → all PASS.
Run: `pytest -m "not slow" -q` → 0 failures.
Run: `ruff check .` → 0.

- [ ] **Step 6: Commit**

```bash
git add api/routes/sessions/scan.py api/routes/sessions/reorg.py api/routes/presence.py tests/integration/test_forbid_extra_keys.py
git commit -m "fix(api): forbid unknown keys on scan/reorg/presence bodies

ApplyRatioRequest/ScanFileOcrRequest/ReorgOpCreate/ReorgSource/ReorgDest/
HeartbeatBody/FocusBody/LeaveBody gain extra='forbid'; the scan and
scan_ocr raw dicts become Any-typed ScanRequest/ScanOcrRequest keeping
their manual validation (400 semantics unchanged)."
```

---

## Chunk 3: allow_over_pages (spec §3)

### Task 4: Backend flag

**Files:**
- Modify: `api/routes/sessions/writes.py` (both 422 sites + 2 models)
- Test: `tests/integration/test_override_cap.py` (extend)

- [ ] **Step 1: Write the failing tests (extend `test_override_cap.py`)**

```python
def test_cell_override_over_cap_with_flag_allowed(client, session_with_pending_cell):
    """allow_over_pages=True bypasses the cap (2-docs-per-page corpus case)."""
    sid, hosp, sigla = session_with_pending_cell  # total pages = 9
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override",
        json={"value": 18, "allow_over_pages": True},
    )
    assert r.status_code == 200, r.text
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["user_override"] == 18


def test_per_file_override_over_cap_with_flag_allowed(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell  # big.pdf = 8 pages
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 16, "allow_over_pages": True},
    )
    assert r.status_code == 200, r.text


def test_flag_does_not_bypass_negative_or_max(client, session_with_pending_cell):
    """The flag only lifts the pages cap — nothing else."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": -1, "allow_over_pages": True},
    )
    assert r.status_code == 422, r.text  # Field(ge=0) — pydantic validation
```

The existing `test_cell_override_capped_for_documents` /
`test_per_file_override_capped` (no flag → 422) stay untouched — they now
prove the default is unchanged.

- [ ] **Step 2: Run to verify the two `with_flag` tests fail**

Run: `pytest tests/integration/test_override_cap.py -v`
Expected: the two new `with_flag` tests FAIL 422; the rest PASS.

- [ ] **Step 3: Implement**

`OverridePatch` (from Task 2) and `PerFileOverrideRequest` gain:

```python
    allow_over_pages: bool = False
```

Cell site (~line 64, inside the `_is_capped_sigla` block): wrap the cap check —

```python
            if total_pages > 0 and value > total_pages and not body.allow_over_pages:
```

Per-file site (~line 120): same one-condition addition with its
`body.allow_over_pages`. Nothing is persisted about the flag.

- [ ] **Step 4: Run the suite**

Run: `pytest tests/integration/test_override_cap.py tests/integration/test_forbid_extra_keys.py -v` → all PASS.
Run: `pytest -m "not slow" -q` → 0 failures. `ruff check .` → 0.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions/writes.py tests/integration/test_override_cap.py
git commit -m "feat(api): allow_over_pages write-time flag on both override caps

Default unchanged (422 count_exceeds_pages). With the explicit flag the
cap is skipped — the legitimate 2-forms-per-sheet corpus case (HLU
insgral lineas de aire) no longer needs a cell override + note detour.
Negatives/_MAX_REASONABLE_COUNT/checks-exemption untouched."
```

### Task 5: Frontend `over_cap` confirmation

**Files:**
- Modify: `frontend/src/lib/override-input.js`
- Modify: `frontend/src/lib/override-input.test.js`
- Modify: `frontend/src/components/OverridePanel.jsx`
- Modify: `frontend/src/components/InlineEditCount.jsx`
- Modify: `frontend/src/store/session.js` (`saveOverride:~290`, `savePerFileOverride:~387`)
- Modify: `frontend/src/lib/api.js` (`patchOverride:~65`, `patchPerFileOverride:~81`)

- [ ] **Step 1: vitest first — `parseOverrideInput` distinguishes `over_cap`**

Add to `frontend/src/lib/override-input.test.js`:

```js
it("over-cap integer returns overCap (value kept) instead of plain invalid", () => {
  expect(parseOverrideInput("12", { maxPages: 6 })).toEqual({
    value: 12,
    valid: false,
    overCap: true,
  });
});

it("garbage stays plain invalid (no overCap)", () => {
  const r = parseOverrideInput("12abc", { maxPages: 6 });
  expect(r.valid).toBe(false);
  expect(r.overCap).toBeUndefined();
});
```

Run: `cd frontend && npx vitest run src/lib/override-input.test.js`
Expected: FAIL (today over-cap returns `{value: null, valid: false}`).

- [ ] **Step 2: Implement the lib change**

`override-input.js` — replace the cap branch:

```js
  if (maxPages != null && n > maxPages) {
    // Over-cap is NOT garbage: the value parses, it just exceeds the pages.
    // Callers surface a confirmation (allow_over_pages) instead of refusing.
    return { value: n, valid: false, overCap: true };
  }
```

Run the file's vitest → PASS. Existing assertions using `toEqual({value:null,
valid:false})` for the cap case must be updated in the same commit (search the
test file); assertions for garbage input stay.

- [ ] **Step 3: Thread the flag through api.js and the store**

`api.js patchOverride`: after `if (opts.manual) body.manual = true;` add:

```js
    if (opts.allowOverPages) body.allow_over_pages = true;
```

`api.js patchPerFileOverride`: build the body conditionally:

```js
    const body = { count, participant_id: opts.participantId ?? null };
    if (opts.allowOverPages) body.allow_over_pages = true;
```

`store/session.js saveOverride(sessionId, hospital, sigla, value, opts = {})`:
pass `allowOverPages: opts.allowOverPages` into the existing
`api.patchOverride(..., { signal, manual: opts.manual, participantId, allowOverPages: opts.allowOverPages })`.

`store/session.js savePerFileOverride(...)`: add a trailing `opts = {}`
parameter and pass `allowOverPages: opts.allowOverPages` into
`api.patchPerFileOverride(..., { signal, participantId, allowOverPages: opts.allowOverPages })`.

- [ ] **Step 4: OverridePanel confirmation (cell)**

In `OverridePanel.jsx`, `onChangeValue` currently destructures
`{ value: parsed, valid }` and only flushes when `valid`. Read the component
before editing; the change pattern:

- Destructure `overCap` too. On `overCap`: hold the pending value in local
  state (`pendingOverCap = parsed`) and render an inline confirmation under
  the input (reuse the row where the `máx. {maxPages} (páginas)` hint shows):

```jsx
{pendingOverCap != null && (
  <div className="mt-1 flex items-center gap-2 text-xs text-po-suspect">
    <span>La celda tiene {maxPages} páginas. ¿Confirmas {pendingOverCap} documentos?</span>
    <button
      type="button"
      className="rounded border border-po-border px-1.5 py-0.5 text-po-text hover:border-po-border-strong"
      onClick={() => { commit(pendingOverCap, { allowOverPages: true }); setPendingOverCap(null); }}
    >
      Confirmar
    </button>
    <button
      type="button"
      className="text-po-text-muted hover:text-po-text"
      onClick={() => setPendingOverCap(null)}
    >
      Cancelar
    </button>
  </div>
)}
```

where `commit(v, opts)` must call the store's **`saveOverride` directly with
the opts** (`saveOverride(sessionId, hospital, sigla, v, { manual: true,
allowOverPages: true })`) — NOT the panel's existing debounced `flushSave`
wrapper, which only forwards the value and would need reshaping. The
confirmed save is an explicit click; it does not need the debounce.
Cancelar keeps the previous value (today's refuse behavior). The plain
`invalid` hint for garbage input stays as-is. Match the file's exact
structure — the JSX above is the shape, not a paste-blind block.

- [ ] **Step 5: InlineEditCount confirmation (per-file)**

`InlineEditCount.jsx` — on Enter with `v > max` the component currently sets
`invalid`. Change: distinguish over-cap (integer, `> max`) from garbage:

```jsx
onKeyDown={(e) => {
  if (e.key === "Enter") {
    const v = parseInt(draft, 10);
    if (!Number.isNaN(v) && v >= 0 && (max === null || v <= max)) {
      onCommit(v);
      setEditing(false);
    } else if (!Number.isNaN(v) && v >= 0 && max !== null && v > max) {
      setOverCap(v); // new state → confirmation row below the input
    } else {
      setInvalid(true);
    }
  } else if (e.key === "Escape") {
    setEditing(false);
    setOverCap(null);
  }
}}
```

New state `const [overCap, setOverCap] = useState(null);`. Three mechanical
requirements the current code shape imposes:
- the editing-mode `return` is a bare `<input>` today — wrap it in a
  Fragment (`<>...</>`) to host the confirmation row sibling;
- `onChange` currently resets only `invalid` — it must also
  `setOverCap(null)` so typing again dismisses a stale confirmation row;
- while `overCap != null`, suppress the `onBlur={() => setEditing(false)}`
  close (the confirm buttons must be clickable — gate it:
  `onBlur={() => { if (overCap == null) setEditing(false); }}`).

Render the confirmation row:

```jsx
{overCap != null && (
  <span className="ml-1 inline-flex items-center gap-1 text-[11px] text-po-suspect whitespace-nowrap">
    ¿{overCap} docs en {max} págs?
    <button type="button" onClick={() => { onCommit(overCap, { allowOverPages: true }); setOverCap(null); setEditing(false); }} className="underline">Sí</button>
    <button type="button" onClick={() => { setOverCap(null); setEditing(false); }} className="underline text-po-text-muted">No</button>
  </span>
)}
```

`onCommit` gains the optional second argument; its FileList caller passes it
through to `savePerFileOverride(..., { allowOverPages: opts?.allowOverPages })`.
Check `CategoryRow.jsx`'s `onCommit` usage too (the component is shared) —
its cell-level caller goes through `saveOverride`; thread the same optional
`opts`. Callers that ignore the second arg keep working (JS).

- [ ] **Step 6: vitest for the component/store flow**

Add `frontend/src/components/InlineEditCount.test.jsx` cases (follow the
file's existing test style if present; otherwise create with
`@testing-library/react` like the other component tests): typing an over-cap
value + Enter shows the confirmation; "Sí" calls `onCommit(v, {allowOverPages:
true})`; "No" commits nothing.

Run: `cd frontend && npx vitest run` → all green.

- [ ] **Step 7: Build + full gates**

Run: `cd frontend && npm run build` → OK.
Run: `pytest -m "not slow" -q` → 0 failures. `ruff check .` → 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/override-input.js frontend/src/lib/override-input.test.js frontend/src/lib/api.js frontend/src/store/session.js frontend/src/components/OverridePanel.jsx frontend/src/components/InlineEditCount.jsx frontend/src/components/InlineEditCount.test.jsx
git commit -m "feat(web): over-cap confirmation -> allow_over_pages

parseOverrideInput returns overCap (value kept) instead of plain invalid;
OverridePanel + InlineEditCount surface '¿Confirmas N documentos?' and on
confirm resend through saveOverride/savePerFileOverride with the flag.
Cancelar keeps today's refuse behavior; garbage input unchanged."
```

---

## Chunk 4: Presence (spec §4)

### Task 6: `GET /sessions/{id}/presence`

**Files:**
- Modify: `api/routes/presence.py`
- Test: `tests/integration/test_presence_two_participants.py` (extend)

- [ ] **Step 1: Failing test**

```python
def test_get_presence_snapshot(client, session_with_pending_cell):
    """Headless clients can poll the same snapshot the WS pushes."""
    sid, _, _ = session_with_pending_cell
    client.post(
        f"/api/sessions/{sid}/presence/heartbeat",
        json={"participant_id": "p1", "name": "Ana", "color": "#fff"},
    )
    r = client.get(f"/api/sessions/{sid}/presence")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "presence"
    ids = [p["participant_id"] for p in body["participants"]]
    assert "p1" in ids
```

(Use this file's own existing fixtures/imports — read it first; if it builds
sessions differently, follow its idiom instead of `session_with_pending_cell`.)

Run: `pytest tests/integration/test_presence_two_participants.py -v -k get_presence`
Expected: FAIL 404/405.

- [ ] **Step 2: Implement**

In `api/routes/presence.py`:

```python
@router.get("/sessions/{session_id}/presence")
def get_presence(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Return the live presence snapshot (same shape as the WS event).

    Args:
        session_id: YYYY-MM session identifier.
        mgr: session manager (injected).

    Returns:
        Presence event dict with ``type="presence"`` and ``participants``.
    """
    _validate_session_id(session_id)
    return _presence_event(session_id, mgr)
```

No broadcast (read-only).

- [ ] **Step 3: Run + commit**

Run: `pytest tests/integration/test_presence_two_participants.py -v` → PASS; `ruff check .` → 0.

```bash
git add api/routes/presence.py tests/integration/test_presence_two_participants.py
git commit -m "feat(presence): GET snapshot endpoint for headless clients"
```

### Task 7: Agent heartbeat creates/normalizes `kind="agent"`

**Files:**
- Modify: `api/presence.py` (`PresenceRegistry.heartbeat`, lines 54-84)
- Test: `tests/unit/api/test_presence_registry.py` (extend — its ctor idiom is `PresenceRegistry(now=lambda: clock[0])`; the kwarg is **`now`**, not `clock`)

- [ ] **Step 1: Failing test (registry level)**

```python
def test_agent_heartbeat_creates_agent_record():
    """A heartbeat from AGENT_PARTICIPANT_ID must not create a human record.

    Regression 2026-07-08: the agent heartbeated before its first write and
    the UI showed initials instead of the Bot icon."""
    reg = PresenceRegistry(now=lambda: 0.0)
    reg.heartbeat("s", AGENT_PARTICIPANT_ID, name="whatever", color="#000")
    (rec,) = reg.snapshot("s")
    assert rec["kind"] == AGENT_KIND
    assert rec["name"] == AGENT_NAME
    assert rec["color"] == AGENT_COLOR


def test_agent_heartbeat_heals_stale_human_record():
    """A pre-existing human-kind record for the agent id is normalized."""
    reg = PresenceRegistry(now=lambda: 0.0)
    reg.heartbeat("s", AGENT_PARTICIPANT_ID, name="X", color="#000")  # will already be agent post-fix
    # Simulate legacy state:
    reg._participants["s"][AGENT_PARTICIPANT_ID]["kind"] = "human"
    reg.heartbeat("s", AGENT_PARTICIPANT_ID, name="X", color="#000")
    (rec,) = reg.snapshot("s")
    assert rec["kind"] == AGENT_KIND


def test_human_heartbeat_unchanged():
    reg = PresenceRegistry(now=lambda: 0.0)
    reg.heartbeat("s", "p1", name="Ana", color="#fff")
    (rec,) = reg.snapshot("s")
    assert rec["kind"] == "human"
```

Match the file's existing imports (it already imports `PresenceRegistry`;
add `AGENT_PARTICIPANT_ID`, `AGENT_KIND`, `AGENT_NAME`, `AGENT_COLOR`).
`snapshot()`'s exact signature: mirror how the existing tests in that file
read the roster. Run → first two FAIL.

- [ ] **Step 2: Implement in `PresenceRegistry.heartbeat`**

At the top of the method, before the create/renew logic:

```python
        if is_agent(participant_id):
            # Single source for agent identity — a heartbeating agent must
            # show the Bot avatar, not initials (2026-07-08 regression).
            name, color, kind = AGENT_NAME, AGENT_COLOR, AGENT_KIND
```

and in the renew branch, normalize a stale record:

```python
        if existing["kind"] != kind:
            existing["kind"] = kind
            changed = True
```

(Place it with the existing name/color-change detection so the broadcast
`changed` semantics stay coherent — read the method and keep its return
contract: True iff the roster visibly changed.)

- [ ] **Step 3: Run + full gates + commit**

Run: the extended unit file → PASS; `pytest -m "not slow" -q` → 0 failures;
`ruff check .` → 0.

```bash
git add api/presence.py tests/unit/api/test_presence_registry.py
git commit -m "fix(presence): agent heartbeat creates/normalizes kind=agent

heartbeat() hardcoded kind=human on create, so an agent that heartbeated
before its first write wore a human avatar (no Bot icon). Agent identity
(name/color/kind) now comes from the AGENT_* constants on both create and
renew."
```

### Task 8: Round close — gates + output-safety check

- [ ] **Step 1: Full gates**

```bash
pytest -m "not slow" -q        # 0 failures
cd frontend && npx vitest run  # 0 failures
cd frontend && npm run build   # OK
ruff check .                   # 0
```

- [ ] **Step 2: Output safety (spec AC-6)**

Snapshot counts before/after the round on the real DB with the tooling used
in prior rounds (`tools/dump_counts.py` if present — check `tools/`).
Expected: zero row changes.

- [ ] **Step 3: Push**

```bash
git push origin po_overhaul
```
