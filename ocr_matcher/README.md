# ocr_matcher

OCR-aware fuzzy word and phrase matching. Standalone module — no pipeline dependency.

## Overview

Given a word or phrase template, generates a `re`-compatible regex pattern that tolerates
common OCR errors: character confusion, missing accents, abbreviations, and dropped spaces
("pegado" output).

## Public API

```python
from ocr_matcher import (
    generate_charclass_pattern,   # single word → regex pattern
    generate_fuzzy_pattern,       # single word → fuzzy pattern (requires `regex` module)
    generate_phrase_pattern,      # phrase template → regex pattern
    ocr_distance,                 # weighted edit distance between two strings
    is_likely_ocr_of,             # bool: is candidate likely an OCR corruption of target?
)
```

---

## Functions

### `generate_charclass_pattern(word, min_prefix=2, boundary=True)`

Generates a character-class regex for a single word.

- First `min_prefix` chars are mandatory.
- Remaining chars form a **progressive optional suffix** — each char is independently
  optional, so "Pa", "Pag", "Pagi", "Pagin", "Pagina" all match.
- A trailing `\.?` absorbs a period (e.g. "Pag.").
- `boundary=True` (default) prepends `\b`; set `False` for intermediate words inside
  a phrase to support pegado OCR output.
- Accented input (e.g. "Página") and non-accented input ("Pagina") both produce patterns
  that match accented and non-accented OCR output.

```python
import re
from ocr_matcher import generate_charclass_pattern

pat = re.compile(generate_charclass_pattern("Pagina"), re.IGNORECASE)
pat.search("Página 3 de 8")   # matches (real accent preserved by OCR)
pat.search("Paqina 3 de 8")   # matches (g→q OCR confusion)
pat.search("Pag. 3 de 8")     # matches (abbreviated + period)
pat.search("Pag 3 de 8")      # matches (abbreviated, no period)
```

---

### `generate_fuzzy_pattern(word, k=1)`

Generates a fuzzy pattern for the [`regex`](https://pypi.org/project/regex/) module.

Returns `(word){e<=k}` — matches any string within edit distance `k` of `word`.

```python
import regex
from ocr_matcher import generate_fuzzy_pattern

pat = regex.compile(generate_fuzzy_pattern("Pagina", k=2), regex.IGNORECASE)
pat.search("Paqina")   # matches
```

> Note: abbreviations like "Pag." require `k >= 3` and are better handled by
> `generate_charclass_pattern`.

---

### `generate_phrase_pattern(template)`

Generates an OCR-aware regex for a multi-word phrase from a template.

**Template tokens:**

| Token    | Expands to                                    | Captures? |
|----------|-----------------------------------------------|-----------|
| `{num}`  | `([0-9OoIl\|zZ]{1,4})` — digits with common OCR confusions | yes (group) |
| `{word}` | `(\S+)` — any non-space sequence             | yes (group) |
| `literal` | OCR-expanded word via `generate_charclass_pattern` | no |

Tokens are joined with `\s*` so the pattern handles both spaced and pegado output.
Only the first literal word gets `\b` — intermediate literals skip it to allow
pegado matches like `"3de"`.

```python
import re
from ocr_matcher import generate_phrase_pattern

TMPL = "Pagina {num} de {num}"
pat = re.compile(generate_phrase_pattern(TMPL), re.IGNORECASE)

m = pat.search("Página 3 de 8")
m.group(1), m.group(2)   # → ("3", "8")

pat.search("Paqina l de z")   # g→q, 1→l, 2→z OCR errors
pat.search("Pagina3de8")      # pegado: no spaces at all
pat.search("Pag. 3 de 8")     # abbreviated form
pat.search("Pag 3 de 8")      # abbreviated, no period
```

Capture groups correspond to `{num}` / `{word}` tokens in left-to-right order.

---

### `ocr_distance(a, b, ignore_case=False)`

OCR-weighted edit distance. Uses the confusion matrix — visually similar characters
(g↔q, i↔1, 0↔O, 2↔z, etc.) cost less than generic substitutions.

Returns `0.0` for identical strings. Lower = more OCR-plausible match.

```python
from ocr_matcher import ocr_distance

ocr_distance("Pagina", "Paqina")   # low — g↔q is a known confusion
ocr_distance("Pagina", "Xagina")   # higher — X↔P is not
```

---

### `is_likely_ocr_of(candidate, target, threshold=0.5, ignore_case=True)`

Returns `True` if `candidate` is likely an OCR corruption of `target`.

Distance is normalized by word length — threshold is word-length agnostic.

```python
from ocr_matcher import is_likely_ocr_of

is_likely_ocr_of("Paqina", "Pagina")   # True
is_likely_ocr_of("Banana", "Pagina")   # False
```

---

## Module Structure

```
ocr_matcher/
├── __init__.py      # public exports
├── confusion.py     # OCR character confusion matrix (_RAW cost table)
├── pattern.py       # generate_charclass_pattern, generate_fuzzy_pattern
├── phrase.py        # generate_phrase_pattern
├── distance.py      # ocr_distance, is_likely_ocr_of
└── cli.py           # interactive CLI tester (__main__.py entry point)
```

---

## Known Limitations and Decisions

- **Ultra-short prefixes** like "Pg" are not auto-generated from "Pagina" input.
  If "Pg" coverage is needed, pass "Pg" explicitly.
- **OCR digit class** `[0-9OoIl|zZ]` covers the most common confusions.
  Extend `_NUM_CLASS` in `phrase.py` if additional variants appear.
- **ASCII only** in `ocr_distance` — Unicode chars outside the confusion table
  incur standard cost 1.0.

---

## Future Work

- **Numeric anchors**: add anchor words to `{num}` tokens to increase match weight
  in numeric mode (explicitly deferred).
- **Pipeline integration**: replace hardcoded regex in `core/analyzer.py` with
  `generate_phrase_pattern("Pagina {num} de {num}")` + `_to_int()` normalization
  for digit-class captures.
- **Incidence mode vs numeric mode**: use phrase patterns for word/phrase presence
  counting without extracting numbers.
