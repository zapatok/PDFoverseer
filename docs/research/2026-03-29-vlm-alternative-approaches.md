# VLM Alternative Approaches: Research Analysis

**Date:** 2026-03-29
**Author:** Pipeline architecture research
**Status:** Proposals for review

---

## Context: Why Every VLM Integration Has Failed

The inference engine (`core/inference.py`) is a 6-phase constraint propagation system tuned over 42 fixtures. It handles OCR failures by treating them as gaps and filling them with bidirectional hypotheses scored against period alignment and neighbor agreement.

The critical insight from all 5 failed VLM experiments (s2t5 through s2t10):

> **The inference engine handles "no data" better than "wrong data."**

When a page has `method="failed"`, the gap solver generates two hypotheses (forward and backward), scores them, and picks the cheaper one. This works because the gap is bounded by known reads on both sides. But when VLM injects a wrong read (e.g., `2/7` when period=4), it becomes a **hard anchor** that the gap solver treats as ground truth. The wrong anchor poisons the sequence on both sides.

The period-gated rollback (s2t10, current code) guarantees no degradation via two-pass comparison, but it achieves this by rolling back to baseline whenever VLM causes damage -- meaning VLM provides zero net benefit. The confirmation mode boosts confidence but `_build_documents` ignores confidence entirely (lines 581-667 of inference.py), so this also provides zero structural improvement.

**Bottom line:** We need approaches where VLM failure modes cannot corrupt the inference chain.

---

## Approach 1: VLM as Tie-Breaker (Gap Solver Arbitration)

### Concept

The bidirectional gap solver (Phase 1+2, lines 241-386 of inference.py) generates `hyp_fwd` and `hyp_bwd` for each contiguous failure run. When `cost_fwd == cost_bwd`, it currently breaks ties by preferring the hypothesis that creates a document boundary (line 350-355). This heuristic is arbitrary.

**Proposal:** When the two hypotheses tie (or are within a small epsilon), query VLM for the page(s) where the hypotheses DISAGREE, and use the VLM read to break the tie.

### How It Works

1. Gap solver runs normally, produces `hyp_fwd` and `hyp_bwd` for each gap.
2. If `|cost_fwd - cost_bwd| < TIE_EPSILON` (e.g., 0.3):
   a. Find positions where `hyp_fwd[i] != hyp_bwd[i]` (the disagreement points).
   b. Query VLM for ONE disagreement page (the first one, or the one closest to a known neighbor).
   c. If VLM agrees with `hyp_fwd` -> pick `hyp_fwd`. If with `hyp_bwd` -> pick `hyp_bwd`. If neither -> use the existing tie-break heuristic.
3. If gap costs are clearly different -> use the winner as before, no VLM query.

### Benefit Estimate

- **How many ties exist?** In ART_670 with ~170 failed pages forming ~40-60 contiguous gaps, roughly 5-15 gaps will have close costs. Of those, maybe 3-8 will have VLM correctly break the tie.
- **Structural impact:** Each correct tie-break could fix 1 document boundary, potentially recovering 1-3 docs.
- **Projected improvement:** +0 to +5 docs (conservative), +0 to +8 docs (optimistic).

### Cost

- **VLM queries:** 5-15 per PDF (only tie situations). At 33s/query local: 3-8 minutes. At 2s/query Claude: 10-30 seconds.
- **Complexity:** Medium. Requires threading VLM query into the gap solver loop (currently pure computation). The gap solver would need a `vlm_provider` parameter or a callback.
- **Code changes:** `core/inference.py` (gap solver), `core/pipeline.py` (pass provider).

### Failure Modes

1. **VLM breaks tie in the wrong direction.** Mitigation: the tie was already ambiguous, so the damage from picking the wrong hypothesis is bounded by `TIE_EPSILON` cost difference. This is structurally safer than injecting VLM reads as anchors.
2. **VLM read matches neither hypothesis.** Mitigation: fall through to existing heuristic. Zero degradation.
3. **Performance regression on non-tie gaps.** Impossible: VLM is not queried for non-ties.

### Safety

**Can it degrade baseline?** Only if a tie-break picks a worse hypothesis AND that worse hypothesis has lower cost+VLM than the better one. Since both hypotheses are equally scored, the maximum damage per tie is the same as the existing arbitrary heuristic -- it's replacing one guess with a different guess, not injecting wrong data into a known-good sequence.

However: if TIE_EPSILON is set too high, "near-ties" that were actually correct (cost_fwd slightly < cost_bwd) could be overridden. Mitigation: start with epsilon=0 (exact ties only) and gradually increase.

### Viability: **MEDIUM-HIGH**

Low query count, bounded damage, targets genuine uncertainty. The main risk is that exact ties may be rare enough that the feature has negligible impact.

---

## Approach 2: VLM as Post-Pipeline Validator (Read-Only Audit)

### Concept

Run the entire pipeline (OCR + inference + build_documents) with zero VLM involvement. Then, as a separate post-processing step, use VLM to audit specific results and generate a **human review queue** without changing any pipeline output.

### How It Works

1. Pipeline runs normally, produces `documents[]` and `reads[]`.
2. Post-pipeline auditor identifies "audit targets":
   a. Incomplete documents (found_total != declared_total).
   b. Documents where ALL pages are inferred (no OCR-confirmed pages).
   c. Pages with `confidence <= 0.45` (Phase 3 cross-validation failures).
   d. Documents at period boundaries (where the gap solver switched hypotheses).
3. For each audit target, render the page image and query VLM.
4. Compare VLM response against the pipeline's assigned (curr, total):
   - **AGREE:** Mark as "VLM-verified" in metadata. Reduces human review burden.
   - **DISAGREE:** Flag as "VLM-disputed" with both readings. Human reviews only these.
   - **UNPARSEABLE:** No action (VLM couldn't read it either, so pipeline's inference is the best guess).
5. Output: a priority-sorted list of disputed pages for human review.

### Benefit Estimate

- **Direct doc improvement:** Zero. Pipeline output is never modified.
- **Human efficiency:** Instead of reviewing all ~32 low-confidence pages, humans review only the ~5-10 where VLM disagrees. 60-80% reduction in human review time.
- **Indirect improvement:** Human corrections fed back via `re_infer_documents()` will be more targeted and faster.

### Cost

- **VLM queries:** 20-40 per PDF (audit targets). At 33s/query local: 11-22 minutes. At 2s/query Claude: 40-80 seconds.
- **Complexity:** Low. Completely decoupled from pipeline. New module, no changes to inference.
- **Code changes:** New `core/vlm_auditor.py` (or extend `vlm_resolver.py`), UI changes to show audit results.

### Failure Modes

1. **VLM disagrees on a correct inference.** Human sees both; worst case is wasted review time.
2. **VLM agrees on a wrong inference.** Human skips reviewing a bad page. But this is the same risk as no VLM at all (human would have had to find it themselves).
3. **Too many disputes.** If VLM disputes 80% of inferences, the review queue isn't actually reduced.

### Safety

**Can it degrade baseline?** Impossible. Pipeline output is read-only. VLM is purely advisory.

### Viability: **HIGH**

Zero risk, clear UX value, simple implementation. The only question is whether the dispute rate is low enough to actually reduce human work. If VLM accuracy on inferred pages is ~80%, then ~20% of audited pages will be disputed -- still a significant reduction from reviewing all of them.

---

## Approach 3: VLM for Visual Document Boundary Detection (Layout Analysis)

### Concept

Instead of asking VLM "what page number is this?", ask it "is this the first page of a new document?" First pages in CRS lecture PDFs typically have distinct visual features: title blocks, headers, different text density, logos, stamps. VLM can detect these layout cues without needing to read tiny text.

### How It Works

1. After OCR, identify pages where inference produced `curr=1` with low confidence (inferred boundaries).
2. Render a LARGER crop of those pages (not just the top-right corner, but the full top quarter or even full page at low DPI).
3. Query VLM with a layout-oriented prompt:
   > "Is this the first page of a document? Look for: title/header at top, different layout from a continuation page, stamps or signatures. Answer YES or NO."
4. Binary classification (YES/NO) is much easier for VLM than OCR digit extraction.
5. If VLM says YES and inference says curr=1 -> boost confidence.
6. If VLM says NO and inference says curr=1 -> reduce confidence (but don't remove the boundary -- flag for review).
7. If VLM says YES and inference says curr!=1 -> flag as potential missed boundary.

### Benefit Estimate

- **Direct doc improvement:** Could recover 2-5 docs where the inference engine placed a boundary incorrectly or missed one.
- **Accuracy advantage:** Binary classification (first page vs continuation) is fundamentally easier than OCR digit extraction. VLM accuracy for "is this page 1?" should be 90-95%, vs 79-89% for exact N/M extraction.
- **Complementary signal:** This is information the OCR pipeline CANNOT extract. It's a genuinely new evidence source.

### Cost

- **VLM queries:** 15-30 per PDF (only inferred boundaries + suspected missed boundaries). At 33s/query local: 8-17 minutes. At 2s/query Claude: 30-60 seconds.
- **Complexity:** Medium-High. Requires a different rendering strategy (larger crop), different prompt, different parsing (YES/NO instead of N/M), and integration with a part of inference that currently doesn't accept external signals.
- **Code changes:** New function in `vlm_resolver.py`, changes to `_render_clip` or new render function, potentially changes to `_build_documents` to accept VLM boundary evidence.

### Failure Modes

1. **CRS PDFs with uniform layouts.** If all pages look the same (no distinct first-page features), VLM classification becomes random. Mitigation: check a sample first; if VLM accuracy < 70% on known boundaries, disable.
2. **Multi-document pages.** A single PDF page might contain the end of one document and the start of another. VLM sees "first page" features but the boundary isn't at page start.
3. **False positive first-page detection.** Pages with headers or stamps that aren't actually document starts. This could introduce false boundaries that the inference engine then trusts.

### Safety

**Can it degrade baseline?** Only if VLM boundary evidence overrides confident inference results. Mitigation: VLM boundary evidence should only BOOST or FLAG, never override. Implementation: VLM-YES adds +0.15 to curr=1 confidence; VLM-NO creates a review flag but doesn't change the read.

### Viability: **MEDIUM**

The concept is sound (binary classification is easier than OCR), but it depends heavily on CRS PDFs having distinguishable first-page layouts. This is an empirical question that needs a quick feasibility test on 5-10 known first pages before building the full system.

---

## Approach 4: Minimal VLM -- Zero-Confidence Contradiction Resolution

### Concept

The absolute smallest possible VLM role: query VLM ONLY when two conditions are simultaneously true:

1. A page has `confidence <= 0.10` (Phase 4 fallback or cross-validation cap), AND
2. Its two neighbors provide contradictory signals (left says it should be page X, right says it should be page Y, and X != Y).

These are pages where the inference engine has essentially given up. VLM input here cannot make things worse because the inference engine already has zero conviction.

### How It Works

1. After `_infer_missing()`, scan for pages matching both criteria.
2. For each candidate, query VLM.
3. If VLM provides a parseable read:
   a. Check if the read is consistent with EITHER neighbor.
   b. If consistent with one neighbor -> adopt the VLM read at confidence 0.50.
   c. If consistent with neither -> discard (VLM is confused too).
   d. If consistent with both -> adopt at confidence 0.70.
4. Re-run `_build_documents()` with the updated reads.

### Benefit Estimate

- **How many zero-confidence contradictions exist?** In ART_670 baseline: the XVAL bad entries (marked with cross-symbol in telemetry) are the candidates. Typically 0-5 per PDF.
- **Projected improvement:** +0 to +2 docs (very conservative). This targets the rarest failure mode.
- **Real value:** Not in doc count but in correctness -- fixing a 0-confidence page often fixes the sequence around it.

### Cost

- **VLM queries:** 0-5 per PDF. At 33s/query local: 0-3 minutes. At 2s/query Claude: 0-10 seconds.
- **Complexity:** Low. Simple filter + existing VLM query infrastructure.
- **Code changes:** Small addition to `pipeline.py`, reuses existing `vlm_resolver.py`.

### Failure Modes

1. **VLM agrees with the wrong neighbor.** The neighbor validation catches some of this, but if both neighbors are also inferred (cascading uncertainty), VLM might pick the wrong chain.
2. **Too few candidates.** If the inference engine rarely produces zero-confidence contradictions, this feature does nothing.

### Safety

**Can it degrade baseline?** Extremely unlikely. The affected pages already have confidence 0.10 -- any VLM input that passes neighbor validation is likely an improvement. However, a strict safety measure: count boundaries before and after VLM application, rollback if any are lost (reuse existing rollback logic).

### Viability: **HIGH**

Minimal queries, minimal risk, minimal implementation effort. The question is whether it provides enough value to justify the feature's existence. Recommended as a first step -- if it works, expand the scope gradually.

---

## Approach 5: VLM Pre-Filter (Has Page Number vs No Page Number)

### Concept

Instead of asking VLM to READ the page number, ask it a simpler question: "Does this image contain a page number?" Binary YES/NO classification.

This information helps the inference engine know which gaps are "page number exists but OCR couldn't read it" (VLM-YES) vs "no page number present" (VLM-NO). The second case is much more likely to be a document boundary.

### How It Works

1. Before inference, for each `method="failed"` page:
   a. Render the crop and query VLM: "Does this image contain text that looks like a page number (e.g., 'Pagina N de M' or similar)? Answer YES or NO."
   b. Record the binary result.
2. Modify the gap solver to use this signal:
   - VLM-YES pages: the gap solver knows a page number EXISTS but was unreadable. It should propagate from neighbors more aggressively (the page is a continuation, not a boundary).
   - VLM-NO pages: the gap solver knows no page number is present. This is a STRONGER signal for a document boundary than "OCR failed."
3. Concretely: for VLM-NO pages, increase the boundary penalty (`effective_cbpen * 1.5`) for hypotheses that assign them a continuation page number (curr > 1).

### Benefit Estimate

- **How often does "no page number" mean boundary?** In CRS PDFs, pages without "Pagina N de M" are typically: cover pages, section dividers, full-page images, or the first page of a document that uses a different numbering scheme. Many of these ARE document boundaries.
- **Projected improvement:** +2 to +8 docs. Better boundary placement at the cost of some false signals on pages with unconventional numbering.
- **Accuracy advantage:** "Is there a page number?" is easier than "what page number?" -- expected VLM accuracy ~92-95%.

### Cost

- **VLM queries:** ALL failed pages (170 in ART_670). At 33s/query local: 94 minutes. At 2s/query Claude: 5-6 minutes.
- **Complexity:** Medium. Requires a second prompt, binary parsing, and modifications to the gap solver's cost function.
- **Code changes:** New function in `vlm_resolver.py`, changes to `_infer_missing` gap solver cost function to accept external evidence.

### Failure Modes

1. **VLM says YES but there's no page number** (false positive). The gap solver treats it as a continuation, potentially merging two documents. This is the SAME failure mode as wrong OCR reads.
2. **VLM says NO but there IS a page number** (false negative). The gap solver adds boundary bias, potentially splitting a document. Less common, and the damage is bounded (Phase 6 orphan suppression catches some splits).
3. **High query count eliminates the performance advantage.** 170 queries at 33s = 94 minutes. This is the same problem as Tier 3 OCR.

### Safety

**Can it degrade baseline?** Yes, if VLM classification errors bias the gap solver incorrectly. Mitigation: make the binary signal a SOFT input (cost adjustment, not hard constraint). Also: two-pass rollback.

### Viability: **LOW-MEDIUM**

The query count problem is fatal for local VLM. With Claude API (~5 minutes) it's feasible. The concept is sound but the implementation is invasive (modifying the gap solver's cost function) and the binary signal may not be reliable enough on CRS PDFs where many pages without page numbers are NOT boundaries.

---

## Approach 6: Post-Pipeline Human Assist Queue

### Concept

The simplest possible VLM role: after the pipeline finishes, use VLM to generate a PRIORITIZED human review queue. VLM doesn't change anything; it just tells the human which pages to look at first.

### How It Works

1. Pipeline finishes normally.
2. Identify review candidates:
   a. All pages with `method="inferred"` and `confidence < 0.60`.
   b. All incomplete documents.
   c. All pages flagged with issues.
3. Query VLM for each candidate.
4. Generate a priority queue:
   - **Priority 1 (URGENT):** VLM disagrees with inference AND VLM confidence is high. "VLM says 1/4 but inference says 3/4 -- human should check."
   - **Priority 2 (CHECK):** VLM couldn't parse the image. "Even VLM couldn't read this -- likely a genuine OCR failure."
   - **Priority 3 (SKIP):** VLM agrees with inference. "VLM confirms inference -- probably correct."
5. Present the queue in the UI (IssueInbox component already exists).

### Benefit Estimate

- **Direct doc improvement:** Zero. Pipeline output is never modified.
- **Human efficiency:** Massive. Instead of reviewing all flagged pages equally, human starts with the highest-probability errors. Expected 3-5x speedup in human review.
- **Indirect improvement:** Better human corrections -> better `re_infer_documents()` results.

### Cost

- **VLM queries:** 20-50 per PDF. At 33s/query local: 11-28 minutes. At 2s/query Claude: 40-100 seconds.
- **Complexity:** Low. New module, no changes to inference or pipeline.
- **Code changes:** New `core/vlm_auditor.py`, small UI update to IssueInbox.

### Failure Modes

1. **VLM disputes correct inferences (false alarms).** Human wastes time reviewing correct pages. But this is bounded by the total number of disputes.
2. **VLM confirms wrong inferences (missed alarms).** Human skips a bad page. Same risk as no VLM.
3. **Human ignores the queue.** Then VLM added nothing. But the queue is optional.

### Safety

**Can it degrade baseline?** Impossible. Read-only.

### Viability: **HIGH**

Identical to Approach 2 but with a different framing (prioritization vs verification). In practice, Approaches 2 and 6 would be implemented as the same feature. Merging them: VLM post-pipeline audit with priority-sorted review queue.

---

## Approach 7: Consensus Mode (Tesseract + VLM Must Agree)

### Concept

Only accept a page read when BOTH Tesseract AND VLM agree on the same (curr, total). This eliminates VLM's worst failure mode (wrong reads that corrupt inference) because a wrong VLM read requires an unlikely coincidence with Tesseract error.

### How It Works

There are two sub-variants:

**7A: Pre-inference consensus on failed pages.**
1. For each `method="failed"` page, query VLM.
2. Also re-run Tesseract with different preprocessing (e.g., higher DPI, different binarization).
3. If both produce the same (curr, total) -> accept as `method="consensus"` at confidence 0.95.
4. If they disagree -> keep as `method="failed"`, let inference handle it.

**7B: Post-inference consensus filter.**
1. Run pipeline normally.
2. For each inferred page, query VLM.
3. If VLM agrees with the inferred value -> boost confidence.
4. If VLM disagrees -> flag for review but DO NOT change the inferred value.

### Benefit Estimate

- **7A projected improvement:** Depends on Tesseract retry hit rate. If Tesseract with different params reads 10% of previously failed pages, and VLM agrees on 80% of those, that's ~14 consensus reads (0.10 * 170 * 0.80). Of those, maybe 5-8 provide new information the inference engine didn't have. +2 to +5 docs.
- **7B projected improvement:** Same as Approach 2 (confidence-only, no structural change). But provides stronger verification than VLM alone.

### Cost

- **7A VLM queries:** 170 (all failed pages). Same performance problem as Tier 3.
- **7B VLM queries:** 20-40 (inferred pages only). Manageable.
- **Complexity:** 7A is high (Tesseract retry with different params is a new pipeline stage). 7B is low (reuses existing confirmation mode).

### Failure Modes

1. **7A: Both Tesseract and VLM wrong in the same way.** Rare but catastrophic -- would inject a high-confidence wrong read. Probability: ~1-2% of consensus reads.
2. **7B: VLM agrees with wrong inference.** Boosts confidence on a wrong page. But since `_build_documents` ignores confidence, no structural damage.

### Safety

**7A can degrade baseline** if a correlated error produces a wrong consensus read. Mitigation: period gate + rollback.
**7B cannot degrade baseline** (confidence-only changes).

### Viability: **7A: LOW, 7B: MEDIUM**

7A has the same query count problem as previous approaches. 7B is essentially the existing confirmation mode (already implemented as s2t10) with the caveat that it provides zero structural improvement because `_build_documents` ignores confidence.

---

## Comparative Summary

| # | Approach | Queries | Time (local) | Time (Claude) | Max Benefit | Can Degrade? | Complexity | Viability |
|---|----------|---------|-------------|---------------|-------------|-------------|------------|-----------|
| 1 | Tie-breaker | 5-15 | 3-8 min | 10-30s | +0 to +5 docs | Bounded | Medium | **MEDIUM-HIGH** |
| 2 | Validator/Audit | 20-40 | 11-22 min | 40-80s | 0 docs (UX) | Impossible | Low | **HIGH** |
| 3 | Layout boundary | 15-30 | 8-17 min | 30-60s | +2 to +5 docs | Bounded | Med-High | **MEDIUM** |
| 4 | Zero-conf only | 0-5 | 0-3 min | 0-10s | +0 to +2 docs | Very unlikely | Low | **HIGH** |
| 5 | Pre-filter | 170 | 94 min | 5-6 min | +2 to +8 docs | Yes (soft) | Medium | **LOW-MEDIUM** |
| 6 | Human assist | 20-50 | 11-28 min | 40-100s | 0 docs (UX) | Impossible | Low | **HIGH** |
| 7A | Consensus (pre) | 170 | 94 min | 5-6 min | +2 to +5 docs | Rare | High | **LOW** |
| 7B | Consensus (post) | 20-40 | 11-22 min | 40-80s | 0 docs | Impossible | Low | **MEDIUM** |

---

## Recommended Strategy: Layered Adoption

Based on the analysis, the recommended implementation order is:

### Phase A: Immediate (safe, low effort)

**Approach 4 (Zero-conf contradiction resolution) + Approach 2/6 (Post-pipeline audit queue)**

Rationale:
- Approach 4 queries 0-5 pages, takes seconds, and targets the only pages where VLM literally cannot make things worse. Even if it helps just 1 PDF out of 21, the cost is negligible.
- Approach 2/6 is a pure UX improvement with zero pipeline risk. It makes the human correction workflow faster, which is the ACTUAL bottleneck -- the inference engine already gets 606/668 docs correct, so the remaining 62 docs require human review regardless.
- Combined, these two features make VLM useful without any risk.

### Phase B: Targeted (moderate effort, bounded risk)

**Approach 1 (Tie-breaker) + Approach 3 (Layout boundary detection -- feasibility test only)**

Rationale:
- Approach 1 is the only proposal that can improve DOC count with bounded risk and minimal queries. The tie-breaker operates at the point of maximum uncertainty, where VLM input is most valuable and least dangerous.
- Approach 3 needs a feasibility test first: render 20 known first pages and 20 known continuation pages, query VLM with the binary prompt, measure accuracy. If accuracy > 85%, proceed to implementation. If < 85%, abandon.

### Phase C: Never (unless fundamentals change)

**Approach 5 (Pre-filter), 7A (Consensus pre-inference)**

These require querying all 170 failed pages, which takes 94 minutes with local VLM. This is unacceptable for a pipeline that currently runs in 20 minutes. Even with Claude API (5-6 minutes), the cost/benefit ratio is poor because the inference engine already handles most gaps correctly.

---

## Key Architectural Insight

The fundamental constraint is:

> **`_build_documents` ignores confidence.** It only uses `curr`, `total`, and `method` (for the inferred vs direct distinction on line 623 and 635). Confidence affects the issue inbox and telemetry, but never changes which documents are formed or how pages are assigned to them.

This means ANY approach that only modifies confidence (Approaches 2, 6, 7B, and the current s2t10 confirmation mode) will NEVER improve DOC or COM counts. The only approaches that can improve structural accuracy are those that change `curr`, `total`, or the order of reads before `_build_documents` runs:

- **Approach 1** (changes which hypothesis wins in the gap solver)
- **Approach 3** (provides new boundary evidence that could change gap solver scoring)
- **Approach 4** (directly changes curr/total on zero-confidence pages)
- **Approach 5** (changes gap solver cost function)

The confidence-only approaches are valuable for UX (human review prioritization) but not for automated accuracy.

---

## Open Question: Should `_build_documents` Use Confidence?

A more radical change: modify `_build_documents` to account for confidence when forming documents. For example:

- If an inferred `curr=1` page has confidence < 0.30, treat it as a continuation rather than a boundary.
- If a direct-OCR page has confidence 1.0 but contradicts its neighbors, flag it for possible misread.

This would make confidence-only VLM approaches (2, 6, 7B) structurally meaningful. But it requires changes to the core inference engine, which has been painstakingly tuned. The risk/reward tradeoff is unclear and would need eval harness validation.

This is not a VLM question -- it's an inference engine question. But it's worth noting because it unlocks an entire class of VLM integration approaches that are currently inert.
