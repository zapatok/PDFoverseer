"""Leave-one-fixture-out benchmark for the DiT classifier head.

For each canonical fixture (eval/fixtures/real/*.json with a matching
PDF in data/samples/), train the classifier head on the OTHER 20
fixtures' DiT embeddings + per-page labels, then evaluate on the
held-out fixture's pages. Report per-fixture and aggregate F1.

This is the Option C MVP from the dit-embeddings-option-b plan,
fast-tracked because:
  1. The 21 canonical fixtures already provide ~3500 per-page labels
     (curr==1 = cover, else = not cover) - no manual labeling needed.
  2. DiT embeddings for all 21 PDFs are already cached on disk by
     benchmark_canonical_dit.py, so this script just consumes them.
  3. The classifier head is tiny (768 -> 64 -> 1) and trains in
     seconds per fold on the GTX 1080.

Output: docs/superpowers/reports/<date>-dit-classifier-lofo.md
"""

from __future__ import annotations

import io
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.pixel_density.dit_classifier_head import (  # noqa: E402
    predict_proba,
    train_head,
)
from eval.pixel_density.dit_embeddings import ensure_dit_embeddings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path("eval/fixtures/real")
SAMPLES_DIR = Path("data/samples")
REPORT_DIR = Path("docs/superpowers/reports")

# Decision threshold sweep applied to predict_proba output.
# We pick the best threshold per held-out fixture? No - that would leak.
# We pick the best threshold based on the training-set OOF or just sweep and
# report each. For an honest LOFO number we evaluate at threshold 0.5 (the
# Bayes-optimal point for a calibrated BCE+pos_weight model) and ALSO sweep
# to show the precision/recall tradeoff.
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7]
DEFAULT_THRESHOLD = 0.5


@dataclass
class FoldResult:
    name: str
    family: str
    n_pages: int
    expected_covers: int
    predicted_covers: int  # at DEFAULT_THRESHOLD
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    threshold_sweep: dict[float, tuple[float, float, float]]  # thr -> (P, R, F1)


def _family_of(name: str) -> str:
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
    for c in (
        f"{name}.pdf",
        f"{name}docs.pdf",
        f"{name}.pdf.pdf",
        f"{name.lower()}.pdf",
        f"{name.lower()}docs.pdf",
    ):
        p = SAMPLES_DIR / c
        if p.exists():
            return p
    return None


def _labels_from_fixture(fixture: dict, n_pages: int) -> np.ndarray | None:
    """Build a (n_pages,) {0,1} label array. Returns None if any unlabeled.

    Pages where curr is None (failed OCR) make the fixture unusable for
    training because we can't decide their label. We mask them out by
    returning None for that fixture.
    """
    labels = np.full(n_pages, -1, dtype=np.int8)
    for r in fixture["reads"]:
        page_idx = int(r["pdf_page"]) - 1  # JSON 1-indexed
        if not (0 <= page_idx < n_pages):
            continue
        if r.get("curr") is None:
            continue
        labels[page_idx] = 1 if r["curr"] == 1 else 0
    return labels


def _prf1(predicted: np.ndarray, expected: np.ndarray) -> tuple[int, int, int, float, float, float]:
    pred_b = predicted.astype(bool)
    exp_b = expected.astype(bool)
    tp = int(np.sum(pred_b & exp_b))
    fp = int(np.sum(pred_b & ~exp_b))
    fn = int(np.sum(~pred_b & exp_b))
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    return tp, fp, fn, p, r, f1


def load_all_fixtures() -> list[tuple[str, np.ndarray, np.ndarray]]:
    """Return list of (name, embeddings, labels) for usable fixtures.

    Skips fixtures with no matching PDF or with unlabeled pages
    (logs both reasons).
    """
    out: list[tuple[str, np.ndarray, np.ndarray]] = []
    skipped: list[tuple[str, str]] = []

    for json_path in sorted(FIXTURES_DIR.glob("*.json")):
        fixture = json.loads(json_path.read_text(encoding="utf-8"))
        name = fixture.get("name", json_path.stem)
        pdf = _find_pdf(name)
        if pdf is None:
            skipped.append((name, "no PDF"))
            continue
        embeddings = ensure_dit_embeddings(str(pdf))
        labels = _labels_from_fixture(fixture, embeddings.shape[0])
        if labels is None:
            skipped.append((name, "unlabeled pages"))
            continue
        # Mask any pages that remained -1 (no read for that index)
        mask = labels != -1
        if mask.sum() == 0:
            skipped.append((name, "all pages unlabeled"))
            continue
        out.append((name, embeddings[mask], labels[mask].astype(np.int64)))

    if skipped:
        for n, reason in skipped:
            logger.info("  SKIP %s: %s", n, reason)
    return out


def lofo_evaluate(
    fixtures: list[tuple[str, np.ndarray, np.ndarray]],
    *,
    epochs: int = 30,
    seed: int = 0,
) -> list[FoldResult]:
    """Run leave-one-fixture-out evaluation."""
    results: list[FoldResult] = []
    n = len(fixtures)
    for i, (name, X_test, y_test) in enumerate(fixtures):
        # Concatenate the other 20 fixtures' data for training.
        train_X_parts = [X for j, (_, X, _) in enumerate(fixtures) if j != i]
        train_y_parts = [y for j, (_, _, y) in enumerate(fixtures) if j != i]
        X_train = np.concatenate(train_X_parts, axis=0)
        y_train = np.concatenate(train_y_parts, axis=0)

        logger.info(
            "[%d/%d] %s  train=%d  test=%d  pos_train=%d/%d",
            i + 1,
            n,
            name,
            X_train.shape[0],
            X_test.shape[0],
            int((y_train == 1).sum()),
            X_train.shape[0],
        )

        model, _meta = train_head(X_train, y_train, epochs=epochs, seed=seed)
        probs = predict_proba(model, X_test)

        # Threshold sweep for the per-fold report
        sweep: dict[float, tuple[float, float, float]] = {}
        for thr in THRESHOLDS:
            preds = (probs >= thr).astype(np.int64)
            _, _, _, p, r, f1 = _prf1(preds, y_test)
            sweep[thr] = (p, r, f1)

        # Default threshold result for the headline metrics
        preds = (probs >= DEFAULT_THRESHOLD).astype(np.int64)
        tp, fp, fn, p, r, f1 = _prf1(preds, y_test)

        results.append(
            FoldResult(
                name=name,
                family=_family_of(name),
                n_pages=int(X_test.shape[0]),
                expected_covers=int((y_test == 1).sum()),
                predicted_covers=int(preds.sum()),
                tp=tp,
                fp=fp,
                fn=fn,
                precision=p,
                recall=r,
                f1=f1,
                threshold_sweep=sweep,
            )
        )
        logger.info(
            "    expected=%d predicted=%d  P=%.3f R=%.3f F1=%.3f",
            int((y_test == 1).sum()),
            int(preds.sum()),
            p,
            r,
            f1,
        )

    return results


def aggregate(results: list[FoldResult]) -> dict:
    n = len(results)
    if n == 0:
        return {}
    micro_tp = sum(r.tp for r in results)
    micro_fp = sum(r.fp for r in results)
    micro_fn = sum(r.fn for r in results)
    p = micro_tp / (micro_tp + micro_fp) if (micro_tp + micro_fp) > 0 else 0.0
    r = micro_tp / (micro_tp + micro_fn) if (micro_tp + micro_fn) > 0 else 0.0
    micro_f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    macro_f1 = sum(x.f1 for x in results) / n
    return {
        "n": n,
        "micro_p": p,
        "micro_r": r,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
    }


def by_family(results: list[FoldResult]) -> dict[str, dict]:
    fams: dict[str, list[FoldResult]] = {}
    for r in results:
        fams.setdefault(r.family, []).append(r)
    return {f: aggregate(rs) for f, rs in fams.items()}


def format_report(results: list[FoldResult]) -> str:
    lines: list[str] = []
    lines.append("# DiT classifier head - leave-one-fixture-out benchmark")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(
        "Architecture: 768 -> 64 -> 1 MLP, BCE+pos_weight, Adam lr=1e-3, 30 epochs, threshold=0.5."
    )
    lines.append("")
    lines.append(
        "_Comparison: DiT+cosine percentile p=60 best result was "
        "micro F1 = 0.531 on the same 21 fixtures._"
    )
    lines.append("")

    agg = aggregate(results)
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- Fixtures: {agg['n']}")
    lines.append(f"- Micro precision: {agg['micro_p']:.3f}")
    lines.append(f"- Micro recall:    {agg['micro_r']:.3f}")
    lines.append(f"- **Micro F1:      {agg['micro_f1']:.3f}**")
    lines.append(f"- Macro F1:        {agg['macro_f1']:.3f}")
    lines.append("")

    lines.append("## Per-family")
    lines.append("")
    fams = by_family(results)
    lines.append("| Family | N | Micro P | Micro R | Micro F1 | Macro F1 |")
    lines.append("|--------|--:|--------:|--------:|---------:|---------:|")
    for fam in sorted(fams):
        a = fams[fam]
        lines.append(
            f"| {fam} | {a['n']} | {a['micro_p']:.3f} | {a['micro_r']:.3f} | "
            f"{a['micro_f1']:.3f} | {a['macro_f1']:.3f} |"
        )
    lines.append("")

    lines.append("## Per-fixture (held out)")
    lines.append("")
    lines.append("| Fixture | Family | Pages | Expected | Predicted | TP | FP | FN | P | R | F1 |")
    lines.append("|---------|--------|------:|---------:|----------:|---:|---:|---:|--:|--:|---:|")
    for r in results:
        lines.append(
            f"| {r.name} | {r.family} | {r.n_pages} | {r.expected_covers} | "
            f"{r.predicted_covers} | {r.tp} | {r.fp} | {r.fn} | "
            f"{r.precision:.2f} | {r.recall:.2f} | {r.f1:.2f} |"
        )
    lines.append("")

    lines.append("## Threshold sensitivity (per fixture)")
    lines.append("")
    lines.append("F1 at each decision threshold (rows = fixtures):")
    lines.append("")
    header = "| Fixture | " + " | ".join(f"thr={t:.1f}" for t in THRESHOLDS) + " |"
    sep = "|" + "---|" * (len(THRESHOLDS) + 1)
    lines.append(header)
    lines.append(sep)
    for r in results:
        cells = " | ".join(f"{r.threshold_sweep[t][2]:.2f}" for t in THRESHOLDS)
        lines.append(f"| {r.name} | {cells} |")
    return "\n".join(lines)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    logger.info("Loading fixtures + cached DiT embeddings...")
    fixtures = load_all_fixtures()
    if not fixtures:
        logger.error("No usable fixtures found")
        return 1

    logger.info("Loaded %d fixtures for LOFO", len(fixtures))
    total_pages = sum(X.shape[0] for _, X, _ in fixtures)
    total_covers = sum(int((y == 1).sum()) for _, _, y in fixtures)
    logger.info(
        "Total: %d labeled pages, %d covers (%.1f%%)",
        total_pages,
        total_covers,
        100.0 * total_covers / max(total_pages, 1),
    )

    results = lofo_evaluate(fixtures, epochs=30, seed=0)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now():%Y-%m-%d}-dit-classifier-lofo.md"
    report_path.write_text(format_report(results), encoding="utf-8")
    logger.info("Wrote report: %s", report_path)

    agg = aggregate(results)
    print(
        f"BEST DiT classifier head LOFO: "
        f"micro_f1={agg['micro_f1']:.3f}  macro_f1={agg['macro_f1']:.3f}  "
        f"(baseline DiT+cosine percentile=0.531)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
