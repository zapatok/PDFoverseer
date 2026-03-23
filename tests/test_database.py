import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.utils import _PageRead
import api.database as database


def _init_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_sessions.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database._init_db()
    return db_path


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


def test_save_and_get_reads(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    session_id = "11111111-1111-4111-8111-111111111111"
    pdf_path = "/some/test.pdf"
    reads = [
        _make_read(1, 1, 3, "direct", 1.0),
        _make_read(2, 2, 3, "super_resolution", 1.0),
        _make_read(3, 3, 3, "easyocr", 0.9),
    ]
    database.save_reads(session_id, pdf_path, reads)
    result = database.get_reads(session_id, pdf_path)
    assert len(result) == 3
    for orig, got in zip(reads, result):
        assert got.pdf_page == orig.pdf_page
        assert got.curr == orig.curr
        assert got.total == orig.total
        assert got.method == orig.method
        assert abs(got.confidence - orig.confidence) < 1e-9


def test_has_reads(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    session_id = "22222222-2222-4222-8222-222222222222"
    pdf_path = "/another/test.pdf"
    assert database.has_reads(session_id, pdf_path) is False
    database.save_reads(session_id, pdf_path, [_make_read(1, 1, 2)])
    assert database.has_reads(session_id, pdf_path) is True


def test_clear_session(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    sid_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    sid_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    pdf_path = "/shared/test.pdf"
    database.save_reads(sid_a, pdf_path, [_make_read(1, 1, 2)])
    database.save_reads(sid_b, pdf_path, [_make_read(1, 1, 2)])
    database.clear_session(sid_a)
    assert database.has_reads(sid_a, pdf_path) is False
    assert database.has_reads(sid_b, pdf_path) is True
