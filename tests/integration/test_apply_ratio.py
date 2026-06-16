"""Integration: apply-ratio endpoint (RN + Apply R1) + per-file override all_reliable."""

from __future__ import annotations


def test_apply_ratio_treats_pending_only(client, session_with_pending_cell):
    """RN: big.pdf (8pg, Pendiente) gets round(8/2)=4; a.pdf (R1) is untouched."""
    sid, hosp, sigla = session_with_pending_cell  # a.pdf=1pg (R1), big.pdf=8pg (Pendiente)
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 2})
    assert r.status_code == 200, r.text
    files = client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    by_name = {f["name"]: f for f in files}
    assert by_name["big.pdf"]["origin"] == "RN"
    assert by_name["big.pdf"]["per_file_count"] == 4  # round(8/2)
    assert by_name["a.pdf"]["origin"] == "R1"  # untouched
    assert by_name["a.pdf"]["per_file_count"] == 1


def test_apply_r1_is_ratio_n1(client, session_with_pending_cell):
    """Apply R1 = ratio N=1: each page counts as one document."""
    sid, hosp, sigla = session_with_pending_cell
    r = client.post(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/apply-ratio", json={"n": 1})
    assert r.status_code == 200, r.text
    files = {
        f["name"]: f for f in client.get(f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files").json()
    }
    assert files["big.pdf"]["per_file_count"] == 8  # each page a document
    assert files["big.pdf"]["origin"] == "RN"


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
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/files/big.pdf/override",
        json={"count": 3},
    )
    assert r.status_code == 200, r.text
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["cells"][hosp][sigla]["all_reliable"] is True
