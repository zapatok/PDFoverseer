"""
tools/regex_pattern_test.py — Controlled regex pattern comparison test
=======================================================================
Tests 4 regex strategies for "Página N de M" detection on a sample of
success and failure pages from ART_670.

Uses existing OCR text from data/ocr_all/all_index.csv — no re-OCR needed.

Patterns tested
---------------
  CONTROL    current production: P.{0,6} N de M
  NO_ANCHOR  pure N de M, no prefix
  SOFT       N de M where a P-word appears on the same line
  WORD       any word before N de M (\\w+ N de M)

Usage
-----
    python tools/regex_pattern_test.py
    python tools/regex_pattern_test.py --n 25 --seed 42
"""

import argparse
import csv
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils import _PAGE_PATTERNS, _Z2, _to_int

# ─── Pattern definitions ────────────────────────────────────────────────────

# Same digit character class as production
_D = r"[0-9OoIilL|zZtT\'\'\'\`\´]{1,3}"

_CONTROL = _PAGE_PATTERNS[0]  # P.{0,6} N de M

_NO_ANCHOR = re.compile(
    rf"({_D})\s+d[ea]\s+({_D})",
    re.IGNORECASE,
)

# A word starting with P (Página, Pag, Pagina, Pàgina, etc.)
_P_WORD = re.compile(r"\bP\w{0,9}", re.IGNORECASE)

# Any word immediately before N de M
_WORD_ANCHOR = re.compile(
    rf"\w+\s+({_D})\s+d[ea]\s+({_D})",
    re.IGNORECASE,
)


# ─── Parse helpers ──────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return _Z2.sub("2", text)


def _parse_control(text: str) -> tuple[int | None, int | None]:
    m = _CONTROL.search(_norm(text))
    if not m:
        return None, None
    try:
        return _to_int(m.group(1)), _to_int(m.group(2))
    except (ValueError, IndexError):
        return None, None


def _parse_no_anchor(text: str) -> tuple[int | None, int | None]:
    """First plausible N de M match anywhere in text."""
    for m in _NO_ANCHOR.finditer(_norm(text)):
        try:
            c, t = _to_int(m.group(1)), _to_int(m.group(2))
            return c, t
        except (ValueError, IndexError):
            continue
    return None, None


def _parse_word_anchor(text: str) -> tuple[int | None, int | None]:
    """Any word immediately before N de M."""
    for m in _WORD_ANCHOR.finditer(_norm(text)):
        try:
            c, t = _to_int(m.group(1)), _to_int(m.group(2))
            return c, t
        except (ValueError, IndexError):
            continue
    return None, None


def _parse_soft(text: str) -> tuple[int | None, int | None]:
    """N de M where a P-word appears on the same line."""
    for line in _norm(text).splitlines():
        m = _NO_ANCHOR.search(line)
        if not m:
            continue
        if not _P_WORD.search(line):
            continue
        try:
            c, t = _to_int(m.group(1)), _to_int(m.group(2))
            return c, t
        except (ValueError, IndexError):
            continue
    return None, None


def _plausible(curr: int | None, total: int | None) -> bool:
    return curr is not None and total is not None and 1 <= curr <= total <= 999


# ─── Data loading ───────────────────────────────────────────────────────────

def load_art670(csv_path: Path) -> tuple[list[dict], list[dict]]:
    success, fail = [], []
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            if row["pdf_nickname"] != "ART_670":
                continue
            (success if row["tier1_parsed"] else fail).append(row)
    return success, fail


# ─── Report ─────────────────────────────────────────────────────────────────

def _report_section(label: str, rows: list[dict]) -> None:
    n = len(rows)
    print(f"\n{'=' * 70}")
    print(label)
    print("=" * 70)

    counts: dict[str, dict] = {
        k: {"found": 0, "plausible": 0}
        for k in ("control", "no_anchor", "word", "soft")
    }
    disagree: list[tuple] = []  # (page, c_na, t_na, word_ok, soft_ok, text_snippet)

    for row in rows:
        text = row["tier1_text"]
        page = row["page_num"]

        c_ctrl, t_ctrl   = _parse_control(text)
        c_na, t_na       = _parse_no_anchor(text)
        c_word, t_word   = _parse_word_anchor(text)
        c_soft, t_soft   = _parse_soft(text)

        for key, c, t in (
            ("control",   c_ctrl,  t_ctrl),
            ("no_anchor", c_na,    t_na),
            ("word",      c_word,  t_word),
            ("soft",      c_soft,  t_soft),
        ):
            if c is not None:
                counts[key]["found"] += 1
                if _plausible(c, t):
                    counts[key]["plausible"] += 1

        # Pages where no_anchor finds something control misses
        if c_ctrl is None and c_na is not None:
            snippet = text[:100].replace("\n", "\\n")
            disagree.append((page, c_na, t_na, c_word is not None, c_soft is not None, snippet))

    print(f"\n{'Pattern':<12} {'Found':>8} {'Plausible':>10} {'Implausible':>12}")
    print("-" * 45)
    for key in ("control", "no_anchor", "word", "soft"):
        r = counts[key]
        impl = r["found"] - r["plausible"]
        print(
            f"{key:<12}"
            f"  {r['found']:>3}/{n}"
            f"  {r['plausible']:>6}/{n}"
            f"  {impl:>9}"
        )

    print(f"\nDisagreements: no_anchor finds where control misses ({len(disagree)} pages)")
    if disagree:
        print(f"  {'page':>6}  {'result':>8}  word?  soft?  snippet")
        print(f"  {'-'*6}  {'-'*8}  {'-'*5}  {'-'*5}  {'-'*40}")
        for page, c, t, word_ok, soft_ok, snippet in disagree[:15]:
            word_mark = "  yes" if word_ok else "   no"
            soft_mark = "  yes" if soft_ok else "   no"
            print(f"  {page:>6}  {c}/{t:>5}  {word_mark}  {soft_mark}  {snippet!r}")
        if len(disagree) > 15:
            print(f"  ... and {len(disagree) - 15} more")
    else:
        print("  (none — all three patterns agree)")


# ─── Main ───────────────────────────────────────────────────────────────────

def run(n: int = 25, seed: int = 42) -> None:
    csv_path = Path("data/ocr_all/all_index.csv")
    if not csv_path.exists():
        sys.exit(f"ERROR: {csv_path} not found. Run tools/capture_all.py first.")

    success_rows, fail_rows = load_art670(csv_path)
    rng = random.Random(seed)
    sample_s = rng.sample(success_rows, min(n, len(success_rows)))
    sample_f = rng.sample(fail_rows,    min(n, len(fail_rows)))

    print(f"ART_670 — {len(success_rows)} Tier1 successes, {len(fail_rows)} Tier1 failures")
    print(f"Sample  — {len(sample_s)} success + {len(sample_f)} fail  (seed={seed})")

    _report_section(
        f"SUCCESS — {len(sample_s)} pages where Tier1 currently parses correctly",
        sample_s,
    )
    _report_section(
        f"FAILURE — {len(sample_f)} pages where Tier1 currently finds nothing",
        sample_f,
    )
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n",    type=int, default=25, help="pages per group (default 25)")
    ap.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    args = ap.parse_args()
    run(args.n, args.seed)
