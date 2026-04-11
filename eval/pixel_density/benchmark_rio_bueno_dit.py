"""Benchmark DiT+cosine scorers on the rio_bueno ART folders.

Compares each scorer + hyperparameter against the count embedded in each
folder name and writes a markdown report. Run from the project root:

    python eval/pixel_density/benchmark_rio_bueno_dit.py
"""

from __future__ import annotations

import io
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.pixel_density.dit_embeddings import ensure_dit_embeddings  # noqa: E402
from eval.pixel_density.scorer_dit import (  # noqa: E402
    score_dit_find_peaks,
    score_dit_percentile,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CORPUS_ROOT = Path("A:/informe mensual/MARZO/rio_bueno/7.- ART  Realizadas")
REPORT_DIR = Path("docs/superpowers/reports")

# Hyperparameter sweep - small and principled, not a grid-search for hyperopt.
FIND_PEAKS_GRID = [
    {"prominence": 0.05, "distance": 1},
    {"prominence": 0.1, "distance": 1},
    {"prominence": 0.1, "distance": 2},
    {"prominence": 0.2, "distance": 2},
    {"prominence": 0.3, "distance": 2},
]
PERCENTILE_GRID = [65.0, 70.0, 75.0, 80.0, 85.0]

# Baseline numbers from the 2026-04-11 session, for reference only.
BASELINE_RESCUE_C_MAE = 9.5
BASELINE_RESCUE_C_EXACT = 4


@dataclass
class FolderResult:
    name: str
    expected: int
    counted: int
    per_pdf: list[tuple[str, int]]


def _expected_from_folder(name: str) -> int | None:
    m = re.search(r"(\d+)\s*$", name)
    return int(m.group(1)) if m else None


def _unique_pdfs(folder: Path) -> list[Path]:
    pdfs = sorted(list(folder.glob("*.pdf")) + list(folder.glob("*.PDF")))
    seen: set[str] = set()
    unique: list[Path] = []
    for p in pdfs:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def run_scorer(scorer_name: str, params: dict, folders: list[Path]) -> list[FolderResult]:
    results: list[FolderResult] = []
    for folder in folders:
        expected = _expected_from_folder(folder.name)
        if expected is None:
            continue
        per_pdf: list[tuple[str, int]] = []
        total = 0
        for pdf in _unique_pdfs(folder):
            embeddings = ensure_dit_embeddings(str(pdf))
            if scorer_name == "find_peaks":
                covers = score_dit_find_peaks(embeddings, **params)
            elif scorer_name == "percentile":
                covers = score_dit_percentile(embeddings, **params)
            else:
                raise ValueError(f"unknown scorer {scorer_name}")
            per_pdf.append((pdf.name, len(covers)))
            total += len(covers)
        results.append(
            FolderResult(name=folder.name, expected=expected, counted=total, per_pdf=per_pdf)
        )
    return results


def summarize(results: list[FolderResult]) -> tuple[int, float]:
    exact = sum(1 for r in results if r.counted == r.expected)
    mae = sum(abs(r.counted - r.expected) for r in results) / max(len(results), 1)
    return exact, mae


def format_report(
    all_runs: list[tuple[str, dict, list[FolderResult], int, float]],
) -> str:
    lines: list[str] = []
    lines.append("# DiT + Cosine benchmark - rio_bueno ART folders")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Corpus: `{CORPUS_ROOT}`")
    lines.append("")
    lines.append("## Baseline (handcrafted 80-d + L2)")
    lines.append("")
    lines.append(
        f"- `scorer_rescue_c` - exact: {BASELINE_RESCUE_C_EXACT}/13, MAE: {BASELINE_RESCUE_C_MAE}"
    )
    lines.append("")
    lines.append("## DiT + Cosine runs")
    lines.append("")
    lines.append("| Scorer | Params | Exact / 13 | MAE |")
    lines.append("|--------|--------|-----------:|----:|")
    for name, params, _results, exact, mae in all_runs:
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        lines.append(f"| {name} | {params_str} | {exact} | {mae:.2f} |")
    lines.append("")
    lines.append("## Per-folder breakdown (best run)")
    lines.append("")
    # Best = highest exact, tiebreak lowest MAE
    all_runs_sorted = sorted(all_runs, key=lambda r: (-r[3], r[4]))
    best_name, best_params, best_results, best_exact, best_mae = all_runs_sorted[0]
    lines.append(
        f"Best: **{best_name}** with {best_params} - exact {best_exact}/13, MAE {best_mae:.2f}"
    )
    lines.append("")
    lines.append("| Folder | Expected | Counted | Diff |")
    lines.append("|--------|---------:|--------:|-----:|")
    for r in best_results:
        diff = r.counted - r.expected
        lines.append(f"| {r.name} | {r.expected} | {r.counted} | {diff:+d} |")
    return "\n".join(lines)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    if not CORPUS_ROOT.exists():
        logger.error("Corpus not found: %s", CORPUS_ROOT)
        return 1

    folders = [f for f in sorted(CORPUS_ROOT.iterdir()) if f.is_dir()]
    logger.info("Found %d folders in corpus", len(folders))

    all_runs: list[tuple[str, dict, list[FolderResult], int, float]] = []

    for params in FIND_PEAKS_GRID:
        logger.info("Running find_peaks with %s", params)
        results = run_scorer("find_peaks", params, folders)
        exact, mae = summarize(results)
        logger.info("  exact=%d/13  MAE=%.2f", exact, mae)
        all_runs.append(("find_peaks", params, results, exact, mae))

    for pct in PERCENTILE_GRID:
        params = {"percentile": pct}
        logger.info("Running percentile with %s", params)
        results = run_scorer("percentile", params, folders)
        exact, mae = summarize(results)
        logger.info("  exact=%d/13  MAE=%.2f", exact, mae)
        all_runs.append(("percentile", params, results, exact, mae))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now():%Y-%m-%d}-dit-cosine-rio-bueno-benchmark.md"
    report_path.write_text(format_report(all_runs), encoding="utf-8")
    logger.info("Wrote report: %s", report_path)

    # Print summary to stdout
    best = max(all_runs, key=lambda r: (r[3], -r[4]))
    print(
        f"BEST: {best[0]} {best[1]} - exact {best[3]}/13, MAE {best[4]:.2f}  "
        f"(baseline: exact {BASELINE_RESCUE_C_EXACT}/13, MAE {BASELINE_RESCUE_C_MAE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
