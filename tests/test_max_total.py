"""Tests for max_total validation in _parse(). Guard: tot <= 20."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.utils import _parse


class TestMaxTotalValidation:
    """Test that _parse() rejects totals above the max_total threshold."""

    def test_normal_page_accepted(self):
        """Standard 'Página 2 de 4' should parse fine."""
        c, t = _parse("Página 2 de 4")
        assert c == 2 and t == 4

    def test_total_10_accepted(self):
        """Total of 10 is at the boundary — should be accepted."""
        c, t = _parse("Página 3 de 10")
        assert c == 3 and t == 10

    def test_total_11_accepted(self):
        """Total of 11 is within max_total=20 — should be accepted."""
        c, t = _parse("Página 3 de 11")
        assert c == 3 and t == 11

    def test_total_20_accepted(self):
        """Total of 20 is at the boundary — should be accepted."""
        c, t = _parse("Página 5 de 20")
        assert c == 5 and t == 20

    def test_total_21_rejected(self):
        """Total of 21 exceeds max_total=20 — should be rejected."""
        c, t = _parse("Página 5 de 21")
        assert c is None and t is None

    def test_total_40_rejected(self):
        """Total of 40 exceeds max_total=20 — should be rejected (was FP source)."""
        c, t = _parse("Página 2 de 40")
        assert c is None and t is None

    def test_curr_greater_than_total_rejected(self):
        """curr > total should still be rejected."""
        c, t = _parse("Página 5 de 3")
        assert c is None and t is None

    def test_single_page_doc(self):
        """Página 1 de 1 — edge case, should work."""
        c, t = _parse("Página 1 de 1")
        assert c == 1 and t == 1
