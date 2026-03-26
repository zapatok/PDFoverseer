# Word-Anchor OCR Fallback + tot Limit Fix

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two defects in `_parse()` — a silently-too-restrictive `tot <= 10` limit, and a missing fallback pattern for OCR-mangled "Página" prefixes.

**Architecture:** Both changes live exclusively in `core/utils.py:_PAGE_PATTERNS` and the plausibility guard inside `_parse()`. No other files in the pipeline change. The existing loop already handles multi-pattern fallback, so adding the second pattern requires zero logic changes. Tests go in `tests/test_utils.py`, which already covers `_parse()`.

**Tech stack:** Python `re`, `pytest`

---

## Context

### Defect 1 — `tot <= 10` limit silences valid reads

`_parse()` line 55 reads:

```python
if 0 < c <= tot <= 10:
```

The test file already documents the intent as `# total > 99`, meaning the original design allows totals up to 99. ART_670 has 65 real pages with totals of 11–81 that are currently discarded silently. Fixing to `<= 99` aligns code with test intent and the data.

### Defect 2 — Missing fallback for mangled "Página"

When OCR replaces the leading "P" of "Página" with a different letter (P→F, P→H, P→R), the primary pattern `P.{0,6}…` fails. A controlled test on 200 success + 200 failure pages of ART_670 showed that `\w+ N de M` catches 3 plausible cases per 200 failure pages with no regression on success pages.

This pattern is added as a second entry in `_PAGE_PATTERNS` — the existing loop tries it only when the primary fails.

---

## Files

| Action | File | What changes |
|--------|------|--------------|
| Modify | `core/utils.py:55` | `tot <= 10` → `tot <= 99` |
| Modify | `core/utils.py:31-36` | Add word-anchor pattern to `_PAGE_PATTERNS` |
| Modify | `tests/test_utils.py` | Add cases for both fixes |

---

## Chunk 1: Tests + Implementation

### Task 1: Write failing tests

**File:** `tests/test_utils.py`

Add these cases to the existing `@pytest.mark.parametrize` list in `test_parse`:

```python
# Defect 1 — tot > 10 should be accepted up to 99
("Pag 1 de 11",   (1, 11)),   # was silently discarded
("Pag 4 de 40",   (4, 40)),   # was silently discarded
("Pag 1 de 99",   (1, 99)),   # boundary: accepted
("Pag 1 de 100",  (None, None)),  # still rejected (total > 99)

# Defect 2 — word-anchor fallback for mangled "Página"
("Fagen 2 de 4",  (2, 4)),    # P→F
("Higina 3 de 4", (3, 4)),    # P→H
("Ragmne 2 de 4", (2, 4)),    # P→R
# Word-anchor does NOT fire on bare N de M (no word before)
("2 de 4",        (None, None)),
```

Note: the existing case `("Pag 1 de 100", (None, None))` already exists with comment `# total > 99` — do not duplicate it, just verify the comment matches the new limit.

- [ ] **Step 1: Add the 8 new parametrize cases to `tests/test_utils.py`**

  Open `tests/test_utils.py`. Insert the new cases inside the existing `@pytest.mark.parametrize` list, after the last existing entry and before the closing `]`.

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_utils.py -v
  ```

  Expected: 8 new cases FAIL. Existing cases pass unchanged.

---

### Task 2: Fix `tot <= 10` → `tot <= 99`

**File:** `core/utils.py:55`

- [ ] **Step 3: Change the plausibility guard**

  Current:
  ```python
  if 0 < c <= tot <= 10:
  ```

  Change to:
  ```python
  if 0 < c <= tot <= 99:
  ```

- [ ] **Step 4: Run tests**

  ```bash
  pytest tests/test_utils.py -v
  ```

  Expected: the 4 `tot > 10` cases now PASS. The 4 word-anchor cases still FAIL (pattern not added yet).

---

### Task 3: Add word-anchor fallback to `_PAGE_PATTERNS`

**File:** `core/utils.py:31-36`

- [ ] **Step 5: Add the fallback pattern**

  Current `_PAGE_PATTERNS`:
  ```python
  _PAGE_PATTERNS = [
      re.compile(
          r"P.{0,6}\s*([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})\s*\.?\s*d[ea]\s*([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})",
          re.IGNORECASE,
      ),
  ]
  ```

  Replace with:
  ```python
  _PAGE_PATTERNS = [
      # Primary: P-prefix (permissive OCR noise within word, optional spaces)
      re.compile(
          r"P.{0,6}\s*([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})\s*\.?\s*d[ea]\s*([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})",
          re.IGNORECASE,
      ),
      # Fallback: any word before N de M — catches OCR-mangled "Página" (P→F/H/R/etc.)
      re.compile(
          r"\w+\s+([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})\s+d[ea]\s+([0-9OoIilL|zZtT\'\'\'\`\´]{1,3})",
          re.IGNORECASE,
      ),
  ]
  ```

  The fallback uses `\s+` (required spaces) to avoid matching things like `word1de4`.
  The group indices (1, 2) are identical to the primary — `_parse()` loop works unchanged.

- [ ] **Step 6: Run all tests**

  ```bash
  pytest tests/test_utils.py -v
  ```

  Expected: all cases PASS, including the 4 word-anchor cases.

- [ ] **Step 7: Run the full test suite**

  ```bash
  pytest
  ```

  Expected: all tests pass. No regressions in `test_inference.py`, `test_api.py`, etc.

---

### Task 4: Verify with eval harness

- [ ] **Step 8: Run eval on all fixtures**

  ```bash
  python eval/sweep.py --quick
  ```

  Or if `--quick` is not available:
  ```bash
  python eval/report.py
  ```

  Compare results against the baseline documented in `eval/params.py` (production values). With `tot <= 99`, more OCR reads pass — inference may change on fixtures with high-total documents. Acceptable if no fixture regresses below its baseline `doc_count`.

  If any fixture regresses: investigate before proceeding.

---

### Task 5: Commit

- [ ] **Step 9: Commit**

  ```bash
  git add core/utils.py tests/test_utils.py
  git commit -m "fix(ocr): raise tot limit 10→99, add word-anchor fallback pattern

  - _parse() tot<=10 was silently discarding 65 valid ART_670 reads;
    limit raised to 99 to match test intent and real data (max tot=81)
  - \w+ N de M fallback catches OCR-mangled Página (P→F/H/R);
    controlled test: 3/200 gain on failures, zero regression on successes"
  ```
