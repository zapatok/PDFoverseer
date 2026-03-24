# VLM OCR Prototype Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone benchmark + parameter sweep to evaluate Gemma 3 4B (via Ollama) as OCR fallback for reading "Página N de M" from corner crop images.

**Architecture:** Independent `vlm/` package mirroring `eval/` patterns. Ollama `/api/chat` for vision inference, regex parser for response extraction, CSV + fixture-based ground truth, 3-pass sweep (LHS → fine grid → beam search).

**Tech Stack:** Python 3.10+, requests, OpenCV, numpy, Ollama (localhost:11434), Gemma 3 4B

**Spec:** `docs/superpowers/specs/2026-03-24-vlm-ocr-prototype-design.md`

---

## Chunk 1: Core modules (parser, client, ground truth)

### Task 1: Parser — regex extraction from VLM text

**Files:**
- Create: `vlm/__init__.py`
- Create: `vlm/parser.py`
- Create: `tests/test_vlm_parser.py`

- [ ] **Step 1: Write failing tests for parser**

```python
# tests/test_vlm_parser.py
"""Tests for VLM response parser."""
import pytest
from vlm.parser import parse


@pytest.mark.parametrize("text, expected", [
    # Direct N/M format
    ("3/10", (3, 10)),
    ("1/2", (1, 2)),
    # Spanish patterns
    ("Página 3 de 10", (3, 10)),
    ("Pagina 1 de 2", (1, 2)),
    ("Pag. 5 de 8", (5, 8)),
    ("Pág 12 de 15", (12, 15)),
    # English patterns
    ("Page 3 of 10", (3, 10)),
    # Variations
    ("3 de 10", (3, 10)),
    ("3 out of 10", (3, 10)),
    # VLM chatty responses
    ("The page number shown is 3/10.", (3, 10)),
    ("I can see Página 2 de 5 in the image.", (2, 5)),
    # Fallback: two integers <= 999
    ("numbers visible: 7 ... 20", (7, 20)),
    # Should NOT match
    ("No text visible", None),
    ("", None),
    # Integers > 999 should not match fallback
    ("15/07/2024", None),
    # But date-like with de should not match (year > 999)
    ("Fecha: 15 de 2024", None),
])
def test_parse(text, expected):
    assert parse(text) == expected


def test_parse_prefers_specific_over_fallback():
    """If both 'Página N de M' and random integers exist, prefer the named pattern."""
    text = "Código: 2024 Página 3 de 10"
    assert parse(text) == (3, 10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vlm'`

- [ ] **Step 3: Create vlm package and implement parser**

```python
# vlm/__init__.py
"""VLM OCR prototype — Gemma 3 4B via Ollama benchmark & sweep."""
```

```python
# vlm/parser.py
"""Extract (curr, total) page numbers from VLM response text."""
from __future__ import annotations

import re

# Ordered by specificity — first match wins.
_PATTERNS: list[re.Pattern] = [
    # "Página 3 de 10", "Pagina 1 de 2", "Pág. 5 de 8", "Pag 12 de 15"
    re.compile(r"P[áa]g(?:ina)?\.?\s*(\d{1,3})\s*de\s*(\d{1,3})", re.IGNORECASE),
    # "Page 3 of 10"
    re.compile(r"Page\s+(\d{1,3})\s+of\s+(\d{1,3})", re.IGNORECASE),
    # "3 out of 10"
    re.compile(r"(\d{1,3})\s+out\s+of\s+(\d{1,3})", re.IGNORECASE),
    # "3 de 10" (bare, no prefix)
    re.compile(r"(\d{1,3})\s+de\s+(\d{1,3})(?!\d)"),
    # "3/10" (direct format)
    re.compile(r"(\d{1,3})/(\d{1,3})(?!\d)"),
]


def parse(raw_text: str) -> tuple[int, int] | None:
    """Extract (curr, total) from VLM response text.

    Tries named patterns first, then falls back to finding two
    integers <= 999 if no named pattern matches.
    Returns None if nothing parseable is found.
    """
    if not raw_text:
        return None

    # Try specific patterns first
    for pat in _PATTERNS:
        m = pat.search(raw_text)
        if m:
            curr, total = int(m.group(1)), int(m.group(2))
            if 1 <= curr <= total:
                return (curr, total)

    # Fallback: find exactly two standalone integers <= 999
    nums = [int(x) for x in re.findall(r"\b(\d{1,3})\b", raw_text)
            if int(x) <= 999]
    if len(nums) == 2 and 1 <= nums[0] <= nums[1]:
        return (nums[0], nums[1])

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vlm_parser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/__init__.py vlm/parser.py tests/test_vlm_parser.py
git commit -m "feat(vlm): add response parser with regex patterns + fallback"
```

---

### Task 2: Ollama client wrapper

**Files:**
- Create: `vlm/client.py`
- Create: `tests/test_vlm_client.py`

- [ ] **Step 1: Write failing tests for client**

The client talks to Ollama over HTTP, so tests mock `requests.post`.

```python
# tests/test_vlm_client.py
"""Tests for Ollama VLM client."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vlm.client'`

- [ ] **Step 3: Implement client**

```python
# vlm/client.py
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
    Latency is from Ollama's total_duration (nanoseconds → ms).
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vlm_client.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/client.py tests/test_vlm_client.py
git commit -m "feat(vlm): add Ollama vision client with warmup + retry"
```

---

### Task 3: Ground truth loader

**Files:**
- Create: `vlm/ground_truth.py`
- Create: `tests/test_vlm_ground_truth.py`

**Reference files:**
- Read: `data/ocr_all/all_index.csv` — CSV with columns: `pdf_nickname, page_num, tier1_parsed, tier2_parsed, tier1_text, tier2_text, tier3_text, image_path`
- Read: `eval/fixtures/real/*.json` — each has `{"name": str, "source": "real", "reads": [{"pdf_page": int, "curr": int, "total": int, "method": str, "confidence": float}]}`

- [ ] **Step 1: Write failing tests for ground truth loader**

```python
# tests/test_vlm_ground_truth.py
"""Tests for VLM ground truth loader."""
import csv
import json
import pytest
from vlm.ground_truth import load_ground_truth, load_corpus, CorpusEntry

OCR_ALL_DIR = "data/ocr_all"
ALL_INDEX = f"{OCR_ALL_DIR}/all_index.csv"
FIXTURES_DIR = "eval/fixtures/real"


def test_load_ground_truth_returns_dict():
    gt = load_ground_truth()
    assert isinstance(gt, dict)
    assert len(gt) > 0
    # Keys are (nickname, page_num) tuples
    key = next(iter(gt))
    assert isinstance(key, tuple)
    assert len(key) == 2


def test_ground_truth_values_are_curr_total():
    gt = load_ground_truth()
    for key, val in list(gt.items())[:20]:
        nickname, page_num = key
        curr, total = val
        assert isinstance(curr, int)
        assert isinstance(total, int)
        assert 1 <= curr <= total


def test_ground_truth_excludes_inferred():
    """Ground truth should only include direct/super_resolution/easyocr methods."""
    gt = load_ground_truth()
    # We can't directly verify exclusion, but we can check that
    # the fixture-based entries exist for pages with known direct reads.
    # CH_9 page 1 has tier1_parsed="1/2" → should be in GT
    assert ("CH_9", 1) in gt
    assert gt[("CH_9", 1)] == (1, 2)


def test_load_corpus_failures_only():
    entries = load_corpus(failures_only=True)
    assert len(entries) > 0
    for e in entries:
        assert isinstance(e, CorpusEntry)
        assert e.tier1_parsed == ""
        assert e.tier2_parsed == ""


def test_load_corpus_full():
    entries = load_corpus(failures_only=False)
    assert len(entries) > len(load_corpus(failures_only=True))


def test_load_corpus_sample():
    full = load_corpus(failures_only=True)
    sample = load_corpus(failures_only=True, sample_n=20, seed=42)
    assert len(sample) == 20
    # All sampled entries should be from the failures set
    for e in sample:
        assert e.tier1_parsed == ""
        assert e.tier2_parsed == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_ground_truth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vlm.ground_truth'`

- [ ] **Step 3: Implement ground truth loader**

```python
# vlm/ground_truth.py
"""Load ground truth and corpus entries from all_index.csv + eval fixtures."""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

OCR_ALL_DIR = Path("data/ocr_all")
ALL_INDEX = OCR_ALL_DIR / "all_index.csv"
FIXTURES_DIR = Path("eval/fixtures/real")

# Trusted methods from eval fixtures (NOT "inferred" or "failed")
_TRUSTED_METHODS = {"direct", "super_resolution", "easyocr"}


@dataclass
class CorpusEntry:
    pdf_nickname: str
    page_num: int
    tier1_parsed: str
    tier2_parsed: str
    image_path: str  # relative to OCR_ALL_DIR


def _parse_nm(s: str) -> tuple[int, int] | None:
    """Parse 'N/M' string into (curr, total)."""
    if not s or "/" not in s:
        return None
    parts = s.split("/")
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def load_ground_truth() -> dict[tuple[str, int], tuple[int, int]]:
    """Build ground truth dict from CSV tier reads + eval fixtures.

    Returns {(pdf_nickname, page_num): (curr, total)}.
    Priority: CSV tier1/tier2 parsed reads first, then eval fixture reads
    (excluding inferred/failed methods).
    """
    gt: dict[tuple[str, int], tuple[int, int]] = {}

    # Source 1: CSV tier reads (highest priority — actual OCR results)
    with open(ALL_INDEX, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nickname = row["pdf_nickname"]
            page = int(row["page_num"])
            key = (nickname, page)
            if key in gt:
                continue
            parsed = _parse_nm(row["tier1_parsed"]) or _parse_nm(row["tier2_parsed"])
            if parsed:
                gt[key] = parsed

    # Source 2: Eval fixtures (fill gaps with trusted OCR reads only)
    if FIXTURES_DIR.exists():
        for fpath in sorted(FIXTURES_DIR.glob("*.json")):
            data = json.loads(fpath.read_text(encoding="utf-8"))
            nickname = data["name"]
            for read in data["reads"]:
                if read["method"] not in _TRUSTED_METHODS:
                    continue
                key = (nickname, read["pdf_page"])
                if key in gt:
                    continue
                curr, total = read.get("curr"), read.get("total")
                if curr is not None and total is not None:
                    gt[key] = (curr, total)

    return gt


def load_corpus(
    failures_only: bool = True,
    sample_n: int | None = None,
    seed: int = 42,
) -> list[CorpusEntry]:
    """Load corpus entries from all_index.csv.

    Args:
        failures_only: If True, only return entries where both tier1 and tier2 failed.
        sample_n: If set, randomly sample N entries.
        seed: Random seed for sampling.
    """
    entries: list[CorpusEntry] = []
    with open(ALL_INDEX, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t1 = row["tier1_parsed"].strip()
            t2 = row["tier2_parsed"].strip()
            if failures_only and (t1 or t2):
                continue
            entries.append(CorpusEntry(
                pdf_nickname=row["pdf_nickname"],
                page_num=int(row["page_num"]),
                tier1_parsed=t1,
                tier2_parsed=t2,
                image_path=row["image_path"],
            ))

    if sample_n is not None and sample_n < len(entries):
        rng = random.Random(seed)
        entries = rng.sample(entries, sample_n)

    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vlm_ground_truth.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/ground_truth.py tests/test_vlm_ground_truth.py
git commit -m "feat(vlm): add ground truth loader (CSV + eval fixtures)"
```

---

## Chunk 2: Benchmark runner + preprocessing

### Task 4: Image preprocessing

**Files:**
- Create: `vlm/preprocess.py`
- Create: `tests/test_vlm_preprocess.py`

- [ ] **Step 1: Write failing tests for preprocessing**

```python
# tests/test_vlm_preprocess.py
"""Tests for VLM image preprocessing."""
import cv2
import numpy as np
import pytest
from vlm.preprocess import apply_preprocess


@pytest.fixture
def color_image():
    """A 100x100 color image with some variation."""
    img = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    return img


def test_preprocess_none(color_image):
    result = apply_preprocess(color_image, mode="none", upscale=1.0)
    assert result.shape == color_image.shape
    assert np.array_equal(result, color_image)


def test_preprocess_grayscale(color_image):
    result = apply_preprocess(color_image, mode="grayscale", upscale=1.0)
    # Grayscale converted back to 3-channel for Ollama
    assert result.shape[0] == 100
    assert result.shape[1] == 100


def test_preprocess_otsu(color_image):
    result = apply_preprocess(color_image, mode="otsu", upscale=1.0)
    assert result.shape[0] == 100
    assert result.shape[1] == 100
    # Otsu produces binary image — only 0 and 255
    unique = np.unique(result)
    assert len(unique) <= 2


def test_preprocess_contrast(color_image):
    result = apply_preprocess(color_image, mode="contrast", upscale=1.0)
    assert result.shape[0] == 100
    assert result.shape[1] == 100


def test_preprocess_upscale(color_image):
    result = apply_preprocess(color_image, mode="none", upscale=2.0)
    assert result.shape[0] == 200
    assert result.shape[1] == 200


def test_preprocess_upscale_with_mode(color_image):
    result = apply_preprocess(color_image, mode="grayscale", upscale=1.5)
    assert result.shape[0] == 150
    assert result.shape[1] == 150


def test_preprocess_invalid_mode(color_image):
    with pytest.raises(ValueError, match="Unknown preprocess mode"):
        apply_preprocess(color_image, mode="invalid", upscale=1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_preprocess.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement preprocessing**

```python
# vlm/preprocess.py
"""Image preprocessing for VLM input."""
from __future__ import annotations

import cv2
import numpy as np


def apply_preprocess(img: np.ndarray, mode: str, upscale: float) -> np.ndarray:
    """Apply preprocessing + upscale to an image.

    Args:
        img: BGR numpy array (as read by cv2.imread).
        mode: One of "none", "grayscale", "otsu", "contrast".
        upscale: Scale factor (1.0 = no change).

    Returns:
        Processed BGR numpy array.
    """
    if mode == "none":
        out = img.copy()
    elif mode == "grayscale":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    elif mode == "otsu":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        out = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    elif mode == "contrast":
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        out = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    else:
        raise ValueError(f"Unknown preprocess mode: {mode!r}")

    if upscale != 1.0:
        h, w = out.shape[:2]
        new_h, new_w = int(h * upscale), int(w * upscale)
        out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vlm_preprocess.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/preprocess.py tests/test_vlm_preprocess.py
git commit -m "feat(vlm): add image preprocessing (grayscale, otsu, contrast, upscale)"
```

---

### Task 5: Benchmark runner

**Files:**
- Create: `vlm/benchmark.py`
- Create: `tests/test_vlm_benchmark.py`

**Reference files:**
- Read: `vlm/client.py` — `query()` and `warmup()` functions
- Read: `vlm/parser.py` — `parse()` function
- Read: `vlm/ground_truth.py` — `load_ground_truth()`, `load_corpus()`, `CorpusEntry`
- Read: `vlm/preprocess.py` — `apply_preprocess()`

- [ ] **Step 1: Write failing tests for benchmark**

```python
# tests/test_vlm_benchmark.py
"""Tests for VLM benchmark runner."""
from unittest.mock import patch, MagicMock
import pytest
from vlm.benchmark import run, compute_metrics


def test_compute_metrics_perfect():
    results = [
        {"parsed": (1, 3), "ground_truth": (1, 3), "latency_ms": 200.0},
        {"parsed": (2, 3), "ground_truth": (2, 3), "latency_ms": 300.0},
        {"parsed": (3, 3), "ground_truth": (3, 3), "latency_ms": 250.0},
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == 1.0
    assert m["curr_match"] == 1.0
    assert m["parse_rate"] == 1.0
    assert m["mean_latency_ms"] == pytest.approx(250.0)


def test_compute_metrics_partial():
    results = [
        {"parsed": (1, 3), "ground_truth": (1, 3), "latency_ms": 200.0},
        {"parsed": (2, 5), "ground_truth": (2, 3), "latency_ms": 300.0},  # curr OK, total wrong
        {"parsed": None, "ground_truth": (3, 3), "latency_ms": 250.0},     # parse failed
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == pytest.approx(1 / 3)
    assert m["curr_match"] == pytest.approx(2 / 3)
    assert m["parse_rate"] == pytest.approx(2 / 3)


def test_compute_metrics_no_ground_truth():
    """Pages without ground truth count for parse_rate but not accuracy."""
    results = [
        {"parsed": (1, 3), "ground_truth": None, "latency_ms": 200.0},
        {"parsed": (2, 3), "ground_truth": (2, 3), "latency_ms": 300.0},
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == 1.0  # 1/1 with GT
    assert m["parse_rate"] == 1.0   # 2/2 parsed


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["exact_match"] == 0.0
    assert m["parse_rate"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_benchmark.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement benchmark runner**

```python
# vlm/benchmark.py
"""Benchmark runner — evaluate VLM OCR on corpus images."""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import cv2

from vlm.client import query, warmup
from vlm.ground_truth import load_ground_truth, load_corpus, OCR_ALL_DIR
from vlm.parser import parse
from vlm.preprocess import apply_preprocess

log = logging.getLogger(__name__)
RESULTS_DIR = Path("vlm/results")

# Defaults matching the first prompt candidate in params.py
DEFAULT_CONFIG = {
    "prompt": "Read the page number pattern 'Pagina N de M' from this image. Reply only with N/M.",
    "temperature": 0.0,
    "top_p": 1.0,
    "seed": 42,
    "preprocess": "none",
    "upscale": 1.0,
}


def compute_metrics(results: list[dict]) -> dict:
    """Compute accuracy and latency metrics from benchmark results.

    Each result dict has: parsed, ground_truth, latency_ms.
    """
    if not results:
        return {
            "exact_match": 0.0, "curr_match": 0.0, "parse_rate": 0.0,
            "mean_latency_ms": 0.0, "p95_latency_ms": 0.0,
        }

    n_total = len(results)
    n_parsed = sum(1 for r in results if r["parsed"] is not None)
    with_gt = [r for r in results if r["ground_truth"] is not None]
    n_with_gt = len(with_gt)

    n_exact = sum(1 for r in with_gt if r["parsed"] == r["ground_truth"])
    n_curr = sum(
        1 for r in with_gt
        if r["parsed"] is not None and r["parsed"][0] == r["ground_truth"][0]
    )

    times = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    mean_lat = statistics.mean(times) if times else 0.0
    p95_lat = (sorted(times)[int(len(times) * 0.95)] if len(times) >= 2
               else (times[0] if times else 0.0))

    return {
        "exact_match": n_exact / n_with_gt if n_with_gt else 0.0,
        "curr_match": n_curr / n_with_gt if n_with_gt else 0.0,
        "parse_rate": n_parsed / n_total if n_total else 0.0,
        "mean_latency_ms": mean_lat,
        "p95_latency_ms": p95_lat,
    }


def run(config: dict | None = None, failures_only: bool = True,
        sample_n: int | None = None) -> dict:
    """Run benchmark with given config.

    Returns dict with config, metrics, and per-image results.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    gt = load_ground_truth()
    corpus = load_corpus(failures_only=failures_only, sample_n=sample_n)

    log.info("Benchmark: %d images, failures_only=%s", len(corpus), failures_only)
    warmup()

    results = []
    for i, entry in enumerate(corpus):
        img_path = OCR_ALL_DIR / entry.image_path
        img = cv2.imread(str(img_path))
        if img is None:
            results.append({
                "nickname": entry.pdf_nickname, "page": entry.page_num,
                "parsed": None, "ground_truth": gt.get((entry.pdf_nickname, entry.page_num)),
                "latency_ms": 0.0, "raw_text": "", "error": f"imread failed: {img_path}",
            })
            continue

        img = apply_preprocess(img, mode=cfg["preprocess"], upscale=cfg["upscale"])

        # Write preprocessed image to temp file (not in data dir)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            cv2.imwrite(tmp.name, img)
            tmp_file = Path(tmp.name)

        resp = query(
            str(tmp_file),
            prompt=cfg["prompt"],
            temperature=cfg["temperature"],
            top_p=cfg["top_p"],
            seed=cfg["seed"],
        )

        tmp_file.unlink(missing_ok=True)

        parsed = parse(resp["raw_text"]) if not resp["error"] else None
        gt_val = gt.get((entry.pdf_nickname, entry.page_num))

        results.append({
            "nickname": entry.pdf_nickname, "page": entry.page_num,
            "parsed": parsed, "ground_truth": gt_val,
            "latency_ms": resp["latency_ms"], "raw_text": resp["raw_text"],
            "error": resp["error"],
        })

        if (i + 1) % 50 == 0 or i == 0:
            pct = (i + 1) / len(corpus) * 100
            log.info("  %d/%d (%.0f%%)", i + 1, len(corpus), pct)

    metrics = compute_metrics(results)
    return {
        "config": cfg,
        "metrics": metrics,
        "n_images": len(corpus),
        "n_with_gt": sum(1 for r in results if r["ground_truth"] is not None),
        "results": results,
        "run_at": datetime.now().isoformat(),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="VLM OCR Benchmark")
    parser.add_argument("--full", action="store_true", help="Run on all images (not just failures)")
    parser.add_argument("--sample", type=int, default=None, help="Random sample of N images")
    parser.add_argument("--prompt", type=str, default=None)
    parser.add_argument("--temp", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--preprocess", type=str, default=None)
    parser.add_argument("--upscale", type=float, default=None)
    args = parser.parse_args()

    cfg = {}
    if args.prompt is not None: cfg["prompt"] = args.prompt
    if args.temp is not None: cfg["temperature"] = args.temp
    if args.top_p is not None: cfg["top_p"] = args.top_p
    if args.seed is not None: cfg["seed"] = args.seed
    if args.preprocess is not None: cfg["preprocess"] = args.preprocess
    if args.upscale is not None: cfg["upscale"] = args.upscale

    result = run(config=cfg, failures_only=not args.full, sample_n=args.sample)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"benchmark_{ts}.json"
    # Strip raw_text from saved results to keep file size down
    save_results = []
    for r in result["results"]:
        sr = {k: v for k, v in r.items() if k != "raw_text"}
        # Convert tuples to lists for JSON
        if sr["parsed"] is not None:
            sr["parsed"] = list(sr["parsed"])
        if sr["ground_truth"] is not None:
            sr["ground_truth"] = list(sr["ground_truth"])
        save_results.append(sr)
    save_data = {**result, "results": save_results}
    out_path.write_text(json.dumps(save_data, indent=2))

    m = result["metrics"]
    print(f"\n{'='*60}")
    print(f"Results: {out_path}")
    print(f"Images: {result['n_images']} | With GT: {result['n_with_gt']}")
    print(f"exact_match:  {m['exact_match']:.1%}")
    print(f"curr_match:   {m['curr_match']:.1%}")
    print(f"parse_rate:   {m['parse_rate']:.1%}")
    print(f"mean_latency: {m['mean_latency_ms']:.0f}ms")
    print(f"p95_latency:  {m['p95_latency_ms']:.0f}ms")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vlm_benchmark.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/benchmark.py tests/test_vlm_benchmark.py
git commit -m "feat(vlm): add benchmark runner with CLI + metrics"
```

---

## Chunk 3: Parameter space, sweep, and report

### Task 6: Parameter space

**Files:**
- Create: `vlm/params.py`

- [ ] **Step 1: Create params.py**

```python
# vlm/params.py
"""Parameter space for VLM OCR sweep."""
from __future__ import annotations

PARAM_SPACE: dict[str, list] = {
    "prompt": [
        "Read the page number pattern 'Pagina N de M' from this image. Reply only with N/M.",
        "Extract the text 'Pagina X de Y' visible in this image. Reply: X/Y",
        "Que numero de pagina dice esta imagen? Formato: N/M",
        "OCR this image. Return only the page number in format N/M.",
    ],
    "temperature": [0.0, 0.1, 0.3, 0.5],
    "top_p": [0.5, 0.9, 1.0],
    "preprocess": ["none", "grayscale", "otsu", "contrast"],
    "upscale": [1.0, 1.5, 2.0],
    "seed": [42, 123, 7],
}
# Total: 4 x 4 x 3 x 4 x 3 x 3 = 1,728 combinations
# Note: seed tests reproducibility — if results are identical across seeds
# at temperature=0, we can drop seed from the space (reducing to 576).

# Filled after first sweep
PRODUCTION_PARAMS: dict[str, object] = {
    "prompt": PARAM_SPACE["prompt"][0],
    "temperature": 0.0,
    "top_p": 1.0,
    "preprocess": "none",
    "upscale": 1.0,
    "seed": 42,
}
```

- [ ] **Step 2: Commit**

```bash
git add vlm/params.py
git commit -m "feat(vlm): add parameter space for sweep"
```

---

### Task 7: Sweep tests + runner

**Files:**
- Create: `tests/test_vlm_sweep.py`
- Create: `vlm/sweep.py`

**Reference files:**
- Read: `eval/sweep.py` — pattern to follow for LHS + fine grid + beam search

- [ ] **Step 1: Write failing tests for sweep utilities**

```python
# tests/test_vlm_sweep.py
"""Tests for VLM sweep utilities."""
import pytest
from vlm.sweep import lhs_sample, adjacent_configs, rank_key
from vlm.params import PARAM_SPACE


def test_lhs_sample_count():
    configs = lhs_sample(10)
    assert len(configs) == 10


def test_lhs_sample_deterministic():
    a = lhs_sample(10, seed=42)
    b = lhs_sample(10, seed=42)
    assert a == b


def test_lhs_sample_different_seeds():
    a = lhs_sample(10, seed=42)
    b = lhs_sample(10, seed=99)
    assert a != b


def test_lhs_sample_valid_values():
    configs = lhs_sample(20)
    for cfg in configs:
        for k, v in cfg.items():
            assert v in PARAM_SPACE[k], f"{k}={v} not in PARAM_SPACE"


def test_adjacent_configs_shifts_one_param():
    base = {k: vals[1] for k, vals in PARAM_SPACE.items()}  # middle values
    adjs = adjacent_configs(base)
    for adj in adjs:
        diffs = [k for k in base if adj[k] != base[k]]
        assert len(diffs) == 1, f"Expected 1 diff, got {diffs}"


def test_adjacent_configs_stays_in_bounds():
    # Use first values — can only shift right
    base = {k: vals[0] for k, vals in PARAM_SPACE.items()}
    adjs = adjacent_configs(base)
    for adj in adjs:
        for k, v in adj.items():
            assert v in PARAM_SPACE[k]


def test_rank_key_ordering():
    better = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 300}
    worse = {"exact_match": 0.5, "curr_match": 0.7, "mean_latency_ms": 200}
    assert rank_key(better) < rank_key(worse)  # better sorts first


def test_rank_key_tiebreak_by_curr():
    a = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 300}
    b = {"exact_match": 0.8, "curr_match": 0.7, "mean_latency_ms": 300}
    assert rank_key(a) < rank_key(b)


def test_rank_key_tiebreak_by_latency():
    a = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 200}
    b = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 500}
    assert rank_key(a) < rank_key(b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_sweep.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement sweep**

```python
# vlm/sweep.py
"""3-pass parameter sweep for VLM OCR.

Pass 1: Latin Hypercube Sample — 80 configs
Pass 2: Fine grid around top-10 — adjacent index +/-1 per param
Pass 3: Beam search from top-3

Usage:
    python -m vlm.sweep
    python -m vlm.sweep --sample 50    # use 50-image subset per config
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

from vlm.benchmark import run, compute_metrics
from vlm.params import PARAM_SPACE

log = logging.getLogger(__name__)
RESULTS_DIR = Path("vlm/results")

LHS_SAMPLES = 80
PASS2_TOP_N = 10
BEAM_TOP_N = 3
RANDOM_SEED = 42


def lhs_sample(n: int, seed: int = RANDOM_SEED) -> list[dict]:
    """Latin Hypercube Sample from parameter space."""
    rng = random.Random(seed)
    keys = list(PARAM_SPACE.keys())
    indices_per_param: dict[str, list[int]] = {}
    for k, vals in PARAM_SPACE.items():
        m = len(vals)
        slots = [rng.randint(0, m - 1) for _ in range(n)]
        rng.shuffle(slots)
        indices_per_param[k] = slots

    configs = []
    for i in range(n):
        cfg = {k: PARAM_SPACE[k][indices_per_param[k][i]] for k in keys}
        configs.append(cfg)
    return configs


def adjacent_configs(base: dict) -> list[dict]:
    """Generate configs with one parameter shifted +/-1 index."""
    configs = []
    for k, vals in PARAM_SPACE.items():
        try:
            idx = vals.index(base[k])
        except ValueError:
            continue
        for new_idx in [idx - 1, idx + 1]:
            if 0 <= new_idx < len(vals):
                cfg = dict(base)
                cfg[k] = vals[new_idx]
                configs.append(cfg)
    return configs


def rank_key(metrics: dict) -> tuple:
    """Sort key: exact_match desc, curr_match desc, latency asc."""
    return (-metrics["exact_match"], -metrics["curr_match"], metrics["mean_latency_ms"])


def run_sweep(sample_n: int | None = None) -> dict:
    """Execute 3-pass sweep, saving results per config for crash resilience."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results: list[tuple[dict, dict]] = []  # (config, metrics)

    def run_configs(configs: list[dict], label: str) -> list[tuple[dict, dict]]:
        results = []
        for i, cfg in enumerate(configs):
            t0 = datetime.now()
            result = run(config=cfg, failures_only=True, sample_n=sample_n)
            metrics = result["metrics"]
            results.append((cfg, metrics))

            # Save per-config for crash resilience
            cfg_path = RESULTS_DIR / f"sweep_{ts}_config_{len(all_results) + len(results):04d}.json"
            cfg_path.write_text(json.dumps({
                "config": cfg, "metrics": metrics,
                "n_images": result["n_images"], "n_with_gt": result["n_with_gt"],
            }, indent=2))

            elapsed = (datetime.now() - t0).total_seconds()
            remaining = (len(configs) - i - 1) * elapsed
            log.info(
                "  %s %d/%d | exact=%.1f%% curr=%.1f%% parse=%.1f%% | %.0fs/cfg ETA %.0fm",
                label, i + 1, len(configs),
                metrics["exact_match"] * 100, metrics["curr_match"] * 100,
                metrics["parse_rate"] * 100, elapsed, remaining / 60,
            )
        return results

    def top_k(results: list[tuple[dict, dict]], k: int) -> list[tuple[dict, dict]]:
        return sorted(results, key=lambda x: rank_key(x[1]))[:k]

    # Pre-check: seed stability at temp=0
    # If 3 seeds give identical results, drop seed from sweep space
    log.info("Seed stability check (3 seeds x 20 images)...")
    seed_results = []
    for s in PARAM_SPACE["seed"]:
        cfg = {k: PARAM_SPACE[k][0] for k in PARAM_SPACE}
        cfg["seed"] = s
        cfg["temperature"] = 0.0
        r = run(config=cfg, failures_only=True, sample_n=20)
        seed_results.append(r["metrics"]["exact_match"])
    if len(set(seed_results)) == 1:
        log.info("  Seeds are stable at temp=0 — dropping seed from sweep space.")
        # Use a reduced space without seed variation
        global PARAM_SPACE_ACTIVE
        PARAM_SPACE_ACTIVE = {k: v for k, v in PARAM_SPACE.items() if k != "seed"}
    else:
        log.info("  Seeds vary (results: %s) — keeping seed in sweep.", seed_results)
        PARAM_SPACE_ACTIVE = PARAM_SPACE

    # Pass 1: LHS
    log.info("Pass 1: Latin Hypercube Sample (%d configs)...", LHS_SAMPLES)
    p1 = run_configs(lhs_sample(LHS_SAMPLES), "P1")
    all_results.extend(p1)
    top10 = top_k(all_results, PASS2_TOP_N)

    # Pass 2: Fine grid
    log.info("Pass 2: Fine grid around top-%d...", PASS2_TOP_N)
    p2_configs: list[dict] = []
    seen = set()
    for cfg, _ in top10:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen:
                seen.add(key)
                p2_configs.append(adj)
    p2 = run_configs(p2_configs, "P2")
    all_results.extend(p2)
    top3 = top_k(all_results, BEAM_TOP_N)

    # Pass 3: Beam search
    log.info("Pass 3: Beam search from top-%d...", BEAM_TOP_N)
    p3_configs: list[dict] = []
    seen3 = set()
    for cfg, _ in top3:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen3:
                seen3.add(key)
                p3_configs.append(adj)
    p3 = run_configs(p3_configs, "P3")
    all_results.extend(p3)

    # Final ranking
    ranked = top_k(all_results, 20)
    top_configs = []
    for rank, (cfg, metrics) in enumerate(ranked, 1):
        top_configs.append({"rank": rank, "config": cfg, "metrics": metrics})

    summary = {
        "run_at": datetime.now().isoformat(),
        "total_configs_tested": len(all_results),
        "sample_n": sample_n,
        "top_configs": top_configs,
    }
    summary_path = RESULTS_DIR / f"sweep_{ts}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Sweep complete. Summary: %s", summary_path)
    return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="VLM OCR Parameter Sweep")
    parser.add_argument("--sample", type=int, default=None,
                        help="Use N-image subset per config (faster iteration)")
    args = parser.parse_args()
    run_sweep(sample_n=args.sample)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run sweep tests to verify they pass**

Run: `pytest tests/test_vlm_sweep.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vlm/sweep.py tests/test_vlm_sweep.py
git commit -m "feat(vlm): add 3-pass parameter sweep (LHS + fine grid + beam)"
```

---

### Task 8: Report printer

**Files:**
- Create: `vlm/report.py`

**Reference files:**
- Read: `eval/report.py` — pattern to follow

- [ ] **Step 1: Implement report**

```python
# vlm/report.py
"""Print ranked results from VLM sweep.

Usage:
    python -m vlm.report                           # latest summary
    python -m vlm.report vlm/results/sweep_X.json  # specific file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path("vlm/results")


def load_result(path: Path | None = None) -> dict:
    if path is None:
        candidates = sorted(RESULTS_DIR.glob("sweep_*_summary.json"))
        if not candidates:
            print("No sweep results found in vlm/results/")
            sys.exit(1)
        path = candidates[-1]
    print(f"Report for: {path}\n")
    return json.loads(path.read_text())


def print_report(result: dict) -> None:
    total = result["total_configs_tested"]
    sample = result.get("sample_n", "all")

    print(f"Sweep: {result['run_at']}  |  {total} configs  |  sample={sample}\n")
    print(f"{'Rank':>4}  {'exact':>7}  {'curr':>7}  {'parse':>7}  "
          f"{'lat_ms':>7}  {'p95_ms':>7}  {'pre':>10}  {'up':>4}  {'temp':>4}  {'top_p':>5}  prompt")
    print("-" * 110)

    for cfg_entry in result["top_configs"]:
        rank = cfg_entry["rank"]
        m = cfg_entry["metrics"]
        c = cfg_entry["config"]
        prompt_abbrev = c["prompt"][:40] + "..." if len(c["prompt"]) > 40 else c["prompt"]
        print(
            f"{rank:4d}  {m['exact_match']:6.1%}  {m['curr_match']:6.1%}  "
            f"{m['parse_rate']:6.1%}  {m['mean_latency_ms']:7.0f}  "
            f"{m['p95_latency_ms']:7.0f}  {c['preprocess']:>10}  "
            f"{c['upscale']:4.1f}  {c['temperature']:4.1f}  {c['top_p']:5.1f}  "
            f"{prompt_abbrev}"
        )
    print()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = load_result(path)
    print_report(result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add vlm/report.py
git commit -m "feat(vlm): add sweep report printer"
```

---

### Task 9: Gitignore + __main__ entries

**Files:**
- Create: `vlm/results/.gitkeep`
- Modify: `.gitignore` — add `vlm/results/*.json`
- Create: `vlm/__main__.py`

- [ ] **Step 1: Add gitignore and __main__**

```python
# vlm/__main__.py
"""Allow `python -m vlm.benchmark`, `python -m vlm.sweep`, `python -m vlm.report`."""
print("Usage:")
print("  python -m vlm.benchmark [--full] [--sample N] [--prompt '...'] [--temp F]")
print("  python -m vlm.sweep [--sample N]")
print("  python -m vlm.report [path/to/summary.json]")
```

Append to `.gitignore`:
```
# VLM sweep results
vlm/results/*.json
```

Create empty `vlm/results/.gitkeep`.

- [ ] **Step 2: Commit**

```bash
git add vlm/__main__.py vlm/results/.gitkeep .gitignore
git commit -m "chore(vlm): add gitignore for results + __main__ usage helper"
```

---

### Task 10: Smoke test with Ollama (manual verification)

**Prerequisites:** Ollama running locally with `gemma3:4b` pulled.

- [ ] **Step 1: Verify Ollama is running**

Run: `curl -s http://localhost:11434/api/tags | python -m json.tool | grep gemma`
Expected: `"name": "gemma3:4b"` in output. If not: `ollama pull gemma3:4b`

- [ ] **Step 2: Run benchmark on 5 images**

Run: `python -m vlm.benchmark --sample 5`
Expected: Output with metrics (exact_match, curr_match, parse_rate, latency). Verify no crashes.

- [ ] **Step 3: Review raw results**

Run: `cat vlm/results/benchmark_*.json | python -m json.tool | head -40`
Expected: JSON with config, metrics, and per-image results.

- [ ] **Step 4: Run full failures benchmark**

Run: `python -m vlm.benchmark`
Expected: Processes ~697 images. Note exact_match and parse_rate for viability assessment.

- [ ] **Step 5: Commit any fixes from smoke test**

```bash
git add -u
git commit -m "fix(vlm): smoke test corrections"
```
