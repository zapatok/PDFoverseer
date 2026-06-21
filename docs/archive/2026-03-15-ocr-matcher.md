# ocr_matcher — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `ocr_matcher` package that generates OCR-aware match patterns for arbitrary words using a weighted confusion matrix, weighted Levenshtein distance, and fuzzy regex search — with no connection to the main PDFoverseer pipeline.

**Architecture:** Three focused modules — `confusion.py` holds the empirically-documented OCR character substitution weights; `distance.py` wraps `weighted-levenshtein` to score how likely a string is an OCR corruption of a target word; `pattern.py` generates both a character-class regex and a `regex`-module fuzzy pattern from a word. A `cli.py` ties them together as an interactive terminal tester.

**Tech Stack:** Python 3.10, `weighted-levenshtein` (PyPI), `regex` (PyPI), `pytest` for tests.

**Isolation:** All files live under `ocr_matcher/`. The existing `regex_builder.py` at the project root is superseded by this package but left in place until the new module is validated.

---

## Chunk 1: Project scaffold + dependencies

### Task 1: Install dependencies and create package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `ocr_matcher/__init__.py`

- [ ] **Step 1: Install the three new dependencies into the venv**

```bash
pip install regex weighted-levenshtein numpy
```

Expected output includes lines like:
```
Successfully installed regex-... weighted-levenshtein-...
```

- [ ] **Step 2: Verify imports work**

```bash
python -c "import regex; import weighted_levenshtein; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Add dependencies to requirements.txt**

Append to `requirements.txt`:
```
regex>=2024.0.0
weighted-levenshtein>=0.2.1
numpy>=1.24.0
```

- [ ] **Step 4: Create the package directory and empty `__init__.py`**

```bash
mkdir ocr_matcher
```

Contents of `ocr_matcher/__init__.py`:
```python
"""ocr_matcher — OCR-aware fuzzy word matching. Standalone, off-pipeline."""
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt ocr_matcher/__init__.py
git commit -m "feat(ocr_matcher): scaffold package + add dependencies"
```

---

## Chunk 2: confusion.py — the weighted OCR character table

### Task 2: Build the confusion matrix

**Files:**
- Create: `ocr_matcher/confusion.py`
- Create: `tests/test_ocr_confusion.py`

The confusion table maps `(char_a, char_b)` pairs to a substitution cost `0.0–1.0`.
- `0.0` = free substitution (identical chars)
- `~0.05–0.15` = very common OCR confusion (g↔q, i↔1, 0↔O)
- `~0.2–0.4` = plausible but less frequent confusion
- `1.0` = default cost (unrelated chars)

The table must be **bidirectional**: if `('g','q')` has cost 0.05, then `('q','g')` also has cost 0.05.

- [ ] **Step 1: Write failing tests**

`tests/test_ocr_confusion.py`:
```python
from ocr_matcher.confusion import substitution_cost, build_matrix

def test_identical_chars_cost_zero():
    assert substitution_cost('a', 'a') == 0.0

def test_common_ocr_pair_low_cost():
    # g↔q is a very common OCR confusion
    assert substitution_cost('g', 'q') < 0.2
    assert substitution_cost('q', 'g') < 0.2  # bidirectional

def test_unrelated_chars_full_cost():
    assert substitution_cost('g', 'z') == 1.0

def test_matrix_shape():
    m = build_matrix()
    assert m.shape == (128, 128)

def test_matrix_diagonal_zero():
    import numpy as np
    m = build_matrix()
    assert all(m[i, i] == 0.0 for i in range(128))

def test_matrix_is_symmetric_for_known_pair():
    m = build_matrix()
    assert m[ord('g'), ord('q')] == m[ord('q'), ord('g')]
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_ocr_confusion.py -v
```

Expected: all 6 tests FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `ocr_matcher/confusion.py`**

```python
"""
confusion.py — OCR character substitution cost table.

Costs are in range [0.0, 1.0]:
  0.0  = same character (free)
  0.05–0.15 = very common OCR confusion
  0.2–0.4   = plausible OCR confusion
  1.0  = default (unrelated characters)

Sources: Schulz & Mihov 2002, arxiv:1604.06225, arxiv:2602.14524,
         Tesseract unicharambigs, community OCR error catalogs.
"""

import numpy as np

# fmt: off
# (char_a, char_b, cost)  — table is made bidirectional automatically
_RAW: list[tuple[str, str, float]] = [
    # --- Very common single-char substitutions (Tesseract + EasyOCR) ---
    ('0', 'O', 0.05), ('0', 'o', 0.05), ('O', 'o', 0.05),
    ('1', 'l', 0.05), ('1', 'i', 0.05), ('1', 'I', 0.05), ('1', '|', 0.05),
    ('l', 'i', 0.08), ('l', 'I', 0.08), ('l', '|', 0.08),
    ('i', 'I', 0.08),
    ('g', 'q', 0.05), ('g', '9', 0.10),
    ('q', '9', 0.10),
    ('s', '5', 0.08), ('s', 'S', 0.05), ('s', '$', 0.10),
    ('5', 'S', 0.08), ('5', '$', 0.10),
    ('z', '2', 0.08), ('z', 'Z', 0.05),
    ('2', 'Z', 0.08),
    ('a', '@', 0.10), ('a', 'á', 0.05), ('a', 'à', 0.05),
    ('e', '3', 0.10), ('e', 'é', 0.05), ('e', 'è', 0.05),
    ('n', 'ñ', 0.05),
    ('u', 'ü', 0.05), ('u', 'ú', 0.05),
    ('o', 'ó', 0.05), ('o', 'ò', 0.05),
    ('c', '(', 0.10), ('c', 'C', 0.05),
    ('b', '6', 0.10), ('b', 'B', 0.05),
    ('h', '#', 0.15),
    ('t', '+', 0.15),
    # --- Less frequent but documented ---
    ('d', '0', 0.20),
    # ('d', 'a') cost 0.25 is intentionally excluded from charclass generation
    # (threshold uses strict < 0.25) — weak visual claim, drives false positives
    ('f', 't', 0.20),
    ('P', 'p', 0.05), ('F', 'f', 0.05),
    ('B', '8', 0.10), ('B', '3', 0.12),
    ('D', '0', 0.15),
]
# fmt: on


def build_matrix() -> np.ndarray:
    """Return a 128×128 float64 cost matrix (ASCII only)."""
    m = np.ones((128, 128), dtype=np.float64)
    np.fill_diagonal(m, 0.0)
    for a, b, cost in _RAW:
        if ord(a) < 128 and ord(b) < 128:
            m[ord(a), ord(b)] = cost
            m[ord(b), ord(a)] = cost  # bidirectional
    return m


# Module-level singleton — build once
_MATRIX: np.ndarray = build_matrix()


def substitution_cost(a: str, b: str) -> float:
    """
    Return the OCR substitution cost for replacing character `a` with `b`.

    Returns 0.0 for identical chars, 1.0 for unrelated chars, and
    a value in (0, 1) for known OCR confusion pairs.
    """
    if a == b:
        return 0.0
    ia, ib = ord(a), ord(b)
    if ia >= 128 or ib >= 128:
        # Unicode chars not in table — treat as full cost unless identical
        return 0.0 if a == b else 1.0
    return float(_MATRIX[ia, ib])
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_ocr_confusion.py -v
```

Expected: all 6 PASS

- [ ] **Step 5: Commit**

```bash
git add ocr_matcher/confusion.py tests/test_ocr_confusion.py
git commit -m "feat(ocr_matcher): confusion matrix with weighted OCR char costs"
```

---

## Chunk 3: distance.py — weighted OCR distance scorer

### Task 3: Weighted Levenshtein wrapper

**Files:**
- Create: `ocr_matcher/distance.py`
- Create: `tests/test_ocr_distance.py`

- [ ] **Step 1: Write failing tests**

`tests/test_ocr_distance.py`:
```python
from ocr_matcher.distance import ocr_distance, is_likely_ocr_of

def test_identical_strings_zero_distance():
    assert ocr_distance("pagina", "pagina") == 0.0

def test_common_ocr_error_low_distance():
    # g→q is a common confusion, distance should be much less than 1
    assert ocr_distance("pagina", "paqina") < 0.2

def test_unrelated_string_high_distance():
    assert ocr_distance("pagina", "contrato") > 1.0

def test_is_likely_ocr_true():
    assert is_likely_ocr_of("paqina", "pagina", threshold=0.5)

def test_is_likely_ocr_false():
    assert not is_likely_ocr_of("contrato", "pagina", threshold=0.5)

def test_single_insertion_cost():
    # "paginaa" has one extra char — insertion cost is 1.0 (default)
    d = ocr_distance("pagina", "paginaa")
    assert 0.5 < d < 1.5

def test_case_insensitive_option():
    assert ocr_distance("Pagina", "pagina", ignore_case=True) == 0.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_ocr_distance.py -v
```

Expected: all FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `ocr_matcher/distance.py`**

```python
"""
distance.py — OCR-weighted string distance.

Uses weighted-levenshtein with the confusion matrix from confusion.py.
Substitutions of visually similar characters (g↔q, i↔1, etc.) cost less
than generic substitutions, producing a score that reflects OCR plausibility.
"""

import numpy as np
from weighted_levenshtein import levenshtein

from ocr_matcher.confusion import build_matrix

# Insertion and deletion costs: uniform 1.0 per character
_INSERT = np.ones(128, dtype=np.float64)
_DELETE = np.ones(128, dtype=np.float64)
_SUBSTITUTE = build_matrix()


def ocr_distance(a: str, b: str, ignore_case: bool = False) -> float:
    """
    Compute the OCR-weighted edit distance between strings `a` and `b`.

    Lower = more likely to be an OCR variant of the same word.
    Returns 0.0 for identical strings.

    Only handles ASCII (ord < 128). Unicode chars outside the confusion
    table incur standard cost 1.0 per operation.
    """
    if ignore_case:
        a, b = a.lower(), b.lower()
    if a == b:
        return 0.0
    # weighted_levenshtein only handles ASCII (0–127)
    a_safe = "".join(c if ord(c) < 128 else "?" for c in a)
    b_safe = "".join(c if ord(c) < 128 else "?" for c in b)
    return float(levenshtein(a_safe, b_safe,
                             insert_costs=_INSERT,
                             delete_costs=_DELETE,
                             substitute_costs=_SUBSTITUTE))


def is_likely_ocr_of(candidate: str, target: str,
                     threshold: float = 0.5,
                     ignore_case: bool = True) -> bool:
    """
    Return True if `candidate` is likely an OCR corruption of `target`.

    `threshold` is the maximum allowed weighted edit distance per character.
    A per-character threshold normalizes for word length.
    """
    if not target:
        return False
    dist = ocr_distance(candidate, target, ignore_case=ignore_case)
    normalized = dist / max(len(target), len(candidate))
    return normalized <= threshold
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ocr_distance.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add ocr_matcher/distance.py tests/test_ocr_distance.py
git commit -m "feat(ocr_matcher): OCR-weighted Levenshtein distance scorer"
```

---

## Chunk 4: pattern.py — upgraded regex generator

### Task 4: Pattern generator using confusion weights

**Files:**
- Create: `ocr_matcher/pattern.py`
- Create: `tests/test_ocr_pattern.py`

This replaces `regex_builder.py`. Key upgrade: character classes are built from the confusion table, not from a hand-coded dict. Two output modes:

- **`generate_charclass_pattern(word)`** — builds a `re`-compatible character-class regex (same approach as before, but driven by the confusion table)
- **`generate_fuzzy_pattern(word, k)`** — returns `(word){e<=k}` for the `regex` module

- [ ] **Step 1: Write failing tests**

`tests/test_ocr_pattern.py`:
```python
import re
import regex as re_fuzzy

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern

# --- charclass pattern ---

def test_charclass_matches_exact():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("pagina")

def test_charclass_matches_ocr_g_q():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("paqina")

def test_charclass_matches_abbreviation():
    pat = re.compile(generate_charclass_pattern("pagina"), re.IGNORECASE)
    assert pat.search("pag.")

def test_charclass_no_false_positive():
    pat = re.compile(generate_charclass_pattern("firma"), re.IGNORECASE)
    assert not pat.search("contrato")

def test_charclass_word_boundary():
    # "firma" should NOT match inside "confirmar"
    pat = re.compile(generate_charclass_pattern("firma"), re.IGNORECASE)
    assert not pat.search("confirmar")

# --- fuzzy pattern ---

def test_fuzzy_matches_exact():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    assert pat.search("pagina")

def test_fuzzy_matches_one_error():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    assert pat.search("paqina")  # g→q

def test_fuzzy_no_match_beyond_k():
    pat = re_fuzzy.compile(generate_fuzzy_pattern("pagina", k=1), re_fuzzy.IGNORECASE)
    # 3 changes: pag→con, i→t, na→to
    assert not pat.search("contrato")
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_ocr_pattern.py -v
```

Expected: all FAIL

- [ ] **Step 3: Implement `ocr_matcher/pattern.py`**

```python
"""
pattern.py — OCR-aware regex pattern generator.

Two modes:
  generate_charclass_pattern(word) → re-compatible character-class pattern
  generate_fuzzy_pattern(word, k)  → regex-module fuzzy pattern (word){e<=k}
"""

import re
import unicodedata

from ocr_matcher.confusion import _MATRIX, _RAW

# Build char → list[alternative chars] from the confusion table
# Only include alternatives with cost <= THRESHOLD
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
    # Collect unique alternatives; include the original char
    chars: list[str] = [base]
    for alt in alts:
        stripped = _strip_accents(alt).lower()
        if stripped not in chars:
            chars.append(stripped)
    if len(chars) == 1:
        return re.escape(chars[0])
    inner = "".join(re.escape(ch) if ch in r'\.^$*+?{}[]|()' else ch
                    for ch in chars)
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

    # Mandatory prefix: first char + optional noise + rest of prefix
    first = _char_class(prefix_chars[0])
    if len(prefix_chars) == 1:
        prefix_pat = first
    else:
        rest = "".join(_char_class(c) for c in prefix_chars[1:])
        # .? absorbs a single OCR-inserted noise character after the first
        prefix_pat = first + (".?" if n > min_prefix else "") + rest

    # Optional suffix (abbreviation support)
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

    Args:
        word: Target word (will be regex-escaped).
        k:    Maximum number of errors (insertions + deletions + substitutions).
    """
    escaped = re.escape(word.strip())
    return rf"({escaped}){{e<={k}}}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ocr_pattern.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add ocr_matcher/pattern.py tests/test_ocr_pattern.py
git commit -m "feat(ocr_matcher): charclass + fuzzy pattern generator"
```

---

## Chunk 5: cli.py — terminal tester

### Task 5: Interactive CLI

**Files:**
- Create: `ocr_matcher/cli.py`

No tests for the CLI — it's a human-facing display tool. Manual testing only.

- [ ] **Step 1: Implement `ocr_matcher/cli.py`**

```python
"""
cli.py — Terminal tester for ocr_matcher.

Usage:
    python -m ocr_matcher Pagina
    python -m ocr_matcher Pagina Inspeccion Firma
"""

import sys
import re

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern, _ALTERNATIVES, _strip_accents
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
    # Noise injection
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
    print(f"  {'Variante':<25}  {'Distancia OCR':>14}")
    print(f"  {'-'*25}  {'-'*14}")
    for variant, dist in variants:
        bar = "#" * max(1, int((1.0 - min(dist, 1.0)) * 12))
        print(f"  {variant:<25}  {dist:>8.3f}  {bar}")
    print(f"\n  Total variantes: {len(variants)}")


def main() -> None:
    words = sys.argv[1:] if len(sys.argv) > 1 else ["Pagina"]
    for w in words:
        show(w)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add `__main__.py` so `python -m ocr_matcher` works**

`ocr_matcher/__main__.py`:
```python
from ocr_matcher.cli import main
main()
```

- [ ] **Step 3: Manual test**

```bash
python -m ocr_matcher Pagina Firma Inspeccion
```

Expected: each word shows its pattern, fuzzy pattern, and a table of variants with OCR distance scores.

- [ ] **Step 4: Commit**

```bash
git add ocr_matcher/cli.py ocr_matcher/__main__.py
git commit -m "feat(ocr_matcher): interactive CLI tester with variant coverage + OCR distance"
```

---

## Chunk 6: Smoke test + final validation

### Task 6: Full integration smoke test

**Files:**
- Create: `tests/test_ocr_smoke.py`

- [ ] **Step 1: Write smoke test**

`tests/test_ocr_smoke.py`:
```python
"""
End-to-end smoke test: word → pattern → match.
Simulates the real use case: OCR'd text contains a corrupted word,
and we need to detect it using the generated pattern.
"""

import re
import regex as re_fuzzy

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern
from ocr_matcher.distance import is_likely_ocr_of

# Lines with single-char OCR errors — caught by both charclass AND fuzzy k=1
OCR_LINES_SINGLE_ERROR = [
    "Paqina 3 de 5",      # g→q substitution
    "P@gina 1 de 10",     # noise after P (one inserted char)
    "Pag1na 4 de 6",      # i→1 substitution
    "Pagina 7 de 7",      # exact (no errors)
]

# Lines with abbreviations — charclass handles these; fuzzy k=1 does NOT
# (abbreviation = 3+ deletions, beyond k=1 budget)
OCR_LINES_ABBREV = [
    "pag. 2 de 8",        # abbreviation + lowercase
]

NOT_PAGINA_LINES = [
    "Contrato de trabajo",
    "Firma del supervisor",
    "Fecha: 2026-03-15",
    "Total: 12345",
]


def test_charclass_catches_single_error_lines():
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in OCR_LINES_SINGLE_ERROR:
        assert pat.search(line), f"Expected match in: {line!r}"


def test_charclass_catches_abbreviations():
    # Abbreviations are charclass territory — the optional suffix group covers them
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in OCR_LINES_ABBREV:
        assert pat.search(line), f"Expected abbreviation match in: {line!r}"


def test_charclass_no_false_positives():
    pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
    for line in NOT_PAGINA_LINES:
        assert not pat.search(line), f"Unexpected match in: {line!r}"


def test_fuzzy_catches_single_error_lines():
    # fuzzy k=1 covers single-char errors; abbreviations require k>=3 (not tested here)
    pat = re_fuzzy.compile(generate_fuzzy_pattern("Pagina", k=1), re_fuzzy.IGNORECASE)
    for line in OCR_LINES_SINGLE_ERROR:
        assert pat.search(line), f"Fuzzy expected match in: {line!r}"


def test_distance_scorer_ranks_variants_correctly():
    # "paqina" should score as more likely OCR of "pagina" than "contrato"
    d_variant = is_likely_ocr_of("paqina", "pagina")
    d_unrelated = is_likely_ocr_of("contrato", "pagina")
    assert d_variant is True
    assert d_unrelated is False
```

- [ ] **Step 2: Run all tests together**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Final commit**

```bash
git add tests/test_ocr_smoke.py
git commit -m "test(ocr_matcher): smoke test — end-to-end word→pattern→match validation"
```

---

## Summary

After all 6 tasks, the deliverable is:

```
ocr_matcher/
├── __init__.py       # package marker
├── __main__.py       # python -m ocr_matcher entry point
├── confusion.py      # OCR character cost table (128×128 matrix)
├── distance.py       # weighted Levenshtein scorer
├── pattern.py        # charclass + fuzzy pattern generator
└── cli.py            # terminal tester

tests/
├── test_ocr_confusion.py
├── test_ocr_distance.py
├── test_ocr_pattern.py
└── test_ocr_smoke.py
```

Run the full suite at any point with:
```bash
pytest tests/ -v
```

Run the CLI with any word:
```bash
python -m ocr_matcher Pagina Inspeccion Firma Fecha
```
