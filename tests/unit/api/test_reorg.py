from api.reorg import OP_TYPES, build_manifest, resolve_op_defaults, validate_op


def _src_pages():
    return {"art_crs.pdf": 50, "x.pdf": 1}


def test_validate_move_file_ok():
    op = {
        "op_type": "move_file",
        "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
        "dest": {"hospital": "HRB", "sigla": "odi"},
        "doc_count": 1,
    }
    assert validate_op(op, src_pages=_src_pages(), existing_ops=[]) == []


def test_validate_rejects_dest_equals_source_for_move():
    op = {
        "op_type": "move_file",
        "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
        "dest": {"hospital": "HRB", "sigla": "art"},
        "doc_count": 1,
    }
    assert validate_op(op, src_pages=_src_pages(), existing_ops=[])


def _extract(page_range, *, dest_sigla="odi", **extra):
    """An extract_pages op in the CANONICAL shape: page_range nested under source."""
    src = {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"}
    if page_range is not None:
        src["page_range"] = page_range
    op = {
        "op_type": "extract_pages",
        "source": src,
        "dest": {"hospital": "HRB", "sigla": dest_sigla},
    }
    op.update(extra)
    return op


def test_validate_extract_requires_range():
    assert validate_op(_extract(None), src_pages=_src_pages(), existing_ops=[])


def test_validate_range_bounds_and_doc_cap():
    assert validate_op(_extract([0, 3]), src_pages=_src_pages(), existing_ops=[])
    assert validate_op(_extract([3, 60]), src_pages=_src_pages(), existing_ops=[])
    assert validate_op(_extract([5, 3]), src_pages=_src_pages(), existing_ops=[])
    assert validate_op(_extract([1, 2], doc_count=5), src_pages=_src_pages(), existing_ops=[])
    # a valid in-bounds extract (page_range nested under source) passes — guards
    # against the regression where page_range was read at the top level.
    assert validate_op(_extract([3, 7]), src_pages=_src_pages(), existing_ops=[]) == []


def test_validate_rejects_overlapping_extract_same_file():
    existing = [{**_extract([3, 7]), "status": "pending"}]
    assert validate_op(
        _extract([5, 9], dest_sigla="reunion"), src_pages=_src_pages(), existing_ops=existing
    )
    assert (
        validate_op(
            _extract([8, 9], dest_sigla="reunion"), src_pages=_src_pages(), existing_ops=existing
        )
        == []
    )


def test_resolve_defaults_move_file_uses_per_file():
    op = {
        "op_type": "move_file",
        "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
        "dest": {"hospital": "HRB", "sigla": "odi"},
    }
    src_cell = {"per_file": {"art_crs.pdf": 3}, "worker_marks": {}}
    out = resolve_op_defaults(op, src_cell=src_cell)
    assert out["doc_count"] == 3 and out["worker_count"] == 0


def test_build_manifest_includes_only_pending():
    state = {
        "reorg_ops": [
            {"id": "op_001", "status": "pending", "op_type": "rotate"},
            {"id": "op_002", "status": "applied", "op_type": "rotate"},
        ]
    }
    m = build_manifest(state, month="2026-06")
    assert m["manifest_version"] == 1 and m["month"] == "2026-06"
    assert [o["id"] for o in m["operations"]] == ["op_001"]
