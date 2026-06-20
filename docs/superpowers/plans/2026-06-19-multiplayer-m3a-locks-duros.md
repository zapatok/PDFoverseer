# Multiplayer M3a — Hard locks (human collision protection) · Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax. Subagents are **Sonnet minimum** (never Haiku).

**Goal:** Two humans editing the same month can't clobber each other: opening a cell **claims** it (you become its editor); anyone else who opens it sees it **read-only** with the owner's badge + an inline notice; a contested write is rejected with **409**.

**Architecture:** Extend the existing M2 `PresenceRegistry` so `focus` is an **atomic claim** (free cell → you're `editor`; held cell → you're `viewer`, the holder keeps `editor`) — at-most-one editor per cell, guaranteed by `SessionManager`'s single `RLock`. Single-cell write endpoints take a `participant_id` and, **inside the same `@_synchronized` write** (no TOCTOU), reject the write with `CellLockedError`→409 when the cell is held by a *different* participant. The frontend derives read-only gating purely from the live `presence` snapshot (the editor of a cell that isn't me), so it auto-recovers when the holder leaves.

**Tech Stack:** FastAPI (sync handlers, `@_synchronized` + `RLock`, exception handler → 409), in-memory `PresenceRegistry`, React + Zustand v5, vitest.

**Spec:** `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` §6.1–§6.4, §7, §12 (M3 bullet). This plan is **M3a** — the human-collision core. **Deferred to M3b** (separate plan): Claude as a per-cell participant (auto-claim on write) + the scanner skipping locked cells (`cell_skipped`). Do NOT build those here.

**Branch:** work directly on `po_overhaul`; push at end of the round.

---

## Design decisions (read before coding)

1. **One editor per cell, derived from presence.** The editor of `cell` is the live participant with `focused_cell == cell` and `mode == "editor"`. `focus` (claim) is the only thing that mints an editor. The lease (TTL 45s, M2) auto-frees the lock when a participant is purged — no special release path.
2. **Enforcement rule (deliberate reading of §6.4):** a write is rejected **iff the cell is currently held by a *different* participant** (an editor ≠ me). A **free** cell never 409s — this keeps bulk/coarse writes and the normal claim-then-edit flow working; the only thing we protect is the real collision (two people on the *same* cell). §6.4's "verify the writer is the editor" is the common path (the browser claimed via `focus` first); we implement its intent ("locked by another → 409") rather than 409-ing writes to free cells, which would break "mark selected as ready" and any write whose browser hasn't claimed. The atomic claim+check still holds because the check runs inside the write's `RLock`.
3. **`participant_id` is optional on writes.** When absent (old client / existing tests / no active presence) there is no enforcement — and since locks only exist when someone has actively claimed, endpoints behave exactly as today unless a real conflict exists. No existing test needs changing.
4. **Frontend gating derives from `presence`, not from "my mode".** Read-only iff `cellLockHolder(presence, h, s, me)` is non-null. This auto-recovers: when the holder leaves, the `presence` broadcast drops them → the cell becomes editable again without the viewer having to do anything. (My own stale `mode:"viewer"` is irrelevant to gating.)
   - **§6.2 response contract is satisfied via the snapshot, not a separate field.** The `focus` endpoint already returns the **full presence snapshot** in its HTTP body (M2), and every participant record carries `focused_cell` + `mode`. So the claimer gets its own `mode` *and* can derive the cell's `lock_holder` (`cellLockHolder`) immediately from the focus response — the same data §6.2 asks for (`{mode, lock_holder}`), just delivered as the whole snapshot rather than a bespoke shape. No change to the `focus` route's return is needed in M3a; do NOT add a separate `{mode, lock_holder}` body.
5. **Claim already wired:** `focus` is called on cell select / `null` on back (M2, `HospitalDetail` effect). M3a only changes what `focus` *does* server-side and how the UI reacts.

## File structure

**Backend:**
- `api/presence.py` — `PresenceRegistry.focus` becomes a claim (sets `mode`); add `_editor_of` + public `lock_holder`. Add `CellLockedError`.
- `api/state.py` — `SessionManager`: add `_editor_conflict` helper; thread `participant_id` + the conflict check into the single-cell write methods (`apply_user_override`, `apply_per_file_override`, `apply_worker_count`, `set_note`, `apply_confirmed`, `clear_near_matches`, and the apply-ratio path).
- `api/main.py` — register a `CellLockedError` exception handler → 409.
- `api/routes/sessions.py` — add `participant_id: str | None = None` to the write bodies; pass it through.
- Tests: `tests/unit/api/test_presence_locks.py` (registry claim), `tests/unit/api/test_lock_enforcement.py` (endpoint 409), extend `tests/integration/test_presence_two_participants.py`.

**Frontend:**
- `frontend/src/lib/presence.js` — `cellLockHolder(participants, hospital, sigla, selfId)`.
- `frontend/src/lib/api.js` — write methods accept/send `participant_id`.
- `frontend/src/store/session.js` — write actions pass `participant_id`; handle a 409 (toast + refetch the cell, revert optimistic).
- `frontend/src/components/DetailPanel.jsx`, `frontend/src/components/FileList.jsx` — read-only gating + inline notice + owner badge when locked.
- vitest: `presence.test.js` (new selector), `store/session.lock.test.js` (409 handling).

## Constants / naming
- `CellLockedError` lives in `api/presence.py` (next to the registry it derives from).
- 409 response body: `{"detail":"cell_locked","hospital":...,"sigla":...,"lock_holder":{participant_id,name,color,kind}}`.

---

## Chunk 1: Registry — atomic claim + lock_holder

### Task 1: `focus` becomes a claim (editor/viewer)

**Files:** Modify `api/presence.py`; Test `tests/unit/api/test_presence_locks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_presence_locks.py
from api.presence import PresenceRegistry

def _reg():
    return PresenceRegistry(now=lambda: 1000.0)

def test_first_to_focus_a_free_cell_is_editor():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")
    rec = next(p for p in r.snapshot("m") if p["participant_id"] == "p1")
    assert rec["mode"] == "editor"
    assert rec["focused_cell"] == "HRB|odi"

def test_second_to_focus_held_cell_is_viewer_holder_keeps_editor():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.heartbeat("m", "p2", name="C", color="#b")
    r.focus("m", "p1", "HRB|odi")          # p1 editor
    r.focus("m", "p2", "HRB|odi")          # p2 joins -> viewer
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p1"]["mode"] == "editor"
    assert snap["p2"]["mode"] == "viewer"

def test_lock_holder_reports_the_editor_excluding_self():
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.heartbeat("m", "p2", name="Carla", color="#b")
    r.focus("m", "p1", "HRB|odi")
    assert r.lock_holder("m", "HRB|odi", exclude="p2")["participant_id"] == "p1"
    # the holder excluding itself = nobody is "in my way"
    assert r.lock_holder("m", "HRB|odi", exclude="p1") is None
    assert r.lock_holder("m", "HRB|art", exclude="p2") is None  # free cell

def test_releasing_a_cell_frees_the_lock():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")          # editor
    r.focus("m", "p1", None)               # back to month view
    assert r.lock_holder("m", "HRB|odi", exclude="p2") is None

def test_moving_to_another_cell_frees_the_previous():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.focus("m", "p1", "HRB|art")
    assert r.lock_holder("m", "HRB|odi", exclude="p2") is None
    assert r.lock_holder("m", "HRB|art", exclude="p2")["participant_id"] == "p1"
```

- [ ] **Step 2: Run, verify it fails** (`lock_holder` missing; `mode` not set by `focus`).

- [ ] **Step 3: Implement** — in `api/presence.py`:

Add a private editor finder and a public lock_holder; make `focus` set `mode`:

```python
    def _editor_of(self, session_id: str, cell: str, exclude: str | None = None) -> str | None:
        """participant_id of the live editor of `cell`, or None. Caller purges first."""
        for pid, r in self._participants.get(session_id, {}).items():
            if pid == exclude:
                continue
            if r["focused_cell"] == cell and r["mode"] == "editor":
                return pid
        return None

    def lock_holder(self, session_id: str, cell: str, exclude: str | None = None) -> dict | None:
        """Public snapshot of the cell's editor (excluding `exclude`), or None if free."""
        self._purge_expired(session_id)
        pid = self._editor_of(session_id, cell, exclude=exclude)
        if pid is None:
            return None
        r = self._participants[session_id][pid]
        return {k: r[k] for k in _PUBLIC_FIELDS}
```

Replace the body of `focus` so it claims (editor if free, viewer if held):

```python
    def focus(self, session_id: str, participant_id: str, cell: str | None) -> bool:
        """Focus = atomic claim (caller holds the RLock). Free cell -> editor; held
        cell -> viewer (the holder keeps editor). cell=None releases. Returns True
        iff the roster changed."""
        changed = self._purge_expired(session_id)
        rec = self._participants.setdefault(session_id, {}).get(participant_id)
        if rec is None:
            return changed  # focus before heartbeat: ignore, be forgiving
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if cell is None:
            new_mode = "editor"  # mode is moot when not focused; reset to default
        else:
            new_mode = "viewer" if self._editor_of(session_id, cell, exclude=participant_id) else "editor"
        if rec["focused_cell"] != cell or rec["mode"] != new_mode:
            rec["focused_cell"] = cell
            rec["mode"] = new_mode
            return True
        return changed
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `feat(multiplayer): focus is an atomic claim + lock_holder (M3a)`

### Task 2: `CellLockedError` + SessionManager exposure

**Files:** Modify `api/presence.py` (error), `api/state.py` (helper + pass-through); Test `tests/unit/api/test_presence_locks.py`

- [ ] **Step 1: Add the error** in `api/presence.py` (module level):

```python
class CellLockedError(Exception):
    """Raised when a write targets a cell held by a different participant (M3a)."""
    def __init__(self, hospital: str, sigla: str, holder: dict):
        self.hospital = hospital
        self.sigla = sigla
        self.holder = holder
        super().__init__(f"{hospital}|{sigla} locked by {holder.get('name')}")
```

- [ ] **Step 2: Add a manager helper + a public `presence_lock_holder`** in `api/state.py` (decorated `@_synchronized`, mirroring the M2 presence methods):

```python
    @_synchronized
    def presence_lock_holder(self, session_id, cell, exclude=None):
        return self._presence.lock_holder(session_id, cell, exclude=exclude)

    def _editor_conflict(self, session_id, hospital, sigla, participant_id):
        """The lock_holder dict if (hospital|sigla) is held by a DIFFERENT participant,
        else None. participant_id None -> no enforcement (legacy/tests).
        Call ONLY from inside an already-@_synchronized method (it reads _presence
        under the held RLock — that is what makes check+write atomic, spec §6.4)."""
        if participant_id is None:
            return None
        return self._presence.lock_holder(session_id, f"{hospital}|{sigla}", exclude=participant_id)
```

Write a test that `_editor_conflict` returns the holder for a contended cell and `None` for a free cell / matching participant / `participant_id=None` (use a real `SessionManager` with a tmp DB, like `test_presence_manager.py`). 

- [ ] **Step 3:** Run, verify pass.
- [ ] **Step 4: Commit** — `feat(multiplayer): CellLockedError + SessionManager lock-conflict helper (M3a)`

> **Chunk 1 review:** plan-document-reviewer + `pytest tests/unit/api/test_presence_locks.py tests/unit/api/test_presence_manager.py -v` + `ruff check api/`.

---

## Chunk 2: Write-endpoint enforcement (409)

### Task 3: Enforce in the single-cell write methods

**Files:** Modify `api/state.py` (write methods); Test `tests/unit/api/test_lock_enforcement.py`

The write methods to guard **in-method** (all already `@_synchronized`, all keyword-only args): `apply_user_override`, `apply_per_file_override`, `apply_worker_count`, `set_note`, `apply_confirmed`, `clear_near_matches`. For EACH:

> **apply-ratio is handled differently (do NOT guard `apply_per_file_ocr_result`).** The `apply_ratio` route (`api/routes/sessions.py:apply_ratio` ~L281) does NOT call `apply_user_override`; it loops `mgr.apply_per_file_ocr_result(...)` per file then `mgr.finalize_cell_ocr(...)`. Those same methods are called by the **OCR scanner** (with no `participant_id`), so guarding them directly is wrong. Instead add ONE thin gate method and call it at the route **before** the loop (Task 4):
> ```python
>     @_synchronized
>     def check_cell_lock(self, session_id, hospital, sigla, participant_id):
>         holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
>         if holder is not None:
>             raise CellLockedError(hospital, sigla, holder)
> ```
> This is TOCTOU-safe for ratio: the operator reached the ratio button by selecting the cell in DetailPanel = they already `focus`-claimed it = they are its editor, so no *other* participant can be the editor during the loop (a second person who opens the cell becomes `viewer`, never editor). The pre-check just confirms no *other* holder. (Same method is reusable for any future multi-write route.)

For each of the 6 in-method writes:

- [ ] **Step 1:** Add a keyword param `participant_id: str | None = None` to the method signature (at the end, default None — backward compatible).
- [ ] **Step 2:** As the FIRST statement in the method body (inside the lock), add:

```python
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            from api.presence import CellLockedError
            raise CellLockedError(hospital, sigla, holder)
```

(Use a module-level import of `CellLockedError` at the top of `state.py` instead of the inline import if there's no circular-import issue — `presence.py` imports nothing from `state.py`, so top-level is fine and preferred.)

- [ ] **Step 3: Write the failing test** `tests/unit/api/test_lock_enforcement.py` (manager-level, real tmp DB):

```python
import pytest
from api.presence import CellLockedError
from api.state import SessionManager

def _mgr(tmp_path):
    from core.db.connection import open_connection
    from core.db.migrations import init_schema
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    return SessionManager(conn=conn)

def test_write_to_cell_held_by_another_raises(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")          # Carla holds HRB|odi
    with pytest.raises(CellLockedError):
        mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")

def test_editor_can_write_its_own_cell(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")  # no raise

def test_free_cell_and_no_participant_id_are_unenforced(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")  # free -> ok
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5)                       # None -> ok
```

> **IMPORTANT — the guarded methods take keyword-only args** (`def apply_user_override(self, session_id, hospital, sigla, *, value, manual=False)`; `set_note(..., *, text, status)`, etc.). Read each real signature in `api/state.py` and add `participant_id: str | None = None` as a trailing keyword param; call them with keyword args in tests (`value=5`, `text=...`, `status=...`).

- [ ] **Step 4:** Run, verify the held-cell test fails first (before guarding), then passes after. Confirm the other two pass.
- [ ] **Step 5: Commit** — `feat(multiplayer): reject writes to a cell held by another participant (M3a)`

### Task 4: Routes pass `participant_id`; 409 exception handler

**Files:** Modify `api/routes/sessions.py` (bodies + calls), `api/main.py` (handler); Test `tests/unit/api/test_lock_enforcement.py`

- [ ] **Step 1:** Thread `participant_id` from each write route into its manager call:
  - Add `participant_id: str | None = None` to the Pydantic bodies `PerFileOverrideRequest` (L798), `ClearNearMatchBody` (L850), `WorkerCountPatch` (L879), `NotePatch` (L928), `ConfirmRequest` (L974), `ApplyRatioRequest` (L277); pass `participant_id=body.participant_id` (keyword) into the corresponding manager write call.
  - **`patch_override` (~L756) is NOT a Pydantic model** — it takes `body: dict = Body(...)` and reads `body.get("value")` / `body.get("manual", False)` inline. Match that style: read `participant_id = body.get("participant_id")` inline and pass it through. (Do NOT migrate this route to a model — keep the change minimal/consistent.)
  - **apply-ratio:** in the `apply_ratio` route, call `mgr.check_cell_lock(session_id, hospital, sigla, body.participant_id)` **before** the per-file loop (Task 3's gate method). Do not touch `apply_per_file_ocr_result`/`finalize_cell_ocr`.
- [ ] **Step 2:** Register the exception handler in `api/main.py` (after `create_app()` builds the app, before `return app`):

```python
    from fastapi.responses import JSONResponse
    from api.presence import CellLockedError

    @app.exception_handler(CellLockedError)
    async def _cell_locked_handler(_request, exc: CellLockedError):
        return JSONResponse(
            status_code=409,
            content={"detail": "cell_locked", "hospital": exc.hospital,
                     "sigla": exc.sigla, "lock_holder": exc.holder},
        )
```

- [ ] **Step 3: Write the failing endpoint test** (TestClient, hit presence focus then a write with a different participant_id → 409 with `lock_holder`):

```python
from fastapi.testclient import TestClient
from api.main import create_app

def test_override_endpoint_409_when_locked_by_another():
    with TestClient(create_app()) as c:
        c.post("/api/sessions/2026-04/presence/heartbeat", json={"participant_id":"p2","name":"Carla","color":"#b"})
        c.post("/api/sessions/2026-04/presence/focus", json={"participant_id":"p2","cell":"HRB|odi"})
        r = c.patch("/api/sessions/2026-04/cells/HRB/odi/override",
                    json={"value": 5, "participant_id": "p1"})
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Carla"
```

(Match the override endpoint's real body shape.)

- [ ] **Step 4:** Run, verify pass. Then `pytest tests/ -k "override or worker or note or confirm or ratio or near or presence or scan or session" -q` → no regressions (writes without `participant_id`, or to free cells, still succeed).
- [ ] **Step 5: Commit** — `feat(multiplayer): write endpoints carry participant_id + 409 handler (M3a)`

### Task 5: Two-participant 409 integration

**Files:** extend `tests/integration/test_presence_two_participants.py`

- [ ] **Step 1:** Add a test: p1 focuses `HRB|odi`; p2 focuses the same → p2 snapshot shows `mode:"viewer"`; p2's override write → 409; after p1 focuses elsewhere (releases), p2's write succeeds. Run → pass.
- [ ] **Step 2:** `ruff check api/ tests/` → 0.
- [ ] **Step 3: Commit** — `test(multiplayer): two-participant lock + 409 + release integration (M3a)`

> **Chunk 2 review:** plan-document-reviewer + full `pytest tests/ -q` (no regression to M1/M2/scan/output) + `ruff check .`.

---

## Chunk 3: Frontend — claim awareness + 409 handling

### Task 6: `cellLockHolder` selector

**Files:** Modify `frontend/src/lib/presence.js`, `frontend/src/lib/presence.test.js`

- [ ] **Step 1: Failing tests:**

```js
import { cellLockHolder } from "./presence";
const ps = [
  { participant_id: "p1", name: "Daniel", color: "#a", focused_cell: "HRB|odi", mode: "editor" },
  { participant_id: "p2", name: "Carla", color: "#b", focused_cell: "HRB|odi", mode: "viewer" },
];
it("returns the editor of a cell when it isn't me", () => {
  expect(cellLockHolder(ps, "HRB", "odi", "p2").participant_id).toBe("p1");
});
it("returns null when I am the editor", () => {
  expect(cellLockHolder(ps, "HRB", "odi", "p1")).toBeNull();
});
it("returns null for a free cell / empty list", () => {
  expect(cellLockHolder(ps, "HRB", "art", "p2")).toBeNull();
  expect(cellLockHolder(undefined, "HRB", "odi", "p2")).toBeNull();
});
it("ignores viewers (only an editor locks)", () => {
  const onlyViewer = [{ participant_id: "p2", focused_cell: "HRB|odi", mode: "viewer" }];
  expect(cellLockHolder(onlyViewer, "HRB", "odi", "p1")).toBeNull();
});
```

- [ ] **Step 2–4:** implement + run:

```js
export function cellLockHolder(participants, hospital, sigla, selfId) {
  const key = `${hospital}|${sigla}`;
  return (participants ?? []).find(
    (p) => p.focused_cell === key && p.mode === "editor" && p.participant_id !== selfId,
  ) ?? null;
}
```

- [ ] **Step 5: Commit** — `feat(multiplayer): cellLockHolder selector (M3a)`

### Task 7: write actions send `participant_id` + handle 409

**Files:** Modify `frontend/src/lib/api.js`, `frontend/src/store/session.js`; Test `frontend/src/store/session.lock.test.js`

- [ ] **Step 1:** In `api.js`, the write methods must (a) include `participant_id` in their JSON body, and (b) surface a 409's **structured** body. Today the helper reads `res.text()` on non-ok, so the `{detail, lock_holder}` payload is lost in a string. Add a helper that preserves it and use it in the write methods:

```js
async function jsonOrThrowStructured(res) {
  if (res.ok) return res.json();
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error body */ }
  const err = new Error(body?.detail || res.statusText);
  err.status = res.status;
  err.body = body;            // {detail, hospital, sigla, lock_holder} on a 409
  throw err;
}
```

Each write method takes/sends `participant_id` (the store passes it) and routes its response through `jsonOrThrowStructured`. Confirm the exact store-called method names by reading `api.js` + the store; the writes are: override, per-file override, worker-count, note, confirm, apply-ratio, clear-near-matches.

- [ ] **Step 2:** In `store/session.js`, each write action passes `getIdentity()?.participant_id` (guard `typeof localStorage === "undefined"` first, like the M2 presence actions). Wrap the write in `try/catch`; on `err.status === 409`: `toast.error(\`\${err.body?.lock_holder?.name ?? "Otro usuario"} está editando esta celda\`)` and **refetch** to discard the optimistic change (call `get().refetchSession(session.session_id)` — the M1/M2 action — or the existing per-cell refetch path used after scans). **Store action names (verified):** the note action is `saveNote` (not `setNote`); the ratio action is `applyRatioCell` (not `applyRatio`). Use the real names: `saveOverride`, `savePerFileOverride`, the worker-count save, `saveNote`, `confirmCell`, `applyRatioCell`, `clearNearMatches`.
- [ ] **Step 3: Test** `session.lock.test.js` (jsdom, mock `../lib/api` + `sonner`): a write action calls `api.*` with `participant_id` in the body; when `api.*` rejects with `{status:409, body:{lock_holder:{name:"Carla"}}}`, the store calls `toast.error` (with Carla's name) and triggers `refetchSession`. Run → pass.
- [ ] **Step 4:** `npx vitest run` (all green) + `npm run build`.
- [ ] **Step 5: Commit** — `feat(multiplayer): writes carry participant_id + revert on 409 (M3a)`

> **Chunk 3 review:** plan-document-reviewer + `npx vitest run` + `npm run build`.

---

## Chunk 4: Frontend — read-only gating UI

### Task 8: DetailPanel read-only when locked

**Files:** Modify `frontend/src/components/DetailPanel.jsx`

- [ ] **Step 1:** Compute the holder near the top (after the early return guards):

```jsx
import { cellLockHolder } from "../lib/presence";
import { getParticipantId } from "../lib/identity";
import PresenceBadge from "./PresenceBadge";
// ...
const presence = useSessionStore((s) => s.presence);
const lockHolder = cellLockHolder(presence, hospital, sigla, getParticipantId());
const locked = lockHolder !== null;
```

- [ ] **Step 2:** When `locked`, render a **visible inline notice** at the top of the panel (po-* tokens, amber/suspect tone) with the holder's `PresenceBadge` (sm) + text `"{lockHolder.name} está editando esta celda"`. Spanish-neutro.
- [ ] **Step 3:** **Disable the edit controls** while `locked`: the `SegmentedToggle` (Por archivos/Manual), the ratio buttons (Aplicar R1 / ratio N), the `OverridePanel` (pass a `disabled`/`locked` prop or wrap), the `NotePanel`, the worker-count "Contar/Continuar/Revisar" button, and the near-match action buttons. Reuse existing `disabled` props where the controls/`ui/Button` support them; for inputs add `disabled={locked}`. Do NOT hide them — show them disabled so the layout is stable and the state is legible. (This is the UI backstop; the 409 from Chunk 2 is the server backstop.)
- [ ] **Step 4:** `npm run build`; manually reason through: when `lockHolder` is null (free / I'm the editor) everything is interactive exactly as today (no regression for the single-user case — `presence` empty → `cellLockHolder` null → nothing disabled).
- [ ] **Step 5: Commit** — `feat(multiplayer): DetailPanel read-only + owner notice when cell is locked (M3a)`

### Task 9: FileList read-only when locked

**Files:** Modify `frontend/src/components/FileList.jsx`

- [ ] **Step 1:** Same pattern: `const lockHolder = cellLockHolder(presence, hospital, sigla, getParticipantId()); const locked = !!lockHolder;`
- [ ] **Step 2:** When `locked`, disable the per-file `InlineEditCount` inputs and the `ReorgMenu` trigger (pass `disabled`), and show the same inline "{name} está editando" banner at the top (or rely on DetailPanel's — but FileList is a separate column, so a compact lock hint here is worth it). Keep the file list itself readable (viewing is allowed).
- [ ] **Step 3:** `npm run build`; confirm single-user path unaffected (empty presence → not locked).
- [ ] **Step 4: Commit** — `feat(multiplayer): FileList read-only when cell is locked (M3a)`

### Task 10: CategoryRow editor indicator (optional polish)

**Files:** Modify `frontend/src/components/CategoryRow.jsx`

- [ ] **Step 1:** The per-cell `PresenceBadge`s already render (M2). When a participant on this cell is the **editor** (`mode === "editor"` and not me), give their badge a subtle lock affordance (e.g., a `ring` in a po-* token, or a tiny `Lock` lucide icon overlay). Keep it minimal; do not change layout. This makes "who owns which cell" legible from the list.
- [ ] **Step 2:** `npm run build`.
- [ ] **Step 3: Commit** — `feat(multiplayer): mark the editing owner on the category row badge (M3a)`

> **Chunk 4 review:** plan-document-reviewer + `npx vitest run` + `npm run build` + `ruff check .`. Then the holistic cross-chunk review.

---

## Final verification (before declaring done)

- [ ] `pytest -m "not slow" -q` (incl. eval/tests) — green; plus a full `pytest -q` if time allows (the slow corpus run).
- [ ] `npx vitest run` — green incl. new lock tests.
- [ ] `npm run build` — OK; rebuild `frontend/dist`.
- [ ] `ruff check .` — 0.
- [ ] **Single-user regression (hard requirement):** with no second participant (empty `presence`), every control is interactive and every write succeeds exactly as before — `cellLockHolder` is null, `participant_id` writes hit free cells, no 409.
- [ ] **Live 2-context LAN smoke (Brave debug, isolated contexts):** A opens `HRB|odi` (becomes editor); B opens the same cell → B sees the panel **read-only** + "Daniel está editando esta celda" + Daniel's badge; B forcing a write (or before the UI updates) gets a 409 and the value reverts; A moves to another cell → B's panel becomes editable. Roster/badges from M2 still work.

## Out of scope (M3b — separate plan)
Claude as a per-cell participant (auto-claim on write via the same `_editor_conflict` seam, extended so an **agent** `participant_id` claims a *free* cell instead of just being checked; fixed `claude`/agent identity; 409-reporting), and the **scanner** skipping cells locked by another (`cell_skipped` event + `scan_complete.skipped` + claim-as-claude). The enforcement helper is written so M3b only adds the "agent auto-claims a free cell" branch.
