"""
cli.py — Terminal tester for ocr_matcher.

Usage:
    python -m ocr_matcher Pagina
    python -m ocr_matcher Pagina Inspeccion Firma
"""

import sys
import re

from ocr_matcher.pattern import (
    generate_charclass_pattern,
    generate_fuzzy_pattern,
    _ALTERNATIVES,
    _strip_accents,
)
from ocr_matcher.distance import ocr_distance


def _list_variants(word: str, compiled: re.Pattern) -> list[tuple[str, float]]:
    """
    Generate candidate strings by single-char substitution and check which match.
    Returns (variant, ocr_distance) pairs sorted by distance ascending.
    """
    base = _strip_accents(word).lower()
    candidates: list[str] = [base]

    for pos, c in enumerate(base):
        for alt in _ALTERNATIVES.get(c, []):
            alt_base = _strip_accents(alt).lower()
            variant = base[:pos] + alt_base + base[pos + 1:]
            candidates.append(variant)

    # Abbreviations
    candidates += [base[:2] + ".", base[:2], base[:3] + "."]
    # Noise injection after first char
    candidates += [base[0] + "@" + base[1:], base[0] + "4" + base[1:]]

    seen: set[str] = set()
    results: list[tuple[str, float]] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            if compiled.search(c):
                dist = ocr_distance(c, base, ignore_case=True)
                results.append((c, dist))

    results.sort(key=lambda x: x[1])
    return results


def show(word: str) -> None:
    charclass_pat = generate_charclass_pattern(word)
    fuzzy_pat = generate_fuzzy_pattern(word, k=1)
    compiled = re.compile(charclass_pat, re.IGNORECASE)

    variants = _list_variants(word, compiled)

    print(f"\n{'='*60}")
    print(f"  Palabra  : {word}")
    print(f"  Patron   : {charclass_pat}")
    print(f"  Fuzzy    : {fuzzy_pat}")
    print(f"{'='*60}")
    print(f"  {'Variante':<25}  {'Dist. OCR':>10}  {'Prob.'}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*12}")
    for variant, dist in variants:
        bar = "#" * max(1, int((1.0 - min(dist, 1.0)) * 12))
        print(f"  {variant:<25}  {dist:>10.3f}  {bar}")
    print(f"\n  Total variantes cubiertas: {len(variants)}")


def main() -> None:
    words = sys.argv[1:] if len(sys.argv) > 1 else ["Pagina"]
    for w in words:
        show(w)


if __name__ == "__main__":
    main()
