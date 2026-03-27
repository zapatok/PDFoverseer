"""VLM provider interface: pluggable VLM backends for page number extraction."""
from __future__ import annotations

import base64
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import requests

from core.utils import VLM_PROMPT, VLM_TEMPERATURE, VLM_TOP_P

log = logging.getLogger(__name__)

# ── VLM Response Parsing ─────────────────────────────────────────────────────

# Patterns ordered by specificity, first match wins.
_VLM_PATTERNS: list[re.Pattern] = [
    re.compile(r"P[áa]g(?:ina)?\.?\s*(\d{1,3})\s*de\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"Page\s+(\d{1,3})\s+of\s+(\d{1,3})", re.IGNORECASE),
    re.compile(r"(\d{1,3})\s+out\s+of\s+(\d{1,3})", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d{1,3})\s+de\s+(\d{1,3})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,3})/(\d{1,3})(?!\d)"),
]


def parse_vlm_response(raw_text: str) -> tuple[tuple[int, int] | None, float]:
    """Parse VLM response text into (curr, total) and confidence.

    Returns:
        (parsed, confidence) where parsed is (curr, total) or None,
        and confidence is 0.85 for named/direct patterns, 0.60 for
        fallback heuristic, 0.0 if unparseable.
    """
    if not raw_text:
        return None, 0.0

    for pat in _VLM_PATTERNS:
        m = pat.search(raw_text)
        if m:
            curr, total = int(m.group(1)), int(m.group(2))
            if 1 <= curr <= total:
                return (curr, total), 0.85
            return None, 0.0

    # Fallback: find exactly two standalone integers <= 999
    nums = [int(x) for x in re.findall(r"\b(\d{1,3})\b", raw_text) if int(x) <= 999]
    if len(nums) == 2 and 1 <= nums[0] <= nums[1]:
        return (nums[0], nums[1]), 0.60

    return None, 0.0


# ── Data Types ───────────────────────────────────────────────────────────────

@dataclass
class VLMResult:
    """Result from a VLM query."""
    raw_text: str
    parsed: tuple[int, int] | None   # (curr, total) or None if unparseable
    confidence: float                  # parser confidence (0.0-1.0)
    latency_ms: float
    error: str | None


# ── Provider Interface ───────────────────────────────────────────────────────

class VLMProvider(ABC):
    """Abstract base for VLM backends."""
    name: str  # "ollama" | "claude"

    @abstractmethod
    def query(self, image_path: str) -> VLMResult:
        """Send image to VLM and return parsed result."""
        ...


# ── Ollama Provider ──────────────────────────────────────────────────────────

class OllamaProvider(VLMProvider):
    """Gemma 3 4B via local Ollama server."""
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gemma3:4b",
        timeout: int = 10,
    ):
        self._base_url = base_url
        self._model = model
        self._timeout = timeout

    def query(self, image_path: str) -> VLMResult:
        try:
            img_bytes = Path(image_path).read_bytes()
        except OSError as e:
            return VLMResult("", None, 0.0, 0.0, f"read error: {e}")

        b64 = base64.b64encode(img_bytes).decode("ascii")
        body = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": VLM_PROMPT, "images": [b64]},
            ],
            "stream": False,
            "options": {
                "temperature": VLM_TEMPERATURE,
                "top_p": VLM_TOP_P,
                "seed": 42,
                "num_predict": 50,
            },
        }

        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return VLMResult("", None, 0.0, 0.0, "timeout")
        except requests.RequestException as e:
            return VLMResult("", None, 0.0, 0.0, str(e))

        data = resp.json()
        raw_text = data.get("message", {}).get("content", "")
        latency_ms = data.get("total_duration", 0) / 1_000_000

        parsed, confidence = parse_vlm_response(raw_text)
        return VLMResult(raw_text, parsed, confidence, latency_ms, None)


# ── Claude Provider ──────────────────────────────────────────────────────────

class ClaudeProvider(VLMProvider):
    """Claude Haiku 4.5 via Anthropic API."""
    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ):
        import os
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model

    def query(self, image_path: str) -> VLMResult:
        if not self._api_key:
            return VLMResult("", None, 0.0, 0.0, "ANTHROPIC_API_KEY not set")

        import anthropic

        try:
            img_bytes = Path(image_path).read_bytes()
        except OSError as e:
            return VLMResult("", None, 0.0, 0.0, f"read error: {e}")

        b64 = base64.b64encode(img_bytes).decode("ascii")
        suffix = Path(image_path).suffix.lower().lstrip(".")
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
            suffix, "image/png"
        )

        client = anthropic.Anthropic(api_key=self._api_key)
        t0 = time.perf_counter()
        try:
            resp = client.messages.create(
                model=self._model,
                max_tokens=50,
                temperature=VLM_TEMPERATURE,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": VLM_PROMPT},
                    ],
                }],
            )
        except Exception as e:
            return VLMResult("", None, 0.0, 0.0, str(e))

        latency_ms = (time.perf_counter() - t0) * 1000
        raw_text = resp.content[0].text if resp.content else ""

        parsed, confidence = parse_vlm_response(raw_text)
        return VLMResult(raw_text, parsed, confidence, latency_ms, None)
