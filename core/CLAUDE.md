# core/ — OCR Pipeline & Inference Engine

## Counting architecture (read first)

PDFoverseer counts documents per (hospital, sigla) in two passes, dispatched by
`core/scanners/patterns.py` (one `scan_strategy` per sigla):

- **Pase 1 — filename glob** (`SimpleFilenameScanner`): ~90% of cells. 1 PDF = 1
  document, no OCR. Counts recursively via `count_pdfs_by_sigla`.
- **Pase 2 — OCR** (`AnchorsScanner` / `PaginationScanner`): the implicit
  compilations. See **Scanner Architecture** at the end for the triad.

Pase-1 filename matching has two per-sigla escape hatches (Fase 5, F14/F6/F14a
— `core/scanners/patterns.py:SiglaPattern` + `core/scanners/utils/filename_glob.py`),
both needed because a few real-corpus files don't carry a clean sigla token:

- **`count_scope: "folder"`** (default `"token"`) — the resolved category
  folder itself is the classifier; every PDF inside counts, no filename token
  required. Only `chps` uses this today: its real files are unnamed by
  convention (`crs.pdf`, `titan.pdf`).
- **`_SIGLA_TOKEN_ALIASES`** (`filename_glob.py`) — extra filename tokens that
  resolve to a sigla beyond its literal name: `chps` also matches the real
  corpus's `"cphs"` spelling, and `revdocmaq` (which has no `"revdocmaq"` token
  anywhere in the corpus) matches the phrase `"revision_documentacion"`.

The **V4 pipeline** documented immediately below is **quarantined**: a
**deferred fallback** (spec decision D10), wired to **nothing**. It is not
reached through `PaginationScanner` or any other scanner — `PaginationScanner`
counts via a separate, much lighter engine, `utils/pagination_count.py` (see
**PaginationScanner + the pagination engine** below), which does its own OCR +
recovery and never imports `pipeline.py`/`inference.py`/`ocr.py`. A second,
unrelated adapter, `utils/v4_count.py`, bridges V4's `analyze_pdf` into a
`ScanResult` shape but is itself unwired — its only importer is its own test
(`tests/unit/scanners/utils/test_v4_count.py`). `core/__init__.py` deliberately
does not eagerly import the V4 cluster either (see its module docstring) so a
plain `import core.*` no longer probes cv2/torch. The V4 / inference sections
below describe that quarantined engine's internals, kept importable for
tests/tools only; the active, current design is the scanner triad.

## V4 Pipeline (pipeline.py — deferred fallback, wired to nothing)

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


## Scanner Architecture (ocr-per-sigla, `v1-ocr-per-sigla`)

The pase-2 OCR counting layer lives in `core/scanners/` and is **data-driven**:
`patterns.py` is the single source of truth — one entry per sigla for all 20
SIGLAS (enforced by a completeness-gate test,
`tests/unit/scanners/test_patterns_registry.py`).

### The scanner triad

`register_defaults()` builds one scanner per sigla, picked by the
`scan_strategy` field of its `patterns.py` entry:

| scan_strategy | Scanner | Counting technique |
|---------------|---------|--------------------|
| `none` | `SimpleFilenameScanner` | filename glob only (pase 1) |
| `anchors` | `AnchorsScanner` | OCR the header band, match flavor anchors |
| `pagination` | `PaginationScanner` | count documents via the pagination engine ("Página N de M" corner OCR + lite recovery) |

Distribution today (20 siglas, after the 2026-06-23 revdocmaq/espacios
additions): 2 `none` (reunion, revdocmaq — the latter has no OCR samples yet,
provisional), 6 `anchors` (charla, chintegral, dif_pts — RCH "1 de 2" bug;
senal — landscape; chps; maquinaria — `count_type=checks`), 12 `pagination`
(art, irl [`cover_code`], odi, insgral, bodega, caliente, exc, ext, altura,
herramientas_elec, andamios, espacios).

### OcrScannerBase (shared harness)

`AnchorsScanner` and `PaginationScanner` both subclass `OcrScannerBase`
(`ocr_scanner_base.py`) — a Template Method that owns the ~75% shared `count_ocr`
scaffolding (folder guard, PDF enumeration, `only`/`skip` filtering, the per-PDF
loop with cancel + A7 + `on_pdf` emit semantics, and `ScanResult` assembly). Each
subclass implements only `_count_one_pdf(pdf)` (page-count + A7 + its engine +
fallback → a `_PdfOutcome`) plus an optional `_precheck` (anchors' no-flavors
short-circuit). The per-PDF I/O (`get_page_count` + the engine) is kept in the
subclass module so the unit tests' monkeypatches (which target
`core.scanners.{anchors,pagination}_scanner.*`) still bind.

### AnchorsScanner

OCRs the top fraction of each page (`top_fraction`, default 0.25) and counts a
page as a document **cover** when it matches at least `min_match` of a flavor's
text **anchors**. A sigla may declare several **flavors** (template variants);
a flavor may declare **anti_anchors** that reject a page even when anchors
match (kills cross-category misfiles and shadow covers). Anchors are structural
text — titles, field labels, pagination — never raw form codes (decision A12).

**F8 (honest confidence):** a multi-page PDF for which the engine finds
**zero** covers is low-trust — a genuine multi-page compilation almost never
has 0 covers, so a silent 0 is far more likely a missed/renamed anchor than an
empty cell (live case: senal showed 0/18 with no error, read as "listo"). The
count itself stays 0 (still the honest number); confidence drops to LOW (the
`anchors_low_confidence` flag) so the operator reviews it via the keyboard
counter.

### PaginationScanner + the pagination engine

`PaginationScanner` counts documents by their "Página N de M" pagination via
`utils/pagination_count.count_documents_by_pagination` (the **lite engine**,
introduced at `SCANNER_PATTERNS_VERSION = v4-pagination`; current version is
`v6-token-aliases` — see `core/utils.py`). Per page it OCRs only the
**top-right corner** (orientation-aware), parses the pagination + the form code,
and **recovers** unreadable corners by completing the numeric sequence from
neighbors (plain forward-fill — no autocorrelation / Dempster-Shafer). A document
starts at every `curr == 1`; `cover_code` (IRL) restricts that to covers whose
form code matches (so appendix page-1s inside an induction packet don't count).
A7 still applies (1-page = 1 doc, no OCR). A count that needed heavy recovery
(>30% of pages), had any unresolved failed read, or hit the cover_code-with-recovery
edge downgrades the cell to LOW confidence for review (keyboard counter). **F7**
adds a 4th trigger: without a `cover_code`, *any* recovered document-start
(a recovered `curr==1`) also downgrades to LOW, even a single one far under the
30% heavy-recovery threshold — a recovered `curr==1` is a plausible fabricated
start in a mixed-length compilation, so it can't be trusted silently. (With
`cover_code` set this edge doesn't need its own check: `count_starts` requires
a code match, so a recovered `curr==1` is never counted in the first place —
the cover_code-with-recovery trigger above already covers that case.)

Validated by a real-corpus benchmark (`docs/research/2026-06-21-pagination-benchmark-results.md`):
pagination wins or ties anchors on every paginated sigla (clean ART anchors 0/5 →
pagination 5/5; degraded merged ART −11 → +1 via recovery; herramientas_elec −17 →
60/60). Migrated siglas keep their anchor flavors on the `patterns.py` entry
(unused) for **one-line reversibility** (flip `scan_strategy` back to `anchors`).

> The heavy **V4 pipeline** (`pipeline.py` / `utils/v4_count.py`) is retained in
> the repo as a **deferred fallback** (spec D10) — no longer wired into any
> scanner. It supersedes the original `corner_count` helper that undercounted
> (13/18); the lite engine's recovery layer + honest LOW-confidence routing now
> close that gap without the full solver. RCH (charla/chintegral/dif_pts) stays on
> anchors — its template repeats "Página 1 de 2" on continuations (the bug), so
> pagination would over-count.

### Uniform behaviors

- **A7** — a 1-page PDF counts as 1 document, locked, without OCR.
- **A8** — a missing sigla folder yields count 0 with a `folder_missing` flag,
  never an error.
- **A14** — a page matching `min_match - 1` anchors is surfaced as near-match
  telemetry (`ScanResult.telemetry.near_matches`) — a candidate for a new
  flavor.

Bump `SCANNER_PATTERNS_VERSION` in `utils.py` on any change to the anchor sets
or scan strategies. Fixture/ground-truth conventions: see
`tests/fixtures/scanners/README.md`.
