"""Specialized scanners must be the ones returned by get(sigla) after
register_defaults(). simple_factory still wins for the other 14 siglas."""

from core.scanners import all_siglas, clear, get, register_defaults
from core.scanners.art_scanner import ArtScanner
from core.scanners.charla_scanner import CharlaScanner
from core.scanners.irl_scanner import IrlScanner
from core.scanners.odi_scanner import OdiScanner
from core.scanners.simple_factory import SimpleFilenameScanner


def test_art_uses_art_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("art"), ArtScanner)


def test_odi_uses_odi_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("odi"), OdiScanner)


def test_irl_uses_irl_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("irl"), IrlScanner)


def test_charla_uses_charla_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("charla"), CharlaScanner)


def test_non_specialized_uses_simple_factory() -> None:
    clear()
    register_defaults()
    # 4 specialized + 14 simple = 18 total
    specialized = {"art", "odi", "irl", "charla"}
    for sigla in all_siglas():
        scanner = get(sigla)
        if sigla in specialized:
            assert not isinstance(scanner, SimpleFilenameScanner), sigla
        else:
            assert isinstance(scanner, SimpleFilenameScanner), sigla
