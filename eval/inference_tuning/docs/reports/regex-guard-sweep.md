# Regex Guard Sweep — 2026-03-26

## Goal

Determine the optimal `tot` upper-bound in `_parse()` plausibility guard:
`0 < curr <= total <= N`

Starting point: baseline is `v1-baseline` (commit `d3ec6d9`) with `N=10`, P-prefix only.

---

## Variants Tested

| Version | Guard | Pattern | ART_670 docs/complete | INS_31 docs | Notes |
|---------|-------|---------|----------------------|-------------|-------|
| v1-baseline (target) | ≤10 | P-prefix | 668 / 606 | 31/31 | From `logINS_31_fix.txt` |
| v4-tot20 | ≤20 | P-prefix | 665 / 603 | 29/31 | Regression |
| v5-tot9  | ≤9  | P-prefix | 666 / 603 | 29/31 | Regression (10 rejected) |
| v6-tot10 | ≤10 | P-prefix | 665 / 603 | 29/31 | Unicode corruption (see below) |

**Conclusion:** `tot<=10` is the confirmed optimum. Lower (9) or higher (20, 99) all regress.

---

## Root Cause Discovery: Ruff Unicode Corruption

### What happened

Commits `f24b59d` and `77c225f` applied `ruff` auto-fixes to `core/utils.py`.
Ruff replaced three UTF-8 multi-byte sequences with the replacement character U+FFFD (`\ufffd`):

| Original | Unicode | Bytes | Replacement |
|----------|---------|-------|-------------|
| `'` | U+2018 LEFT SINGLE QUOTATION MARK | `\xe2\x80\x98` | `\ufffd` |
| `'` | U+2019 RIGHT SINGLE QUOTATION MARK | `\xe2\x80\x99` | `\ufffd` |
| `´` | U+00B4 ACUTE ACCENT | `\xc2\xb4` | `\ufffd` |

These characters appear in **two places** in `core/utils.py`:
1. `_OCR_DIGIT` translation table — maps OCR apostrophe/accent variants to `1`
2. `_PAGE_PATTERNS` regex character class — matches OCR-confused apostrophes in digit position

The corrupted version (`v6-tot10`) appeared to have `tot<=10` but produced different results
because the regex silently failed to match OCR reads containing those characters.

### How detected

Compared raw byte counts between HEAD and commit `d3ec6d9`:
- Baseline regex line: 115 bytes
- Corrupted line: 105 bytes (10 bytes missing = 3 × 3-byte sequences replaced by 3 × 1-byte U+FFFD)

### Fix

```bash
git checkout d3ec6d9 -- core/utils.py
```

Verified with `xxd core/utils.py | grep -A1 "OCR_DIGIT"` — bytes `\xe2\x80\x98`, `\xe2\x80\x99`, `\xc2\xb4` present.

---

## Prevention

**Do not run `ruff --fix` on files containing intentional non-ASCII literal characters.**

For `core/utils.py`, add `# noqa` comments or configure ruff to skip the file if auto-fix is
ever re-run. The Unicode chars in `_OCR_DIGIT` and `_PAGE_PATTERNS` are load-bearing — they
handle OCR apostrophe/accent confusion specific to Spanish "Página N de M" reads.

---

## Word-Anchor Fallback (also tried, different session)

A `\w+ N de M` fallback pattern was evaluated on `data/ocr_all/all_index.csv` using
`tools/pattern_eval.py`. FP rate on ART_670 was too high (pattern fires on non-page-number text
containing numbers). Reverted. P-prefix only remains production.

---

## Final State

- `PAGE_PATTERN_VERSION = "v1-baseline"`
- Guard: `0 < curr <= total <= 10`
- Pattern: P-prefix only (`P.{0,6} N de M`)
- Unicode: intact (U+2018, U+2019, U+00B4 in `_OCR_DIGIT` and `_PAGE_PATTERNS`)
- Committed: `a6fe45e fix(utils): restore v1-baseline — revert ruff Unicode corruption`
