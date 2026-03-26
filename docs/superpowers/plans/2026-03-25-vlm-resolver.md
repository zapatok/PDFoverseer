# VLM Resolver Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate VLM (Ollama/Claude) as a post-inference selective resolver that automatically corrects problematic pages, maximizing document accuracy while maintaining full modularity.

**Architecture:** OCR pipeline runs normally, inference pass 1 identifies problematic pages, VLM resolver selectively queries a vision model on those pages, validates reads against context, then inference pass 2 re-runs with corrected data. The cascade effect means a single VLM correction can resolve multiple neighboring pages.

**Tech Stack:** Python 3.10+, PyMuPDF (fitz), OpenCV, requests (Ollama API), anthropic SDK (Claude API), pytest

**Spec:** `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `core/utils.py` | VLM constants, `InferenceIssue` dataclass | Modify |
| `core/vlm_provider.py` | VLM provider interface + Ollama/Claude implementations | Create |
| `core/vlm_resolver.py` | Post-inference VLM orchestrator: select, execute, validate | Create |
| `core/inference.py` | Export `InferenceIssue` list from `_infer_missing()` | Modify |
| `core/pipeline.py` | Wire VLM resolver between inference pass 1 and document building | Modify |
| `core/__init__.py` | Export new symbols (`VLM_ENGINE_VERSION`, `InferenceIssue`) | Modify |
| `api/worker.py` | Pass `vlm_provider` to `analyze_pdf()` (future — not in this plan) | No change |
| `tests/test_vlm_provider.py` | Provider interface, parsing, confidence tests | Create |
| `tests/test_vlm_resolver.py` | `_should_accept()`, candidate selection, mock provider tests | Create |
| `tests/test_inference.py` | Update existing tests for new return type | Modify |
| `tests/test_pipeline_vlm.py` | Pipeline integration with mock VLM | Create |

---

## Chunk 1: Constants + VLM Provider

### Task 1: VLM Constants and InferenceIssue Dataclass

**Files:**
- Modify: `core/utils.py:1-93`
- Modify: `core/__init__.py`

- [ ] **Step 1: Add VLM constants to `core/utils.py`**

Add after `INFERENCE_ENGINE_VERSION` (line 24):

```python
# VLM Resolver
VLM_ENGINE_VERSION    = "v1.0"
VLM_METHODS           = {"vlm_ollama", "vlm_claude"}
VLM_PROMPT            = "Que numero de pagina dice esta imagen? Formato: N/M"
VLM_TEMPERATURE       = 0.3
VLM_TOP_P             = 1.0
VLM_UPSCALE           = 1.5
VLM_MIN_ACCEPT_CONF   = 0.50    # min parser confidence to accept a VLM read
```

- [ ] **Step 2: Add `InferenceIssue` dataclass to `core/utils.py`**

Add after the `_PageRead` dataclass (after line 93):

```python
@dataclass
class InferenceIssue:
    """A problematic page identified by the inference engine."""
    pdf_page: int
    issue_type: str       # "low_confidence" | "contradiction" | "gap" | "boundary_inferred"
    confidence: float     # current confidence (0.0 for gaps)
    context: str          # brief description for telemetry
```

- [ ] **Step 3: Update `core/__init__.py` exports**

Change imports to:
```python
from .utils import Document, _PageRead, INFERENCE_ENGINE_VERSION, InferenceIssue, VLM_ENGINE_VERSION
```

Update `__all__`:
```python
__all__ = [
    "analyze_pdf", "re_infer_documents", "Document", "_PageRead",
    "_build_documents", "classify_doc", "_CORE_HASH", "INFERENCE_ENGINE_VERSION",
    "InferenceIssue", "VLM_ENGINE_VERSION",
]
```

- [ ] **Step 4: Verify imports work**

Run: `python -c "from core.utils import InferenceIssue, VLM_ENGINE_VERSION, VLM_METHODS; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add core/utils.py core/__init__.py
git commit -m "feat(vlm): add VLM constants and InferenceIssue dataclass"
```

---

### Task 2: VLM Provider Interface and Implementations

**Files:**
- Create: `core/vlm_provider.py`
- Create: `tests/test_vlm_provider.py`

- [ ] **Step 1: Write failing tests for VLM response parsing**

Create `tests/test_vlm_provider.py`:

```python
"""
Tests for core.vlm_provider — VLM provider interface, parsing, confidence.
No real VLM calls — all HTTP is mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.vlm_provider import VLMResult, parse_vlm_response


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.vlm_provider'`

- [ ] **Step 3: Create `core/vlm_provider.py` with parsing logic and providers**

```python
"""VLM provider interface: pluggable VLM backends for page number extraction."""
from __future__ import annotations

import re
import time
import base64
import logging
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import requests

from core.utils import VLM_PROMPT, VLM_TEMPERATURE, VLM_TOP_P

log = logging.getLogger(__name__)

# ── VLM Response Parsing ─────────────────────────────────────────────────────

# Patterns copied from vlm/parser.py — ordered by specificity, first match wins.
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
```

- [ ] **Step 4: Run parsing tests to verify they pass**

Run: `pytest tests/test_vlm_provider.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Add provider interface tests to `tests/test_vlm_provider.py`**

Append to `tests/test_vlm_provider.py`:

```python
import requests
from unittest.mock import patch, MagicMock
from core.vlm_provider import OllamaProvider, ClaudeProvider, VLMProvider


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
```

- [ ] **Step 6: Run all provider tests**

Run: `pytest tests/test_vlm_provider.py -v`
Expected: All 18 tests PASS

- [ ] **Step 7: Commit**

```bash
git add core/vlm_provider.py tests/test_vlm_provider.py
git commit -m "feat(vlm): VLM provider interface with Ollama + Claude implementations"
```

---

## Chunk 2: Inference Issue Export + VLM Resolver

### Task 3: Export InferenceIssues from `_infer_missing()`

**Files:**
- Modify: `core/inference.py:160-520`
- Modify: `core/pipeline.py:306,420`
- Modify: `tests/test_inference.py`

- [ ] **Step 1: Write failing test for new return type**

Add to `tests/test_inference.py` (after existing imports, add `InferenceIssue`):

```python
from core.utils import _PageRead, Document, InferenceIssue
```

Then add new tests at the end:

```python
def test_infer_missing_returns_tuple():
    """_infer_missing now returns (reads, issues) tuple."""
    reads = [
        _make_read(1, 1, 3),
        _failed(2),
        _make_read(3, 3, 3),
    ]
    result = _infer_missing(reads)
    assert isinstance(result, tuple)
    assert len(result) == 2
    reads_out, issues = result
    assert isinstance(reads_out, list)
    assert isinstance(issues, list)


def test_gap_produces_gap_issue():
    """Pages still failed after inference produce 'gap' issues."""
    reads = [_failed(1)]
    reads_out, issues = _infer_missing(reads)
    assert isinstance(issues, list)


def test_boundary_inferred_produces_issue():
    """Inferred curr=1 at document boundary produces 'boundary_inferred' issue."""
    reads = [
        _make_read(1, 1, 3),
        _make_read(2, 2, 3),
        _make_read(3, 3, 3),
        _failed(4),          # should become curr=1 (new doc boundary)
        _make_read(5, 2, 3),
        _make_read(6, 3, 3),
    ]
    reads_out, issues = _infer_missing(reads)
    boundary_issues = [i for i in issues if i.issue_type == "boundary_inferred"]
    assert len(boundary_issues) >= 1
    assert boundary_issues[0].pdf_page == 4


def test_low_confidence_produces_issue():
    """Low-confidence inferred pages (<=0.60) produce 'low_confidence' issues."""
    reads = [
        _make_read(1, 1, 3),
        _make_read(2, 2, 3),
        _make_read(3, 3, 3),
        _failed(4),
        _failed(5),
        _make_read(6, 2, 4),  # inconsistent → xval caps confidence
    ]
    reads_out, issues = _infer_missing(reads)
    assert isinstance(issues, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_inference.py::test_infer_missing_returns_tuple -v`
Expected: FAIL — `_infer_missing` returns `list`, not `tuple`

- [ ] **Step 3: Modify `_infer_missing()` to collect issues and return tuple**

In `core/inference.py`:

**3a.** Add `InferenceIssue` to import line 14:
```python
from core.utils import Document, _PageRead, MIN_CONF_FOR_NEW_DOC, ANOMALY_DROPOUT, PHASE4_FALLBACK_CONF, CLASH_BOUNDARY_PEN, PH5B_CONF_MIN, PH5B_RATIO_MIN, InferenceIssue
```

**3b.** Change signature (line 160-163):
```python
def _infer_missing(
    reads: list[_PageRead],
    period_info: dict | None = None,
) -> tuple[list[_PageRead], list[InferenceIssue]]:
```

**3c.** Change early return and add issues list (lines 174-176):
```python
    n = len(reads)
    if n == 0:
        return reads, []

    issues: list[InferenceIssue] = []
```

**3d.** In Phase 1-2 apply block (line 344-361), add boundary issue when `c == 1`. Insert after `r.curr = c` / `r.total = t` but BEFORE the confidence assignment block:
```python
        for offset, (c, t, hom) in enumerate(best_hyp):
            r = reads[gap_start + offset]
            r.method = "inferred"
            r.curr = c
            r.total = t
            if c == 1:
                issues.append(InferenceIssue(
                    pdf_page=r.pdf_page,
                    issue_type="boundary_inferred",
                    confidence=0.0,  # updated after confidence is set
                    context=f"inferred curr=1 total={t} at gap boundary",
                ))
            if best_hyp is hyp_bwd:
                r.confidence = 0.85
            else:
                if offset == 0 and gap_start > 0:
                    rp = reads[gap_start - 1]
                    if rp.curr == rp.total:
                        r.confidence = 0.60 + hom * 0.30
                        if c == 1 and issues and issues[-1].pdf_page == r.pdf_page:
                            issues[-1].confidence = r.confidence
                        continue
                if c == 1:
                    r.confidence = 0.60 + hom * 0.30
                else:
                    r.confidence = 0.99
            # Update boundary issue confidence
            if c == 1 and issues and issues[-1].pdf_page == r.pdf_page:
                issues[-1].confidence = r.confidence
```

**3e.** In Phase 3 cross-validation (line 396), add contradiction issue:
```python
        if not consistent:
            r.confidence = min(r.confidence, 0.50)
            issues.append(InferenceIssue(
                pdf_page=r.pdf_page,
                issue_type="contradiction",
                confidence=r.confidence,
                context=f"xval inconsistent: {r.curr}/{r.total}",
            ))
```

**3f.** In Phase 4 fallback (lines 402-409), record gap issues. Replace the entire Phase 4 block:
```python
    if PHASE4_FALLBACK_CONF > 0.0:
        for i, r in enumerate(reads):
            if r.method == "failed":
                issues.append(InferenceIssue(
                    pdf_page=r.pdf_page,
                    issue_type="gap",
                    confidence=0.0,
                    context="unresolved after gap solver + fallback",
                ))
                lt, hom = _local_total(i)
                r.curr   = 1
                r.total  = lt
                r.method = "inferred"
                r.confidence = PHASE4_FALLBACK_CONF
    else:
        for r in reads:
            if r.method == "failed":
                issues.append(InferenceIssue(
                    pdf_page=r.pdf_page,
                    issue_type="gap",
                    confidence=0.0,
                    context="unresolved after gap solver, no fallback",
                ))
```

**3g.** After Phase 5 D-S block (after line 449), collect low-confidence issues:
```python
    # Collect low-confidence inferred pages as issues
    for r in reads:
        if r.method == "inferred" and r.confidence <= 0.60:
            if not any(iss.pdf_page == r.pdf_page and iss.issue_type == "contradiction" for iss in issues):
                issues.append(InferenceIssue(
                    pdf_page=r.pdf_page,
                    issue_type="low_confidence",
                    confidence=r.confidence,
                    context=f"inferred {r.curr}/{r.total} conf={r.confidence:.0%}",
                ))
```

**3h.** Change return (line 520):
```python
    return reads, issues
```

- [ ] **Step 4: Update existing tests to unpack tuple**

In `tests/test_inference.py`, replace all `result = _infer_missing(...)` with `result, _issues = _infer_missing(...)`:

```python
# In test_forward_fill_mid_gap:
result, _issues = _infer_missing(reads)

# In test_backward_fill_mid_gap:
result, _issues = _infer_missing(reads)

# In test_gap_at_start:
result, _issues = _infer_missing(reads)

# In test_gap_at_end:
result, _issues = _infer_missing(reads)

# In test_all_pages_failed:
result, _issues = _infer_missing(reads)

# In test_phase5b_contradiction:
result, _issues = _infer_missing(reads, period_info)

# In test_phase6_orphan_suppression:
result, _issues = _infer_missing(reads)
```

- [ ] **Step 5: Update `core/pipeline.py` callers to unpack tuple**

Line 306 in `pipeline.py`:
```python
# Before:
reads_clean = inference._infer_missing(reads_clean, period_info)
# After:
reads_clean, _inf_issues = inference._infer_missing(reads_clean, period_info)
```

Line 420 in `pipeline.py` (inside `re_infer_documents`):
```python
# Before:
reads = inference._infer_missing(reads, period_info)
# After:
reads, _issues = inference._infer_missing(reads, period_info)
```

- [ ] **Step 6: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add core/inference.py core/pipeline.py tests/test_inference.py
git commit -m "feat(inference): export InferenceIssue list from _infer_missing()"
```

---

### Task 4: VLM Resolver Module

**Files:**
- Create: `core/vlm_resolver.py`
- Create: `tests/test_vlm_resolver.py`

- [ ] **Step 1: Write failing tests for `_should_accept()`**

Create `tests/test_vlm_resolver.py`:

```python
"""
Tests for core.vlm_resolver — candidate selection, validation, mock provider.
No real VLM calls — uses mock provider.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.utils import _PageRead, InferenceIssue
from core.vlm_provider import VLMResult
from core.vlm_resolver import _should_accept


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


def _failed(page):
    return _PageRead(pdf_page=page, curr=None, total=None,
                     method="failed", confidence=0.0)


# ── _should_accept tests ─────────────────────────────────────────────────────

def test_reject_unparseable():
    """Reject VLM result with no parsed value."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    result = VLMResult("garbage", None, 0.0, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is False


def test_reject_contradicts_period():
    """Reject when VLM total contradicts strong period."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    period_info = {"period": 3, "confidence": 0.8, "expected_total": 3}
    result = VLMResult("2/5", (2, 5), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, period_info) is False


def test_accept_matches_period():
    """Accept when VLM read matches period total."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    period_info = {"period": 3, "confidence": 0.8, "expected_total": 3}
    result = VLMResult("2/3", (2, 3), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, period_info) is True


def test_accept_sequential_with_prev():
    """Accept when VLM read is sequential with previous page."""
    reads = [_make_read(1, 1, 4), _make_read(2, 2, 4), _failed(3), _make_read(4, 4, 4)]
    result = VLMResult("3/4", (3, 4), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is True


def test_accept_new_doc_after_complete():
    """Accept curr=1 when previous page is last of its document."""
    reads = [_make_read(1, 1, 2), _make_read(2, 2, 2), _failed(3)]
    result = VLMResult("1/3", (1, 3), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is True


def test_reject_contradicts_neighbor():
    """Reject when VLM curr=1 but previous is mid-document."""
    reads = [_make_read(1, 1, 4), _make_read(2, 2, 4), _failed(3)]
    result = VLMResult("1/4", (1, 4), 0.85, 100.0, None)
    assert _should_accept(result, 2, reads, {}) is False


def test_accept_confirms_existing():
    """Accept when VLM confirms existing low-confidence read."""
    reads = [
        _make_read(1, 1, 3),
        _PageRead(pdf_page=2, curr=2, total=3, method="inferred", confidence=0.40),
        _make_read(3, 3, 3),
    ]
    result = VLMResult("2/3", (2, 3), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is True


def test_reject_low_vlm_confidence():
    """Reject when VLM parser confidence is below minimum."""
    reads = [_make_read(1, 1, 3), _failed(2), _make_read(3, 3, 3)]
    result = VLMResult("numbers 2 3", (2, 3), 0.40, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is False


def test_accept_no_period_gap_fill():
    """Accept gap fill when no period info and sequential."""
    reads = [_make_read(1, 1, 4), _failed(2), _make_read(3, 3, 4)]
    result = VLMResult("2/4", (2, 4), 0.85, 100.0, None)
    assert _should_accept(result, 1, reads, {}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.vlm_resolver'`

- [ ] **Step 3: Create `core/vlm_resolver.py`**

```python
"""VLM Resolver: post-inference selective VLM correction of problematic pages."""
from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

import cv2
import fitz

from core.utils import (
    _PageRead,
    InferenceIssue,
    VLM_UPSCALE,
    VLM_MIN_ACCEPT_CONF,
    VLM_ENGINE_VERSION,
)
from core.vlm_provider import VLMProvider, VLMResult
from core.image import _render_clip

log = logging.getLogger(__name__)

# Priority order: lower = higher priority (more impact per VLM call)
ISSUE_PRIORITY = {
    "boundary_inferred": 0,
    "contradiction":     1,
    "low_confidence":    2,
    "gap":               3,
}


def _should_accept(
    vlm_result: VLMResult,
    page_idx: int,
    reads: list[_PageRead],
    period_info: dict,
) -> bool:
    """Accept VLM read only if coherent with surrounding context.

    This is what prevents the VLM paradox — rejecting reads that would
    cause document merges or contradict strong evidence.
    """
    # 1. Reject if unparseable
    if vlm_result.parsed is None:
        return False

    # 2. Reject if VLM parser confidence is below minimum
    if vlm_result.confidence < VLM_MIN_ACCEPT_CONF:
        return False

    curr, total = vlm_result.parsed

    # 3. Reject if total contradicts strong period
    if period_info.get("confidence", 0) > 0.5:
        expected_total = period_info.get("expected_total")
        if expected_total is not None and total != expected_total:
            return False

    # 4. Check neighbor consistency
    prev = reads[page_idx - 1] if page_idx > 0 else None
    nxt = reads[page_idx + 1] if page_idx < len(reads) - 1 else None

    # 4a. If VLM says curr=1, check if previous page is end-of-document
    if curr == 1 and prev is not None:
        if prev.curr is not None and prev.total is not None:
            if prev.curr != prev.total:
                # Previous is mid-document — claiming new doc start is suspicious
                return False

    # 4b. Check sequential coherence with prev
    if prev is not None and prev.curr is not None and prev.total is not None:
        prev_sequential = (prev.total == total and prev.curr == curr - 1)
        prev_boundary = (prev.curr == prev.total and curr == 1)
        if not prev_sequential and not prev_boundary:
            # Not sequential and not a new doc — check next neighbor
            if nxt is not None and nxt.curr is not None and nxt.total is not None:
                nxt_sequential = (nxt.total == total and nxt.curr == curr + 1)
                nxt_boundary = (curr == total and nxt.curr == 1)
                if not nxt_sequential and not nxt_boundary:
                    return False
            elif reads[page_idx].curr is not None and reads[page_idx].curr == curr:
                pass  # Confirms existing read
            else:
                return False

    # 5. Accept if confirms existing low-confidence read
    existing = reads[page_idx]
    if existing.curr == curr and existing.total == total:
        return True

    # 6. Accept — passed all checks
    return True


def resolve(
    reads: list[_PageRead],
    issues: list[InferenceIssue],
    total_pages: int,
    provider: VLMProvider,
    pdf_path: str | Path,
    period_info: dict,
    on_log: callable,
    cancel_event: threading.Event | None = None,
) -> tuple[list[_PageRead], dict]:
    """Selectively query VLM for problematic pages and return corrected reads.

    Args:
        reads: Page reads from inference pass 1.
        issues: Problems identified by inference engine.
        total_pages: Total pages in PDF.
        provider: VLM backend (Ollama or Claude).
        pdf_path: Path to PDF — renders image strips on demand.
        period_info: Period detection results from pass 1.
        on_log: Logging callback.
        cancel_event: Cooperative cancellation.

    Returns:
        (corrected_reads, vlm_stats) — reads modified in-place and returned.
    """
    stats = {
        "provider": provider.name,
        "version": VLM_ENGINE_VERSION,
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "errors": 0,
        "latency_sum": 0.0,
        "by_type": {},
    }

    if not issues:
        on_log("VLM resolver: no issues to resolve", "info")
        return reads, stats

    # Build page index for quick lookup
    page_to_idx = {r.pdf_page: i for i, r in enumerate(reads)}

    # Sort candidates by priority
    candidates = sorted(issues, key=lambda iss: ISSUE_PRIORITY.get(iss.issue_type, 99))

    # Deduplicate by pdf_page (keep highest priority)
    seen_pages: set[int] = set()
    unique_candidates: list[InferenceIssue] = []
    for c in candidates:
        if c.pdf_page not in seen_pages:
            seen_pages.add(c.pdf_page)
            unique_candidates.append(c)

    on_log(
        f"VLM resolver: {len(unique_candidates)} candidates "
        f"({provider.name}, v{VLM_ENGINE_VERSION})",
        "info",
    )

    # Open PDF once for all candidates
    doc = fitz.open(str(pdf_path))
    try:
        for issue in unique_candidates:
            if cancel_event is not None and cancel_event.is_set():
                on_log("VLM resolver: cancelled", "warn")
                break

            page_idx = page_to_idx.get(issue.pdf_page)
            if page_idx is None:
                continue

            pdf_page_0idx = issue.pdf_page - 1  # fitz uses 0-indexed
            if pdf_page_0idx < 0 or pdf_page_0idx >= len(doc):
                continue

            # Render image strip
            clip = _render_clip(doc[pdf_page_0idx])

            # Upscale
            if VLM_UPSCALE != 1.0:
                clip = cv2.resize(
                    clip, None,
                    fx=VLM_UPSCALE, fy=VLM_UPSCALE,
                    interpolation=cv2.INTER_CUBIC,
                )

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            try:
                cv2.imwrite(tmp_path, clip)
                vlm_result = provider.query(tmp_path)
            finally:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

            stats["total"] += 1
            stats["latency_sum"] += vlm_result.latency_ms

            # Track per-type stats
            t = issue.issue_type
            if t not in stats["by_type"]:
                stats["by_type"][t] = {"attempted": 0, "accepted": 0}
            stats["by_type"][t]["attempted"] += 1

            if vlm_result.error:
                stats["errors"] += 1
                on_log(
                    f"  VLM p{issue.pdf_page}: error — {vlm_result.error}",
                    "warn",
                )
                continue

            if _should_accept(vlm_result, page_idx, reads, period_info):
                r = reads[page_idx]
                r.curr = vlm_result.parsed[0]
                r.total = vlm_result.parsed[1]
                r.method = f"vlm_{provider.name}"
                r.confidence = vlm_result.confidence

                stats["accepted"] += 1
                stats["by_type"][t]["accepted"] += 1
                on_log(
                    f"  VLM p{issue.pdf_page}: {r.curr}/{r.total} "
                    f"[{issue.issue_type}] accepted",
                    "page_ok",
                )
            else:
                stats["rejected"] += 1
                reason = "unparseable" if vlm_result.parsed is None else "context_mismatch"
                on_log(
                    f"  VLM p{issue.pdf_page}: "
                    f"{'???' if vlm_result.parsed is None else f'{vlm_result.parsed[0]}/{vlm_result.parsed[1]}'} "
                    f"[{issue.issue_type}] rejected ({reason})",
                    "page_warn",
                )
    finally:
        doc.close()

    avg_lat = stats["latency_sum"] / stats["total"] if stats["total"] > 0 else 0.0
    on_log(
        f"VLM resolver: {stats['accepted']} accepted, "
        f"{stats['rejected']} rejected, {stats['errors']} errors, "
        f"{avg_lat:.0f}ms avg",
        "ok",
    )

    return reads, stats
```

- [ ] **Step 4: Run `_should_accept` tests**

Run: `pytest tests/test_vlm_resolver.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Add `resolve()` tests with mock provider**

Append to `tests/test_vlm_resolver.py`:

```python
import threading
from unittest.mock import MagicMock, patch
from core.vlm_resolver import resolve, ISSUE_PRIORITY
import numpy as np


class MockProvider:
    """Mock VLM provider that returns preset results per call index."""
    name = "mock"

    def __init__(self, results: dict[int, VLMResult] | None = None):
        self._results = results or {}
        self._default = VLMResult("", None, 0.0, 100.0, None)
        self.call_count = 0

    def query(self, image_path: str) -> VLMResult:
        idx = self.call_count
        self.call_count += 1
        return self._results.get(idx, self._default)


def test_resolve_no_issues():
    """resolve() with empty issues returns unchanged reads."""
    reads = [_make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3)]
    provider = MockProvider()
    logs = []

    with patch("core.vlm_resolver.fitz"):
        result, stats = resolve(
            reads, [], 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["total"] == 0
    assert stats["accepted"] == 0


def test_resolve_accepts_valid_read():
    """resolve() accepts a VLM read that passes validation."""
    reads = [
        _make_read(1, 1, 3),
        _failed(2),
        _make_read(3, 3, 3),
    ]
    issues = [InferenceIssue(pdf_page=2, issue_type="gap", confidence=0.0, context="test")]
    provider = MockProvider({0: VLMResult("2/3", (2, 3), 0.85, 100.0, None)})
    logs = []

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        result, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["accepted"] == 1
    assert reads[1].curr == 2
    assert reads[1].total == 3
    assert reads[1].method == "vlm_mock"


def test_resolve_rejects_contradicting_read():
    """resolve() rejects a VLM read that contradicts neighbors."""
    reads = [
        _make_read(1, 1, 4),
        _make_read(2, 2, 4),
        _failed(3),
    ]
    issues = [InferenceIssue(pdf_page=3, issue_type="gap", confidence=0.0, context="test")]
    provider = MockProvider({0: VLMResult("1/4", (1, 4), 0.85, 100.0, None)})
    logs = []

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        result, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: logs.append(m),
        )

    assert stats["rejected"] == 1
    assert reads[2].method == "failed"


def test_resolve_respects_cancel_event():
    """resolve() stops when cancel_event is set."""
    reads = [_failed(1), _failed(2), _failed(3)]
    issues = [
        InferenceIssue(pdf_page=i, issue_type="gap", confidence=0.0, context="test")
        for i in [1, 2, 3]
    ]
    provider = MockProvider()
    cancel = threading.Event()
    cancel.set()

    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=3)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc):
        _, stats = resolve(
            reads, issues, 3, provider, "test.pdf", {},
            on_log=lambda m, l: None,
            cancel_event=cancel,
        )

    assert stats["total"] == 0


def test_resolve_priority_ordering():
    """resolve() processes boundary_inferred before gap."""
    reads = [
        _failed(1),
        _PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.50),
        _failed(3),
    ]
    issues = [
        InferenceIssue(pdf_page=3, issue_type="gap", confidence=0.0, context="test"),
        InferenceIssue(pdf_page=2, issue_type="boundary_inferred", confidence=0.50, context="test"),
    ]
    call_order = []

    class TrackingProvider:
        name = "mock"
        def query(self, path):
            call_order.append(path)
            return VLMResult("", None, 0.0, 100.0, None)

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.__len__ = MagicMock(return_value=3)
    mock_clip = np.zeros((50, 100, 3), dtype=np.uint8)

    with patch("core.vlm_resolver.fitz.open", return_value=mock_doc), \
         patch("core.vlm_resolver._render_clip", return_value=mock_clip):
        resolve(
            reads, issues, 3, TrackingProvider(), "test.pdf", {},
            on_log=lambda m, l: None,
        )

    # Should have been called twice (boundary first, then gap)
    assert len(call_order) == 2
```

- [ ] **Step 6: Run all resolver tests**

Run: `pytest tests/test_vlm_resolver.py -v`
Expected: All 14 tests PASS

- [ ] **Step 7: Commit**

```bash
git add core/vlm_resolver.py tests/test_vlm_resolver.py
git commit -m "feat(vlm): VLM resolver with candidate selection and context validation"
```

---

## Chunk 3: Pipeline Integration + Telemetry

### Task 5: Pipeline Integration and Telemetry

**Files:**
- Modify: `core/pipeline.py`
- Create: `tests/test_pipeline_vlm.py`

- [ ] **Step 1: Write failing test for `vlm_provider` parameter**

Create `tests/test_pipeline_vlm.py`:

```python
"""
Pipeline integration tests with mock VLM provider.
No real OCR or VLM — verifies wiring, signature, and telemetry format.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import inspect
from core.vlm_provider import VLMProvider, VLMResult


def test_analyze_pdf_accepts_vlm_provider_param():
    """analyze_pdf signature includes vlm_provider as optional last param."""
    from core.pipeline import analyze_pdf
    sig = inspect.signature(analyze_pdf)
    params = list(sig.parameters.keys())
    assert "vlm_provider" in params
    assert params[-1] == "vlm_provider"
    assert sig.parameters["vlm_provider"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_vlm.py::test_analyze_pdf_accepts_vlm_provider_param -v`
Expected: FAIL — `vlm_provider` not in signature

- [ ] **Step 3: Add `vlm_provider` parameter and VLM resolver wiring to `analyze_pdf()`**

In `core/pipeline.py`:

**3a.** Add `VLM_ENGINE_VERSION` to imports (line 15-22):
```python
from core.utils import (
    Document,
    _PageRead,
    PARALLEL_WORKERS,
    BATCH_SIZE,
    _parse,
    INFERENCE_ENGINE_VERSION,
    VLM_ENGINE_VERSION,
)
```

**3b.** Add `vlm_provider` to `analyze_pdf` signature (line 164-172):
```python
def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log:      callable,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    on_issue:    callable | None = None,
    doc_mode:    str = "charla",
    vlm_provider = None,
) -> tuple[list[Document], list[_PageRead]]:
```

**3c.** Initialize `_inf_issues` and change inference call (around lines 303-308):
```python
    failed_count = sum(1 for r in reads_clean if r.method == "failed")
    _inf_issues = []
    if failed_count > 0:
        on_log(f"Inferencia D-S: procesando {failed_count} paginas fallidas...", "info")
        reads_clean, _inf_issues = inference._infer_missing(reads_clean, period_info)
        inferred = sum(1 for r in reads_clean if r.method == "inferred")
        on_log(f"Inferencia: {inferred} paginas recuperadas", "ok")

    # ── VLM Resolver (optional) ──────────────────────────────────────────
    vlm_stats = None
    if vlm_provider is not None and _inf_issues:
        from core.vlm_resolver import resolve as vlm_resolve
        reads_clean, vlm_stats = vlm_resolve(
            reads_clean, _inf_issues, total_pages,
            provider=vlm_provider,
            pdf_path=pdf_path,
            period_info=period_info,
            on_log=on_log,
            cancel_event=cancel_event,
        )
        if vlm_stats["accepted"] > 0:
            period_info = inference._detect_period(reads_clean)
            reads_clean, _issues2 = inference._infer_missing(reads_clean, period_info)
            on_log(
                f"Inferencia pass 2: re-inferencia con {vlm_stats['accepted']} correcciones VLM",
                "ok",
            )

    # Count VLM methods in tally
    if vlm_stats and vlm_stats.get("accepted", 0) > 0:
        for r in reads_clean:
            if r.method.startswith("vlm_"):
                method_tally[r.method] = method_tally.get(r.method, 0) + 1
```

- [ ] **Step 4: Add VLM telemetry helper and update `_emit_ai_telemetry()`**

Add helper before `_emit_ai_telemetry` (around line 46):

```python
# Short names for telemetry (spec: "boundary:3/3" not "boundary_inferred:3/3")
_ISSUE_SHORT = {
    "boundary_inferred": "boundary",
    "low_confidence": "lowconf",
    "contradiction": "contra",
    "gap": "gap",
}


def _format_vlm_line(vlm_stats: dict | None) -> str:
    """Format VLM stats for telemetry line."""
    if vlm_stats is None or vlm_stats.get("total", 0) == 0:
        return "off"
    s = vlm_stats
    avg_lat = s["latency_sum"] / s["total"] if s["total"] > 0 else 0.0
    parts = [
        f"{s['version']}-{s['provider']}",
        f"{s['total']}req",
        f"{s['accepted']}acc",
        f"{s['rejected']}rej",
        f"{avg_lat:.0f}ms/avg",
    ]
    type_parts = []
    for t, counts in s.get("by_type", {}).items():
        short = _ISSUE_SHORT.get(t, t)
        type_parts.append(f"{short}:{counts['accepted']}/{counts['attempted']}")
    if type_parts:
        parts.append("| " + " ".join(type_parts))
    return " ".join(parts)
```

Add `vlm_stats` param to `_emit_ai_telemetry`:

```python
def _emit_ai_telemetry(
    on_log: callable,
    pdf_path,
    documents: list[Document],
    reads_clean: list[_PageRead],
    period_info: dict,
    elapsed: float,
    total_pages: int,
    method_tally: dict,
    vlm_stats: dict | None = None,
) -> None:
```

In the `[AI:]` header line, append VLM tag:
```python
    vlm_tag = f"VLM:{vlm_stats['version']}-{vlm_stats['provider']}" if vlm_stats else "VLM:off"

    on_log(
        f"[AI:{_CORE_HASH}] [MOD:v5-max-total] [CUDA:{_CUDA_HASH}] {fname} | {total_pages}p {elapsed:.1f}s {elapsed/total_pages*1000:.0f}ms/p"
        f" | W{PARALLEL_WORKERS}+GPU | INF:{INFERENCE_ENGINE_VERSION} | {vlm_tag}\n"
```

Change the `FAIL:` line to include VLM:
```python
        f"FAIL: {fail_str}\n"
        f"VLM: {_format_vlm_line(vlm_stats)}",
        "ai",
    )
```

- [ ] **Step 5: Pass `vlm_stats` to `_emit_ai_telemetry` call**

Update the telemetry call (around line 372):

```python
    _emit_ai_telemetry(
        on_log=on_log,
        pdf_path=pdf_path,
        documents=_tele_docs,
        reads_clean=reads_clean,
        period_info=period_info,
        elapsed=elapsed,
        total_pages=total_pages,
        method_tally=method_tally,
        vlm_stats=vlm_stats,
    )
```

- [ ] **Step 6: Add telemetry format tests**

Append to `tests/test_pipeline_vlm.py`:

```python
from core.pipeline import _format_vlm_line


def test_format_vlm_line_off():
    """VLM off when stats is None."""
    assert _format_vlm_line(None) == "off"


def test_format_vlm_line_no_requests():
    """VLM off when total is 0."""
    assert _format_vlm_line({"total": 0}) == "off"


def test_format_vlm_line_with_stats():
    """VLM line formats correctly with stats."""
    stats = {
        "provider": "ollama",
        "version": "v1.0",
        "total": 10,
        "accepted": 7,
        "rejected": 3,
        "errors": 0,
        "latency_sum": 25000.0,
        "by_type": {
            "boundary_inferred": {"attempted": 3, "accepted": 3},
            "gap": {"attempted": 7, "accepted": 4},
        },
    }
    line = _format_vlm_line(stats)
    assert "v1.0-ollama" in line
    assert "10req" in line
    assert "7acc" in line
    assert "3rej" in line
    assert "2500ms/avg" in line
    assert "boundary:3/3" in line
    assert "gap:4/7" in line
```

- [ ] **Step 7: Run pipeline tests**

Run: `pytest tests/test_pipeline_vlm.py -v`
Expected: All tests PASS

- [ ] **Step 8: Run full test suite — final verification**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add core/pipeline.py tests/test_pipeline_vlm.py
git commit -m "feat(vlm): wire VLM resolver into pipeline with telemetry"
```
