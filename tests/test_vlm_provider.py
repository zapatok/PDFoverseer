"""
Tests for core.vlm_provider — VLM provider interface, parsing, confidence.
No real VLM calls — all HTTP is mocked.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.vlm_provider import (
    ClaudeProvider,
    OllamaProvider,
    VLMProvider,
    VLMResult,
    parse_vlm_response,
)

# ── parse_vlm_response tests ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_parsed,expected_conf", [
    # Named patterns — high confidence
    ("Página 3 de 10", (3, 10), 0.85),
    ("Pag 1 de 4", (1, 4), 0.85),
    ("Page 2 of 5", (2, 5), 0.85),
    ("3 out of 10", (3, 10), 0.85),
    # Bare N de M
    ("3 de 10", (3, 10), 0.85),
    # Direct N/M — high confidence
    ("**3/4**", (3, 4), 0.85),
    ("1/4", (1, 4), 0.85),
    # Fallback two-integer heuristic — lower confidence
    ("the numbers are 2 and 5", (2, 5), 0.60),
    # Invalid: curr > total
    ("Página 5 de 3", None, 0.0),
    # Unparseable
    ("no numbers here", None, 0.0),
    ("", None, 0.0),
    # Claude-style verbose response
    ("# Respuesta\n\nSegún la imagen, el número de página es: **2/4**", (2, 4), 0.85),
    # Edge: single page
    ("Página 1 de 1", (1, 1), 0.85),
])
def test_parse_vlm_response(raw, expected_parsed, expected_conf):
    parsed, conf = parse_vlm_response(raw)
    assert parsed == expected_parsed
    assert conf == pytest.approx(expected_conf, abs=0.01)


# ── Provider interface tests ─────────────────────────────────────────────────


def test_ollama_provider_is_vlm_provider():
    """OllamaProvider implements VLMProvider ABC."""
    p = OllamaProvider()
    assert isinstance(p, VLMProvider)
    assert p.name == "ollama"


def test_claude_provider_is_vlm_provider():
    """ClaudeProvider implements VLMProvider ABC."""
    p = ClaudeProvider(api_key="test-key")
    assert isinstance(p, VLMProvider)
    assert p.name == "claude"


def test_ollama_query_success(tmp_path):
    """OllamaProvider.query() returns parsed result on success."""
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": "**2/4**"},
        "total_duration": 2_500_000_000,  # 2500ms in nanoseconds
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("core.vlm_provider.requests.post", return_value=mock_resp):
        p = OllamaProvider()
        result = p.query(str(img))

    assert result.parsed == (2, 4)
    assert result.confidence == 0.85
    assert result.latency_ms == pytest.approx(2500.0)
    assert result.error is None


def test_ollama_query_timeout(tmp_path):
    """OllamaProvider.query() returns error on timeout."""
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    with patch("core.vlm_provider.requests.post", side_effect=requests.Timeout):
        p = OllamaProvider()
        result = p.query(str(img))

    assert result.parsed is None
    assert result.error == "timeout"


def test_provider_file_not_found():
    """Provider returns error when image file doesn't exist."""
    p = OllamaProvider()
    result = p.query("/nonexistent/image.png")
    assert result.error is not None
    assert "read error" in result.error
