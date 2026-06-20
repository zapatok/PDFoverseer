# Multiplayer M2 — Presencia · Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Subagents are **Sonnet minimum** (never Haiku) per project convention.

**Goal:** Two humans (Daniel, Carla) working the same month see each other's identity and which cell each is in, live — without any locking or read-only gating (that's M3).

**Architecture:** An in-memory participant registry per session (ephemeral, never persisted), shared under `SessionManager`'s existing `RLock`. Liveness via HTTP `heartbeat`/`focus`/`leave` (the WS stays a download-only pipe, reusing the M1 `_emit` bridge to broadcast a full `presence` snapshot on any change). Frontend gains a `participant_id`+name+color identity (localStorage), a heartbeat loop, focus calls on cell select, and presence UI (per-cell badge in the reserved CategoryRow slot + a header roster).

**Tech Stack:** FastAPI (sync route handlers + `app.state.loop` bridge), in-memory dict registry with injectable clock, React + Zustand v5, vitest.

**Spec:** `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` (§5–§9, §12 M2 bullet, §13). This plan implements **only M2**. The M2↔M3 seam is load-bearing (see "Seam discipline" below).

**Branch:** work directly on `po_overhaul`; push at end of the round (no feature worktree).

---

## Seam discipline (M2 vs M3) — read before coding

Spec §12: in **M2**, `focus` only records `focused_cell` for presence. There is **NO exclusivity**, the `mode` field is **not load-bearing**, and **no UI acts on it**. Concretely, for M2:

- `focus` always succeeds; the registry never denies a cell or computes "who is the editor".
- The `presence` event carries `focused_cell` and a `mode` field fixed to `"editor"` (placeholder; M3 makes it meaningful). The frontend renders the badge from `focused_cell` and **ignores `mode`**.
- Write endpoints do **not** take `participant_id` and do **not** check locks (M3).
- The scanner does **not** skip cells (M3).
- **Claude presence is deferred to M3** (it's tied to claim-on-write / per-cell-active, which is M3). The registry supports `kind="agent"` for forward-compat, but nothing wires Claude in M2.

Keeping these out of M2 is the point — do not add them "while we're here".

## File structure

**Backend (new):**
- `api/presence.py` — `PresenceRegistry`: pure in-memory logic + injectable clock. Single responsibility: participant lifecycle (join/renew, focus, leave, expire, snapshot).
- `api/routes/presence.py` — 3 HTTP endpoints; broadcasts `presence` on change.
- `tests/unit/api/test_presence_registry.py`, `tests/unit/api/test_presence_endpoints.py`, `tests/integration/test_presence_two_participants.py`.

**Backend (modified):**
- `api/routes/ws.py` — move the `_emit` bridge here (it belongs next to `broadcast`); re-export usage.
- `api/routes/sessions.py` — import `_emit` from `ws` instead of defining it (mechanical).
- `api/state.py` — `SessionManager` gains a `PresenceRegistry` member + synchronized pass-through methods.
- `api/main.py` — register the presence router.

**Frontend (new):**
- `frontend/src/lib/identity.js` — participant_id + name + color in localStorage (pure, testable).
- `frontend/src/lib/presence.js` — pure selectors (`participantsInCell`, `rosterParticipants`, `initials`).
- `frontend/src/components/IdentityDialog.jsx` — first-run name+color prompt (uses `ui/Dialog`).
- `frontend/src/components/PresenceBadge.jsx` — colored avatar (initials + name tooltip).
- `frontend/src/components/PresenceRoster.jsx` — stacked avatars of connected participants.
- vitest: `identity.test.js`, `presence.test.js`, `store/session.presence.test.js`.

**Frontend (modified):**
- `frontend/src/lib/api.js` — `presenceHeartbeat`/`presenceFocus`/`presenceLeave`.
- `frontend/src/store/session.js` — `presence` state, `presence` WS case, heartbeat loop + focus + leave wiring in `openMonth`.
- `frontend/src/App.jsx` — mount `IdentityDialog` + header `PresenceRoster`.
- `frontend/src/views/HospitalDetail.jsx` — call `setFocus(cell)` on select / `null` on back.
- `frontend/src/components/CategoryRow.jsx` — render `PresenceBadge`(s) in the reserved trailing slot.

## Constants

- `PRESENCE_TTL_SECONDS = 45` and `PRESENCE_HEARTBEAT_SECONDS = 15` — module-level in `api/presence.py` (API-layer config, not pipeline; module-level per convention). Mirror `HEARTBEAT_MS = 15000` in `frontend/src/lib/identity.js`.

---

## Chunk 1: Backend — PresenceRegistry + SessionManager integration

### Task 1: PresenceRegistry — join/renew + snapshot

**Files:**
- Create: `api/presence.py`
- Test: `tests/unit/api/test_presence_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_presence_registry.py
from api.presence import PresenceRegistry

def test_heartbeat_creates_participant_and_snapshot_lists_it():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    changed = reg.heartbeat("2026-04", "p1", name="Daniel", color="#e5484d")
    assert changed is True  # join is a change
    snap = reg.snapshot("2026-04")
    assert len(snap) == 1
    assert snap[0]["participant_id"] == "p1"
    assert snap[0]["name"] == "Daniel"
    assert snap[0]["color"] == "#e5484d"
    assert snap[0]["kind"] == "human"
    assert snap[0]["focused_cell"] is None
    assert "expires_at" not in snap[0]  # internal field, not exposed

def test_heartbeat_renew_without_change_returns_false():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="Daniel", color="#e5484d")
    clock[0] = 1005.0
    changed = reg.heartbeat("2026-04", "p1", name="Daniel", color="#e5484d")
    assert changed is False  # pure renew, no roster change → no broadcast
```

- [ ] **Step 2: Run, verify it fails** — `pytest tests/unit/api/test_presence_registry.py -v` → FAIL (no module).

- [ ] **Step 3: Implement `api/presence.py`**

```python
"""In-memory participant registry for multiplayer presence (M2).

Ephemeral collaboration state — NEVER persisted to the session blob (spec §9).
Pure logic + injectable clock; thread-safety is the caller's job (SessionManager
serializes every call under its RLock, spec §6.1).

M2 seam: `focus` only records `focused_cell` for presence. There is no exclusivity
and `mode` is a non-load-bearing placeholder ("editor"); the hard lock / editor
arbitration is M3. Do not add enforcement here.
"""
from __future__ import annotations

import time
from collections.abc import Callable

PRESENCE_TTL_SECONDS = 45.0
PRESENCE_HEARTBEAT_SECONDS = 15.0

# Fields exposed in the presence snapshot (the `expires_at` lease is internal).
_PUBLIC_FIELDS = ("participant_id", "name", "color", "kind", "focused_cell", "mode")


class PresenceRegistry:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        # session_id -> participant_id -> record
        self._participants: dict[str, dict[str, dict]] = {}

    def heartbeat(
        self, session_id: str, participant_id: str, *, name: str, color: str,
        kind: str = "human",
    ) -> bool:
        """Create (join) or renew a participant's lease. Returns True iff the
        roster changed (join, or expiry purge happened) → caller should broadcast."""
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        existing = members.get(participant_id)
        if existing is None:
            members[participant_id] = {
                "participant_id": participant_id,
                "name": name,
                "color": color,
                "kind": kind,
                "focused_cell": None,
                "mode": "editor",  # M2 placeholder; not load-bearing until M3
                "expires_at": self._now() + PRESENCE_TTL_SECONDS,
            }
            return True
        # Renew lease; name/color refresh is allowed but not a "roster change"
        # unless it actually differs.
        existing["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if existing["name"] != name or existing["color"] != color:
            existing["name"] = name
            existing["color"] = color
            return True
        return changed

    def focus(self, session_id: str, participant_id: str, cell: str | None) -> bool:
        """Record the participant's focused cell (M2: presence only, no claim).
        Returns True iff something changed."""
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        rec = members.get(participant_id)
        if rec is None:
            # focus before heartbeat shouldn't happen, but be forgiving: ignore.
            return changed
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if rec["focused_cell"] != cell:
            rec["focused_cell"] = cell
            return True
        return changed

    def leave(self, session_id: str, participant_id: str) -> bool:
        changed = self._purge_expired(session_id)
        members = self._participants.get(session_id, {})
        if participant_id in members:
            del members[participant_id]
            return True
        return changed

    def snapshot(self, session_id: str) -> list[dict]:
        self._purge_expired(session_id)
        members = self._participants.get(session_id, {})
        return [
            {k: rec[k] for k in _PUBLIC_FIELDS}
            for rec in members.values()
        ]

    def _purge_expired(self, session_id: str) -> bool:
        members = self._participants.get(session_id)
        if not members:
            return False
        now = self._now()
        dead = [pid for pid, r in members.items() if r["expires_at"] <= now]
        for pid in dead:
            del members[pid]
        return bool(dead)
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/unit/api/test_presence_registry.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add api/presence.py tests/unit/api/test_presence_registry.py && git commit -m "feat(multiplayer): PresenceRegistry join/renew + snapshot (M2)"`

### Task 2: PresenceRegistry — focus, leave, lease expiry

**Files:**
- Modify: `tests/unit/api/test_presence_registry.py`

- [ ] **Step 1: Add failing tests**

```python
def test_focus_sets_focused_cell_and_is_a_change():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="Daniel", color="#x")
    assert reg.focus("2026-04", "p1", "HRB|odi") is True
    assert reg.snapshot("2026-04")[0]["focused_cell"] == "HRB|odi"
    # focus to the same cell again → no change
    assert reg.focus("2026-04", "p1", "HRB|odi") is False
    # focus(None) = back to month/hospital view
    assert reg.focus("2026-04", "p1", None) is True
    assert reg.snapshot("2026-04")[0]["focused_cell"] is None

def test_leave_removes_participant():
    reg = PresenceRegistry(now=lambda: 1000.0)
    reg.heartbeat("2026-04", "p1", name="D", color="#x")
    assert reg.leave("2026-04", "p1") is True
    assert reg.snapshot("2026-04") == []
    assert reg.leave("2026-04", "p1") is False  # already gone

def test_expired_lease_is_purged_on_access():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="D", color="#x")
    reg.heartbeat("2026-04", "p2", name="C", color="#y")
    clock[0] = 1000.0 + 46.0  # both leases (TTL 45s) now expired
    # snapshot purges; a fresh heartbeat from p1 re-joins it (change=True)
    assert reg.snapshot("2026-04") == []
    assert reg.heartbeat("2026-04", "p1", name="D", color="#x") is True

def test_one_participants_expiry_is_a_change_for_others():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="D", color="#x")
    clock[0] = 1020.0
    reg.heartbeat("2026-04", "p2", name="C", color="#y")  # p2 lease to 1065
    clock[0] = 1050.0  # p1 (exp 1045) dead, p2 alive
    changed = reg.heartbeat("2026-04", "p2", name="C", color="#y")
    assert changed is True  # p1 purged → roster changed
    assert {p["participant_id"] for p in reg.snapshot("2026-04")} == {"p2"}
```

- [ ] **Step 2: Run** → the focus/leave/expiry tests pass with the Task 1 implementation (verify): `pytest tests/unit/api/test_presence_registry.py -v` → PASS. (If any fails, fix `presence.py` minimally.)

- [ ] **Step 3: Commit** — `git commit -am "test(multiplayer): PresenceRegistry focus/leave/expiry (M2)"`

### Task 3: SessionManager presence pass-throughs (shared RLock)

**Files:**
- Modify: `api/state.py` (`SessionManager.__init__` ~L94-96; append methods after `finalize` ~L674)
- Test: `tests/unit/api/test_presence_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_presence_manager.py
from api.state import SessionManager

def test_manager_presence_roundtrip(tmp_path):
    from core.db.connection import open_connection
    from core.db.migrations import init_schema
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    assert mgr.presence_heartbeat("2026-04", "p1", name="D", color="#x") is True
    assert mgr.presence_focus("2026-04", "p1", "HRB|odi") is True
    snap = mgr.presence_snapshot("2026-04")
    assert snap[0]["focused_cell"] == "HRB|odi"
    assert mgr.presence_leave("2026-04", "p1") is True
    assert mgr.presence_snapshot("2026-04") == []
```

- [ ] **Step 2: Run, verify fail** → `pytest tests/unit/api/test_presence_manager.py -v` → FAIL (no method).

- [ ] **Step 3: Implement** — in `SessionManager.__init__`, after `self._lock = ...`, add:

```python
        from api.presence import PresenceRegistry
        self._presence = PresenceRegistry()
```

Append synchronized pass-throughs. **The file's setters all use the `@_synchronized` decorator** (defined at `api/state.py:84-88`; applied at `:99`, `:132`, etc.) — use it here too (it acquires `self._lock`, which is the shared RLock). Do **not** use explicit `with self._lock:` — match the file's universal convention:

```python
    # ── Presence (M2) — ephemeral, shares this manager's RLock (spec §6.1) ──
    @_synchronized
    def presence_heartbeat(self, session_id, participant_id, *, name, color, kind="human"):
        return self._presence.heartbeat(
            session_id, participant_id, name=name, color=color, kind=kind)

    @_synchronized
    def presence_focus(self, session_id, participant_id, cell):
        return self._presence.focus(session_id, participant_id, cell)

    @_synchronized
    def presence_leave(self, session_id, participant_id):
        return self._presence.leave(session_id, participant_id)

    @_synchronized
    def presence_snapshot(self, session_id):
        return self._presence.snapshot(session_id)
```

- [ ] **Step 4: Run, verify pass** → PASS.

- [ ] **Step 5: Commit** — `git add api/state.py tests/unit/api/test_presence_manager.py && git commit -m "feat(multiplayer): SessionManager presence methods under shared RLock (M2)"`

> **Chunk 1 review:** dispatch plan-document-reviewer + run `pytest tests/unit/api/test_presence*.py -v` and `ruff check api/presence.py api/state.py`. All green before Chunk 2.

---

## Chunk 2: Backend — presence endpoints + broadcast

### Task 4: Extract shared helpers (`_emit` → ws.py, `_validate_session_id`) for reuse by presence

> Two shared helpers the presence router needs. Today: `_emit` is defined in `sessions.py:~503`; session-id validation is **inline everywhere** via the module-level regex `_SESSION_ID_RE` (`sessions.py:42`) — there is **no** `_validate_session_id` callable. Both must be made importable.

**Files:**
- Modify: `api/routes/ws.py` (add `_emit`), `api/routes/sessions.py` (extract `_validate_session_id`; import `_emit` from ws)

- [ ] **Step 1:** Move the `_emit` function verbatim from `sessions.py` into `ws.py` (it belongs next to `broadcast`). `ws.py` needs `import asyncio` and `from fastapi import Request` (add if absent). In `sessions.py`, delete the local def and add `from api.routes.ws import _emit` next to the existing `broadcast` import. Keep all call sites unchanged.
- [ ] **Step 2:** In `sessions.py`, add a tiny helper next to `_SESSION_ID_RE`:

```python
from fastapi import HTTPException  # already imported; reuse

def _validate_session_id(session_id: str) -> None:
    """Raise 400 if session_id is not a valid YYYY-MM (format check, before any
    DB lookup). Shared by the session and presence routers."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="invalid session_id (expected YYYY-MM)")
```

Then **replace the inline `if not _SESSION_ID_RE.match(...): raise HTTPException(400, ...)` checks** in the existing session endpoints with `_validate_session_id(session_id)` (mechanical; preserves behavior — keep the format check BEFORE the DB/404 lookup at every call site). Match the existing 400 detail string if it differs.

- [ ] **Step 3:** Run the existing suite to prove no regression: `pytest tests/ -k "scan or worker or override or reorg or output or session" -q` → all PASS (M1 broadcasts still fire; 400s unchanged).
- [ ] **Step 4: Commit** — `git commit -am "refactor(multiplayer): extract _emit (→ws.py) + _validate_session_id for presence reuse"`

### Task 5: Presence endpoints + broadcast on change

**Files:**
- Create: `api/routes/presence.py`
- Modify: `api/main.py` (import + `include_router`)
- Test: `tests/unit/api/test_presence_endpoints.py`

- [ ] **Step 1: Write the failing test** (use the app's TestClient WITH `with` so `app.state.loop` is set and broadcasts don't no-op — mirror existing WS-aware tests):

```python
# tests/unit/api/test_presence_endpoints.py
from fastapi.testclient import TestClient
from api.main import create_app

def _client():
    return TestClient(create_app())

def test_heartbeat_returns_snapshot_and_join_broadcasts():
    with _client() as c:
        # open a real session first (presence is per existing session id)
        c.post("/api/sessions", json={"session_id": "2026-04"})
        r = c.post("/api/sessions/2026-04/presence/heartbeat",
                   json={"participant_id": "p1", "name": "Daniel", "color": "#e5484d"})
        assert r.status_code == 200
        body = r.json()
        assert body["participants"][0]["participant_id"] == "p1"

def test_focus_then_snapshot_reflects_cell():
    with _client() as c:
        c.post("/api/sessions", json={"session_id": "2026-04"})
        c.post("/api/sessions/2026-04/presence/heartbeat",
               json={"participant_id": "p1", "name": "D", "color": "#x"})
        c.post("/api/sessions/2026-04/presence/focus",
               json={"participant_id": "p1", "cell": "HRB|odi"})
        r = c.post("/api/sessions/2026-04/presence/heartbeat",
                   json={"participant_id": "p1", "name": "D", "color": "#x"})
        me = next(p for p in r.json()["participants"] if p["participant_id"] == "p1")
        assert me["focused_cell"] == "HRB|odi"

def test_bad_session_id_400():
    with _client() as c:
        r = c.post("/api/sessions/not-a-month/presence/heartbeat",
                   json={"participant_id": "p1", "name": "D", "color": "#x"})
        assert r.status_code == 400
```

- [ ] **Step 2: Run, verify fail** → FAIL (404, no route).

- [ ] **Step 3: Implement `api/routes/presence.py`** (reuse the session-id validator and `get_manager` Depends from `sessions.py`; reuse `_emit` from `ws.py`). The presence event is the full snapshot; broadcast only when the manager reports a change:

```python
"""Presence endpoints (multiplayer M2). HTTP up-channel; WS carries the `presence`
snapshot down. No locking/enforcement here — that is M3 (spec §6.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.routes.sessions import _validate_session_id, get_manager  # reuse helpers
from api.routes.ws import _emit
from api.state import SessionManager

router = APIRouter()


class HeartbeatBody(BaseModel):
    participant_id: str
    name: str
    color: str


class FocusBody(BaseModel):
    participant_id: str
    cell: str | None = None


class LeaveBody(BaseModel):
    participant_id: str


def _presence_event(session_id: str, mgr: SessionManager) -> dict:
    return {"type": "presence", "session_id": session_id,
            "participants": mgr.presence_snapshot(session_id)}


@router.post("/sessions/{session_id}/presence/heartbeat")
def heartbeat(session_id: str, body: HeartbeatBody, request: Request,
              mgr: SessionManager = Depends(get_manager)):
    _validate_session_id(session_id)
    changed = mgr.presence_heartbeat(
        session_id, body.participant_id, name=body.name, color=body.color)
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event  # always return the snapshot in the HTTP body (spec §6.2)


@router.post("/sessions/{session_id}/presence/focus")
def focus(session_id: str, body: FocusBody, request: Request,
          mgr: SessionManager = Depends(get_manager)):
    _validate_session_id(session_id)
    changed = mgr.presence_focus(session_id, body.participant_id, body.cell)
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event


@router.post("/sessions/{session_id}/presence/leave")
def leave(session_id: str, body: LeaveBody, request: Request,
          mgr: SessionManager = Depends(get_manager)):
    _validate_session_id(session_id)
    changed = mgr.presence_leave(session_id, body.participant_id)
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event
```

In `api/main.py`: add `presence` to the `from api.routes import ...` line (`main.py:14`) and `app.include_router(presence.router, prefix="/api")` after the other routers and **before** the StaticFiles mount (`main.py:~76`). `_validate_session_id` and `_emit` are both importable thanks to Task 4.

- [ ] **Step 4: Run, verify pass** → `pytest tests/unit/api/test_presence_endpoints.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add api/routes/presence.py api/main.py tests/unit/api/test_presence_endpoints.py && git commit -m "feat(multiplayer): presence heartbeat/focus/leave endpoints + presence broadcast (M2)"`

### Task 6: Two-participant integration test (no browser)

**Files:**
- Create: `tests/integration/test_presence_two_participants.py`

- [ ] **Step 1: Write the test** — two participant_ids hit the API; assert each sees the other in the snapshot and focus is reflected.

```python
from fastapi.testclient import TestClient
from api.main import create_app

def test_two_participants_see_each_other():
    with TestClient(create_app()) as c:
        c.post("/api/sessions", json={"session_id": "2026-04"})
        c.post("/api/sessions/2026-04/presence/heartbeat",
               json={"participant_id": "p1", "name": "Daniel", "color": "#a"})
        r = c.post("/api/sessions/2026-04/presence/heartbeat",
                   json={"participant_id": "p2", "name": "Carla", "color": "#b"})
        ids = {p["participant_id"] for p in r.json()["participants"]}
        assert ids == {"p1", "p2"}
        c.post("/api/sessions/2026-04/presence/focus",
               json={"participant_id": "p2", "cell": "HRB|odi"})
        r = c.post("/api/sessions/2026-04/presence/heartbeat",
                   json={"participant_id": "p1", "name": "Daniel", "color": "#a"})
        carla = next(p for p in r.json()["participants"] if p["participant_id"] == "p2")
        assert carla["focused_cell"] == "HRB|odi"
        # p2 leaves → p1 no longer sees it
        c.post("/api/sessions/2026-04/presence/leave", json={"participant_id": "p2"})
        r = c.post("/api/sessions/2026-04/presence/heartbeat",
                   json={"participant_id": "p1", "name": "Daniel", "color": "#a"})
        assert {p["participant_id"] for p in r.json()["participants"]} == {"p1"}
```

- [ ] **Step 2: Run** → PASS.
- [ ] **Step 3:** `ruff check api/ tests/` → 0 violations.
- [ ] **Step 4: Commit** — `git add tests/integration/test_presence_two_participants.py && git commit -m "test(multiplayer): two-participant presence integration (M2)"`

> **Chunk 2 review:** plan-document-reviewer + full `pytest tests/ -q` (no regressions) + `ruff check .`.

---

## Chunk 3: Frontend — identity, store wiring, API, pure selectors

### Task 7: Identity (participant_id + name + color in localStorage)

**Files:**
- Create: `frontend/src/lib/identity.js`, `frontend/src/lib/identity.test.js`

- [ ] **Step 1: Write failing tests** (`// @vitest-environment jsdom` for localStorage):

```js
// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { getParticipantId, getIdentity, setIdentity, COLORS, pickColor } from "./identity";

describe("identity", () => {
  beforeEach(() => localStorage.clear());

  it("getParticipantId mints once and is stable", () => {
    const a = getParticipantId();
    const b = getParticipantId();
    expect(a).toBe(b);
    expect(a).toMatch(/.{8,}/);
  });

  it("getIdentity is null until set", () => {
    expect(getIdentity()).toBeNull();
  });

  it("setIdentity persists name+color and getIdentity returns them", () => {
    setIdentity({ name: "Daniel", color: COLORS[0] });
    const id = getIdentity();
    expect(id.name).toBe("Daniel");
    expect(id.color).toBe(COLORS[0]);
    expect(id.participant_id).toBe(getParticipantId());
  });

  it("pickColor returns a palette color deterministically by seed", () => {
    expect(COLORS).toContain(pickColor("p1"));
    expect(pickColor("p1")).toBe(pickColor("p1"));
  });
});
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `identity.js`** — `participant_id` via `crypto.randomUUID()` stored at `po_participant_id`; identity `{name,color}` at `po_identity` (JSON); `COLORS` a small distinct palette; `pickColor(seed)` hashes seed → palette index; export `HEARTBEAT_MS = 15000`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git add frontend/src/lib/identity.js frontend/src/lib/identity.test.js && git commit -m "feat(multiplayer): participant identity (id+name+color) in localStorage (M2)"`

### Task 8: Pure presence selectors

**Files:**
- Create: `frontend/src/lib/presence.js`, `frontend/src/lib/presence.test.js`

- [ ] **Step 1: Write failing tests** (node env):

```js
import { describe, it, expect } from "vitest";
import { participantsInCell, rosterParticipants, initials } from "./presence";

const ps = [
  { participant_id: "p1", name: "Daniel", color: "#a", focused_cell: "HRB|odi" },
  { participant_id: "p2", name: "Carla Soto", color: "#b", focused_cell: "HRB|odi" },
  { participant_id: "p3", name: "X", color: "#c", focused_cell: null },
];

it("participantsInCell filters by hospital|sigla, excluding self", () => {
  const res = participantsInCell(ps, "HRB", "odi", "p1");
  expect(res.map((p) => p.participant_id)).toEqual(["p2"]);
});
it("participantsInCell returns [] for an empty/absent list", () => {
  expect(participantsInCell(undefined, "HRB", "odi", "p1")).toEqual([]);
});
it("rosterParticipants returns everyone (incl. self)", () => {
  expect(rosterParticipants(ps).length).toBe(3);
});
it("initials takes up to two words, uppercased", () => {
  expect(initials("Carla Soto")).toBe("CS");
  expect(initials("Daniel")).toBe("D");
  expect(initials("")).toBe("?");
});
```

- [ ] **Step 2–4:** implement `presence.js` (guard `?? []`, build `${hospital}|${sigla}` key, exclude `selfId`), run, pass.
- [ ] **Step 5: Commit** — `git commit -am "feat(multiplayer): pure presence selectors (M2)"`

### Task 9: API client methods

**Files:**
- Modify: `frontend/src/lib/api.js`

- [ ] **Step 1:** Add `presenceHeartbeat(sessionId, body)`, `presenceFocus(sessionId, body)`, `presenceLeave(sessionId, body)` — POST JSON to the three endpoints, mirroring existing `api.*` methods (use the same base + fetch helper). `presenceLeave` should also expose a `beaconLeave(sessionId, body)` variant using `navigator.sendBeacon` for unload.
- [ ] **Step 2:** No standalone test (thin wrappers); covered by the store test (Task 10). `npm run build` must still pass.
- [ ] **Step 3: Commit** — `git commit -am "feat(multiplayer): presence API client methods (M2)"`

### Task 10: Store — presence state, WS case, heartbeat/focus/leave lifecycle

**Files:**
- Modify: `frontend/src/store/session.js`
- Test: `frontend/src/store/session.presence.test.js`

- [ ] **Step 1: Write failing tests** (`// @vitest-environment jsdom`; mock `../lib/api` + `../lib/ws` like `session.visibility.test.js`):
  - `_handleWSEvent({type:"presence", participants:[...]})` sets `state.presence` to that array.
  - `openMonth` seeds `presence` from the heartbeat response and starts an interval (assert `api.presenceHeartbeat` called; use `vi.useFakeTimers()` to advance `HEARTBEAT_MS` and assert a 2nd call).
  - `setFocus(cell)` calls `api.presenceFocus` with `{participant_id, cell}`.
  - re-`openMonth` clears the previous interval (no double heartbeats).

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** in `session.js`:
  - Add `presence: []` to initial state, plus `_heartbeat: null` (interval handle) and `_unloadHandler: null` (pagehide listener ref).
  - In `_handleWSEvent`, add `case "presence": set({ presence: event.participants ?? [] }); break;`.
  - Add a single **`startPresence()`** action (the one heartbeat code path, called from BOTH `openMonth` and the identity dialog):

    ```js
    startPresence: () => {
      const { session, _heartbeat } = get();
      const id = getIdentity();
      if (!session || !id) return;            // no month open or not named yet → off
      if (_heartbeat) clearInterval(_heartbeat); // idempotent: never double-start
      const sid = session.session_id;
      const beat = () =>
        api.presenceHeartbeat(sid, { participant_id: id.participant_id, name: id.name, color: id.color })
           .then((r) => set({ presence: r.participants ?? [] }))
           .catch(() => {});
      beat();                                  // immediate join
      const handle = setInterval(beat, HEARTBEAT_MS);
      set({ _heartbeat: handle });
    },
    ```

  - In `openMonth`: after the session is set, clear any previous `_heartbeat` (mirror the existing `_ws`/`_visHandler` cleanup), then call `get().startPresence()`. Register a `pagehide` listener → `api.beaconLeave(sid, {participant_id})`, store it as `_unloadHandler`, and remove the previous one on re-`openMonth` (exactly like `_visHandler`). Reset `presence: []` on month switch.
  - Add `setFocus: (cell) => { const { session } = get(); const id = getIdentity(); if (id && session) api.presenceFocus(session.session_id, { participant_id: id.participant_id, cell }); }` and `leavePresence: () => { const { session, _heartbeat } = get(); const id = getIdentity(); if (_heartbeat) clearInterval(_heartbeat); if (id && session) api.presenceLeave(session.session_id, { participant_id: id.participant_id }); set({ _heartbeat: null }); }`.
  - **Guard:** `startPresence`/`setFocus` no-op when `getIdentity()` is null (user hasn't named themselves) — presence stays off until Task 12's dialog calls `startPresence()` after `setIdentity`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git add frontend/src/store/session.js frontend/src/store/session.presence.test.js && git commit -m "feat(multiplayer): store presence state + heartbeat/focus/leave lifecycle (M2)"`

> **Chunk 3 review:** plan-document-reviewer + `npx vitest run` (all green) + `npm run build`.

---

## Chunk 4: Frontend — presence UI

### Task 11: PresenceBadge + PresenceRoster

**Files:**
- Create: `frontend/src/components/PresenceBadge.jsx`, `frontend/src/components/PresenceRoster.jsx`

- [ ] **Step 1:** `PresenceBadge({ participant, size })` — a round avatar: `participant.color` background, white `initials(participant.name)`, wrapped in `ui/Tooltip` showing the full name. Use `po-*` tokens for borders/ring; no raw palette classes. Sizes `sm` (cell badge) / `md` (roster).
- [ ] **Step 2:** `PresenceRoster()` — reads `presence` from the store via `rosterParticipants`, renders overlapping `PresenceBadge`s (md). Empty list → renders nothing.
- [ ] **Step 3:** No render test infra dependency — keep logic in the tested `presence.js`; these are presentational. `npm run build` passes.
- [ ] **Step 4: Commit** — `git commit -am "feat(multiplayer): PresenceBadge + PresenceRoster components (M2)"`

### Task 12: Wire identity dialog + roster into App

**Files:**
- Create: `frontend/src/components/IdentityDialog.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1:** `IdentityDialog` (uses `ui/Dialog`) — opens when `getIdentity()` is null. Fields: name (text, required, trimmed, min 1 char) + color (swatches from `COLORS`, default `pickColor(getParticipantId())`). On submit → `setIdentity({name, color})`, close, then call the store's **`startPresence()`** action (the single heartbeat path from Task 10 — handles the "month already open, identity just set now" case by starting the heartbeat that `openMonth` skipped). Spanish-neutral microcopy ("¿Cómo te llamas?", "Elige un color", "Entrar"). Friendly for a non-technical user (Carla).
- [ ] **Step 2:** In `App.jsx`, render `<IdentityDialog />` (self-gating on missing identity) and add `<PresenceRoster />` to the header (right side).
- [ ] **Step 3:** `npm run build` passes; manual check that the dialog appears on first load (no identity) and not after.
- [ ] **Step 4: Commit** — `git commit -am "feat(multiplayer): identity dialog + header roster (M2)"`

### Task 13: Per-cell badge in CategoryRow + focus wiring

**Files:**
- Modify: `frontend/src/components/CategoryRow.jsx`, `frontend/src/views/HospitalDetail.jsx`

- [ ] **Step 1:** In `HospitalDetail`, keep store focus in sync with the **local `selected` state** (don't try to intercept `setSelected`, which is passed down as `onSelect` to `CategoryGroup`). Add:

```jsx
const setFocus = useSessionStore((s) => s.setFocus);
useEffect(() => {
  setFocus(selected ? `${hospital}|${selected}` : null);
  return () => setFocus(null); // clear on unmount / hospital change
}, [hospital, selected, setFocus]);
```

This fires whenever the selected sigla changes (so the badge moves cell-to-cell within a hospital, not just on leave) and clears focus when leaving the hospital view (`onBack` unmounts → cleanup runs).
- [ ] **Step 2:** In `CategoryRow`, read `presence` from the store + `getParticipantId()`; compute `participantsInCell(presence, hospital, sigla, selfId)`; render their `PresenceBadge`(sm) in the **reserved trailing slot** (the comment block at L61-64 — "space reserved for a future 'user working here' chip"). Keep it left of / alongside the count without disturbing the existing layout.
- [ ] **Step 3:** `npm run build` passes.
- [ ] **Step 4: Commit** — `git commit -am "feat(multiplayer): per-cell presence badge + focus wiring (M2)"`

> **Chunk 4 review:** plan-document-reviewer + `npx vitest run` + `npm run build` + `ruff check .`. Then the holistic cross-chunk review.

---

## Final verification (before declaring done)

- [ ] `pytest tests/ -q` — full backend suite green (no regression to M1/scan/reorg/output).
- [ ] `npx vitest run` — all green incl. new identity/presence/store tests.
- [ ] `npm run build` — OK; rebuild `frontend/dist` so the LAN server serves M2.
- [ ] `ruff check .` — 0 violations.
- [ ] **Live LAN smoke (manual, two machines):** Daniel + a second device open the same month. Each sees the other's badge in the roster; opening a cell shows the other's badge on that category row; closing the tab removes them within ~45 s (lease) or instantly (`leave` beacon). **No locking/read-only behavior** (that's M3) — both can still edit freely. Drive via a separate Brave `--remote-debugging-port=9222` instance for one client if useful.
- [ ] Single-user regression: with one participant, the app behaves exactly as before.

## Out of scope (M3, do not build here)

Hard locks, `mode`-driven read-only gating, `participant_id` on write endpoints, 409 on contested writes, scanner cell-skipping (`cell_skipped`/`scan_complete.skipped`), Claude as a per-cell-active participant. The registry's `kind="agent"` and `mode` field exist only as forward-compat placeholders.
