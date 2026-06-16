"""Integration: apply-ratio endpoint (RN + Apply R1) + per-file override all_reliable."""

from __future__ import annotations


def test_apply_ratio_treats_pending_only(client, session_with_pending_cell):
    """RN: big.pdf (8pg, Pendiente) gets round(8/2)=4; a.pdf (R1) is untouched."""
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=1pg (R1), big.pdf=8pg (Pendiente)
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    assert r.status_code == 200, r.text
    files = client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    by_name = {f["name"]: f for f in files}
    assert by_name["2026-04-15_odi_big.pdf"]["origin"] == "RN"
    assert by_name["2026-04-15_odi_big.pdf"]["per_file_count"] == 4  # round(8/2)
    assert by_name["2026-04-10_odi_a.pdf"]["origin"] == "R1"  # untouched
    assert by_name["2026-04-10_odi_a.pdf"]["per_file_count"] == 1


def test_apply_r1_is_ratio_n1(client, session_with_pending_cell):
    """Apply R1 = ratio N=1: each page counts as one document."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 1})
    assert r.status_code == 200, r.text
    files = {
        f["name"]: f for f in client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    }
    assert files["2026-04-15_odi_big.pdf"]["per_file_count"] == 8  # each page a document
    assert files["2026-04-15_odi_big.pdf"]["origin"] == "RN"


def test_ratio_lights_green(client, session_with_pending_cell):
    """After apply-ratio resolves all Pendiente files, all_reliable becomes True."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    assert r.status_code == 200, r.text
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["all_reliable"] is True


def test_per_file_override_of_all_pendings_lights_green(client, session_with_pending_cell):
    """Overriding the lone Pendiente file per-file makes the cell reliable (Task 5)."""
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=R1, big.pdf=Pendiente
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/2026-04-15_odi_big.pdf/override",
        json={"count": 3},
    )
    assert r.status_code == 200, r.text
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["all_reliable"] is True


def test_apply_ratio_is_idempotent_on_rn_files(client, session_with_pending_cell):
    """A second apply-ratio with a different N leaves already-RN files untouched
    (clobber-guard: RN is not Pendiente)."""
    sid, hosp, sigla = session_with_pending_cell
    client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 3})
    assert r.status_code == 200, r.text
    files = {
        f["name"]: f for f in client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    }
    # still 4 (round(8/2) from the first call), NOT round(8/3)=3 — the second pass skipped it
    assert files["2026-04-15_odi_big.pdf"]["per_file_count"] == 4
    assert files["2026-04-15_odi_big.pdf"]["origin"] == "RN"


def test_apply_ratio_skips_unreadable_pdf(tmp_path, client, session_with_pending_cell):
    """An unreadable PDF (page_count 0 → origin 'Error') is skipped, not turned into
    RN, and does not break the rest of the cell (spec §4.1)."""
    sid, hosp, sigla = session_with_pending_cell
    folder = tmp_path / "ABRIL" / hosp / "3.-ODI Visitas"
    (folder / "broken.pdf").write_bytes(b"not a real pdf")
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    assert r.status_code == 200, r.text
    files = {
        f["name"]: f for f in client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    }
    assert files["broken.pdf"]["origin"] == "Error"  # skipped, not RN
    assert files["2026-04-15_odi_big.pdf"]["origin"] == "RN"  # the real pending file still processed
    assert files["2026-04-10_odi_a.pdf"]["origin"] == "R1"
