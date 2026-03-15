"""
pattern.py — OCR-aware regex pattern generator.

Two modes:
  generate_charclass_pattern(word) → re-compatible character-class pattern
  generate_fuzzy_pattern(word, k)  → regex-module fuzzy pattern (word){e<=k}
"""

import re
import unicodedata

from ocr_matcher.confusion import _RAW

# Build char → list[alternative chars] from the confusion table.
# Only include alternatives with cost strictly less than _ALT_THRESHOLD.
# (Pairs at exactly 0.25 like ('d','a') are excluded — too weak for charclass.)
_ALT_THRESHOLD = 0.25  # strict < (not <=) — pairs at exactly 0.25 are excluded
_ALTERNATIVES: dict[str, list[str]] = {}

for _a, _b, _cost in _RAW:
    if _cost < _ALT_THRESHOLD:
        _ALTERNATIVES.setdefault(_a.lower(), []).append(_b)
        _ALTERNATIVES.setdefault(_b.lower(), []).append(_a)


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _char_class(c: str) -> str:
    """Return a regex character class for `c` including OCR alternatives."""
    base = _strip_accents(c).lower()
    alts = _ALTERNATIVES.get(base, [])
    chars: list[str] = [base]
    for alt in alts:
        stripped = _strip_accents(alt).lower()
        if stripped not in chars:
            chars.append(stripped)
    if len(chars) == 1:
        return re.escape(chars[0])
    inner = "".join(
        re.escape(ch) if ch in r'\.^$*+?{}[]|()' else ch
        for ch in chars
    )
    return f"[{inner}]"


def generate_charclass_pattern(word: str, min_prefix: int = 2) -> str:
    """
    Generate a character-class regex pattern for `word`.

    The first `min_prefix` characters are mandatory (with a .? noise absorber
    after char 1). The rest become an optional group to cover abbreviations.
    A trailing \\.? handles "Pag." vs "Pag".
    A \\b at the start prevents substring matches.

    Returns a raw pattern string for use with re.compile(..., re.IGNORECASE).
    """
    word = word.strip()
    n = len(word)
    if n == 0:
        return ""

    prefix_len = min(min_prefix, n)
    prefix_chars = word[:prefix_len]
    suffix_chars = word[prefix_len:]

    first = _char_class(prefix_chars[0])
    if len(prefix_chars) == 1:
        prefix_pat = first
    else:
        rest = "".join(_char_class(c) for c in prefix_chars[1:])
        prefix_pat = first + (".?" if n > min_prefix else "") + rest

    if suffix_chars:
        suffix_pat = "".join(_char_class(c) for c in suffix_chars)
        full_pat = prefix_pat + f"(?:{suffix_pat})?"
    else:
        full_pat = prefix_pat

    return r"\b" + full_pat + r"\.?"


def generate_fuzzy_pattern(word: str, k: int = 1) -> str:
    """
    Generate a fuzzy pattern for the `regex` module.

    Returns `(word){e<=k}` — matches any string within edit distance k
    of `word`. Requires: `import regex` (not standard `re`).

    Note: abbreviations (e.g. "Pag." for "Pagina") require k>=3 and are
    better handled by generate_charclass_pattern instead.

    Args:
        word: Target word (will be regex-escaped).
        k:    Maximum number of errors (insertions + deletions + substitutions).
    """
    escaped = re.escape(word.strip())
    return rf"({escaped}){{e<={k}}}"
