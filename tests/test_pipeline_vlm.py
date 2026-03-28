"""
Pipeline integration tests with mock VLM provider.
No real OCR or VLM — verifies wiring, signature, and telemetry format.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect  # noqa: E402

import pytest  # noqa: E402

from core.pipeline import _format_vlm_line  # noqa: E402
from core.vlm_provider import VLMProvider  # noqa: E402


def test_analyze_pdf_accepts_vlm_provider_param():
    """analyze_pdf signature includes vlm_provider as optional last param."""
    from core.pipeline import analyze_pdf
    sig = inspect.signature(analyze_pdf)
    params = list(sig.parameters.keys())
    assert "vlm_provider" in params
    assert params[-1] == "vlm_provider"
    assert sig.parameters["vlm_provider"].default is None


def test_format_vlm_line_off():
    """VLM off when stats is None."""
    assert _format_vlm_line(None) == "off"


def test_format_vlm_line_no_requests():
    """VLM off when queried is 0."""
    assert _format_vlm_line({"queried": 0}) == "off"


def test_format_vlm_line_with_stats():
    """VLM Tier 3 line formats correctly with stats."""
    stats = {
        "provider": "ollama",
        "version": "v1.0",
        "queried": 10,
        "read": 7,
        "failed": 2,
        "errors": 1,
        "latency_sum": 25000.0,
    }
    line = _format_vlm_line(stats)
    assert "v1.0-ollama" in line
    assert "10req" in line
    assert "7read" in line
    assert "2fail" in line
    assert "1err" in line
    assert "2500ms/avg" in line
