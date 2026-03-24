# VLM OCR Prototype — Gemma 3 4B via Ollama

**Date:** 2026-03-24
**Status:** Draft
**Branch:** TBD (feature/vlm-ocr-prototype)

## Goal

Build a standalone benchmark and parameter sweep module that tests Gemma 3 4B (via Ollama) as an OCR fallback for reading "Pagina N de M" patterns from corner crop images of PDF pages. The module must prove viability before any pipeline integration.

## Context

The current OCR pipeline has three tiers:
- **Tier 1:** Tesseract direct — handles ~43% of pages
- **Tier 2:** Tesseract + super-resolution — handles ~37%
- **Tier 3:** EasyOCR (GPU) — recovers only ~0.4% (14 pages across 20 PDFs)

697 pages (20%) fail all tiers. Gemma 3 4B could replace EasyOCR as Tier 3, potentially recovering a significant portion of these failures.

**Test corpus:** 3,465 corner crop images in `data/ocr_all/`, indexed by `all_index.csv`.

## Non-Goals

- Pipeline integration (deferred until viability proven)
- Replacing Tiers 1 or 2
- Supporting models other than Gemma 3 4B (initially)
- Real-time inference optimization

## Module Structure

```
vlm/
├── __init__.py
├── client.py          # Ollama wrapper: query(image, prompt, **kwargs) → str
├── parser.py          # Extract (curr, total) from VLM text output
├── benchmark.py       # Run corpus, measure accuracy/latency vs ground truth
├── sweep.py           # LHS → fine grid → beam search over parameter space
├── params.py          # PARAM_SPACE + PRODUCTION_PARAMS (after sweep)
├── report.py          # Ranked results table
├── ground_truth.py    # Load eval fixtures + all_index.csv → ground truth dict
└── results/           # Sweep result JSONs (gitignored)
```

## Component Design

### client.py — Ollama Wrapper

Single function interface:

```python
def query(image_path: str, prompt: str, model: str = "gemma3:4b",
          temperature: float = 0.0, top_p: float = 1.0) -> dict:
    """Send image to Ollama, return {raw_text, latency_ms, error}."""
```

- HTTP POST to `http://localhost:11434/api/chat` (Ollama vision endpoint)
- Request body: `{"model": "gemma3:4b", "messages": [{"role": "user", "content": prompt, "images": [base64]}], "stream": false, "options": {"temperature": t, "top_p": p, "num_predict": 50, "seed": s}}`
- Response text from `response["message"]["content"]`
- Timeout: 10 seconds per image
- **Warmup:** before benchmarking, send an empty preload request to `/api/generate` with `{"model": "gemma3:4b"}` to load weights into VRAM (documented Ollama method). This avoids penalizing the first real request.
- **`num_predict: 50`** — limit response to 50 tokens (we only need "N/M", prevents rambling)
- **`seed: 42`** — fixed seed for reproducibility across sweep runs (varied in sweep params for robustness testing)
- Single retry on connection error
- **Latency from Ollama response:** use `total_duration` field (nanoseconds) from the API response instead of Python-side timing — more accurate, excludes HTTP overhead
- Returns `{"raw_text": str, "latency_ms": float, "error": str | None}`

### parser.py — Response Parser

```python
def parse(raw_text: str) -> tuple[int, int] | None:
    """Extract (curr, total) from VLM response text."""
```

Multiple regex patterns to handle VLM output variation:
- `N/M` (direct format as requested in prompt)
- `Pagina N de M` (Spanish, with accent variations)
- `Page N of M` (English)
- `N de M`, `N out of M`
- Fallback: find two integers in text where both are <= 999, treat as (curr, total)

Returns `None` if no pattern matches.

### ground_truth.py — Ground Truth Loader

```python
def load_ground_truth() -> dict[tuple[str, int], tuple[int, int]]:
    """Return {(pdf_nickname, page_num): (curr, total)} from available sources."""
```

Priority:
1. **Tesseract reads** — pages where `tier1_parsed` or `tier2_parsed` succeeded in `all_index.csv`
2. **Eval fixtures** — `eval/fixtures/real/*.json` reads with `curr` and `total`, **excluding** reads where `method` is `"inferred"` or `"failed"` (only `"direct"`, `"super_resolution"`, `"easyocr"` are trusted as ground truth)
3. Pages with no ground truth are excluded from accuracy scoring but included in `parse_rate`

**Note:** `image_path` in `all_index.csv` is relative to `data/ocr_all/`. The `tier1_parsed` column contains `"N/M"` strings that must be split into `(curr, total)` integers.

### benchmark.py — Benchmark Runner

```python
def run(config: dict, failures_only: bool = True) -> dict:
    """Run benchmark with given config, return metrics dict."""
```

Execution flow:
1. Load ground truth via `ground_truth.py`
2. Filter corpus: `--failures-only` (default) filters to images where both `tier1_parsed` and `tier2_parsed` are empty in `all_index.csv` (~697 images); `--full` uses all 3,465 images; `--sample N` picks N random images for quick sanity checks
3. For each image:
   a. Preprocess according to config (`none` / `grayscale` / `otsu` / `contrast`)
   b. Upscale if configured
   c. `client.query(image, prompt, temp, top_p)`
   d. `parser.parse(raw_text)` → `(curr, total) | None`
   e. Compare vs ground truth
4. Calculate metrics, save JSON

CLI interface:
```bash
python -m vlm.benchmark                          # failures-only, default params
python -m vlm.benchmark --full                    # all 3,465 images
python -m vlm.benchmark --sample 50                 # quick sanity check (50 random images)
python -m vlm.benchmark --prompt "..." --temp 0.1   # custom params
```

### params.py — Parameter Space

```python
PARAM_SPACE = {
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

```

### sweep.py — Parameter Sweep

Three-pass optimization (mirrors `eval/sweep.py`):

1. **LHS pass** — 80 random configs from 576-space
2. **Fine grid** — top-10 winners → adjacent parameter variations
3. **Beam search** — top-3 → exhaustive neighborhood

Each config runs `benchmark.run(config, failures_only=True)`.

Results saved as JSON **per config** (not per pass) in `vlm/results/` for crash resilience. Progress logged to console: `"config 15/80, exact_match=0.68, ETA 5h 20m"`.

**Wall-clock estimate:** 697 images × ~500ms/image = ~6 min/config. Pass 1 (80 configs) ≈ 8 hours. The sweep can use `--sample N` to run on a subset for faster iteration.

**First run optimization:** Before pass 1, run a quick seed-stability check (3 seeds × 1 prompt × temp=0 × 20 images). If results are identical across seeds at temp=0, drop `seed` from the sweep space (1,728 → 576 combinations).

### report.py — Results Report

Reads sweep JSON files, prints ranked table:

```
Rank  exact_match  curr_match  parse_rate  latency_ms  prompt(abbrev)  temp  top_p  preprocess  upscale
  1       0.72        0.78       0.91         340       "Read the..."   0.0   1.0   grayscale     1.5
  2       0.70        0.76       0.89         355       "Extract..."    0.1   0.9   none          1.0
  ...
```

Ranking: `exact_match` desc → `curr_match` desc → `mean_latency_ms` asc.

## Scoring

```python
score = {
    "exact_match": n_correct / n_with_gt,      # curr AND total correct
    "curr_match":  n_curr_ok / n_with_gt,       # curr correct (total may differ)
    "parse_rate":  n_parsed / n_total,           # parseable response (even if wrong)
    "mean_latency_ms": mean(times),
    "p95_latency_ms":  percentile(times, 95),
}
```

## Image Preprocessing

Applied before sending to Ollama:

| Mode | Description |
|------|-------------|
| `none` | Raw PNG as captured by the pipeline |
| `grayscale` | Convert to single-channel grayscale |
| `otsu` | Otsu binarization (same as Tesseract tier) |
| `contrast` | CLAHE adaptive contrast enhancement |

Upscale (1.0x / 1.5x / 2.0x) applied after preprocessing via `cv2.resize` with `INTER_CUBIC`.

**Note on Gemma 3 image handling:** The model normalizes all input images to **896×896 pixels**, encoded to **256 tokens** (per Google model card). Our crops are ~372×367px, so the model upscales internally. The `upscale` parameter tests whether upscaling *before* sending (with a better interpolation method) improves results vs letting the model's internal resize handle it. If sweep shows no difference, this parameter can be dropped.

## Dependencies

- `requests` (already in requirements.txt)
- `opencv-python` (already in requirements.txt as `opencv-python-headless`)
- `numpy` (already in requirements.txt)
- **Ollama** must be running locally with `gemma3:4b` pulled (`ollama pull gemma3:4b`)

No new pip dependencies required.

**Note:** Ollama with Gemma 3 4B uses ~4-5GB VRAM. Do not run concurrently with EasyOCR/PyTorch to avoid OOM on 8GB GPUs.

## Success Criteria

The prototype is considered viable if:
- `exact_match` > 50% on the 697 failure images (recovers more than ~350 pages)
- `parse_rate` > 80% (model understands the task most of the time)
- `mean_latency_ms` < 2000 (under 2s per image, acceptable for Tier 3 fallback)

For context, EasyOCR currently recovers 14 of ~697 failures (2%). Even 20% recovery would be a significant improvement.

## Risks

- **Gemma 3 4B quality:** Small VLMs may struggle with low-quality scanned images; the sweep explores preprocessing to mitigate this
- **Ollama latency:** Local inference on ~8GB VRAM GPU; batch of 697 images at ~500ms each ≈ 6 minutes (acceptable for benchmark)
- **Ground truth gaps:** Some failure pages may have no ground truth from inference; these are excluded from accuracy but tracked via parse_rate
