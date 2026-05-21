"""Specialized scanners must be the ones returned by get(sigla) after
register_defaults(). simple_factory still wins for the other 14 siglas.

NOTE: These tests encode the OLD hard-coded dispatch contract (art→ArtScanner,
etc.). Chunk 3 replaced that with patterns.py-driven dispatch, so art/odi/irl/
charla now map to SimpleFilenameScanner until Chunk 4 populates their PATTERNS
entries and deletes the specialized scanner classes. Marked xfail until then.
"""

import pytest

from core.scanners import all_siglas, clear, get, register_defaults
from core.scanners.art_scanner import ArtScanner
from core.scanners.charla_scanner import CharlaScanner
from core.scanners.irl_scanner import IrlScanner
from core.scanners.odi_scanner import OdiScanner
from core.scanners.simple_factory import SimpleFilenameScanner

_CHUNK4_REASON = (
    "Old hard-coded dispatch superseded by patterns.py in Chunk 3. "
    "Chunk 4 will populate PATTERNS for art/odi/irl/charla and delete "
    "the specialized scanner classes — these tests will be replaced then."
)


@pytest.mark.xfail(reason=_CHUNK4_REASON, strict=False)
def test_art_uses_art_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("art"), ArtScanner)


@pytest.mark.xfail(reason=_CHUNK4_REASON, strict=False)
def test_odi_uses_odi_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("odi"), OdiScanner)


@pytest.mark.xfail(reason=_CHUNK4_REASON, strict=False)
def test_irl_uses_irl_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("irl"), IrlScanner)


@pytest.mark.xfail(reason=_CHUNK4_REASON, strict=False)
def test_charla_uses_charla_scanner() -> None:
    clear()
    register_defaults()
    assert isinstance(get("charla"), CharlaScanner)


@pytest.mark.xfail(reason=_CHUNK4_REASON, strict=False)
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
