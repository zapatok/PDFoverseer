"""Charla scanner: per_file populated from compilation page_count_pure result."""

from pathlib import Path
from unittest.mock import patch

from core.scanners.cancellation import CancellationToken
from core.scanners.charla_scanner import CharlaScanner


def test_charla_per_file_filename_glob_path_multi_pdf(tmp_path: Path):
    """≥2 PDFs → no compilation, filename_glob path. per_file de simple_factory."""
    (tmp_path / "2026-04-01_charla_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_charla_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = CharlaScanner(sigla="charla")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.per_file == {
        "2026-04-01_charla_a_empresa.pdf": 1,
        "2026-04-02_charla_b_empresa.pdf": 1,
    }


def test_charla_per_file_compilation_ocr_path(tmp_path: Path):
    """1 PDF + flag_compilation_suspect → page_count_pure; per_file = {filename: count}."""
    pdf = tmp_path / "2026-04-15_charla_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners.charla_scanner.flag_compilation_suspect",
            return_value=True,
        ),
        patch("core.scanners.charla_scanner.count_documents_in_pdf") as mock_ocr,
    ):
        mock_ocr.return_value.count = 18
        scanner = CharlaScanner(sigla="charla")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    assert result.method == "page_count_pure"
    assert result.count == 18
    assert result.per_file == {"2026-04-15_charla_compilacion_empresa.pdf": 18}


def test_charla_per_file_fallback_preserves_base(tmp_path: Path):
    """OCR fail path → fallback retorna per_file de la base (filename_glob)."""
    pdf = tmp_path / "2026-04-15_charla_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners.charla_scanner.flag_compilation_suspect",
            return_value=True,
        ),
        patch(
            "core.scanners.charla_scanner.count_documents_in_pdf",
            side_effect=RuntimeError("PDF read failed"),
        ),
    ):
        scanner = CharlaScanner(sigla="charla")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    # Base sería simple_factory(folder) → per_file={pdf.name: 1}
    assert result.per_file == {"2026-04-15_charla_compilacion_empresa.pdf": 1}
