"""Tests for Ollama VLM client."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import patch, MagicMock
import pytest
from vlm.client import query, warmup


@pytest.fixture
def mock_ollama_response():
    """Simulate a successful Ollama /api/chat response."""
    return {
        "model": "gemma3:4b",
        "message": {"role": "assistant", "content": "3/10"},
        "done": True,
        "total_duration": 500_000_000,  # 500ms in nanoseconds
    }


def test_query_success(mock_ollama_response, tmp_path):
    # Create a tiny test image
    import cv2
    import numpy as np
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    img_path = tmp_path / "test.png"
    cv2.imwrite(str(img_path), img)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_ollama_response

    with patch("vlm.client.requests.post", return_value=mock_resp) as mock_post:
        result = query(str(img_path), prompt="Read page number", temperature=0.0)

    assert result["raw_text"] == "3/10"
    assert result["latency_ms"] == pytest.approx(500.0)
    assert result["error"] is None

    # Verify request structure
    call_args = mock_post.call_args
    body = call_args.kwargs.get("json") or call_args[1].get("json")
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    assert len(body["messages"][0]["images"]) == 1
    assert body["options"]["num_predict"] == 50
    assert body["options"]["temperature"] == 0.0
    assert body["options"]["top_p"] == 1.0
    assert body["options"]["seed"] == 42


def test_query_timeout(tmp_path):
    import cv2
    import numpy as np
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    img_path = tmp_path / "test.png"
    cv2.imwrite(str(img_path), img)

    import requests
    with patch("vlm.client.requests.post", side_effect=requests.Timeout("timeout")):
        result = query(str(img_path), prompt="Read page number")

    assert result["raw_text"] == ""
    assert result["error"] is not None
    assert "timeout" in result["error"].lower()


def test_warmup_sends_preload():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"model": "gemma3:4b", "done": True}

    with patch("vlm.client.requests.post", return_value=mock_resp) as mock_post:
        warmup()

    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert "/api/generate" in url
    body = call_args.kwargs.get("json") or call_args[1].get("json")
    assert body["model"] == "gemma3:4b"


def test_query_retry_on_connection_error(tmp_path):
    import cv2
    import numpy as np
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    img_path = tmp_path / "test.png"
    cv2.imwrite(str(img_path), img)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": "1/3"}, "done": True, "total_duration": 300_000_000,
    }

    import requests as req_mod
    with patch("vlm.client.requests.post", side_effect=[
        req_mod.ConnectionError("refused"), mock_resp,
    ]) as mock_post:
        result = query(str(img_path), prompt="Read page number")

    assert result["raw_text"] == "1/3"
    assert result["error"] is None
    assert mock_post.call_count == 2  # first failed, retry succeeded
