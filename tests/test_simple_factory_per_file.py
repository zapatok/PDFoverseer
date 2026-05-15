"""SimpleFilenameScanner devuelve per_file = {matched_filename: 1}."""

from pathlib import Path

from core.scanners.simple_factory import SimpleFilenameScanner


def test_simple_factory_per_file_only_matching_files(tmp_path: Path):
    (tmp_path / "2026-04-01_art_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "ignore.txt").write_text("not a pdf")

    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path)

    assert result.per_file == {
        "2026-04-01_art_a_empresa.pdf": 1,
        "2026-04-02_art_b_empresa.pdf": 1,
    }
    # Sanity: count and per_file en sync
    assert result.count == sum(result.per_file.values())


def test_simple_factory_per_file_empty_when_no_match(tmp_path: Path):
    """Folder con PDFs pero ninguno matchea sigla → per_file = {}."""
    (tmp_path / "irl_only.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path)
    assert result.per_file == {}


def test_simple_factory_per_file_empty_when_folder_missing(tmp_path: Path):
    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path / "no_such_folder")
    assert result.per_file == {}
