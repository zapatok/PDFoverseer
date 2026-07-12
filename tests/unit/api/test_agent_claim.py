"""Tests for M3b Chunk 1: Claude agent identity + agent_focus / agent_claim_cell / agent_leave."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from api.presence import (
    AGENT_KIND,
    AGENT_NAME,
    AGENT_PARTICIPANT_ID,
    PresenceRegistry,
    is_agent,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _reg():
    return PresenceRegistry(now=lambda: 1000.0)


# Presence is fully in-memory (keyed by session_id string); these tests do NOT
# open a DB session — matching the idiom in test_presence_locks.py.


# ── Task 1: PresenceRegistry ──────────────────────────────────────────────────


def test_is_agent():
    assert is_agent(AGENT_PARTICIPANT_ID)
    assert not is_agent("some-uuid")
    assert not is_agent(None)


def test_agent_focus_registers_and_claims_free_cell():
    r = _reg()
    changed = r.agent_focus("m", "HRB|odi")
    assert changed is True
    rec = next(p for p in r.snapshot("m") if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert rec["name"] == AGENT_NAME
    assert rec["kind"] == AGENT_KIND
    assert rec["focused_cell"] == "HRB|odi"
    assert rec["mode"] == "editor"


def test_agent_focus_on_human_held_cell_makes_agent_viewer():
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")  # human editor
    r.agent_focus("m", "HRB|odi")  # agent joins -> viewer (does NOT steal)
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p1"]["mode"] == "editor"
    assert snap[AGENT_PARTICIPANT_ID]["mode"] == "viewer"


def test_agent_focus_none_releases():
    r = _reg()
    r.agent_focus("m", "HRB|odi")
    r.agent_focus("m", None)
    assert r.lock_holder("m", "HRB|odi", exclude="p9") is None


def test_agent_focus_moving_between_cells_frees_the_previous():
    """The scanner (Chunk 3) claims one cell at a time then moves to the next; the
    previously claimed cell must become free when the agent's focus moves."""
    r = _reg()
    r.agent_focus("m", "HRB|odi")
    r.agent_focus("m", "HRB|art")  # move to next cell
    assert r.lock_holder("m", "HRB|odi", exclude="p9") is None  # previous freed
    holder = r.lock_holder("m", "HRB|art", exclude="p9")
    assert holder is not None and holder["participant_id"] == AGENT_PARTICIPANT_ID


def test_agent_focus_returns_true_on_change_false_on_noop():
    r = _reg()
    assert r.agent_focus("m", "HRB|odi") is True  # new registration
    # Same cell, same mode, no TTL expirations — lease refreshed but roster unchanged.
    assert r.agent_focus("m", "HRB|odi") is False


def test_agent_focus_kind_survives_snapshot():
    """The `kind` field must survive the _PUBLIC_FIELDS projection."""
    r = _reg()
    r.agent_focus("m", "HRB|odi")
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap[AGENT_PARTICIPANT_ID]["kind"] == AGENT_KIND


# ── Task 2: SessionManager ────────────────────────────────────────────────────


def test_agent_claim_free_cell_returns_none(tmp_path, make_manager):
    mgr = make_manager
    result = mgr.agent_claim_cell("2026-04", "HRB", "odi")
    assert result is None


def test_agent_claim_free_cell_makes_agent_editor(tmp_path, make_manager):
    mgr = make_manager
    mgr.agent_claim_cell("2026-04", "HRB", "odi")
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is not None
    assert holder["participant_id"] == AGENT_PARTICIPANT_ID
    assert holder["kind"] == AGENT_KIND


def test_agent_claim_human_held_cell_returns_holder(tmp_path, make_manager):
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")  # human editor
    holder = mgr.agent_claim_cell("2026-04", "HRB", "odi")
    assert holder is not None
    assert holder["participant_id"] == "p1"


def test_agent_claim_human_held_cell_does_not_make_agent_editor(tmp_path, make_manager):
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    mgr.agent_claim_cell("2026-04", "HRB", "odi")
    # Human must still be the editor (not claude)
    snap = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert snap["p1"]["mode"] == "editor"
    # Claim was skipped (agent_claim_cell returned early before agent_focus), so the
    # agent must not be in the roster at all — a hard assert documents that contract.
    assert AGENT_PARTICIPANT_ID not in snap


def test_agent_leave_removes_agent(tmp_path, make_manager):
    mgr = make_manager
    mgr.agent_claim_cell("2026-04", "HRB", "odi")
    # agent should be in the roster
    snap_before = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert AGENT_PARTICIPANT_ID in snap_before
    mgr.agent_leave("2026-04")
    snap_after = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert AGENT_PARTICIPANT_ID not in snap_after


def test_atomic_claim_two_agents_same_free_cell(tmp_path, make_manager):
    """Two concurrent agent_claim_cell on same free cell: both return None (same agent).
    The cell must end up with exactly claude as editor."""
    mgr = make_manager

    results = []
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait()
        results.append(mgr.agent_claim_cell("2026-04", "HRB", "odi"))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Both calls return None (same agent, no conflict)
    assert all(r is None for r in results)
    # Claude must be the editor exactly once
    snap = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert snap[AGENT_PARTICIPANT_ID]["mode"] == "editor"
    # At-most-one editor invariant
    editors = [p for p in snap.values() if p["mode"] == "editor"]
    assert len(editors) == 1


def test_atomic_claim_agent_vs_human_exactly_one_editor(tmp_path, make_manager):
    """One agent_claim_cell vs one human presence_focus on the same free cell.
    Exactly one must end up as the cell's editor."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")

    barrier = threading.Barrier(2)

    def agent_claim():
        barrier.wait()
        mgr.agent_claim_cell("2026-04", "HRB", "odi")

    def human_focus():
        barrier.wait()
        mgr.presence_focus("2026-04", "p1", "HRB|odi")

    t1 = threading.Thread(target=agent_claim)
    t2 = threading.Thread(target=human_focus)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    snap = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    editors = [p for p in snap.values() if p["focused_cell"] == "HRB|odi" and p["mode"] == "editor"]
    # At-most-one editor invariant (spec §13)
    assert len(editors) == 1


# ── Task 3: agent auto-claim on write ────────────────────────────────────────


def _make_session(mgr, tmp_path) -> str:
    """Create session 2026-04 in the DB; returns the session_id."""
    state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    return state["session_id"]


def test_agent_override_claims_free_cell(tmp_path, make_manager):
    """Agent writing to a free cell with participant_id='claude' claims it as editor."""
    mgr = make_manager
    _make_session(mgr, tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="claude")
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is not None
    assert holder["participant_id"] == AGENT_PARTICIPANT_ID
    assert holder["kind"] == AGENT_KIND


def test_agent_write_to_human_held_cell_raises(tmp_path, make_manager):
    """Agent trying to write a human-held cell gets CellLockedError (M3a path)."""
    from api.presence import CellLockedError

    mgr = make_manager
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")  # human editor
    with pytest.raises(CellLockedError):
        mgr.apply_user_override("2026-04", "HRB", "odi", value=3, participant_id="claude")


def test_human_write_free_cell_does_not_claim(tmp_path, make_manager):
    """A human write to a free cell does NOT auto-claim (only agents claim on write)."""
    mgr = make_manager
    _make_session(mgr, tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")
    # No heartbeat was issued for p1, so no presence record exists — free cell
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is None


def test_agent_set_note_claims_free_cell(tmp_path, make_manager):
    """Agent set_note on a free cell auto-claims it (pattern spans all 6 methods)."""
    mgr = make_manager
    _make_session(mgr, tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=1)  # create cell first (no participant)
    mgr.set_note(
        "2026-04", "HRB", "odi", text="check this", status="por_resolver", participant_id="claude"
    )
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is not None
    assert holder["participant_id"] == AGENT_PARTICIPANT_ID


# ── Self-lend (2026-07-10): the scan launcher's own hold is borrowed ─────────


def test_agent_claim_lend_from_holder_claims_and_demotes(tmp_path, make_manager):
    """lend_from == the holder: the launcher yields editorship — the agent claims
    (returns None), the human drops to viewer, and the agent is the editor."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")

    result = mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1")

    assert result is None
    snap = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert snap["p1"]["mode"] == "viewer"
    assert snap[AGENT_PARTICIPANT_ID]["mode"] == "editor"
    assert snap[AGENT_PARTICIPANT_ID]["focused_cell"] == "HRB|odi"


def test_agent_claim_lend_from_other_participant_still_skips(tmp_path, make_manager):
    """lend_from != the holder (Carla protection): unchanged M3b skip."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")

    holder = mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1")

    assert holder is not None
    assert holder["participant_id"] == "p2"
    snap = {p["participant_id"]: p for p in mgr.presence_snapshot("2026-04")}
    assert snap["p2"]["mode"] == "editor"
    assert AGENT_PARTICIPANT_ID not in snap


def test_agent_claim_lend_from_none_keeps_legacy_skip(tmp_path, make_manager):
    """No participant_id in the request (legacy client) → strict M3b behavior."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")

    holder = mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from=None)

    assert holder is not None
    assert holder["participant_id"] == "p1"


def test_agent_claim_lend_from_free_cell_is_plain_claim(tmp_path, make_manager):
    """lend_from on a FREE cell must not break the normal claim."""
    mgr = make_manager
    assert mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1") is None
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is not None and holder["participant_id"] == AGENT_PARTICIPANT_ID


# ── Self-lend v1.1 (2026-07-11, §B2): the lender gets editorship back ────────


def test_promote_to_editor_reinstates_lender():
    """After demote_to_viewer (the lend step), promote_to_editor flips the
    lender back to editor — the mainline scan-end path."""
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.demote_to_viewer("m", "HRB|odi", "p1")

    changed = r.promote_to_editor("m", "HRB|odi", "p1")

    assert changed is True
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p1"]["mode"] == "editor"


def test_promote_to_editor_noop_if_lender_changed_focus():
    """The lender navigated away from the cell mid-scan -> no promotion for the
    (now stale) cell they used to hold."""
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.demote_to_viewer("m", "HRB|odi", "p1")
    r.focus("m", "p1", "HRB|art")  # moved to a different (free) cell

    changed = r.promote_to_editor("m", "HRB|odi", "p1")

    assert changed is False
    assert r.lock_holder("m", "HRB|odi", exclude="x") is None


def test_promote_to_editor_noop_if_other_editor_present():
    """Another human claimed the cell while the agent held it -> the lender must
    NOT dethrone them on promotion."""
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.demote_to_viewer("m", "HRB|odi", "p1")
    r.heartbeat("m", "p2", name="Carla", color="#b")
    r.focus("m", "p2", "HRB|odi")  # Carla claims the free (agent-held) cell

    changed = r.promote_to_editor("m", "HRB|odi", "p1")

    assert changed is False
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p2"]["mode"] == "editor"
    assert snap["p1"]["mode"] == "viewer"


def test_promote_to_editor_noop_if_lender_lease_expired():
    """The lender's heartbeat lapsed (TTL) during a long scan -> no promotion of
    a participant who is no longer present."""
    clock = {"t": 1000.0}
    r = PresenceRegistry(now=lambda: clock["t"])
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.demote_to_viewer("m", "HRB|odi", "p1")
    clock["t"] += 46.0  # > PRESENCE_TTL_SECONDS (45s)

    changed = r.promote_to_editor("m", "HRB|odi", "p1")

    assert changed is False
    assert all(p["participant_id"] != "p1" for p in r.snapshot("m"))


def test_agent_claim_lend_out_appends_on_lend(tmp_path, make_manager):
    """agent_claim_cell records (hospital, sigla, lend_from) in lent_out only
    when a real lend happened (holder == lend_from)."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    lent: list = []

    result = mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1", lent_out=lent)

    assert result is None
    assert lent == [("HRB", "odi", "p1")]


def test_agent_claim_lend_out_untouched_on_free_cell(tmp_path, make_manager):
    """A plain claim on a free cell (no lend) must not append to lent_out."""
    mgr = make_manager
    lent: list = []

    mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1", lent_out=lent)

    assert lent == []


def test_agent_claim_lend_out_untouched_on_skip(tmp_path, make_manager):
    """A skip (holder != lend_from) must not append to lent_out."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    lent: list = []

    holder = mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1", lent_out=lent)

    assert holder is not None
    assert lent == []


def test_promote_lender_pass_through(tmp_path, make_manager):
    """SessionManager.promote_lender delegates to PresenceRegistry.promote_to_editor
    under the manager's lock."""
    mgr = make_manager
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    lent: list = []
    mgr.agent_claim_cell("2026-04", "HRB", "odi", lend_from="p1", lent_out=lent)
    mgr.agent_leave("2026-04")

    changed = mgr.promote_lender("2026-04", "HRB", "odi", "p1")

    assert changed is True
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x")
    assert holder is not None and holder["participant_id"] == "p1"
