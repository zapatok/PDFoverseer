# Pixel Density First-Page Detector — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone CLI script that detects document first pages in a PDF by comparing pixel darkness density against a user-specified reference page.

**Architecture:** Single Python script with pure-function core (`dark_ratio`, `find_matches`) and I/O layer (`render_thumbnail`, `compute_ratios`, `show_plot`, `main`). Lives in a dedicated git worktree isolated from the main pipeline.

**Tech Stack:** Python 3.10+, PyMuPDF (fitz), NumPy, Matplotlib — all available in `.venv-cuda`.

---

## Chunk 1: Setup + Core Logic + CLI

### Task 1: Create the worktree

**Files:**
- Create worktree: `.worktrees/pixel-density/` on branch `feature/pixel-density`

- [ ] **Step 1: Create the worktree**

```bash
cd A:/PROJECTS/PDFoverseer
git worktree add .worktrees/pixel-density -b feature/pixel-density
```

Expected output: `Preparing worktree (new branch 'feature/pixel-density')`

- [ ] **Step 2: Verify**

```bash
git worktree list
```

Expected: three entries — main, crop-selector, ocr-matcher, and the new pixel-density worktree.

---

### Task 2: Write failing tests for pure functions

**Files:**
- Create: `.worktrees/pixel-density/test_pixel_density.py`

These are the only unit-testable functions (pure, no I/O). Write the tests first.

- [ ] **Step 1: Create test file**

`.worktrees/pixel-density/test_pixel_density.py`:

```python
import numpy as np
import pytest
from pixel_density import dark_ratio, find_matches


def test_dark_ratio_all_black():
    img = np.zeros((10, 10), dtype=np.uint8)
    assert dark_ratio(img) == 1.0


def test_dark_ratio_all_white():
    img = np.full((10, 10), 255, dtype=np.uint8)
    assert dark_ratio(img) == 0.0


def test_dark_ratio_half():
    # Bottom half black (value 0), top half white (value 200)
    img = np.zeros((10, 10), dtype=np.uint8)
    img[:5, :] = 200
    assert dark_ratio(img) == pytest.approx(0.5)


def test_find_matches_basic():
    ratios = [0.10, 0.30, 0.32, 0.50, 0.29]
    # ref=index 1 (ratio=0.30), threshold=0.05
    # matches: 0.30 (±0), 0.32 (+0.02), 0.29 (-0.01) → indices 1, 2, 4
    matches = find_matches(ratios, ref_idx=1, threshold=0.05)
    assert set(matches) == {1, 2, 4}


def test_find_matches_always_includes_ref():
    ratios = [0.10, 0.50, 0.90]
    matches = find_matches(ratios, ref_idx=1, threshold=0.01)
    assert 1 in matches  # reference is always within 0 of itself


def test_find_matches_boundary():
    ratios = [0.20, 0.30, 0.38]
    # threshold=0.08: 0.38 is exactly at boundary (|0.38-0.30|=0.08) → included
    matches = find_matches(ratios, ref_idx=1, threshold=0.08)
    assert 2 in matches
```

- [ ] **Step 2: Run tests — confirm they fail with ImportError**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
../../.venv-cuda/Scripts/python -m pytest test_pixel_density.py -v
```

Expected: `ModuleNotFoundError: No module named 'pixel_density'`

---

### Task 3: Implement pure functions to make tests pass

**Files:**
- Create: `.worktrees/pixel-density/pixel_density.py` (pure functions only for now)

- [ ] **Step 1: Create pixel_density.py with pure functions**

`.worktrees/pixel-density/pixel_density.py`:

```python
"""
pixel_density.py — Detect document first pages by pixel darkness density.

Standalone experiment script. No imports from the main PDFoverseer project.

Usage:
    python pixel_density.py path/to/file.pdf 1
    python pixel_density.py path/to/file.pdf 1 --dpi 10 --threshold 0.10
    python pixel_density.py path/to/file.pdf 1 --save-plot out.png
    python pixel_density.py path/to/file.pdf 1 --no-plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF
import matplotlib.pyplot as plt
import numpy as np


# ── Pure functions (unit-testable) ────────────────────────────────────────────

def dark_ratio(img: np.ndarray) -> float:
    """Return fraction of pixels strictly darker than mid-grey (value < 128).

    Args:
        img: 2-D uint8 grayscale array (H × W).

    Returns:
        Float in [0.0, 1.0]; 1.0 = all black, 0.0 = all white.
    """
    return float((img < 128).mean())


def find_matches(
    ratios: list[float],
    ref_idx: int,
    threshold: float,
) -> list[int]:
    """Return 0-based page indices whose dark_ratio is within threshold of ref.

    Args:
        ratios:    dark_ratio per page (0-indexed).
        ref_idx:   0-based index of the reference page.
        threshold: absolute tolerance (e.g. 0.08 means ±8 percentage points).

    Returns:
        Sorted list of matching 0-based page indices (always includes ref_idx).
    """
    ref = ratios[ref_idx]
    return [i for i, r in enumerate(ratios) if abs(r - ref) <= threshold]
```

- [ ] **Step 2: Run tests — confirm pure functions pass**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
../../.venv-cuda/Scripts/python -m pytest test_pixel_density.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
git add pixel_density.py test_pixel_density.py
git commit -m "feat(pixel-density): pure functions dark_ratio + find_matches with tests"
```

---

### Task 4: Implement I/O layer (rendering + ratios)

**Files:**
- Modify: `.worktrees/pixel-density/pixel_density.py` — append rendering functions

- [ ] **Step 1: Append rendering functions after the pure functions block**

Add to `pixel_density.py` after the `find_matches` function:

```python
# ── I/O layer (PDF rendering) ─────────────────────────────────────────────────

def render_thumbnail(page: fitz.Page, dpi: int = 15) -> np.ndarray:
    """Render one PDF page as a grayscale numpy array at low DPI.

    Args:
        page: PyMuPDF page object.
        dpi:  Render resolution. 15 DPI gives ~124×175 px for A4.

    Returns:
        2-D uint8 grayscale array (H × W).
    """
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    # alpha=False guarantees pix.n == 1 (no alpha channel), reshape is safe.
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)


def compute_ratios(pdf_path: str, dpi: int) -> list[float]:
    """Open a PDF and return dark_ratio for every page.

    Args:
        pdf_path: Path to the PDF file.
        dpi:      Render resolution passed to render_thumbnail.

    Returns:
        List of floats, one per page, 0-indexed.
    """
    doc = fitz.open(pdf_path)
    ratios: list[float] = []
    for page in doc:
        img = render_thumbnail(page, dpi)
        ratios.append(dark_ratio(img))
    doc.close()
    return ratios
```

- [ ] **Step 2: Verify existing tests still pass (no regressions)**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
../../.venv-cuda/Scripts/python -m pytest test_pixel_density.py -v
```

Expected: all 6 PASS.

---

### Task 5: Implement plot

**Files:**
- Modify: `.worktrees/pixel-density/pixel_density.py` — append show_plot

- [ ] **Step 1: Append show_plot after compute_ratios**

```python
# ── Visualisation ─────────────────────────────────────────────────────────────

def show_plot(
    ratios: list[float],
    ref_idx: int,
    matches: list[int],
    threshold: float,
    save_path: str | None = None,
) -> None:
    """Plot dark_ratio curve with matched pages highlighted.

    Args:
        ratios:    dark_ratio per page (0-indexed).
        ref_idx:   0-based reference page index.
        matches:   0-based indices of matched pages.
        threshold: tolerance used for matching (for band display).
        save_path: if given, save figure to this path instead of displaying.
    """
    ref = ratios[ref_idx]
    pages = list(range(1, len(ratios) + 1))  # 1-indexed for display

    fig, ax = plt.subplots(figsize=(16, 4))

    # Full density curve
    ax.plot(pages, ratios, color="grey", linewidth=0.5, label="dark ratio")

    # ±threshold band around reference value
    ax.axhspan(
        ref - threshold, ref + threshold,
        alpha=0.15, color="blue",
        label=f"±{threshold:.3f} band",
    )

    # Reference page marker
    ax.axvline(
        ref_idx + 1, color="blue", linewidth=1.5,
        label=f"reference (p{ref_idx + 1}, ratio={ref:.3f})",
    )

    # Matched pages as red dots
    match_pages  = [m + 1       for m in matches]
    match_ratios = [ratios[m]   for m in matches]
    ax.scatter(
        match_pages, match_ratios,
        color="red", s=4, zorder=5,
        label=f"matches ({len(matches)})",
    )

    ax.set_xlabel("Page")
    ax.set_ylabel("Dark ratio")
    ax.set_title(
        f"Pixel density — {len(matches)} matches / {len(ratios)} pages "
        f"(ref p{ref_idx + 1}, threshold ±{threshold:.3f})"
    )
    ax.legend(loc="upper right")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"Plot saved to {save_path}")
    else:
        plt.show()
```

---

### Task 6: Implement CLI entry point

**Files:**
- Modify: `.worktrees/pixel-density/pixel_density.py` — append main + `__main__` guard

- [ ] **Step 1: Append main() and entry guard**

```python
# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect document first pages by pixel darkness density.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("pdf_path",  help="Path to the PDF file")
    parser.add_argument("ref_page",  type=int,
                        help="Reference page number (1-indexed)")
    parser.add_argument("--dpi",       type=int,   default=15,
                        help="Render DPI for thumbnails")
    parser.add_argument("--threshold", type=float, default=0.08,
                        help="Absolute dark_ratio tolerance for match")
    parser.add_argument("--save-plot", metavar="PATH", default=None,
                        help="Save plot to file instead of displaying")
    parser.add_argument("--no-plot",   action="store_true",
                        help="Skip the plot entirely")
    args = parser.parse_args()

    ref_idx = args.ref_page - 1

    print(f"Rendering {Path(args.pdf_path).name} at {args.dpi} DPI …")
    ratios = compute_ratios(args.pdf_path, args.dpi)

    if ref_idx < 0 or ref_idx >= len(ratios):
        print(
            f"Error: ref_page {args.ref_page} is out of range "
            f"(PDF has {len(ratios)} pages).",
            file=sys.stderr,
        )
        sys.exit(1)

    ref     = ratios[ref_idx]
    matches = find_matches(ratios, ref_idx, args.threshold)
    lo, hi  = ref - args.threshold, ref + args.threshold

    print(f"Reference page {args.ref_page}: dark_ratio={ref:.3f}")
    print(f"Threshold: ±{args.threshold:.3f}  →  [{lo:.3f} – {hi:.3f}]")
    print(f"Matches: {len(matches)} / {len(ratios)} pages")

    if not args.no_plot:
        show_plot(ratios, ref_idx, matches, args.threshold, args.save_plot)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests one final time**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
../../.venv-cuda/Scripts/python -m pytest test_pixel_density.py -v
```

Expected: all 6 PASS.

- [ ] **Step 3: Commit**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
git add pixel_density.py
git commit -m "feat(pixel-density): rendering, plot, and CLI entry point"
```

---

### Task 7: Smoke test with a real PDF

This is a manual validation step. The user runs the script and interprets the output.

- [ ] **Step 1: Run against the test PDF**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
../../.venv-cuda/Scripts/python pixel_density.py \
    "../../eval/fixtures/real/ART_HLL_674docsapp.pdf" 1
```

> **Note:** Adjust the path to `ART_HLL_674docsapp.pdf` if it lives elsewhere in the project. The script is run from the worktree root so relative paths are relative to `.worktrees/pixel-density/`.

Expected console output format (exact values depend on the PDF):
```
Rendering ART_HLL_674docsapp.pdf at 15 DPI …
Reference page 1: dark_ratio=0.XXX
Threshold: ±0.080  →  [X.XXX – X.XXX]
Matches: NNN / NNNN pages
```

**Pass criteria for Step 1:**
- No exception or traceback
- `dark_ratio` is a float in [0.0, 1.0]
- `Matches` count is a positive integer less than the total page count
- Plot window opens without error

The plot window will open. Check visually:
- Red dots are not uniformly spread — they should cluster at roughly regular intervals (one cluster per document)
- The density curve shows visible variation (not flat), indicating the signal is present

- [ ] **Step 2: Verify --no-plot flag (headless check)**

```bash
../../.venv-cuda/Scripts/python pixel_density.py \
    "../../eval/fixtures/real/ART_HLL_674docsapp.pdf" 1 --no-plot
```

Expected: same console output as Step 1, no plot window, no error.

- [ ] **Step 3: Tune threshold until match count is in [600, 750]**

Adjust `--threshold` iteratively (try 0.05, 0.10, 0.12, 0.15) until `Matches` falls in the target range **[600, 750]** (ground truth: 674 documents). Record the threshold value that lands closest to 674.

```bash
../../.venv-cuda/Scripts/python pixel_density.py \
    "../../eval/fixtures/real/ART_HLL_674docsapp.pdf" 1 --threshold 0.05 --no-plot

../../.venv-cuda/Scripts/python pixel_density.py \
    "../../eval/fixtures/real/ART_HLL_674docsapp.pdf" 1 --threshold 0.12 --no-plot
```

**If no threshold in [0.03, 0.20] produces a count in [600, 750]:** the scalar density signal is insufficient for this PDF → note this outcome and stop. Grid-mode extension is the next step (see spec Future Extension Points). Do not keep tuning indefinitely.

- [ ] **Step 4: Save a plot for reference**

```bash
../../.venv-cuda/Scripts/python pixel_density.py \
    "../../eval/fixtures/real/ART_HLL_674docsapp.pdf" 1 \
    --threshold <best_value_from_step3> \
    --save-plot A:/PROJECTS/PDFoverseer/.worktrees/pixel-density/density_art674.png
```

Expected: `Plot saved to A:/PROJECTS/PDFoverseer/.worktrees/pixel-density/density_art674.png` and the file exists on disk.

- [ ] **Step 4: Final commit**

```bash
cd A:/PROJECTS/PDFoverseer/.worktrees/pixel-density
git add -A
git commit -m "chore(pixel-density): smoke test complete — pixel_density.py ready"
```
