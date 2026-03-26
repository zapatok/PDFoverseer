# VLM Resolver — Post-Inference Vision Language Model Integration

**Date:** 2026-03-25
**Status:** Design approved (brainstorming)
**Branch:** TBD (will use worktree)

---

## Problem

The OCR pipeline produces ~15-20% failure pages (no page number detected) on real-world CRS lecture PDFs. The inference engine recovers most via constraint propagation, but some remain low-confidence or unresolved.

VLM models (Gemma 3 4B local, Claude Haiku 4.5 API) achieve 79-89% exact accuracy on these failure pages. However, naively filling all OCR gaps with VLM reads **worsens** inference by -7.1pp because:

1. Failure gaps serve as natural document boundary separators
2. Some VLM reads are incorrect, causing document merges
3. The inference engine is robust to gaps but fragile to wrong reads

## Solution

A **post-inference selective VLM resolver** that:
1. Lets OCR + inference run normally (pass 1)
2. Identifies problematic pages from inference metadata
3. Selectively queries a VLM provider on high-impact candidates
4. Validates VLM reads against context before accepting
5. Re-runs inference with corrected reads (pass 2)

This avoids the paradox by only using VLM where the inference engine signals uncertainty, and validating reads before injection.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Separate module (`core/vlm_resolver.py`) | Inference stays pure, VLM is optional with zero overhead when disabled |
| Execution timing | Post-inference, pre-document-building | Inference already knows which pages are problematic |
| Provider model | Plugin/strategy pattern, Ollama default | User can swap providers; local is free, Claude is higher accuracy |
| User interaction | Transparent with telemetry | Automatic, no user confirmation needed; VLM methods visible in UI/logs |
| Call budget | Unlimited (filtered by inference issues) | Post-inference selection is already surgical; Ollama is free |
| Validation | Context-aware pre-insertion checks | Prevents the paradox: reject VLM reads that contradict neighbors |

## Architecture

```
OCR scan (pipeline.py)
    ↓
Inference pass 1: _detect_period + _infer_missing (inference.py)
    ↓ returns: (reads[], issues[])
VLM Resolver (core/vlm_resolver.py)              ← NEW
    ↓ selects candidates from issues
    ↓ calls VLM provider (core/vlm_provider.py)  ← NEW
    ↓ validates & replaces/confirms reads
    ↓
Inference pass 2: _detect_period + _infer_missing (same functions, fresh run)
    ↓
_build_documents → Final documents + telemetry
```

**Note:** Pass 2 calls `_detect_period` + `_infer_missing` directly (not `re_infer_documents`, which is for manual corrections and resets inferred reads to failed first).

## Files

### New Files

#### `core/vlm_provider.py` — VLM Provider Interface

Formalizes the VLM backend as a pluggable strategy. Each provider implements a common interface.

```python
@dataclass
class VLMResult:
    """Result from a VLM query."""
    raw_text: str
    parsed: tuple[int, int] | None   # (curr, total) or None if unparseable
    confidence: float                  # parser confidence (0.0-1.0)
    latency_ms: float
    error: str | None

class VLMProvider(ABC):
    """Abstract base for VLM backends."""
    name: str                          # "ollama" | "claude"

    @abstractmethod
    def query(self, image_path: str) -> VLMResult:
        """Send image to VLM and return parsed result."""
        ...

class OllamaProvider(VLMProvider):
    """Gemma 3 4B via local Ollama server."""
    name = "ollama"
    # Config: model="gemma3:4b", prompt=Spanish, temp=0.3, upscale=1.5

class ClaudeProvider(VLMProvider):
    """Claude Haiku 4.5 via Anthropic API."""
    name = "claude"
    # Config: model="claude-haiku-4-5-20251001", prompt=Spanish, temp=0.3
```

**Key design points:**
- Prompt, temperature, upscale are hardcoded from sweep1 winner config (Spanish prompt, temp=0.3, top_p=1.0, upscale=1.5)
- Parser logic migrated from `vlm/parser.py` (multi-pattern extraction)
- `vlm/client.py` and `vlm/parser.py` are NOT modified — they belong to the benchmark harness
- Provider instantiation: `OllamaProvider()` or `ClaudeProvider(api_key=...)` — no global state

#### `core/vlm_resolver.py` — VLM Resolver Module

The orchestrator. Three responsibilities: select, execute, validate.

```python
@dataclass
class InferenceIssue:
    """A problematic page identified by the inference engine."""
    pdf_page: int
    issue_type: str       # "low_confidence" | "contradiction" | "gap" | "boundary_inferred"
    confidence: float     # current confidence (0.0 for gaps)
    context: str          # brief description for telemetry

# Priority order for candidate selection:
ISSUE_PRIORITY = {
    "boundary_inferred": 0,   # curr=1 inferred: confirming/rejecting changes entire docs
    "contradiction":     1,   # conflicting reads: VLM as tiebreaker
    "low_confidence":    2,   # uncertain inference: VLM as confirmation
    "gap":               3,   # no read at all: VLM as last resort (cautious)
}

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
    """
    Selectively query VLM for problematic pages and return corrected reads.

    Args:
        pdf_path: Path to PDF file — used to render image strips on demand
                  via fitz.open() + core/image._render_clip().
        period_info: Period detection results from pass 1 (for validation).
        cancel_event: Cooperative cancellation — checked between VLM calls.

    Returns:
        (corrected_reads, vlm_telemetry_dict)

    The corrected reads are suitable for re-inference (pass 2).
    """
```

**Candidate selection** — sorted by `ISSUE_PRIORITY`:

| Priority | Type | Why highest impact |
|----------|------|-------------------|
| 0 | `boundary_inferred` | Confirming/rejecting curr=1 changes entire document boundary |
| 1 | `contradiction` | Cross-validation detected conflicting reads; VLM as tiebreaker |
| 2 | `low_confidence` | D-S score < 0.60; VLM can confirm or replace |
| 3 | `gap` | No read after all phases; VLM as last resort with extra caution |

**Validation pre-insertion** (`_should_accept`):

```python
def _should_accept(
    vlm_result: VLMResult,
    page_idx: int,
    reads: list[_PageRead],
    period_info: dict,
) -> bool:
    """
    Accept VLM read only if coherent with surrounding context.
    This is what prevents the paradox.
    """
    # 1. Reject if parsed is None (unparseable response)
    # 2. Reject if total contradicts period's expected_total (when period is strong)
    # 3. Reject if curr contradicts high-confidence neighbors
    #    (e.g., neighbor says curr=3, VLM says curr=1 — likely wrong)
    # 4. Accept if confirms existing low-confidence read (same curr/total)
    # 5. Accept if fills gap with sequential coherence
    #    (prev.curr + 1 == vlm.curr, or prev.curr == prev.total and vlm.curr == 1)
```

**Execution flow per candidate:**
1. Open PDF via `fitz.open(pdf_path)`, get `fitz.Page` for the target page
2. Render image strip via `core/image._render_clip(page)` → returns `np.ndarray` (BGR)
3. Upscale 1.5x with `cv2.resize()` (from sweep1 winner config)
4. Save to temp file (`tempfile.NamedTemporaryFile(suffix=".png")`) → `image_path`
5. Call `provider.query(image_path)`
6. Clean up temp file
7. If error or no parse → skip (no worse than before)
8. If `_should_accept()` → replace read with VLM result; method = `vlm_ollama` or `vlm_claude`
9. If rejected → log reason, keep original read
10. If `cancel_event` is set → break loop, return partial results

**Performance note:** The PDF is opened once and kept open for all candidates. Temp files are used because both Ollama and Claude providers expect file paths (base64 encoding happens inside the provider).

**Read replacement:**
```python
# When accepted:
read.curr = vlm_result.parsed[0]
read.total = vlm_result.parsed[1]
read.method = f"vlm_{provider.name}"  # "vlm_ollama" or "vlm_claude"
read.confidence = vlm_result.confidence
```

### Modified Files

#### `core/inference.py` — Export InferenceIssues (~15 lines added)

**Change:** `_infer_missing()` returns `tuple[list[_PageRead], list[InferenceIssue]]` instead of `list[_PageRead]`.

Issue collection points (all already detected internally, just need to export):

| Phase | Issue type | Detection point | New logic? |
|-------|-----------|----------------|------------|
| Phase 5 (D-S) | `low_confidence` | Lines 418-420: `r.method == "inferred" and r.confidence <= 0.60` | No — export existing |
| Phase 3 (xval) | `contradiction` | Lines 378-396: inferred pages where `consistent = False` and conf capped at 0.50 | Minor — add issue alongside existing cap |
| Phase 4 (fallback) | `gap` | Lines 402-409: pages still `"failed"` after gap solver | No — export existing |
| Phase 1-2 (gap solver) | `boundary_inferred` | Lines 344-361: when inferred `curr=1` at gap start/after prev.curr==prev.total | Minor — add issue at assignment |

**Signature change:**
```python
# Before:
def _infer_missing(reads, period_info) -> list[_PageRead]:

# After:
def _infer_missing(reads, period_info) -> tuple[list[_PageRead], list[InferenceIssue]]:
```

Callers to update:
- `core/pipeline.py` line 306: `reads_clean = inference._infer_missing(...)` → unpack tuple
- `core/pipeline.py` line 420 (inside `re_infer_documents`): `reads = inference._infer_missing(...)` → unpack tuple (issues discarded here since VLM already ran)
- **Out of scope:** `eval/inference.py` has its own copy of the inference pipeline; it does not need this change since the eval harness does not use VLM.

#### `core/pipeline.py` — VLM Resolver Integration (~25 lines)

After inference pass 1, before document building:

```python
# Existing (updated to unpack tuple):
reads_clean, issues = inference._infer_missing(reads_clean, period_info)

# New (≈20 lines):
if vlm_provider is not None:
    from core.vlm_resolver import resolve as vlm_resolve
    corrected, vlm_stats = vlm_resolve(
        reads_clean, issues, total_pages,
        provider=vlm_provider,
        pdf_path=pdf_path,
        period_info=period_info,
        on_log=on_log,
        cancel_event=cancel_event,
    )
    if vlm_stats["accepted"] > 0:
        # Re-run period detection + inference with VLM-corrected reads
        period_info = inference._detect_period(corrected)
        corrected, _issues2 = inference._infer_missing(corrected, period_info)
        reads_clean = corrected

documents = inference._build_documents(reads_clean, on_log, _issue, period_info)
```

**Thread safety:** The VLM resolver runs on the main pipeline thread, after OCR producers and GPU consumer have finished. No concurrent access to reads. Provider HTTP calls are sequential (one image at a time).

**`analyze_pdf()` signature change** (preserving existing parameter order):
```python
def analyze_pdf(
    pdf_path: str,
    on_progress: callable,               # existing (required)
    on_log: callable,                     # existing (required)
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    on_issue: callable | None = None,
    doc_mode: str = "charla",
    vlm_provider: VLMProvider | None = None,   # ← NEW, optional, last
) -> tuple[list[Document], list[_PageRead]]:
```

When `vlm_provider is None`, the pipeline is identical to today — zero overhead.

#### `core/utils.py` — VLM Method Constants (~3 lines)

Add VLM methods to any method-checking logic:

```python
VLM_METHODS = {"vlm_ollama", "vlm_claude"}
VLM_ENGINE_VERSION = "v1.0"  # VLM resolver version tag for telemetry
```

### Telemetry

#### `[AI:]` Block — New VLM Line

Added after the existing `FAIL:` line:

```
VLM: v1.0-ollama 12req 8acc 4rej 1847ms/avg | boundary:3/3✓ contrad:2/4✓ lowconf:3/5✓
```

Format: `VLM: <version>-<provider> <total_requests>req <accepted>acc <rejected>rej <avg_latency>ms/avg | <type>:<accepted>/<attempted>✓ ...`

When VLM is not active: `VLM: off`

#### Version Tag

New constant `VLM_ENGINE_VERSION` in `core/utils.py`, displayed in the `[AI:]` block alongside `INF:<inference_version>`:

```
[AI:2e436564] [MOD:v5-max-total] [CUDA:abc12345] file.pdf | 100p 5.2s 52ms/p | W6+GPU | INF:s2t-helena | VLM:v1.0-ollama
```

When VLM is off:
```
... | INF:s2t-helena | VLM:off
```

### Files NOT Modified

- `core/ocr.py` — VLM does not interfere with OCR tiers
- `core/image.py` — VLM reuses `_render_clip()` as-is
- `api/*` — API layer is unaware of VLM; it's transparent
- `vlm/client.py`, `vlm/parser.py`, `vlm/benchmark.py` — benchmark harness stays independent

## Image Handling

The VLM resolver renders image strips on demand from the PDF:

1. Open PDF once via `fitz.open(pdf_path)` at the start of `resolve()`
2. For each candidate page, get `fitz.Page` object via `doc[page_idx]`
3. Call `core/image._render_clip(page)` → returns `np.ndarray` (BGR)
4. Upscale 1.5x with `cv2.resize(clip, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)`
5. Save to temp file via `cv2.imwrite(tmp_path, clip)` using `tempfile.NamedTemporaryFile(suffix=".png", delete=False)`
6. Pass `tmp_path` to `provider.query(image_path)`
7. Delete temp file after query completes

This avoids caching thousands of images and reuses existing crop infrastructure. The PDF is opened once per `resolve()` call, not per candidate.

**Note:** `_render_clip` uses full-page rendering (not just the crop region used for OCR). The VLM sees the full top-right corner strip which contains the page number — same region that Tesseract and EasyOCR process.

## VLM Response Parsing

Copied from `vlm/parser.py` (5 patterns + fallback heuristic):

```python
PARSE_PATTERNS = [
    r"P[áa]g(?:ina)?\.?\s*(\d{1,3})\s*de\s*(\d{1,3})",  # "Página 3 de 10"
    r"Page\s+(\d{1,3})\s+of\s+(\d{1,3})",                 # "Page 3 of 10"
    r"(\d{1,3})\s+out\s+of\s+(\d{1,3})",                  # "3 out of 10"
    r"(?<!\d)(\d{1,3})\s+de\s+(\d{1,3})(?!\d)",           # "3 de 10" (bare)
    r"(?<!\d)(\d{1,3})/(\d{1,3})(?!\d)",                   # "3/10" (direct)
]
# Fallback: find exactly two standalone integers ≤ 999
```

Validation: `1 <= curr <= total` (same as `vlm/parser.py`).

**Confidence heuristic** (new — not in benchmark parser, needs tuning via eval):
- Named pattern match (Página/Page/de) → 0.85
- Direct N/M match → 0.85
- Fallback two-integer heuristic → 0.60
- No match → 0.0 (rejected)

## Cascade Effect

A single VLM correction can resolve multiple pages via re-inference:

**Example:** VLM confirms `curr=1, total=4` at page 100 (was `boundary_inferred` at 42% confidence).
- Pass 2 inference: Phase 1-2 propagate forward → pages 101-103 get `curr=2,3,4` at high confidence
- Phase 5 D-S: period alignment boosts neighboring documents
- Net: 1 VLM call resolves 4 pages

This is why the priority system targets boundaries first — maximum cascade impact per VLM call.

## Configuration

All configuration lives in `core/utils.py` alongside existing constants:

```python
# VLM Resolver
VLM_ENGINE_VERSION    = "v1.0"
VLM_PROMPT            = "Que numero de pagina dice esta imagen? Formato: N/M"
VLM_TEMPERATURE       = 0.3
VLM_TOP_P             = 1.0
VLM_UPSCALE           = 1.5
VLM_MIN_ACCEPT_CONF   = 0.50    # min parser confidence to accept a VLM read
```

## Testing Strategy

1. **Unit tests** (`tests/test_vlm_provider.py`):
   - Provider interface contract (mock HTTP)
   - Response parsing (all 4 patterns + edge cases)
   - Confidence scoring

2. **Unit tests** (`tests/test_vlm_resolver.py`):
   - `_should_accept()` with various neighbor/period contexts
   - Candidate selection priority ordering
   - Integration with mock provider (no real VLM calls)
   - Read replacement logic (method, confidence)

3. **Integration tests** (`tests/test_pipeline_vlm.py`):
   - Pipeline with mock VLM provider → verify re-inference triggers
   - Pipeline with `vlm_provider=None` → verify zero overhead / identical behavior

4. **Eval harness** (manual):
   - Run ART_670 with VLM resolver enabled vs disabled
   - Compare document counts, completeness, accuracy against enriched fixture

## Future Extensions

- **Provider fallback chain:** Ollama → Claude (if Ollama fails or confidence low)
- **Batch VLM calls:** Send multiple images per API call (Claude supports this)
- **Adaptive thresholds:** Tune `VLM_MIN_ACCEPT_CONF` based on provider accuracy
- **Phase E integration:** Global coherence validation after VLM pass
