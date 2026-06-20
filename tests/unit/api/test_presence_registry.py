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


def test_focus_sets_focused_cell_and_is_a_change():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="Daniel", color="#x")
    assert reg.focus("2026-04", "p1", "HRB|odi") is True
    assert reg.snapshot("2026-04")[0]["focused_cell"] == "HRB|odi"
    assert reg.focus("2026-04", "p1", "HRB|odi") is False  # same cell -> no change
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
    clock[0] = 1000.0 + 46.0  # TTL 45s -> both expired
    assert reg.snapshot("2026-04") == []
    assert reg.heartbeat("2026-04", "p1", name="D", color="#x") is True


def test_one_participants_expiry_is_a_change_for_others():
    clock = [1000.0]
    reg = PresenceRegistry(now=lambda: clock[0])
    reg.heartbeat("2026-04", "p1", name="D", color="#x")
    clock[0] = 1020.0
    reg.heartbeat("2026-04", "p2", name="C", color="#y")  # p2 lease -> 1065
    clock[0] = 1050.0  # p1 (exp 1045) dead, p2 alive
    changed = reg.heartbeat("2026-04", "p2", name="C", color="#y")
    assert changed is True  # p1 purged -> roster changed
    assert {p["participant_id"] for p in reg.snapshot("2026-04")} == {"p2"}
