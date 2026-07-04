"""Pure detection + suspect-lifecycle helpers for the anti-colados guard.

Covers the spec §8 test list for vertiente 1 (filename) + the shared lifecycle
rules (merge/eviction/precedence, dedupe table §5, counted §4.5, id determinism).
No PDF/OCR I/O — all inputs are plain dicts/lists.
"""

from __future__ import annotations

from core.scanners.utils.colado_guard import (
    KIND_CODE,
    KIND_FILENAME,
    annotate_counted_filename,
    find_foreign_filename_suspects,
    has_open_counted_suspects,
    merge_suspects,
    open_suspects,
    suspect_id,
)


# --------------------------------------------------------------------------- #
# find_foreign_filename_suspects (§3 rule)
# --------------------------------------------------------------------------- #
def test_single_foreign_file_suggested():
    out = find_foreign_filename_suspects(["2026-05-04_odi_jhon.pdf"], sigla_host="art")
    assert len(out) == 1
    s = out[0]
    assert s["kind"] == KIND_FILENAME
    assert s["file"] == "2026-05-04_odi_jhon.pdf"
    assert s["suggested_sigla"] == "odi"
    assert s["page_range"] is None


def test_host_named_file_suppressed():
    # A file that suggests the host (even alongside a foreign token) is silence.
    out = find_foreign_filename_suspects(["2026-05_art_crs.pdf"], sigla_host="art")
    assert out == []


def test_empty_suggestion_is_silence():
    # crs.pdf / titan.pdf suggest nothing (chps real files) → never flagged.
    out = find_foreign_filename_suspects(["crs.pdf", "titan.pdf"], sigla_host="art")
    assert out == []


def test_two_foreign_matches_yield_ambiguous():
    # cphs (chps alias) + reunion both foreign to host 'art' → suggested_sigla None.
    out = find_foreign_filename_suspects(["2026-04-30_cphs_acta_reunion.pdf"], sigla_host="art")
    assert len(out) == 1
    assert out[0]["suggested_sigla"] is None
    assert "chps" in out[0]["evidence"] and "reunion" in out[0]["evidence"]


def test_host_in_multi_match_suppresses():
    # If one of the 2+ matches IS the host, the file belongs → silence.
    out = find_foreign_filename_suspects(["2026-04-30_cphs_acta_reunion.pdf"], sigla_host="chps")
    assert out == []


# --------------------------------------------------------------------------- #
# merge_suspects — per-kind refresh + eviction + precedence (§5)
# --------------------------------------------------------------------------- #
def _fname(file, sigla="odi", counted=False):
    return {
        "id": suspect_id(KIND_FILENAME, file, None, sigla),
        "kind": KIND_FILENAME,
        "file": file,
        "evidence": sigla,
        "suggested_sigla": sigla,
        "page_range": None,
        "counted": counted,
    }


def _code(file, rng=(2, 3), sigla="art"):
    return {
        "id": suspect_id(KIND_CODE, file, rng, sigla),
        "kind": KIND_CODE,
        "file": file,
        "evidence": "F-CRS-ART-01",
        "suggested_sigla": sigla,
        "page_range": list(rng),
        "counted": True,
    }


def test_merge_pase1_replaces_only_filename_kind():
    existing = [_fname("a.pdf"), _code("b.pdf")]
    fresh = [_fname("c.pdf")]
    # scanned_files=None (pase-1): all filename entries replaced; code untouched.
    out = merge_suspects(existing, KIND_FILENAME, fresh, {"b.pdf", "c.pdf"})
    kinds = {(s["kind"], s["file"]) for s in out}
    assert (KIND_FILENAME, "c.pdf") in kinds
    assert (KIND_FILENAME, "a.pdf") not in kinds  # old filename entry gone
    assert (KIND_CODE, "b.pdf") in kinds  # code entry preserved


def test_merge_evicts_absent_file_both_kinds():
    existing = [_fname("gone.pdf"), _code("gone2.pdf")]
    # Neither file present → both evicted, even the code kind we did not refresh.
    out = merge_suspects(existing, KIND_FILENAME, [], present_files=set())
    assert out == []


def test_merge_filename_over_code_precedence_same_file():
    # A whole-file filename suspect for F suppresses code suspects for F.
    existing = [_code("F.pdf")]
    fresh = [_fname("F.pdf")]
    out = merge_suspects(existing, KIND_FILENAME, fresh, {"F.pdf"})
    assert [s["kind"] for s in out] == [KIND_FILENAME]


def test_merge_code_kind_scoped_replace_only_scanned():
    # OCR refresh (scanned_files given) replaces code entries ONLY for scanned PDFs.
    existing = [_code("scanned.pdf"), _code("other.pdf")]
    fresh = [_code("scanned.pdf", rng=(4, 5))]
    out = merge_suspects(
        existing,
        KIND_CODE,
        fresh,
        {"scanned.pdf", "other.pdf"},
        scanned_files={"scanned.pdf"},
    )
    ranges = {(s["file"], tuple(s["page_range"])) for s in out}
    assert ("scanned.pdf", (4, 5)) in ranges  # replaced
    assert ("scanned.pdf", (2, 3)) not in ranges  # old scanned entry gone
    assert ("other.pdf", (2, 3)) in ranges  # unscanned entry preserved


# --------------------------------------------------------------------------- #
# annotate_counted_filename (§4.5)
# --------------------------------------------------------------------------- #
def test_counted_true_when_per_file_positive():
    cell = {"per_file": {"f.pdf": 1}}
    out = annotate_counted_filename([_fname("f.pdf")], cell)
    assert out[0]["counted"] is True


def test_counted_false_when_absent_from_per_file():
    cell = {"per_file": {"other.pdf": 1}}
    out = annotate_counted_filename([_fname("f.pdf")], cell)
    assert out[0]["counted"] is False


def test_counted_uses_override_zero_over_per_file():
    # per_file_overrides[f] == 0 wins over per_file[f] == 3 → contribution 0.
    cell = {"per_file": {"f.pdf": 3}, "per_file_overrides": {"f.pdf": 0}}
    out = annotate_counted_filename([_fname("f.pdf")], cell)
    assert out[0]["counted"] is False


def test_annotate_leaves_code_kind_untouched():
    cell = {"per_file": {}}
    code = _code("x.pdf")  # counted True set by the scanner
    out = annotate_counted_filename([code], cell)
    assert out[0]["counted"] is True


# --------------------------------------------------------------------------- #
# open_suspects — dedupe table (§5), pending-only, cell-scoped
# --------------------------------------------------------------------------- #
def _op(op_type, file, sigla="art", page_range=None, status="pending", hosp="HRB"):
    src = {"hospital": hosp, "sigla": sigla, "file": file}
    if page_range is not None:
        src["page_range"] = page_range
    return {"op_type": op_type, "status": status, "source": src}


def test_move_file_op_suppresses_filename_suspect():
    s = [_fname("F.pdf")]
    ops = [_op("move_file", "F.pdf")]
    assert open_suspects(s, ops, "HRB", "art") == []


def test_move_file_op_suppresses_ranged_code_suspect():
    s = [_code("F.pdf", rng=(2, 3))]
    ops = [_op("move_file", "F.pdf")]
    assert open_suspects(s, ops, "HRB", "art") == []


def test_extract_op_suppresses_overlapping_code_only():
    s = [_code("F.pdf", rng=(2, 4))]
    ops = [_op("extract_pages", "F.pdf", page_range=[3, 5])]
    assert open_suspects(s, ops, "HRB", "art") == []


def test_extract_op_does_not_suppress_nonoverlapping():
    s = [_code("F.pdf", rng=(2, 3))]
    ops = [_op("extract_pages", "F.pdf", page_range=[8, 9])]
    assert len(open_suspects(s, ops, "HRB", "art")) == 1


def test_extract_op_never_suppresses_whole_file_filename_suspect():
    s = [_fname("F.pdf")]  # page_range None
    ops = [_op("extract_pages", "F.pdf", page_range=[1, 2])]
    assert len(open_suspects(s, ops, "HRB", "art")) == 1


def test_rotate_and_split_never_suppress():
    s = [_fname("F.pdf"), _code("F.pdf")]
    ops = [_op("rotate", "F.pdf"), _op("split_in_place", "F.pdf")]
    # filename-over-code isn't applied by open_suspects (that's merge), so both stay.
    assert len(open_suspects(s, ops, "HRB", "art")) == 2


def test_applied_op_does_not_participate():
    s = [_fname("F.pdf")]
    ops = [_op("move_file", "F.pdf", status="applied")]
    assert len(open_suspects(s, ops, "HRB", "art")) == 1


def test_other_cell_op_does_not_suppress():
    # Same basename, DIFFERENT source cell → must not suppress (F10 basename reuse).
    s = [_fname("F.pdf")]
    ops = [_op("move_file", "F.pdf", sigla="odi")]  # op's source sigla != host
    assert len(open_suspects(s, ops, "HRB", "art")) == 1


# --------------------------------------------------------------------------- #
# has_open_counted_suspects (§4.5 all_reliable gate term)
# --------------------------------------------------------------------------- #
def test_has_open_counted_true():
    s = [_fname("f.pdf", counted=True)]
    assert has_open_counted_suspects(s, [], "HRB", "art") is True


def test_has_open_counted_false_when_uncounted():
    s = [_fname("f.pdf", counted=False)]
    assert has_open_counted_suspects(s, [], "HRB", "art") is False


def test_has_open_counted_false_when_op_suppresses():
    s = [_fname("F.pdf", counted=True)]
    ops = [_op("move_file", "F.pdf")]
    assert has_open_counted_suspects(s, ops, "HRB", "art") is False


# --------------------------------------------------------------------------- #
# suspect_id determinism
# --------------------------------------------------------------------------- #
def test_suspect_id_deterministic_and_evidence_scoped():
    a = suspect_id(KIND_FILENAME, "f.pdf", None, "odi")
    b = suspect_id(KIND_FILENAME, "f.pdf", None, "odi")
    c = suspect_id(KIND_FILENAME, "f.pdf", None, "art")
    assert a == b and a.startswith("cs_")
    assert a != c
