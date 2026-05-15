"""ART scanner: per_file populated from compilation OCR result."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.scanners.art_scanner import ArtScanner
from core.scanners.cancellation import CancellationToken


def test_art_per_file_filename_glob_path_multi_pdf(tmp_path: Path):
    """≥2 PDFs → no compilation, filename_glob path. per_file de simple_factory."""
    (tmp_path / "2026-04-01_art_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = ArtScanner(sigla="art")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    # Heredado de simple_factory (Task 4)
    assert result.per_file == {
        "2026-04-01_art_a_empresa.pdf": 1,
        "2026-04-02_art_b_empresa.pdf": 1,
    }


def test_art_per_file_compilation_ocr_path(tmp_path: Path):
    """1 PDF + flag_compilation_suspect → OCR; per_file = {filename: ocr.count}."""
    pdf = tmp_path / "2026-04-15_art_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners.art_scanner.flag_compilation_suspect",
            return_value=True,
        ),
        patch("core.scanners.art_scanner.count_paginations") as mock_ocr,
    ):
        mock_ocr.return_value.count = 24
        scanner = ArtScanner(sigla="art")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    assert result.method == "corner_count"
    assert result.count == 24
    assert result.per_file == {"2026-04-15_art_compilacion_empresa.pdf": 24}


def test_art_per_file_fallback_preserves_base(tmp_path: Path):
    """OCR fail path → fallback retorna per_file de la base (filename_glob)."""
    pdf = tmp_path / "2026-04-15_art_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with (
        patch(
            "core.scanners.art_scanner.flag_compilation_suspect",
            return_value=True,
        ),
        patch(
            "core.scanners.art_scanner.count_paginations",
            side_effect=RuntimeError("OCR exploded"),
        ),
    ):
        scanner = ArtScanner(sigla="art")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    # Base sería simple_factory(folder) → per_file={pdf.name: 1}
    assert result.per_file == {"2026-04-15_art_compilacion_empresa.pdf": 1}
