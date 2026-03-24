"""Ollama vision API wrapper for Gemma 3 4B."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:4b"
TIMEOUT = 10  # seconds per image
WARMUP_TIMEOUT = 60  # seconds for model loading


def warmup(model: str = DEFAULT_MODEL) -> None:
    """Preload model into VRAM via empty /api/generate request."""
    log.info("Warming up %s...", model)
    try:
        requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": model},
            timeout=WARMUP_TIMEOUT,
        )
        log.info("Warmup complete.")
    except requests.RequestException as e:
        log.warning("Warmup failed: %s", e)


def query(
    image_path: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    top_p: float = 1.0,
    seed: int = 42,
    num_predict: int = 50,
) -> dict:
    """Send image to Ollama vision endpoint.

    Returns {"raw_text": str, "latency_ms": float, "error": str | None}.
    Latency is from Ollama's total_duration (nanoseconds -> ms).
    """
    try:
        img_bytes = Path(image_path).read_bytes()
    except OSError as e:
        return {"raw_text": "", "latency_ms": 0.0, "error": f"read error: {e}"}

    b64 = base64.b64encode(img_bytes).decode("ascii")

    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt, "images": [b64]},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "seed": seed,
            "num_predict": num_predict,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=body,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.Timeout:
        return {"raw_text": "", "latency_ms": 0.0, "error": "timeout"}
    except requests.RequestException as e:
        # Single retry on connection error (Ollama may still be loading)
        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json=body,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e2:
            return {"raw_text": "", "latency_ms": 0.0, "error": str(e2)}

    data = resp.json()
    raw_text = data.get("message", {}).get("content", "")
    # total_duration is in nanoseconds
    latency_ns = data.get("total_duration", 0)
    latency_ms = latency_ns / 1_000_000

    return {"raw_text": raw_text, "latency_ms": latency_ms, "error": None}
