"""Shared evaluation: ground-truth loading, metrics computation, reporting."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VLM_FIXTURE = Path(__file__).parent.parent / "fixtures" / "real" / "ART_674.json"
TESS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "real" / "ART_674_tess.json"
TESS_ONLY_CACHE = (
    Path(__file__).parent.parent.parent / "data" / "pixel_density" / "tess_only_pages.json"
)


# ── Ground truth ─────────────────────────────────────────────────────────────


def load_art674_gt() -> set[int]:
    """Load ART_674 VLM ground truth. Returns 0-based page indices where curr==1.

    Returns:
        Set of 0-based page indices representing document cover pages.
    """
    data = json.loads(VLM_FIXTURE.read_text(encoding="utf-8"))
    return {r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1}


def load_tess_only_pages() -> set[int]:
    """Load TESS-ONLY pages: covers that baseline bilateral misses but Tess finds.

    Uses cached result if available; recomputes and caches otherwise.

    Returns:
        Set of 0-based page indices.
    """
    # Try cache first (avoids re-rendering ART_674 every time)
    if TESS_ONLY_CACHE.exists():
        pages = json.loads(TESS_ONLY_CACHE.read_text(encoding="utf-8"))
        logger.info("TESS-ONLY loaded from cache: %d pages", len(pages))
        return set(pages)

    from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches
    from eval.pixel_density.sweep_preprocessing import compute_variant_vectors

    vlm_covers = load_art674_gt()

    # Reproduce baseline bilateral best config (CLAHE/min/kmeans)
    vectors = compute_variant_vectors("data/samples/ART_674.pdf", "clahe", 100, 8)
    scores = bilateral_scores(vectors, "min")
    bilateral_matches, _ = kmeans_matches(scores)
    bilateral_set = set(bilateral_matches)

    # Load Tesseract covers
    tess_data = json.loads(TESS_FIXTURE.read_text(encoding="utf-8"))
    tess_covers = {
        r["pdf_page"] - 1 for r in tess_data["reads"] if r.get("curr") == 1
    }

    # TESS-ONLY = in VLM GT AND in Tess BUT NOT in bilateral
    tess_only = (tess_covers & vlm_covers) - bilateral_set
    logger.info("TESS-ONLY pages: %d (computed and cached)", len(tess_only))

    # Cache for next time
    TESS_ONLY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TESS_ONLY_CACHE.write_text(
        json.dumps(sorted(tess_only)), encoding="utf-8",
    )
    return tess_only


# ── Metrics ──────────────────────────────────────────────────────────────────


def compute_metrics(
    matches: list[int],
    gt_covers: set[int],
    target: int,
    tess_only_pages: set[int] | None = None,
) -> dict:
    """Compute precision, recall, F1, error, and TESS-ONLY recovery.

    Args:
        matches: Detected cover page indices (0-based).
        gt_covers: Ground-truth cover page indices (0-based).
        target: Expected document count.
        tess_only_pages: Pages only Tesseract detects (for recovery metric).

    Returns:
        Dict with tp, fp, fn, precision, recall, f1, error, abs_error,
        matches count, and tess_only_recovered.
    """
    match_set = set(matches)
    n_matches = len(match_set)
    tp = len(match_set & gt_covers)
    fp = len(match_set - gt_covers)
    fn = len(gt_covers - match_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    result: dict = {
        "matches": n_matches,
        "error": n_matches - target,
        "abs_error": abs(n_matches - target),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

    if tess_only_pages is not None:
        result["tess_only_recovered"] = len(match_set & tess_only_pages)

    return result


def compute_metrics_count_only(matches: list[int], target: int) -> dict:
    """Count-only metrics for PDFs without per-page ground truth (e.g. HLL_363).

    Args:
        matches: Detected cover page indices.
        target: Expected document count.

    Returns:
        Dict with matches, error, abs_error.
    """
    return {
        "matches": len(matches),
        "error": len(matches) - target,
        "abs_error": abs(len(matches) - target),
    }


# ── Reporting ────────────────────────────────────────────────────────────────


def report_table(
    results: list[dict],
    sort_key: str = "f1",
    top_n: int = 10,
    descending: bool = True,
) -> None:
    """Print ranked results table to console.

    Args:
        results: List of result dicts (must have params + metric keys).
        sort_key: Key to sort by.
        top_n: Number of rows to print.
        descending: Sort descending (True) or ascending.
    """
    sorted_results = sorted(
        results, key=lambda r: r.get(sort_key, 0), reverse=descending,
    )

    print(f"\n{'=' * 100}")  # noqa: T201
    print(f"Top {top_n} by {sort_key} ({'desc' if descending else 'asc'})")  # noqa: T201
    print(f"{'=' * 100}")  # noqa: T201

    hdr = (
        f"{'#':>3}  {'Params':<40} {'Match':>5} {'Err':>5} "
        f"{'Prec':>6} {'Rec':>6} {'F1':>6} {'TP':>4} {'FP':>4} {'FN':>4}"
    )
    tess_col = (
        " TESS" if any("tess_only_recovered" in r for r in results) else ""
    )
    print(hdr + tess_col)  # noqa: T201
    print("-" * (len(hdr) + len(tess_col)))  # noqa: T201

    for rank, r in enumerate(sorted_results[:top_n], 1):
        params_str = str(r.get("params", ""))[:40]
        tess_str = (
            f" {r['tess_only_recovered']:>4}"
            if "tess_only_recovered" in r
            else ""
        )
        print(  # noqa: T201
            f"{rank:>3}  {params_str:<40} {r.get('matches', 0):>5} "
            f"{r.get('error', 0):>+5} {r.get('precision', 0):>6.3f} "
            f"{r.get('recall', 0):>6.3f} {r.get('f1', 0):>6.3f} "
            f"{r.get('tp', 0):>4} {r.get('fp', 0):>4} {r.get('fn', 0):>4}"
            + tess_str,
        )

    print(f"{'=' * 100}\n")  # noqa: T201


def save_results(results: dict, path: str | Path) -> None:
    """Save results dict as JSON.

    Args:
        results: Arbitrary results dict.
        path: Output path (directories created if needed).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(results, indent=2, default=float), encoding="utf-8",
    )
    logger.info("Results saved to %s", path)
