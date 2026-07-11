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


def test_worker_count_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-count",
        json={"status": "en_progreso", "bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_clear_near_matches_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/near-matches/clear",
        json={"bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_dismiss_colado_unknown_key_422(client, session_with_pending_cell):
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/colado-suspects/nonexistent/dismiss",
        json={"bogus": 1},
    )
    assert r.status_code == 422, r.text


def test_reconcile_worker_marks_unknown_key_422(client, session_with_pending_cell):
    """Body validation runs before the handler, so an invalid from_file is fine —
    the 422 must come from the unknown key, not from any business-logic 404."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-marks/reconcile",
        json={"action": "discard", "from_file": "nonexistent.pdf", "bogus": 1},
    )
    assert r.status_code == 422, r.text


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


def test_create_session_unknown_key_422(client):
    """§B6: POST /sessions joins the extra=forbid surface."""
    r = client.post("/api/sessions", json={"year": 2026, "month": 4, "bogus": 1})
    assert r.status_code == 422, r.text


def test_create_session_year_out_of_range_422(client):
    """§B6: year must be in [2020, 2100] — no orphan session rows from a typo."""
    r = client.post("/api/sessions", json={"year": 99999, "month": 4})
    assert r.status_code == 422, r.text


def test_create_session_month_out_of_range_422(client):
    """§B6: month must be in [1, 12]."""
    r = client.post("/api/sessions", json={"year": 2026, "month": 13})
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
