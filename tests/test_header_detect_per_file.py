"""HeaderDetectScanner: per_file populated from compilation header_detect result."""

from pathlib import Path
from unittest.mock import patch

from core.scanners._header_detect_base import HeaderDetectScanner
from core.scanners.cancellation import CancellationToken


def test_header_detect_per_file_filename_glob_path_multi_pdf(tmp_path: Path):
    """>=2 PDFs -> no compilation, filename_glob path. per_file de simple_factory."""
    (tmp_path / "2026-04-01_irl_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_irl_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = HeaderDetectScanner(sigla="irl", sigla_code="IRL")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.per_file == {
        "2026-04-01_irl_a_empresa.pdf": 1,
        "2026-04-02_irl_b_empresa.pdf": 1,
    }


def test_header_detect_per_file_compilation_ocr_path(tmp_path: Path):
    """1 PDF + flag_compilation_suspect -> OCR; per_file = {filename: ocr.count}."""
    pdf = tmp_path / "2026-04-15_irl_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners._header_detect_base.flag_compilation_suspect",
            return_value=True,
        ),
        patch("core.scanners._header_detect_base.count_form_codes") as mock_ocr,
    ):
        mock_ocr.return_value.count = 12
        scanner = HeaderDetectScanner(sigla="irl", sigla_code="IRL")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    assert result.method == "header_detect"
    assert result.count == 12
    assert result.per_file == {"2026-04-15_irl_compilacion_empresa.pdf": 12}


def test_header_detect_per_file_fallback_preserves_base(tmp_path: Path):
    """OCR fail path -> fallback retorna per_file de la base (filename_glob)."""
    pdf = tmp_path / "2026-04-15_irl_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners._header_detect_base.flag_compilation_suspect",
            return_value=True,
        ),
        patch(
            "core.scanners._header_detect_base.count_form_codes",
            side_effect=RuntimeError("OCR exploded"),
        ),
    ):
        scanner = HeaderDetectScanner(sigla="irl", sigla_code="IRL")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    assert result.per_file == {"2026-04-15_irl_compilacion_empresa.pdf": 1}
