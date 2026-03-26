"""
tools/pattern_eval.py — Pattern validation harness
===================================================
Tests OCR page-number pattern variants against real Tesseract output stored in
data/ocr_all/all_index.csv (captured by tools/capture_all.py).

For each PDF with a known expected_total (structural ground truth), reports:
  - matches   : number of strips where the variant fires
  - correct   : matches where total == expected_total
  - FP        : matches where total != expected_total
  - FP rate   : FP / matches
  - dist      : distribution of matched totals

This lets you evaluate a new pattern before deploying to the live pipeline.

Usage:
    python tools/pattern_eval.py
    python tools/pattern_eval.py --csv data/ocr_all/all_index.csv
    python tools/pattern_eval.py --pdfs ART_670 INS_31.pdf
    python tools/pattern_eval.py --sample 100  # random sample per PDF
    python tools/pattern_eval.py --tier tier2_text
"""

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# OCR digit normalization (same as core/utils.py)
# ---------------------------------------------------------------------------
_Z2 = re.compile(r"(?<!\d)Z(?!\d)")
_OCR_DIGIT = str.maketrans("OoIilLzZ|tT'''`´", "0011112201111111")
DIGIT_CHARS = r"[0-9OoIilL|zZtT\'\'\'\`\´]"


def _to_int(s: str) -> int:
    return int(s.translate(_OCR_DIGIT))


def _apply(pat: re.Pattern, text: str) -> tuple[int | None, int | None]:
    """Apply a single pattern and return (curr, total) or (None, None)."""
    t = _Z2.sub("2", text)
    m = pat.search(t)
    if not m:
        return None, None
    try:
        c, tot = _to_int(m.group(1)), _to_int(m.group(2))
    except (ValueError, IndexError):
        return None, None
    if 0 < c <= tot <= 99:
        return c, tot
    return None, None


# ---------------------------------------------------------------------------
# Pattern variants to compare
# ---------------------------------------------------------------------------
_D = DIGIT_CHARS  # shorthand

VARIANTS: dict[str, re.Pattern] = {
    # 1. Current production: P-prefix only
    "P-prefix": re.compile(
        rf"P.{{0,6}}\s*({_D}{{1,3}})\s*\.?\s*d[ea]\s*({_D}{{1,3}})",
        re.IGNORECASE,
    ),
    # 2. Word anchor: any \\w+ before N de M (reverted fallback)
    "word-anchor": re.compile(
        rf"\w+\s+({_D}{{1,3}})\s+d[ea]\s+({_D}{{1,3}})",
        re.IGNORECASE,
    ),
    # 3. Bare N de M: digits only, no anchor
    "bare-NdeM": re.compile(
        rf"({_D}{{1,3}})\s+d[ea]\s+({_D}{{1,3}})",
        re.IGNORECASE,
    ),
    # 4. P-prefix OR word-anchor combined (variants 1+2, first-match wins)
    # Implemented below as a two-step check, not a single regex.
    # Shown here for documentation — evaluated separately in code.
}

# PDFs where we know the structural expected total
# (all docs in the PDF are N pages, so any OCR match with total != N is a FP)
KNOWN_TOTALS: dict[str, int] = {
    "ART_670":   4,
    "INS_31.pdf": 1,
}

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _eval_variants(
    rows: list[dict],
    variants: dict[str, re.Pattern],
    expected_total: int,
    tier: str,
) -> dict[str, dict]:
    """
    For each variant, count matches / correct / FP and collect total distribution.
    Also evaluates a combined 'P-prefix+bare' meta-variant (first-match wins).
    """
    results: dict[str, dict] = {}
    n = len(rows)

    for name, pat in variants.items():
        matches = 0
        correct = 0
        fp = 0
        total_dist: Counter = Counter()
        fp_examples: list[str] = []

        for row in rows:
            text = row.get(tier, "") or ""
            c, tot = _apply(pat, text)
            if tot is not None:
                matches += 1
                total_dist[tot] += 1
                if tot == expected_total:
                    correct += 1
                else:
                    fp += 1
                    if len(fp_examples) < 3:
                        snippet = text.replace("\n", " ")[:80]
                        fp_examples.append(f"  p{row['page_num']:>4}: {snippet!r}")

        results[name] = {
            "n": n,
            "matches": matches,
            "no_match": n - matches,
            "correct": correct,
            "fp": fp,
            "fp_rate": fp / matches if matches else 0.0,
            "match_rate": matches / n if n else 0.0,
            "total_dist": total_dist,
            "fp_examples": fp_examples,
        }

    # Combined P-prefix + bare-NdeM (first-match wins, same as _PAGE_PATTERNS list)
    combined_name = "P-prefix+bare"
    p1 = variants["P-prefix"]
    p2 = variants["bare-NdeM"]
    matches = correct = fp = 0
    total_dist = Counter()
    fp_examples = []

    for row in rows:
        text = row.get(tier, "") or ""
        c, tot = _apply(p1, text)
        if tot is None:
            c, tot = _apply(p2, text)
        if tot is not None:
            matches += 1
            total_dist[tot] += 1
            if tot == expected_total:
                correct += 1
            else:
                fp += 1
                if len(fp_examples) < 3:
                    snippet = text.replace("\n", " ")[:80]
                    fp_examples.append(f"  p{row['page_num']:>4}: {snippet!r}")

    results[combined_name] = {
        "n": n,
        "matches": matches,
        "no_match": n - matches,
        "correct": correct,
        "fp": fp,
        "fp_rate": fp / matches if matches else 0.0,
        "match_rate": matches / n if n else 0.0,
        "total_dist": total_dist,
        "fp_examples": fp_examples,
    }

    return results


def _print_results(pdf: str, expected_total: int, results: dict[str, dict]) -> None:
    n = next(iter(results.values()))["n"]
    print(f"\n{'='*70}")
    print(f"PDF: {pdf}  |  pages sampled: {n}  |  expected total: {expected_total}")
    print(f"{'='*70}")
    print(f"{'variant':<20} {'match':>6} {'miss':>6} {'correct':>8} {'FP':>6} {'FP%':>7}  top totals")
    print(f"{'-'*20} {'-'*6} {'-'*6} {'-'*8} {'-'*6} {'-'*7}  ----------")

    for name, r in results.items():
        top = ", ".join(
            f"{t}×{c}" for t, c in r["total_dist"].most_common(5)
        )
        fp_pct = f"{r['fp_rate']*100:.1f}%" if r["matches"] else "  —"
        print(
            f"{name:<20} {r['matches']:>6} {r['no_match']:>6} "
            f"{r['correct']:>8} {r['fp']:>6} {fp_pct:>7}  {top}"
        )
        if r["fp_examples"]:
            print("  FP examples:")
            for ex in r["fp_examples"]:
                print(ex)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate pattern variants on real OCR strips")
    ap.add_argument("--csv", default="data/ocr_all/all_index.csv", help="Path to all_index.csv")
    ap.add_argument("--pdfs", nargs="+", default=list(KNOWN_TOTALS.keys()), help="PDF nicknames to evaluate")
    ap.add_argument("--tier", default="tier1_text", choices=["tier1_text", "tier2_text"], help="OCR tier to use")
    ap.add_argument("--sample", type=int, default=0, help="Random sample N rows per PDF (0 = all)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Run tools/capture_all.py first.", file=sys.stderr)
        sys.exit(1)

    # Load CSV grouped by pdf_nickname
    by_pdf: dict[str, list[dict]] = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_pdf[row["pdf_nickname"]].append(row)

    for pdf in args.pdfs:
        if pdf not in KNOWN_TOTALS:
            print(f"WARNING: {pdf!r} not in KNOWN_TOTALS — skipping (add expected total to script)")
            continue
        rows = by_pdf.get(pdf, [])
        if not rows:
            print(f"WARNING: no rows found for {pdf!r}")
            continue

        if args.sample and args.sample < len(rows):
            import random
            rng = random.Random(args.seed)
            rows = rng.sample(rows, args.sample)

        expected = KNOWN_TOTALS[pdf]
        results = _eval_variants(rows, VARIANTS, expected, args.tier)
        _print_results(pdf, expected, results)

    print()


if __name__ == "__main__":
    main()
