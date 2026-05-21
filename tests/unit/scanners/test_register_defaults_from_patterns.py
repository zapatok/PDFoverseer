"""register_defaults must build scanners based on patterns.py scan_strategy."""

from __future__ import annotations

from core.scanners import (
    clear,
    get,
    register_defaults,
)
from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.pagination_scanner import PaginationScanner
from core.scanners.patterns import PATTERNS
from core.scanners.simple_factory import SimpleFilenameScanner


def setup_function():
    clear()


def teardown_function():
    clear()
    register_defaults()  # restore for other tests


def test_register_defaults_picks_scanner_class_by_strategy():
    register_defaults()
    for sigla, pattern in PATTERNS.items():
        scanner = get(sigla)
        strategy = pattern["scan_strategy"]
        if strategy == "anchors":
            assert isinstance(scanner, AnchorsScanner), f"{sigla}: expected AnchorsScanner"
        elif strategy == "pagination":
            assert isinstance(scanner, PaginationScanner), f"{sigla}: expected PaginationScanner"
        elif strategy == "none":
            assert isinstance(scanner, SimpleFilenameScanner), (
                f"{sigla}: expected SimpleFilenameScanner"
            )
