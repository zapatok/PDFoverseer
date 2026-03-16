"""
regex_builder.py — Standalone module (not connected to pipeline yet)

Takes a word and generates an OCR-aware regex pattern that covers:
  - Diacritic variants   (á→a, ñ→n, etc.)
  - OCR char confusions  (g↔q, i↔1↔l, 0↔O, s↔5, z↔2, etc.)
  - Abbreviations        (optional suffix after a mandatory prefix)
  - Trailing period      (Pag. vs Pag)

Usage:
    python regex_builder.py
    python regex_builder.py "Página"
    python regex_builder.py "Inspección" "Firma" "Fecha"
"""

import re
import sys
import unicodedata

# ---------------------------------------------------------------------------
# OCR Confusion Table
# Each entry maps a base ASCII char to the regex character class that
# captures it AND its known Tesseract/EasyOCR misreads.
# ---------------------------------------------------------------------------
_OCR_CLASS: dict[str, str] = {
    "a": "[aáàâ@ä]",
    "b": "[b6B]",
    "c": "[c(©]",
    "d": "[d]",
    "e": "[eéèê3ë]",
    "f": "[f]",
    "g": "[gq9G]",
    "h": "[h#]",
    "i": "[i1l|íì!]",
    "j": "[jJ]",
    "k": "[k]",
    "l": "[l1i|L]",
    "m": "[m]",
    "n": "[nñN]",
    "o": "[o0Oóòôö]",
    "p": "[pP]",
    "q": "[qgQ]",
    "r": "[r]",
    "s": "[s5$S]",
    "t": "[t+T]",
    "u": "[uúùüU]",
    "v": "[vV]",
    "w": "[wW]",
    "x": "[xX]",
    "y": "[yýY]",
    "z": "[z2Z]",
    # Digits
    "0": "[0oO]",
    "1": "[1il|]",
    "2": "[2zZ]",
    "3": "[3e]",
    "4": "[4]",
    "5": "[5s$]",
    "6": "[6b]",
    "7": "[7]",
    "8": "[8B]",
    "9": "[9gq]",
}

DEFAULT_MIN_PREFIX = 2


def _strip_accents(s: str) -> str:
    """Decompose unicode and drop combining marks → pure ASCII base."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _char_class(c: str) -> str:
    """Return the regex character class for one char (handles upper/lower)."""
    base = _strip_accents(c).lower()
    cls = _OCR_CLASS.get(base)
    if cls:
        return cls
    return re.escape(c)


def generate_pattern(
    word: str,
    min_prefix: int = DEFAULT_MIN_PREFIX,
    allow_noise: bool = True,
) -> str:
    """
    Generate an OCR-aware regex pattern from a plain word.

    Args:
        word:        The word to build a pattern for (e.g. "Página").
        min_prefix:  How many leading chars stay mandatory. The rest become
                     optional (covers abbreviations like "Pag." or "Pg").
        allow_noise: If True, a single .? is inserted after the first char
                     to absorb one-char OCR noise (e.g. P@gina).

    Returns:
        A raw pattern string (not compiled).
    """
    if not word:
        return ""

    word = word.strip()
    n = len(word)

    prefix_len = min(min_prefix, n)
    prefix_chars = word[:prefix_len]
    suffix_chars = word[prefix_len:]

    # Build mandatory prefix
    if len(prefix_chars) == 1:
        prefix_pat = _char_class(prefix_chars[0])
    else:
        first = _char_class(prefix_chars[0])
        rest = "".join(_char_class(c) for c in prefix_chars[1:])
        if allow_noise and n > min_prefix:
            prefix_pat = first + ".?" + rest
        else:
            prefix_pat = first + rest

    # Build optional suffix (abbreviation support)
    if suffix_chars:
        suffix_pat = "".join(_char_class(c) for c in suffix_chars)
        full_pat = prefix_pat + f"(?:{suffix_pat})?"
    else:
        full_pat = prefix_pat

    # Optional trailing period (Pag. vs Pag)
    full_pat += r"\.?"

    # Word boundary at the start so we don't match substrings
    # e.g. "in" inside "Pagina" when searching for "Inspeccion"
    return r"\b" + full_pat


def compile_pattern(word: str, **kwargs) -> re.Pattern:
    """Compile generate_pattern() result with IGNORECASE."""
    return re.compile(generate_pattern(word, **kwargs), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Quick interactive tester
# ---------------------------------------------------------------------------
def _make_tests(word: str) -> list[tuple[str, bool]]:
    """Return (test_string, should_match) pairs for a given word."""
    w = word.strip()
    # Base: the word itself and common OCR variants
    base = _strip_accents(w).lower()

    positives = [
        w,                                      # exact
        _strip_accents(w),                      # no accents
        w[:2] + ".",                            # 2-char abbrev + period
        base[0] + "4" + base[1:],              # noise after first char
        base[0] + "@" + base[1:],              # noise after first char
        base.replace("g", "q"),                 # g→q OCR
        base.replace("i", "1"),                 # i→1 OCR
        base.replace("a", "@"),                 # a→@ OCR
        "  " + w + "  ",                        # surrounded by spaces
    ]
    negatives = [
        "nada",
        "relevante",
        "12345",
        # Make sure a totally different word doesn't match
        "Contrato",
        "XYZ",
    ]
    pairs = [(p, True) for p in positives] + [(n, False) for n in negatives]
    # Deduplicate
    seen: set[str] = set()
    result = []
    for s, expected in pairs:
        if s not in seen:
            seen.add(s)
            result.append((s, expected))
    return result


def _demo(words: list[str]) -> None:
    # Reference: the handcrafted regex from analyzer.py (only meaningful for Pagina)
    REFERENCE = r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})"
    ref_re = re.compile(REFERENCE, re.IGNORECASE)

    for word in words:
        pat = generate_pattern(word)
        compiled = re.compile(pat, re.IGNORECASE)
        test_cases = _make_tests(word)

        print(f"\n{'='*62}")
        print(f"  Input   : {word!r}")
        print(f"  Pattern : {pat}")
        print(f"{'='*62}")
        print(f"  {'Test string':<32} {'Expect':>7} {'Got':>5}")
        print(f"  {'-'*32} {'-'*7} {'-'*5}")

        ok_count = 0
        for t, expected in test_cases:
            got = bool(compiled.search(t))
            status = "OK " if got == expected else "FAIL"
            if got == expected:
                ok_count += 1
            disp = repr(t) if len(t) < 30 else repr(t[:27] + "...")
            print(f"  {disp:<32} {'[Y]' if expected else '[ ]':>7} {'[Y]' if got else '[ ]':>5}  {status}")

        print(f"\n  Score: {ok_count}/{len(test_cases)}")


def _extract_chars_from_class(cls: str) -> list[str]:
    """Pull the individual characters out of a regex class like '[aáà@ä]'."""
    # Strip outer brackets
    inner = cls.lstrip("\\b").strip("[]")
    # Simple extraction: just grab non-backslash chars
    chars = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            chars.append(inner[i + 1])
            i += 2
        else:
            chars.append(inner[i])
            i += 1
    return chars


def show_coverage(word: str) -> None:
    """
    Print the generated pattern and a list of example strings it covers.
    Generates variants by substituting each character with its OCR alternatives.
    """
    pat = generate_pattern(word)
    compiled = re.compile(pat, re.IGNORECASE)

    word = word.strip()
    base = _strip_accents(word).lower()
    n = len(base)

    # Build per-position alternatives (only lowercase base chars)
    positions: list[list[str]] = []
    for c in base:
        cls = _OCR_CLASS.get(c, c)
        alts = _extract_chars_from_class(cls)
        # Keep at most 4 per position to avoid explosion
        positions.append(alts[:4])

    # Generate variants: swap one position at a time (not full cartesian product)
    candidates: list[str] = []

    # 1. Exact word (stripped accents)
    candidates.append(base)

    # 2. Single-char substitutions
    for pos, alts in enumerate(positions):
        for alt in alts:
            if alt != base[pos]:
                variant = base[:pos] + alt + base[pos + 1:]
                candidates.append(variant)

    # 3. Abbreviations (2-char prefix + period, no period)
    candidates.append(base[:2] + ".")
    candidates.append(base[:2])
    if n > 3:
        candidates.append(base[:3] + ".")

    # 4. Noise injection after first char
    candidates.append(base[0] + "@" + base[1:])
    candidates.append(base[0] + "4" + base[1:])

    # Deduplicate preserving order
    seen: set[str] = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    # Filter: only those that actually match
    matched = [c for c in unique if compiled.search(c)]
    no_match = [c for c in unique if not compiled.search(c)]

    print(f"\nWord    : {word!r}")
    print(f"Pattern : {pat}")
    print(f"\n  Abarca ({len(matched)} variantes):")
    for v in matched:
        print(f"    {v}")
    if no_match:
        print(f"\n  No abarca ({len(no_match)}):")
        for v in no_match:
            print(f"    {v}")


if __name__ == "__main__":
    words = sys.argv[1:] if len(sys.argv) > 1 else ["Pagina"]
    for w in words:
        show_coverage(w)
