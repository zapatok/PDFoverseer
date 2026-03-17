# Pixel Density First-Page Detector — Design Spec

**Date:** 2026-03-16
**Branch:** feature/pixel-density
**Worktree:** `.worktrees/pixel-density/`
**Status:** Design Review

---

## Overview

Standalone script that detects document start pages in a PDF using pixel darkness density — the fraction of dark pixels in a low-resolution grayscale thumbnail of each page. The hypothesis: first pages of CRS documents have a visually distinctive ink density (headers, stamps, tables) that is consistent enough to identify them without OCR.

This is a validation experiment. No integration with the main pipeline or inference engine in this phase.

---

## Problem

The current inference engine relies on OCR to find "Página N de M" markers. When OCR fails — due to image quality, rotation, or unusual fonts — the engine infers page numbers statistically, sometimes with errors. A complementary structural signal (pixel density) could reinforce or correct those inferences independently.

Before integrating, the hypothesis must be validated: do first pages cluster at a distinct density, and is that cluster tight enough to be usable?

---

## Scope

**In scope:**
- Standalone Python script (`pixel_density.py`)
- CLI: user specifies PDF path and one reference page (1-indexed)
- Renders all pages at low DPI, computes dark pixel ratio per page
- Prints match count to console
- Displays a matplotlib plot of density across all pages

**Out of scope:**
- Integration with `core/analyzer.py` or `eval/inference.py`
- Multi-reference / template learning
- Grid/histogram similarity modes (possible future extension)
- Batch processing of multiple PDFs

---

## Algorithm

### 1. Thumbnail Rendering

Each PDF page is rendered at **15 DPI** using PyMuPDF:

```python
mat = fitz.Matrix(15 / 72, 15 / 72)
pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
```

`alpha=False` guarantees `pix.n == 1` (grayscale, no alpha channel), making the reshape safe.

At 15 DPI, an A4 page renders to approximately 124×175 px (~21 700 pixels). This is sufficient for a stable density ratio while keeping memory and CPU cost negligible even for 8 000-page PDFs.

### 2. Dark Pixel Ratio

```python
dark_ratio = (img < 128).mean()   # fraction of pixels below mid-grey
```

Returns a float in [0.0, 1.0].

### 3. Reference and Matching

- Reference `dark_ratio` = value of the user-specified page.
- A page is a **match** if `|dark_ratio_page - dark_ratio_ref| ≤ threshold`.
- Default threshold: **0.08** (absolute, tunable via `--threshold`).

### 4. Output

**Console:**
```
Reference page 1: dark_ratio=0.312
Threshold: ±0.080  →  [0.232 – 0.392]
Matches: 681 / N pages
```
(N = actual page count of the PDF, shown at runtime.)

**Plot:**
- X axis: page number (1-indexed)
- Y axis: dark_ratio (0.0–1.0)
- Grey line: density curve for all pages
- Horizontal band: ±threshold window around reference
- Red dots: matched pages
- Blue vertical line: reference page

---

## CLI

```bash
# Basic usage — page 1 as reference
python pixel_density.py path/to/file.pdf 1

# Custom DPI and threshold
python pixel_density.py path/to/file.pdf 1 --dpi 10 --threshold 0.10

# Save plot to file instead of showing interactively
python pixel_density.py path/to/file.pdf 1 --save-plot density.png

# Skip plot entirely (console output only)
python pixel_density.py path/to/file.pdf 1 --no-plot
```

**Arguments:**

| Argument | Type | Default | Description |
|---|---|---|---|
| `pdf_path` | positional | — | Path to PDF file |
| `ref_page` | positional | — | Reference page number (1-indexed) |
| `--dpi` | int | 15 | Render DPI for thumbnails |
| `--threshold` | float | 0.08 | Absolute dark_ratio tolerance for match |
| `--save-plot` | path | — | Save plot to file instead of displaying |
| `--no-plot` | flag | False | Skip plot entirely |

---

## File Structure

```
.worktrees/pixel-density/
└── pixel_density.py      # standalone script, no project imports
```

No `__init__.py`, no package structure. Single file, runs directly.

---

## Dependencies

All already available in `.venv-cuda`:

| Library | Use |
|---|---|
| `PyMuPDF` (fitz) | PDF rendering |
| `numpy` | dark_ratio computation |
| `matplotlib` | plot |

No new dependencies required.

---

## Success Criteria

The experiment succeeds if, on `ART_HLL_674docsapp.pdf` with page 1 as reference:

1. **Match count converges near ground truth with manual threshold tuning.** Ground truth is 674 documents. The default threshold (0.08) may not land there — the user will adjust `--threshold` interactively until the match count approximates 674. The goal is to establish that *a threshold exists* that produces a reasonable count, not that the default is correct.

   > **Note on reference page:** Page 1 is assumed to be a representative CRS first page (header table, stamp, signatures). If it is atypical (e.g., a cover sheet with very different ink density), the user should try an alternative reference page.

2. **The plot shows non-uniform distribution of matched pages.** Matched pages should not be uniformly distributed across the PDF — they should cluster at roughly regular intervals (one per document). Visual inspection of the plot is the primary validation method for this criterion.

3. **Runtime under 60 seconds** on the dev machine for the full PDF.

The experiment is considered inconclusive (not failed) if no single threshold produces a match count near 674 — that means the scalar density signal is insufficient and the grid-mode extension should be explored.

---

## Future Extension Points

- **Hybrid reference:** auto-extract reference profile from OCR-confirmed `curr=1` pages; fall back to user-specified page
- **Grid mode (4×4 tiles):** replace scalar density with 16-element spatial vector for higher discriminability
- **D-S integration:** expose `dark_ratio` as an additional evidence source in the inference engine's Dempster-Shafer pool
- **Multi-PDF batch:** produce one plot per PDF with aggregate stats

These are not in scope for this experiment.
