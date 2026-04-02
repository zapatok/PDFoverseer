"""PD V2 Rescue — cross-validation of three rescue lines.

Rescue A: edge_density standalone with V1 threshold (pct_75.2)
Rescue B: score fusion (V1 base + edge boost)
Rescue C: multi-descriptor (dark_ratio + edge_density) with V1 threshold

Usage
-----
    python eval/pixel_density/sweep_rescue.py
    python eval/pixel_density/sweep_rescue.py --rescue A     # single line
    python eval/pixel_density/sweep_rescue.py --rescue A B C  # specific lines
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
from scipy.signal import find_peaks as scipy_find_peaks  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    compute_metrics_count_only,
    load_art674_gt,
    load_tess_only_pages,
    save_results,
)
from eval.pixel_density.features import (  # noqa: E402
    extract_features,
    feat_dark_ratio_grid,
    feat_edge_density_grid,
)
from eval.pixel_density.metrics import bilateral_l2  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100

# ── PDF corpus ──────────────────────────────────────────────────────────────

GENERAL_CORPUS: list[tuple[str, str, int]] = [
    ("ALUM_1", "data/samples/ALUM_1.pdf", 1),
    ("ALUM_19", "data/samples/ALUM_19.pdf", 19),
    ("ART_674", "data/samples/ART_674.pdf", 674),
    ("CASTRO_15", "data/samples/CASTRO_15.pdf", 15),
    ("CASTRO_5", "data/samples/CASTRO_5.pdf", 5),
    ("CHAR_17", "data/samples/CHAR_17.PDF", 17),
    ("CHAR_25", "data/samples/CHAR_25.pdf", 25),
    ("CH_39", "data/samples/CH_39.pdf", 39),
    ("CH_51", "data/samples/CH_51docs.pdf", 51),
    ("CH_74", "data/samples/CH_74docs.pdf", 74),
    ("CH_9", "data/samples/CH_9.pdf", 9),
    ("CH_BSM_18", "data/samples/CH_BSM_18.pdf", 18),
    ("CRS_9", "data/samples/CRS_9.pdf", 9),
    ("HLL_363", "data/samples/HLL_363.pdf", 363),
    ("INSAP_20", "data/samples/INSAP_20.pdf", 20),
    ("INS_31", "data/samples/INS_31.pdf.pdf", 31),
    ("JOGA_19", "data/samples/JOGA_19.pdf", 19),
    ("QUEVEDO_1", "data/samples/QUEVEDO_1.pdf", 1),
    ("QUEVEDO_13", "data/samples/QUEVEDO_13.pdf", 13),
    ("QUEVEDO_2", "data/samples/QUEVEDO_2.pdf", 2),
    ("RACO_25", "data/samples/RACO_25.pdf", 25),
    ("SAEZ_14", "data/samples/SAEZ_14.pdf", 14),
]

ART_CORPUS: list[tuple[str, str, int]] = [
    ("ART_CH_13", "data/samples/arts/ART_CH_13.pdf", 13),
    ("ART_CON_13", "data/samples/arts/ART_CON_13.pdf", 13),
    ("ART_EX_13", "data/samples/arts/ART_EX_13.pdf", 13),
    ("ART_GR_8", "data/samples/arts/ART_GR_8.pdf", 8),
    ("ART_ROC_10", "data/samples/arts/ART_ROC_10.pdf", 10),
]


# ── Cross-validation harness ───────────────────────────────────────────────


def cross_validate(
    scorer: Callable[[np.ndarray], list[int]],
    corpus: list[tuple[str, str, int]],
) -> list[dict]:
    """Run a scorer over multiple PDFs, return per-PDF count metrics.

    Args:
        scorer: Function (pages_array) -> list of detected cover page indices.
        corpus: List of (name, pdf_path, target_doc_count) tuples.

    Returns:
        List of dicts with name, target, matches, error, abs_error.
    """
    results: list[dict] = []
    for name, pdf_path, target in corpus:
        pages = ensure_cache(pdf_path, dpi=DPI)
        matches = scorer(pages)
        metrics = compute_metrics_count_only(matches, target)
        results.append({"name": name, **metrics, "target": target})
    return results


# ── Shared utilities ───────────────────────────────────────────────────────


def _percentile_threshold(scores: np.ndarray, pct: float) -> list[int]:
    """Threshold at given percentile, ensuring page 0 is always included."""
    thresh = np.percentile(scores, pct)
    matches = [i for i in range(len(scores)) if scores[i] >= thresh]
    if 0 not in matches:
        matches.insert(0, 0)
    return matches


def _normalize_01(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize scores to [0, 1]."""
    mn, mx = scores.min(), scores.max()
    if mx - mn < 1e-12:
        return np.zeros_like(scores)
    return (scores - mn) / (mx - mn)


def _robust_z_normalize(matrix: np.ndarray) -> np.ndarray:
    """Robust z-score normalization using median and MAD.

    Args:
        matrix: 2-D array (n_samples, n_features).

    Returns:
        Normalized matrix, same shape.
    """
    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0)
    mad[mad < 1e-12] = 1.0
    return (matrix - median) / (mad * 1.4826)


def _apply_floor(
    matches: list[int],
    scores: np.ndarray,
    floor: float,
) -> list[int]:
    """Remove detected pages whose bilateral score is below an absolute floor.

    Page 0 is always kept (first page of the PDF is always a document start).

    Args:
        matches: Detected cover page indices (0-based).
        scores: Full bilateral score array.
        floor: Minimum absolute score to retain a detection.

    Returns:
        Filtered list of cover page indices.
    """
    return [m for m in matches if m == 0 or scores[m] >= floor]


def _suppress_consecutive(
    matches: list[int],
    scores: np.ndarray,
) -> list[int]:
    """When consecutive pages are both detected, keep only the highest-scoring one.

    Processes runs of consecutive detected pages: within each run, only the
    page with the highest bilateral score survives. Page 0 is always kept
    (even if it loses on score, creating a pair — this is by design since
    page 0 is always a document start).

    Args:
        matches: Detected cover page indices (0-based), must be sorted.
        scores: Full bilateral score array.

    Returns:
        Filtered list of cover page indices, sorted.
    """
    if len(matches) <= 1:
        return list(matches)

    sorted_matches = sorted(matches)
    result: list[int] = []

    # Group into runs of consecutive indices
    runs: list[list[int]] = []
    current_run: list[int] = [sorted_matches[0]]
    for i in range(1, len(sorted_matches)):
        if sorted_matches[i] == sorted_matches[i - 1] + 1:
            current_run.append(sorted_matches[i])
        else:
            runs.append(current_run)
            current_run = [sorted_matches[i]]
    runs.append(current_run)

    for run in runs:
        if len(run) == 1:
            result.append(run[0])
        else:
            # Keep the page with the highest score in this run
            best = max(run, key=lambda p: scores[p])
            result.append(best)
            # Always keep page 0 if it was in the run
            if 0 in run and 0 != best:
                result.append(0)

    return sorted(result)


def _shift_to_cover(
    peaks: list[int],
    scores: np.ndarray,
    score_similarity: float = 0.99,
) -> list[int]:
    """Correct displacement errors by shifting peaks left when the previous page has a similar score.

    When find_peaks detects a peak at page N, but page N-1 has a score within
    the similarity ratio, the real cover is likely at N-1 (the peak landed on
    the last page of the previous document instead of the first page of the
    next). This shifts the detection left by 1 in those cases.

    Page 0 is never shifted (no page before it).

    Args:
        peaks: Detected peak indices (0-based), sorted.
        scores: Full bilateral score array.
        score_similarity: Minimum ratio score[p-1]/score[p] to trigger shift.

    Returns:
        Corrected list of cover page indices, sorted, deduplicated.
    """
    result: list[int] = []
    for p in peaks:
        if p == 0:
            result.append(p)
            continue
        if scores[p - 1] >= scores[p] * score_similarity:
            result.append(p - 1)
        else:
            result.append(p)
    return sorted(set(result))


def _template_rescue(
    confirmed: list[int],
    vectors: list[np.ndarray],
    threshold: float,
) -> list[int]:
    """Rescue undetected pages that are similar to confirmed covers.

    Builds a mean template from the feature vectors of confirmed cover pages,
    then finds undetected pages whose L2 distance to the template is within
    the threshold.

    Args:
        confirmed: Indices of already-detected cover pages (0-based).
        vectors: Feature vectors for all pages (raw, not normalized).
        threshold: Maximum L2 distance from template to rescue a page.

    Returns:
        List of rescued page indices (0-based), sorted. Does NOT include
        pages already in confirmed.
    """
    if not confirmed or threshold <= 0:
        return []

    confirmed_set = set(confirmed)
    template = np.mean([vectors[i] for i in confirmed], axis=0)

    rescued: list[int] = []
    for i in range(len(vectors)):
        if i in confirmed_set:
            continue
        dist = float(np.linalg.norm(vectors[i] - template))
        if dist <= threshold:
            rescued.append(i)

    return sorted(rescued)


# ── Scorers ────────────────────────────────────────────────────────────────


def scorer_v1(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """V1-count baseline: dark_ratio_grid 8x8, L2 bilateral, min, pct_75.2.

    Applies CLAHE preprocessing to match the production V1 pipeline.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    import cv2

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    vectors = []
    for i in range(pages.shape[0]):
        enhanced = clahe.apply(pages[i])
        vectors.append(feat_dark_ratio_grid(enhanced, grid_n=8))
    scores = bilateral_l2(vectors, "min")
    return _percentile_threshold(scores, pct)


def scorer_rescue_a(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """Rescue A: edge_density_grid 4x4, L2 bilateral, min, pct_75.2.

    No CLAHE preprocessing — Canny edge detection operates on raw grayscale,
    and CLAHE (contrast enhancement) would alter edge magnitudes unpredictably.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    vectors = [feat_edge_density_grid(pages[i], grid_n=4) for i in range(pages.shape[0])]
    scores = bilateral_l2(vectors, "min")
    return _percentile_threshold(scores, pct)


def scorer_rescue_b(
    pages: np.ndarray,
    edge_weight: float = 0.2,
    pct: float = 75.2,
) -> list[int]:
    """Rescue B: V1 base + edge_density boost, fused scores with pct threshold.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        edge_weight: Weight for edge_density scores (V1 gets 1 - edge_weight).
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    import cv2

    v1_weight = 1.0 - edge_weight

    # V1 scores (CLAHE + dark_ratio)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    v1_vectors = []
    for i in range(pages.shape[0]):
        enhanced = clahe.apply(pages[i])
        v1_vectors.append(feat_dark_ratio_grid(enhanced, grid_n=8))
    v1_scores = _normalize_01(bilateral_l2(v1_vectors, "min"))

    # Edge density scores
    edge_vectors = [feat_edge_density_grid(pages[i], grid_n=4) for i in range(pages.shape[0])]
    edge_scores = _normalize_01(bilateral_l2(edge_vectors, "min"))

    # Fuse
    fused = v1_weight * v1_scores + edge_weight * edge_scores
    return _percentile_threshold(fused, pct)


def scorer_rescue_c(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """Rescue C: dark_ratio + edge_density, robust-z norm, L2 bilateral, pct_75.2.

    Same feature combination as V2, but with V1's percentile threshold
    instead of KMeans.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    feat_list = ["dark_ratio_grid", "edge_density_grid"]
    vectors = [extract_features(pages[i], feat_list) for i in range(pages.shape[0])]
    matrix = np.vstack(vectors)
    normed = _robust_z_normalize(matrix)
    normed_list = [normed[i] for i in range(normed.shape[0])]
    scores = bilateral_l2(normed_list, "min")
    return _percentile_threshold(scores, pct)


def scorer_v3(
    pages: np.ndarray,
    pct: float = 75.2,
    floor: float = 0.0,
    suppress_consecutive: bool = True,
) -> list[int]:
    """V3: V2_RC features + absolute floor + consecutive suppression.

    Pipeline: extract features -> robust-z normalize -> bilateral L2 ->
    percentile threshold -> absolute floor -> consecutive suppression.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).
        floor: Minimum absolute bilateral score to retain a detection.
            Set to 0.0 to disable (default).
        suppress_consecutive: If True, when consecutive pages are both
            detected, keep only the highest-scoring one.

    Returns:
        List of detected cover page indices (0-based).
    """
    feat_list = ["dark_ratio_grid", "edge_density_grid"]
    vectors = [extract_features(pages[i], feat_list) for i in range(pages.shape[0])]
    matrix = np.vstack(vectors)
    normed = _robust_z_normalize(matrix)
    normed_list = [normed[i] for i in range(normed.shape[0])]
    scores = bilateral_l2(normed_list, "min")

    matches = _percentile_threshold(scores, pct)

    if floor > 0.0:
        matches = _apply_floor(matches, scores, floor)

    if suppress_consecutive:
        matches = _suppress_consecutive(matches, scores)

    return matches


def scorer_find_peaks(
    pages: np.ndarray,
    prominence: float = 0.5,
    distance: int = 2,
    shift_covers: bool = True,
    score_similarity: float = 0.99,
    rescue_threshold: float = 0.0,
) -> list[int]:
    """Detect cover pages as prominent peaks in the bilateral score signal.

    Instead of assuming a fixed ratio of covers (percentile threshold), this
    scorer finds pages that genuinely stand out from their neighbors using
    scipy's peak detection. A cover-shift post-processing step corrects
    displacement errors, and an optional template rescue recovers covers
    that are similar to confirmed detections but weren't peaks themselves.

    Pipeline: extract features -> robust-z normalize -> bilateral L2 ->
    find_peaks (prominence + distance) -> cover shift -> template rescue.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        prominence: Minimum prominence for a peak to be detected. Higher
            values require peaks to stand out more from surroundings.
        distance: Minimum number of pages between detected peaks.
        shift_covers: If True, correct displacement errors by shifting
            peaks left when the previous page has a similar score.
        score_similarity: Similarity ratio for cover-shift (only used
            when shift_covers=True).
        rescue_threshold: Maximum L2 distance (in raw feature space) from
            the mean cover template to rescue undetected pages.
            Set to 0.0 to disable (default).

    Returns:
        List of detected cover page indices (0-based).
    """
    feat_list = ["dark_ratio_grid", "edge_density_grid"]
    vectors = [extract_features(pages[i], feat_list) for i in range(pages.shape[0])]
    matrix = np.vstack(vectors)
    normed = _robust_z_normalize(matrix)
    normed_list = [normed[i] for i in range(normed.shape[0])]
    scores = bilateral_l2(normed_list, "min")

    peaks, _ = scipy_find_peaks(scores, prominence=prominence, distance=distance)
    matches = [int(p) for p in peaks]

    if 0 not in matches:
        matches.insert(0, 0)

    if shift_covers:
        matches = _shift_to_cover(matches, scores, score_similarity)

    if rescue_threshold > 0:
        rescued = _template_rescue(matches, vectors, rescue_threshold)
        matches = sorted(set(matches) | set(rescued))

    return matches


def compute_summary(results: list[dict]) -> dict:
    """Compute aggregate metrics from cross-validation results.

    Args:
        results: List of per-PDF result dicts with abs_error key.

    Returns:
        Dict with mae, exact (count), within_2 (count), n.
    """
    n = len(results)
    errors = [r["abs_error"] for r in results]
    return {
        "mae": sum(errors) / n if n else 0.0,
        "exact": sum(1 for e in errors if e == 0),
        "within_2": sum(1 for e in errors if e <= 2),
        "n": n,
    }


def format_comparison_table(
    v1_results: list[dict],
    rescue_results: dict[str, list[dict]],
) -> None:
    """Print a per-PDF comparison table: V1 vs each rescue line.

    Args:
        v1_results: V1-count per-PDF results.
        rescue_results: {rescue_name: per-PDF results}.
    """
    rescue_names = sorted(rescue_results.keys())
    # Header
    hdr = f"{'PDF':<14} {'Tgt':>4} | {'V1':>4} {'err':>5}"
    for rn in rescue_names:
        hdr += f" | {rn:>4} {'err':>5}"
    print(hdr)  # noqa: T201
    print("-" * len(hdr))  # noqa: T201

    # Rows
    rescue_by_name = {
        rn: {r["name"]: r for r in results}
        for rn, results in rescue_results.items()
    }

    for v1r in v1_results:
        name = v1r["name"]
        row = (f"{name:<14} {v1r['target']:>4} | "
               f"{v1r['matches']:>4} {v1r['error']:>+5}")
        for rn in rescue_names:
            rr = rescue_by_name[rn].get(name)
            if rr:
                row += f" | {rr['matches']:>4} {rr['error']:>+5}"
            else:
                row += f" | {'--':>4} {'--':>5}"
        print(row)  # noqa: T201

    # Summary
    print("-" * len(hdr))  # noqa: T201
    v1_s = compute_summary(v1_results)
    summ = f"{'MAE':<14} {'':>4} | {'':>4} {v1_s['mae']:>5.1f}"
    for rn in rescue_names:
        rs = compute_summary(rescue_results[rn])
        summ += f" | {'':>4} {rs['mae']:>5.1f}"
    print(summ)  # noqa: T201

    exact = f"{'Exact':<14} {'':>4} | {'':>4} {v1_s['exact']:>5}"
    for rn in rescue_names:
        rs = compute_summary(rescue_results[rn])
        exact += f" | {'':>4} {rs['exact']:>5}"
    print(exact)  # noqa: T201

    within = f"{'Within +/-2':<14} {'':>4} | {'':>4} {v1_s['within_2']:>5}"
    for rn in rescue_names:
        rs = compute_summary(rescue_results[rn])
        within += f" | {'':>4} {rs['within_2']:>5}"
    print(within)  # noqa: T201


def main() -> None:
    """Run all rescue lines with cross-validation."""
    parser = argparse.ArgumentParser(
        description="PD V2 Rescue -- cross-validation sweep")
    parser.add_argument("--rescue", nargs="*", default=["A", "B", "C"],
                        choices=["A", "B", "C"],
                        help="Which rescue lines to run (default: all)")
    args = parser.parse_args()

    print("=" * 70)  # noqa: T201
    print("PD V2 Rescue -- Cross-Validation Sweep")  # noqa: T201
    print("=" * 70)  # noqa: T201

    full_corpus = GENERAL_CORPUS + ART_CORPUS
    t_total = time.perf_counter()

    # 1. V1 baseline
    logger.info("\n--- V1 Baseline ---")
    t0 = time.perf_counter()
    v1_results = cross_validate(scorer_v1, full_corpus)
    logger.info("V1 done in %.1fs", time.perf_counter() - t0)

    # 2. Rescue lines
    rescue_results: dict[str, list[dict]] = {}

    if "A" in args.rescue:
        logger.info("\n--- Rescue A: edge_density standalone ---")
        t0 = time.perf_counter()
        rescue_results["A"] = cross_validate(scorer_rescue_a, full_corpus)
        logger.info("Rescue A done in %.1fs", time.perf_counter() - t0)

    if "B" in args.rescue:
        logger.info("\n--- Rescue B: score fusion (sweep edge_weight) ---")
        t0 = time.perf_counter()
        best_b_mae = float("inf")
        best_b_results: list[dict] = []
        best_b_weight = 0.0
        for ew in [0.1, 0.2, 0.3, 0.4]:
            def _scorer_b(pages: np.ndarray, w: float = ew) -> list[int]:
                return scorer_rescue_b(pages, edge_weight=w)
            results_b = cross_validate(_scorer_b, full_corpus)
            mae_b = compute_summary(results_b)["mae"]
            logger.info("  edge_weight=%.1f  MAE=%.1f", ew, mae_b)
            if mae_b < best_b_mae:
                best_b_mae = mae_b
                best_b_results = results_b
                best_b_weight = ew
        rescue_results["B"] = best_b_results
        logger.info("Rescue B best: edge_weight=%.1f MAE=%.1f (%.1fs)",
                     best_b_weight, best_b_mae, time.perf_counter() - t0)

    if "C" in args.rescue:
        logger.info("\n--- Rescue C: multi-descriptor + pct threshold ---")
        t0 = time.perf_counter()
        rescue_results["C"] = cross_validate(scorer_rescue_c, full_corpus)
        logger.info("Rescue C done in %.1fs", time.perf_counter() - t0)

    # 3. Report
    print("\n" + "=" * 70)  # noqa: T201
    print("GENERAL CORPUS (22 PDFs)")  # noqa: T201
    print("=" * 70)  # noqa: T201
    gen_names = {c[0] for c in GENERAL_CORPUS}
    v1_gen = [r for r in v1_results if r["name"] in gen_names]
    rescue_gen = {
        rn: [r for r in results if r["name"] in gen_names]
        for rn, results in rescue_results.items()
    }
    format_comparison_table(v1_gen, rescue_gen)

    print("\n" + "=" * 70)  # noqa: T201
    print("ART FAMILY (5 PDFs)")  # noqa: T201
    print("=" * 70)  # noqa: T201
    art_names = {c[0] for c in ART_CORPUS}
    v1_art = [r for r in v1_results if r["name"] in art_names]
    rescue_art = {
        rn: [r for r in results if r["name"] in art_names]
        for rn, results in rescue_results.items()
    }
    format_comparison_table(v1_art, rescue_art)

    # 4. ART_674 page-level metrics (only PDF with per-page GT)
    print("\n" + "=" * 70)  # noqa: T201
    print("ART_674 Page-Level Metrics (per-page GT available)")  # noqa: T201
    print("=" * 70)  # noqa: T201
    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    art_pages = ensure_cache("data/samples/ART_674.pdf", dpi=DPI)

    scorers = {"V1": scorer_v1, "A": scorer_rescue_a, "C": scorer_rescue_c}
    for label, scorer_fn in scorers.items():
        if label != "V1" and label not in args.rescue:
            continue
        matches = scorer_fn(art_pages)
        m = compute_metrics(matches, gt_covers, 674, tess_only_pages=tess_only)
        print(f"  {label:>2}: F1={m['f1']:.4f}  P={m['precision']:.3f}  "  # noqa: T201
              f"R={m['recall']:.3f}  TP={m['tp']}  FP={m['fp']}  "
              f"FN={m['fn']}  TESS={m.get('tess_only_recovered', 0)}")
    # Rescue B at best weight
    if "B" in args.rescue:
        matches_b = scorer_rescue_b(art_pages, edge_weight=best_b_weight)
        m = compute_metrics(matches_b, gt_covers, 674, tess_only_pages=tess_only)
        print(f"   B: F1={m['f1']:.4f}  P={m['precision']:.3f}  "  # noqa: T201
              f"R={m['recall']:.3f}  TP={m['tp']}  FP={m['fp']}  "
              f"FN={m['fn']}  TESS={m.get('tess_only_recovered', 0)}  "
              f"(edge_weight={best_b_weight})")

    # 5. Save results
    output = {
        "sweep": "pd_v2_rescue",
        "timestamp": datetime.now().isoformat(),
        "v1_results": v1_results,
        "rescue_results": {rn: results for rn, results in rescue_results.items()},
        "summaries": {
            "v1_general": compute_summary(v1_gen),
            "v1_art": compute_summary(v1_art),
        },
    }
    for rn in rescue_results:
        output["summaries"][f"{rn}_general"] = compute_summary(rescue_gen[rn])
        output["summaries"][f"{rn}_art"] = compute_summary(rescue_art[rn])
    if "B" in args.rescue:
        output["best_b_weight"] = best_b_weight

    save_results(output, "data/pixel_density/sweep_rescue.json")
    logger.info("\nTotal time: %.0fs", time.perf_counter() - t_total)


if __name__ == "__main__":
    main()
