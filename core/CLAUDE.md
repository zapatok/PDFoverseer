# core/ — OCR Pipeline & Inference Engine

## V4 Pipeline (pipeline.py)

**Tess-SR only** (EasyOCR removed 2026-03-26, see postmortem):
1. **Producers** (6 parallel workers): PyMuPDF rendering + Tesseract (Tier 1 direct + Tier 2 w/ 4x SR GPU bicubic)
2. **Post-scan:** Period detection (autocorrelation) → Dempster-Shafer fusion → Confidence calibration → Report low-confidence inferred pages (<0.60)

## Key Configurations (utils.py)

```python
DPI              = 150                    # Render DPI
CROP_X_START     = 0.70                   # rightmost 30%
CROP_Y_END       = 0.22                   # top 22%
TESS_CONFIG      = "--psm 6 --oem 1"     # Tesseract config
PARALLEL_WORKERS = 6                      # Tesseract concurrency
BATCH_SIZE       = 12                     # Pages per pause checkpoint

# Inference parameters (sweep2: 2026-03-24, 40 fixtures incl. degraded)
MIN_CONF_FOR_NEW_DOC = 0.55   # min confidence to open a new document boundary
CLASH_BOUNDARY_PEN   = 1.5   # gap-solver penalty for clash at boundaries
PHASE4_FALLBACK_CONF = 0.15  # re-enabled: recovers pages the gap solver missed
PH5B_CONF_MIN        = 0.50  # min period confidence to apply phase 5b correction
PH5B_RATIO_MIN       = 0.90  # lowered 0.95→0.90: fixes INS_31, zero regressions on 40 fixtures
ANOMALY_DROPOUT      = 0.0   # soft dropout for singleton anomalies in homogeneous regions
```

## Page Number Pattern

`PAGE_PATTERN_VERSION = "v1-baseline"` — current registry version

`_PAGE_PATTERNS` (v1, baseline):
1. **Primary** `P.{0,6} N de M` — P-prefix, permissive OCR noise

Plausibility guard: `0 < curr <= total <= 10` (confirmed best after guard sweep 2026-03-26)

Matches: "Pagina 1 de 4", "Pag 2 de 3", etc. (Spanish-centric, with OCR digit normalization)

> **Note:** Word-anchor fallback (`\w+ N de M`) was evaluated and reverted — FP rate too high on ART_670.
> Guard variants tried: tot<=9 (worse), tot<=20 (worse), tot<=99 (much worse). tot<=10 is optimal.
> See `docs/superpowers/plans/2026-03-26-word-anchor-fallback.md` for full results.

## Inference Engine

- **Version:** `s2t-helena` (see `INFERENCE_ENGINE_VERSION` in utils.py)
- **Phases 1-5 + MP + 5b:** OCR results → forward/backward propagation → cross-validation → gap-solver → D-S post-validation → multi-period correction
- **Confidence scores:** 0.0-1.0; <0.60 flagged as uncertain
- **Period inference:** Autocorrelation + Dempster-Shafer + neighbor evidence

## OCR Assumptions

- **Spanish-centric regex** for "Pagina N de M" — adapt if needed for other languages
- **OCR digit normalization:** `O→0, I/i/l/L→1, z/Z→2, |→1, t/T→1, '→1`
- **Image preprocessing cascade:** deskew → color removal → red channel → inpainting → unsharp mask
- **Tesseract config:** `--psm 6 --oem 1` (uniform block text)

## GPU Pipeline

- SR Tier 2: PyTorch GPU bicubic 4x upscale inline in each Tesseract worker (~1ms/page vs ~150ms FSRCNN CPU fallback)
- No separate GPU consumer thread — EasyOCR removed after benchmark showed 0-1% accuracy on ART_670 GT pages

## Telemetry Log Format

After each PDF scan, `pipeline.py` emits two machine-dense log blocks:

**`[AI:]` block** (log level `"ai"`) — scan summary:
```
[AI:<core_hash>] [MOD:v6-tess-sr] [CUDA:<hash>] [REG:<pattern_version>] file.pdf | 45p 3.2s 71ms/p | W6 | INF:s2t-helena
PRE5≡ DOC:5 COM:4(80%) INC:1 INF:3
OCR: direct:40,super_resolution:3
DOCS: 5total → 4ok+1bad(seq:0 under:1) | dist: 3p×2 5p×3
INF: 3total(low:1 mid:1 hi:1) | LOW: p12=2/3(42%)
FAIL: 2pp:7,23
```

**`[DS:]` block** (log level `"ai_inf"`) — inference cross-validation:
```
[DS:<core_hash>] D:5 P:P=3 conf=85% expect=3
INF:3 x̄=72% 1✓1~1✗
✓12:2/3d>3/3@91%>1/3d
~15:3/3s>1/3@55%>2/3d
✗7:->=/>1/3@38%>2/3d
```

XVAL entry format: `<pdf_page>:<left_neighbor>><curr>/<total>@<conf%>><right_neighbor>`
Method chars: `d`=direct, `s`=super_resolution, `e`=easyocr (legacy DB records only), `i`=inferred, `f`=failed, `v`=vlm_ollama, `V`=vlm_claude
