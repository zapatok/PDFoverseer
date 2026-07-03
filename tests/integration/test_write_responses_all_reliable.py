"""Fix A (Fase-6 review) — per-file override + worker-count PATCH responses
carry ``all_reliable``.

Pre-F15, each write's own ``cell_updated`` WS echo wholesale-replaced the cell
in the writer's tab, so the recomputed ``all_reliable`` arrived that way. The
F15 pending-save guard now drops that self-echo, so the HTTP response is the
only channel left — it must carry the field (the ``patch_note`` pattern).
Reuses the integration conftest fixtures (real folders + PDFs, so
``refresh_all_reliable`` actually runs and can flip the value).
"""

from __future__ import annotations


def test_per_file_override_response_carries_all_reliable(client, session_with_pending_cell):
    """Overriding the last unreliable file (big.pdf, Pendiente) flips the cell
    to all-reliable — and the PATCH response itself must say so."""
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=R1, big.pdf=Pendiente

    # Sanity: with big.pdf still Pendiente the cell is not settled.
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla].get("all_reliable") is False

    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 4},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "all_reliable" in body, "response must carry all_reliable (F15 self-echo is dropped)"
    assert body["all_reliable"] is True


def test_worker_count_response_carries_all_reliable(client, session_with_checks_cell):
    """maquinaria (checks): terminado settles the cell — the PATCH response must
    carry the freshly recomputed all_reliable, not the pre-write value."""
    sid, hosp, sigla = session_with_checks_cell

    # en_progreso → not settled; the response already reports it honestly.
    r1 = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-count",
        json={"marks": {"maq.pdf": [{"page": 1, "count": 3}]}, "status": "en_progreso"},
    )
    assert r1.status_code == 200, r1.text
    assert "all_reliable" in r1.json()
    assert r1.json()["all_reliable"] is False

    # terminado → settled; the response must carry the POST-refresh value (a
    # stale pre-refresh read would still say False here).
    r2 = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-count",
        json={
            "marks": {"maq.pdf": [{"page": 1, "count": 5}, {"page": 2, "count": 4}]},
            "status": "terminado",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["all_reliable"] is True
    assert r2.json()["worker_count"] == 9  # existing contract untouched
