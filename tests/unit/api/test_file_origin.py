from api.routes.sessions import file_origin


def test_manual_override_wins():
    assert file_origin(method="v4", override=3, page_count=10, per_file_count=0) == "Manual"
    assert (
        file_origin(method="filename_glob", override=0, page_count=1, per_file_count=1) == "Manual"
    )


def test_unreadable_is_error():
    assert (
        file_origin(method="filename_glob", override=None, page_count=0, per_file_count=None)
        == "Error"
    )


def test_ocr_methods():
    for m in ("header_detect", "corner_count", "header_band_anchors", "v4"):
        assert file_origin(method=m, override=None, page_count=5, per_file_count=2) == "OCR"
        assert file_origin(method=m, override=None, page_count=5, per_file_count=0) == "Revisar"


def test_ratio_n_is_rn():
    assert file_origin(method="ratio_n", override=None, page_count=10, per_file_count=5) == "RN"


def test_page_count_pure_is_r1():
    assert (
        file_origin(method="page_count_pure", override=None, page_count=3, per_file_count=3) == "R1"
    )


def test_filename_glob_r1_vs_pendiente():
    assert (
        file_origin(method="filename_glob", override=None, page_count=1, per_file_count=1) == "R1"
    )
    assert (
        file_origin(method="filename_glob", override=None, page_count=8, per_file_count=None)
        == "Pendiente"
    )


def test_unknown_defaults_r1():
    assert (
        file_origin(method="something_else", override=None, page_count=2, per_file_count=1) == "R1"
    )
