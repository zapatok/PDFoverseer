"""Integration: count <= pages cap on cell + per-file overrides (Task 6)."""

from __future__ import annotations


def test_cell_override_capped_for_documents(client, session_with_pending_cell):
    """Cell override > total pages (9) is rejected 422 for a documents sigla."""
    sid, hosp, sigla = session_with_pending_cell  # total pages = 1 + 8 = 9
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override",
        json={"value": 10},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "count_exceeds_pages"
    assert detail["max"] == 9


def test_cell_override_at_limit_allowed(client, session_with_pending_cell):
    """Cell override == total pages (9) is accepted."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/override",
        json={"value": 9},
    )
    assert r.status_code == 200, r.text


def test_per_file_override_capped(client, session_with_pending_cell):
    """Per-file override > file's page count is rejected 422."""
    sid, hosp, sigla = session_with_pending_cell  # big.pdf = 8 pages
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 9},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "count_exceeds_pages"
    assert detail["max"] == 8


def test_per_file_override_at_limit_allowed(client, session_with_pending_cell):
    """Per-file override == file's page count (8) is accepted."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 8},
    )
    assert r.status_code == 200, r.text


def test_checks_sigla_uncapped(client, session_with_checks_cell):
    """maquinaria (count_type=checks) has no page cap — any reasonable count is accepted."""
    sid, hosp, sigla = session_with_checks_cell  # maq.pdf = 2 pages
    # Override to 50 — way above page count; should be accepted for checks
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/maq.pdf/override",
        json={"count": 50},
    )
    assert r.status_code == 200, r.text
