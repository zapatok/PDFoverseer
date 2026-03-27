# Plan: ART_674 Baseline Eval + Sweep Analysis

**Branch:** `cuda-gpu` (no new branch needed — eval-only, no pipeline changes)
**Scope:** Add ART_674 to the eval harness, run baseline, analyze deltas, optionally re-run sweep.
**Constraints:**
- DO NOT touch `core/` at all
- DO NOT break existing fixture results
- DO NOT run the sweep without explicit user authorization after seeing the baseline report

---

## Session Prompt

> "Continúa el plan en `docs/superpowers/plans/2026-03-27-art674-vlm-rescan.md`.
> El fixture ART_674 ya está en `eval/fixtures/real/ART_674.json` (2,686 reads, method=vlm_opus).
> El ground truth está en `eval/ground_truth.json` (ART_674: doc=674, complete=662, inferred=35).
> El log de producción de referencia está en `manual_test_logs/logINS_31_fix.txt` (ART_670.pdf → DOC:668 vs GT:674).
> El plan tiene 4 tareas. Ejecuta paso a paso, muéstrame los resultados de cada tarea antes de continuar con la siguiente, y NO toques `core/` bajo ningún concepto."

---

## Context: Why This Matters

The production engine run on `ART_670.pdf` (from `logINS_31_fix.txt`) shows:
- **DOC: 668** vs GT **674** → delta **−6 docs**
- **COM: 606 (91%)** vs GT **662** → delta **−56 complete**
- **INC: 62** vs GT **12** → delta **+50 incomplete** (over-fragmenting)
- **INF: 603 pages** inferred (only 35 expected per GT)

This is the largest real PDF we have (2,719 pages, 674 docs). The eval harness has never been run with ART_674 as a fixture — all previous sweeps used it only as `ART_670` without per-page ground truth.

**Key unknowns to answer:**
1. Does eval reproduce the same delta pattern as the AI log?
2. Which params most affect the doc-count error?
3. Are there specific page regions (e.g. p1753–1933 unreadable cluster, 22 structural gaps) that drive the errors?
4. Is the sweep worth re-running to optimize for ART_674?

---

## Task 1: Verify `eval/inference.py` is in sync with `core/inference.py`

**Goal:** Confirm `eval/inference.py` implements all phases present in `core/inference.py` and that `PRODUCTION_PARAMS` in `eval/params.py` matches `core/utils.py` constants.

**Steps:**
1. Read `core/inference.py` and `core/utils.py` — note all phase names and parameter names
2. Read `eval/inference.py` — check for same phases (1, 2, 3, 4/gap-solver, 5, MP, 5b)
3. Read `eval/params.py` PRODUCTION_PARAMS — compare to `core/utils.py` constants
4. If any divergence found: report it to the user **before proceeding**

**Expected result:** All phases present, PRODUCTION_PARAMS values match:
```
min_conf_for_new_doc=0.55, clash_boundary_pen=1.5, phase4_conf=0.15
ph5b_conf_min=0.50, ph5b_ratio_min=0.90, anomaly_dropout=0.0, min_boundary_gap=2
```

**Verification:** No code changes — only read and report.

---

## Task 2: Run baseline eval on ART_674 with PRODUCTION_PARAMS

**Goal:** Confirm eval reproduces the production AI log delta, and see per-region breakdown.

**Steps:**
1. Check how `eval/sweep.py` or `eval/report.py` accepts a single-fixture run (read both files)
2. Write a small standalone script (or confirm existing mechanism) to run ART_674 alone with PRODUCTION_PARAMS and report:
   - doc_count error (eval DOC vs GT 674)
   - complete_count error (eval COM vs GT 662)
   - inferred_count (eval INF vs GT 35)
   - Per-region breakdown: pages 1–1752, 1753–1933 (unreadable cluster), 1934–2719
3. Run it: `python <script>` from project root with venv active
4. Show output to user

**Notes:**
- The PDF is not needed for eval — `eval/` runs on fixture JSON reads only
- ART_674 fixture has 2,686 reads; the remaining 33 pages are structural blank gaps (p1753–1933 cluster) legitimately absent from fixture
- The `load_fixture()` in `eval/ocr_benchmark.py` reads the fixture; check `eval/sweep.py` for how it passes reads to `run_pipeline()`

**Verification:** eval doc_count delta within ±2 of AI log delta (−6 ± 2 = range −4 to −8)

---

## Task 3: Analyze delta breakdown

**Goal:** Understand *where* in the 2,719-page PDF the errors concentrate.

**Steps:**
1. After Task 2 run, collect the inferred vs. actual boundary pages for each missed doc
2. Map errors against known structural features:
   - 22 structural gaps (pages where physical PDF has no content between docs)
   - p1753–1933 unreadable cluster (181 pages, ~45 docs, mostly null in fixture)
3. Produce a summary table:
   ```
   Region           | GT docs | Eval docs | Delta
   p1–1752          |   ???   |    ???    |  ???
   p1753–1933       |   ~45   |    ???    |  ???
   p1934–2719       |   ???   |    ???    |  ???
   ```
4. Report to user with interpretation

**Key question to answer:** Is the −6 doc error driven by the unreadable cluster (unavoidable) or by parameters that could be tuned?

**Verification:** The three regions' GT docs sum to 674.

---

## Task 4: Decision point — re-run sweep?

**Goal:** Recommend whether a sweep re-run including ART_674 is worth it, and if so, propose a targeted param grid.

**Steps:**
1. Based on Task 3 analysis:
   - If errors concentrate in the unreadable cluster → sweep unlikely to help → report "not worth it"
   - If errors appear in readable regions → identify which params are most likely causative
2. If sweep is recommended, propose a targeted grid (not the full 500k-combo sweep):
   - Focus on 2–3 most impactful params (likely: `min_conf_for_new_doc`, `clash_boundary_pen`, `min_boundary_gap`)
   - Estimate combo count (target <10k)
3. **STOP and present findings to user. Do NOT run the sweep without explicit authorization.**

**Output:** A written recommendation with:
- Whether to re-run sweep
- Proposed param grid (if yes)
- Risk assessment: which existing fixtures might regress

---

## Files to Read (Task 1 prep)

| File | Purpose |
|------|---------|
| `core/inference.py` | Reference implementation — all phases |
| `core/utils.py` | Production constants |
| `eval/inference.py` | Parameterized copy — must match |
| `eval/params.py` | `PRODUCTION_PARAMS` — must match `core/utils.py` |
| `eval/sweep.py` | How sweep runs single fixture |
| `eval/report.py` | How results are reported |
| `manual_test_logs/logINS_31_fix.txt` | Production AI log reference |

---

## Files NOT to Touch

- `core/inference.py` — BLOCKED by eval-before-core hook
- `core/utils.py` — no param changes without sweep authorization
- Any existing fixture JSON
- `eval/ground_truth.json` — already updated with ART_674

---

## Expected Commit (end of session)

If a baseline script is written: `feat(eval): add ART_674 baseline runner + delta analysis`
No changes to core, no changes to existing tests, no changes to production params.
