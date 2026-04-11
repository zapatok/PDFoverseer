"""DiT+cosine benchmark on the canonical project fixtures.

Complement to benchmark_rio_bueno_dit.py: that one uses a coarse oracle
(folder-name digit) on a single corpus. This script uses the project's
canonical per-page ground truth in eval/fixtures/real/*.json, paired with
the source PDFs in data/samples/.

For each (PDF, fixture) pair we:
  1. Embed the PDF with DiT (cached).
  2. Extract ground-truth covers from the JSON: pages where curr == 1.
  3. Skip pages where curr is None (failed OCR -> no label).
  4. Run scorer_dit_find_peaks and scorer_dit_percentile across the same
     hyperparameter grid as the rio_bueno script.
  5. Compute precision / recall / F1 over cover indices, plus the
     count-match metric used by the rio_bueno benchmark.

Output: docs/superpowers/reports/<date>-dit-cosine-canonical-fixtures.md
"""

from __future__ import annotations

import io
import json
import logging
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

FIXTURES_DIR = Path("eval/fixtures/real")
SAMPLES_DIR = Path("data/samples")
REPORT_DIR = Path("docs/superpowers/reports")

# Hyperparameter sweep - same shape as benchmark_rio_bueno_dit.py for parity.
FIND_PEAKS_GRID = [
    {"prominence": 0.05, "distance": 1},
    {"prominence": 0.1, "distance": 1},
    {"prominence": 0.1, "distance": 2},
    {"prominence": 0.2, "distance": 2},
    {"prominence": 0.3, "distance": 2},
]
PERCENTILE_GRID = [60.0, 65.0, 70.0, 75.0, 80.0, 85.0]

# Bucket criteria from the original plan.
BASELINE_RESCUE_C_NOTE = (
    "rio_bueno baseline: rescue_c -> 4/13 exact, MAE 9.5. "
    "Canonical fixtures use F1 instead of count-MAE so the bucket "
    "criteria below are reinterpreted."
)


@dataclass
class FixtureResult:
    name: str
    family: str
    n_pages: int
    n_pages_labeled: int
    expected_covers: list[int]
    predicted_covers: list[int]
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    count_diff: int  # predicted_count - expected_count


def _family_of(name: str) -> str:
    """Group fixture name into a coarse family label."""
    upper = name.upper()
    for prefix in (
        "ART",
        "CH_BSM",
        "CH",
        "HLL",
        "INS_31",
        "INSAP",
        "JOGA",
        "RACO",
        "CRS",
        "SAEZ",
        "QUEVEDO",
        "CASTRO",
        "CHAR",
        "ALUM",
    ):
        if upper.startswith(prefix):
            return prefix
    return "OTHER"


def _find_pdf(name: str) -> Path | None:
    """Heuristic: try several filename variants in data/samples/."""
    candidates = [
        f"{name}.pdf",
        f"{name}docs.pdf",
        f"{name}.pdf.pdf",
        f"{name.lower()}.pdf",
        f"{name.lower()}docs.pdf",
    ]
    for c in candidates:
        p = SAMPLES_DIR / c
        if p.exists():
            return p
    return None


def _load_fixture(json_path: Path) -> dict:
    """Load a single fixture JSON without instantiating PageRead (no domain dep)."""
    return json.loads(json_path.read_text(encoding="utf-8"))


def _expected_covers_from_fixture(fixture: dict) -> tuple[list[int], int]:
    """Return (sorted cover indices [0-based], number of pages with a label).

    A "cover" is any page where curr == 1.
    Pages with curr is None (failed OCR) are excluded from labeled count.
    """
    covers: list[int] = []
    labeled = 0
    for r in fixture["reads"]:
        if r.get("curr") is None:
            continue
        labeled += 1
        if r["curr"] == 1:
            covers.append(int(r["pdf_page"]) - 1)  # JSON is 1-indexed
    return sorted(covers), labeled


def _prf1(predicted: set[int], expected: set[int]) -> tuple[int, int, int, float, float, float]:
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return tp, fp, fn, precision, recall, f1


def run_scorer_on_fixtures(
    scorer_name: str,
    params: dict,
    fixtures: list[tuple[str, Path, dict]],
) -> list[FixtureResult]:
    results: list[FixtureResult] = []
    for name, pdf_path, fixture in fixtures:
        embeddings = ensure_dit_embeddings(str(pdf_path))
        if scorer_name == "find_peaks":
            predicted = score_dit_find_peaks(embeddings, **params)
        elif scorer_name == "percentile":
            predicted = score_dit_percentile(embeddings, **params)
        else:
            raise ValueError(f"unknown scorer {scorer_name}")

        expected, labeled = _expected_covers_from_fixture(fixture)
        # Restrict predicted to pages within the labeled range (paranoia: cache
        # could in theory disagree with json on n_pages, e.g. PDF was re-extracted)
        n_pages = embeddings.shape[0]
        predicted = [p for p in predicted if 0 <= p < n_pages]

        tp, fp, fn, prec, rec, f1 = _prf1(set(predicted), set(expected))
        results.append(
            FixtureResult(
                name=name,
                family=_family_of(name),
                n_pages=n_pages,
                n_pages_labeled=labeled,
                expected_covers=expected,
                predicted_covers=predicted,
                tp=tp,
                fp=fp,
                fn=fn,
                precision=prec,
                recall=rec,
                f1=f1,
                count_diff=len(predicted) - len(expected),
            )
        )
    return results


def aggregate(results: list[FixtureResult]) -> dict:
    n = len(results)
    micro_tp = sum(r.tp for r in results)
    micro_fp = sum(r.fp for r in results)
    micro_fn = sum(r.fn for r in results)
    micro_p = micro_tp / (micro_tp + micro_fp) if (micro_tp + micro_fp) > 0 else 0.0
    micro_r = micro_tp / (micro_tp + micro_fn) if (micro_tp + micro_fn) > 0 else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) > 0 else 0.0
    macro_f1 = sum(r.f1 for r in results) / n if n else 0.0
    exact_count = sum(1 for r in results if r.count_diff == 0)
    mae_count = sum(abs(r.count_diff) for r in results) / n if n else 0.0
    return {
        "n_fixtures": n,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "exact_count": exact_count,
        "mae_count": mae_count,
    }


def by_family(results: list[FixtureResult]) -> dict[str, dict]:
    fams: dict[str, list[FixtureResult]] = {}
    for r in results:
        fams.setdefault(r.family, []).append(r)
    return {f: aggregate(rs) for f, rs in fams.items()}


def format_report(
    fixtures_used: list[tuple[str, Path, dict]],
    skipped: list[tuple[str, str]],
    all_runs: list[tuple[str, dict, list[FixtureResult], dict]],
) -> str:
    lines: list[str] = []
    lines.append("# DiT + Cosine benchmark - canonical project fixtures")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"_{BASELINE_RESCUE_C_NOTE}_")
    lines.append("")
    lines.append("## Fixtures included")
    lines.append("")
    lines.append(
        f"{len(fixtures_used)} fixtures with both JSON ground truth and a PDF in `data/samples/`:"
    )
    lines.append("")
    for name, pdf_path, fixture in fixtures_used:
        expected, labeled = _expected_covers_from_fixture(fixture)
        lines.append(
            f"- **{name}** ({_family_of(name)}) - "
            f"{labeled} labeled pages, {len(expected)} expected covers, "
            f"PDF: `{pdf_path.name}`"
        )
    if skipped:
        lines.append("")
        lines.append(f"Skipped {len(skipped)} fixtures (no matching PDF found):")
        lines.append("")
        for name, reason in skipped:
            lines.append(f"- {name} - {reason}")
    lines.append("")
    lines.append("## Sweep results (aggregated micro-averages)")
    lines.append("")
    lines.append(
        "| Scorer | Params | Micro P | Micro R | Micro F1 | Macro F1 | Exact / N | MAE count |"
    )
    lines.append(
        "|--------|--------|--------:|--------:|---------:|---------:|----------:|----------:|"
    )
    for name, params, _r, agg in all_runs:
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        lines.append(
            f"| {name} | {params_str} | "
            f"{agg['micro_precision']:.3f} | {agg['micro_recall']:.3f} | "
            f"{agg['micro_f1']:.3f} | {agg['macro_f1']:.3f} | "
            f"{agg['exact_count']}/{agg['n_fixtures']} | {agg['mae_count']:.2f} |"
        )

    # Best by micro_f1 for the per-fixture + per-family breakdowns
    best = max(all_runs, key=lambda r: r[3]["micro_f1"])
    best_name, best_params, best_results, best_agg = best
    lines.append("")
    lines.append("## Best run - per-family breakdown")
    lines.append("")
    lines.append(
        f"Best by micro-F1: **{best_name}** with {best_params} - micro F1 {best_agg['micro_f1']:.3f}"
    )
    lines.append("")
    fams = by_family(best_results)
    lines.append("| Family | N | Micro P | Micro R | Micro F1 | Exact count |")
    lines.append("|--------|--:|--------:|--------:|---------:|------------:|")
    for fam in sorted(fams):
        a = fams[fam]
        lines.append(
            f"| {fam} | {a['n_fixtures']} | "
            f"{a['micro_precision']:.3f} | {a['micro_recall']:.3f} | "
            f"{a['micro_f1']:.3f} | {a['exact_count']}/{a['n_fixtures']} |"
        )

    lines.append("")
    lines.append("## Best run - per-fixture detail")
    lines.append("")
    lines.append("| Fixture | Family | Expected | Predicted | TP | FP | FN | P | R | F1 | Diff |")
    lines.append("|---------|--------|---------:|----------:|---:|---:|---:|--:|--:|---:|-----:|")
    for r in best_results:
        lines.append(
            f"| {r.name} | {r.family} | {len(r.expected_covers)} | "
            f"{len(r.predicted_covers)} | {r.tp} | {r.fp} | {r.fn} | "
            f"{r.precision:.2f} | {r.recall:.2f} | {r.f1:.2f} | "
            f"{r.count_diff:+d} |"
        )
    return "\n".join(lines)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    if not FIXTURES_DIR.exists():
        logger.error("Fixtures directory not found: %s", FIXTURES_DIR)
        return 1

    fixtures_used: list[tuple[str, Path, dict]] = []
    skipped: list[tuple[str, str]] = []

    for json_path in sorted(FIXTURES_DIR.glob("*.json")):
        fixture = _load_fixture(json_path)
        name = fixture.get("name", json_path.stem)
        pdf = _find_pdf(name)
        if pdf is None:
            skipped.append((name, f"no PDF in {SAMPLES_DIR}"))
            continue
        fixtures_used.append((name, pdf, fixture))

    if not fixtures_used:
        logger.error("No fixture/PDF pairs found")
        return 1

    logger.info("Using %d fixtures (%d skipped)", len(fixtures_used), len(skipped))
    for name, pdf_path, _ in fixtures_used:
        logger.info("  %s -> %s", name, pdf_path.name)

    all_runs: list[tuple[str, dict, list[FixtureResult], dict]] = []

    for params in FIND_PEAKS_GRID:
        logger.info("Running find_peaks with %s", params)
        results = run_scorer_on_fixtures("find_peaks", params, fixtures_used)
        agg = aggregate(results)
        logger.info(
            "  micro_f1=%.3f  exact=%d/%d  MAE=%.2f",
            agg["micro_f1"],
            agg["exact_count"],
            agg["n_fixtures"],
            agg["mae_count"],
        )
        all_runs.append(("find_peaks", params, results, agg))

    for pct in PERCENTILE_GRID:
        params = {"percentile": pct}
        logger.info("Running percentile with %s", params)
        results = run_scorer_on_fixtures("percentile", params, fixtures_used)
        agg = aggregate(results)
        logger.info(
            "  micro_f1=%.3f  exact=%d/%d  MAE=%.2f",
            agg["micro_f1"],
            agg["exact_count"],
            agg["n_fixtures"],
            agg["mae_count"],
        )
        all_runs.append(("percentile", params, results, agg))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now():%Y-%m-%d}-dit-cosine-canonical-fixtures.md"
    report_path.write_text(format_report(fixtures_used, skipped, all_runs), encoding="utf-8")
    logger.info("Wrote report: %s", report_path)

    best = max(all_runs, key=lambda r: r[3]["micro_f1"])
    print(
        f"BEST: {best[0]} {best[1]} - "
        f"micro_f1={best[3]['micro_f1']:.3f}  "
        f"exact={best[3]['exact_count']}/{best[3]['n_fixtures']}  "
        f"MAE={best[3]['mae_count']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
