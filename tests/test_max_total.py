"""Tests for max_total validation in _parse()."""
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

    def test_total_11_rejected(self):
        """Total of 11 exceeds max_total=10 — should be rejected."""
        c, t = _parse("Página 3 de 11")
        assert c is None and t is None

    def test_total_40_rejected(self):
        """The dominant OCR error: 'X de 40' instead of 'X de 4'."""
        c, t = _parse("Página 2 de 40")
        assert c is None and t is None

    def test_total_99_rejected(self):
        """Previous max was 99 — should now be rejected."""
        c, t = _parse("Página 5 de 99")
        assert c is None and t is None

    def test_curr_greater_than_total_rejected(self):
        """curr > total should still be rejected."""
        c, t = _parse("Página 5 de 3")
        assert c is None and t is None

    def test_single_page_doc(self):
        """Página 1 de 1 — edge case, should work."""
        c, t = _parse("Página 1 de 1")
        assert c == 1 and t == 1
