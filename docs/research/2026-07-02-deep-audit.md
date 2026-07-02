# PDFoverseer — Deep Audit (2026-07-02)

**Branch:** `po_overhaul` (clean, 19 commits ahead of `master` — the A+B increments) ·
**Requested by:** Daniel — "auditoría y análisis profundo: bugs, errores, oportunidades de
optimización, todo lo que se pueda haber pasado".

**Method:** four parallel passes — the **counting pipeline** (`core/` + every count-defining
api/frontend path, audited directly by the main agent, never delegated), **`api/` +
`server.py`** (Opus subagent, read-only), **`frontend/src`** (Opus subagent, read-only), and
**tests/eval/docs/config** (Sonnet subagent). Subagent findings were independently
**spot-verified against the code** before inclusion (verification status noted per finding).
Baseline context: the 2026-06-21 pre-master audit (`2026-06-21-pipeline-and-tree-audit.md`);
items it already lists are NOT repeated here unless their status changed.

Every finding has an ID, severity, evidence (`file:line`), a concrete failure scenario, a fix
direction, and an **output-safety tag** (`SAFE` = fix cannot change counting output ·
`VERIFY` = fix touches counts/Excel/UI-visible values — prove no drift before shipping).

---

## 0. Executive summary — what matters most

| # | Finding | Severity | Tag |
|---|---------|----------|-----|
| F1 | **Bug #2 root cause found**: worker totals have 3 disagreeing derivations — UI fallback (unfiltered) ≠ backend/PATCH (present-filtered) ≠ Excel (present-filtered) → "kept its total but lost its marks", and the RESUMEN **silently exports 0** for merged/renamed files' workers | **high** | VERIFY |
| F2 | **Cancelling a multi-cell OCR batch with queued cells crashes `scan_cells_ocr`** (unhandled `fut.result()` on pool-cancelled futures): the batch ends as `scan_complete {errors: N}` instead of `scan_cancelled`, with a spurious crash log and a leaked drain thread + queue per occurrence | medium | SAFE |
| F3 | **Reorg create/delete endpoints bypass the M3 per-cell locks** for both source and dest cells — the exact cross-editor count corruption M3 was built to prevent | **high** | VERIFY |
| F4 | `refresh_reorg_deltas` get-then-set race can silently **drop a reorg op + its count delta** under concurrent requests | medium | VERIFY |
| F5 | **Negative counts are reachable** (per-file inline editor accepts negatives, backend doesn't guard, reorg `doc_count` can exceed the file's real contribution) and `compute_cell_count` has no ≥0 clamp in either language → negative numbers can reach the Excel | medium | VERIFY |
| F6 | **`revdocmaq` will stay at 0 when real files appear**: its `filename_glob` regex is dead config — pase-1 only matches the literal token `revdocmaq` in filenames | medium (latent) | VERIFY |
| F7 | Pagination engine can **over-count at HIGH confidence** in mixed-length compilations (a recovered gap after a completed cycle fabricates a `curr==1`), below the 30 % recovery threshold | medium (edge) | VERIFY |
| F8 | Anchors scanner reports a **0 count at HIGH confidence** for a multi-page PDF with no matched covers (live case: senal 0/18 shows green) | medium | VERIFY |
| QA-25 | **`openpyxl` is missing from `requirements.txt`** — a clean install per the documented Quick Start leaves the app unable to generate its deliverable (the RESUMEN Excel); it works today only because the venv got it out-of-band | high (packaging) | SAFE |

Everything else is medium-to-cosmetic: consistency gaps, latent mirror divergences,
robustness, perf, and doc drift. **The core counting cascade itself
(`compute_cell_count`/`_sum_marks`/the merge guards/A7/A8) was re-reviewed and remains
correct** — the problems above live at the edges (worker totals, reorg, cancellation,
validation) rather than in the document-count derivation.

---

## 1. F1 — Bug #2 root cause (worker count kept its total, lost its marks)

**Reported live by Daniel (2026-06-23, uninvestigated until now).** Mechanism, end to end:

1. `worker_marks` are keyed **by filename** (`{filename: [{page, count}]}`).
   When corpus PDFs are merged/renamed (paso-1 or by hand), the marks become **orphans**
   under the stale keys — nothing re-keys or reconciles them.
2. The canonical Python summer filters orphans out: `_sum_marks` with `present_files`
   (F1-filter), legacy fallback filters by `per_file` keys (`core/cell_count.py:30-45`).
3. **But the UI total takes a different path.** `DetailPanel.jsx:163-166`:
   `cell.worker_count != null ? cell.worker_count : cellWorkerCount(cell, null)`.
   - `worker_count` is an **ephemeral response-only field**: its sole producer is the
     `patch_worker_count` response (`api/routes/sessions/writes.py:220`, present-filtered),
     merged into the store by `saveWorkerCount` (`store/session.js:568`).
   - It is **absent** from `GET /sessions/{id}` state and from every `cell_updated` WS
     snapshot (`_cell_updated_event` broadcasts the raw state cell —
     `api/routes/sessions/_common.py:264-284`), so any month re-open or any remote write
     to the cell erases it from the store.
   - The fallback `cellWorkerCount(cell, null)` → `computeWorkerCount(marks, null)`
     (`frontend/src/lib/worker-count.js:14-25`) applies **no filter at all** — it never
     receives `per_file`, so it cannot mirror Python's legacy branch. Its own docstring
     claims parity; the claim is false for the `per_file`-non-empty case.
     (Note: `cellCount.js:_sumMarks` — the `checks`/maquinaria path — DOES mirror the
     legacy filter faithfully. The divergence is only in `worker-count.js`, i.e. the
     charla/chintegral/dif_pts worker-total surface.)
4. Meanwhile the **viewer and FileList enumerate the live folder**: the merged PDF has no
   marks (`WorkerCountViewer.jsx:434-435` `fileSubtotal(marks, currentFile.name)`), so the
   per-file subtotals/thumbnails show nothing.

**Net symptom:** on re-opening the month, DetailPanel shows the **old total** (unfiltered
orphan marks) while the viewer shows **no marks** — exactly "kept its total but lost its
marks". Worse, the surfaces disagree:

| Surface | Derivation | Value after a merge |
|---|---|---|
| DetailPanel total (fresh session load) | JS unfiltered fallback | **old total** (kept) |
| PATCH response / right after saving | Python, present-filtered | 0 |
| Viewer subtotals / marks list | per current file | 0 / empty |
| **Excel HH (N-columns) + N15** | Python, present-filtered (`api/routes/output.py:160,172`) | **0 — counted workers silently lost from the RESUMEN** |

This is a UI≠Excel divergence on the worker path — the exact class `core/cell_count.py`
was created to eliminate for documents.

**Fix direction (three layers, all needed):**
- **Consistency:** make the backend enrich `worker_count` (present-filtered) into *every*
  cell payload (GET session + `cell_updated` + PATCH), OR pass the real file list to
  `cellWorkerCount` in DetailPanel and delete the unfiltered fallback. One derivation,
  one filter, everywhere. Align `computeWorkerCount(marks, null)` with Python's legacy
  branch (or remove the null path entirely).
- **Product (the real fix for Daniel/Carla):** orphan marks are **counted work being
  silently discarded**. Surface them: "N marcas pertenecen a archivos que ya no existen
  (X.pdf, Y.pdf)" with actions **migrar a un archivo actual** (re-key, preserving page
  info as best-effort) / **descartar**. Silent filtering is correct math but loses hours
  of Carla's counting after every paso-1 reorganization.
- **Tests:** add a cross-language fixture for `per_file`-non-empty + orphan marks (the
  current suite pins Python legacy = 10 in `test_sum_marks_present_files.py:68` but never
  exercises the JS null path against it — that blind spot is where this lived).

Output-safety: VERIFY (worker totals shown/exported change for cells with orphan marks —
that change is the point, but smoke it on a copy DB).

Corroborated independently by the api/ subagent (marks survive all api write paths — the
loss is derivational, not storage) and the frontend subagent (FE-12).

---

## 2. Count-correctness findings

### F2 — Batch-cancel with queued cells crashes the orchestrator; the batch mislabels its ending and leaks the drain thread
- Severity: medium · Category: bug · **SAFE** (fix doesn't touch counts)
- Files: `core/orchestrator/ocr_scan.py:310-348` · `api/routes/sessions/scan.py:484-532`
- Evidence: the cancel-fast branch calls `pool.shutdown(wait=False, cancel_futures=True)`
  (`ocr_scan.py:326`), then the `as_completed` loop keeps calling `fut.result()` **with no
  try/except** (`:327`). A queued-then-cancelled future is immediately "done" and its
  `.result()` raises `concurrent.futures.CancelledError` → escapes the loop, exits the
  `with` block, and — because the sentinel `progress_q.put(_DRAIN_STOP)` (`:347`) is NOT
  in a `finally` — **the drain thread and its mp.Queue leak** (one daemon thread per
  occurrence). The route's `except Exception` in `_run` (`scan.py:493`) then catches it
  (verified empirically on the project's Python 3.10.11:
  `concurrent.futures.CancelledError` MRO is `Error → Exception` — it is *not* asyncio's
  `BaseException` variant), logs a spurious `"scan_cells_ocr crashed"` stack trace,
  releases the agent, and broadcasts the emergency **`scan_complete {scanned: 0,
  errors: N_cells}`**.
- Failure scenario: user scans >2 cells (2 workers ⇒ the rest queue), presses **Cancelar**
  while ≥1 cell hasn't started and the next processed future completed normally → the UI
  reports the batch as **"completado con N errores"** instead of "cancelado" (every cell
  counted as an error, even finished ones), the log shows a crash that isn't one, and a
  drain thread + queue leak. Already-merged per-file results persist (incremental merge),
  so no data is lost. Tests run `max_workers=1` (sync path) — the suite cannot see this.
  Portability note: on any future runtime where `CancelledError` is asyncio's
  `BaseException` flavor, this same gap would escalate to the silent-hang variant, so fix
  it at the source, not the symptom.
- Fix direction: wrap `fut.result()` in `try/except concurrent.futures.CancelledError:
  cancelled += 1; continue` (report a real `scan_cancelled`); move the drain-stop sentinel
  + `drain_thread.join` into a `try/finally` around the pool block.

### F3 — Reorg create/delete endpoints bypass the M3 per-cell locks (source AND dest)
- Severity: **high** · Category: race/bug · **VERIFY**
- Files: `api/routes/sessions/reorg.py:51,90` · `frontend/src/lib/api.js` (no
  `participant_id` on `createReorgOp`/`deleteReorgOp`) · `DetailPanel.jsx:486-493`
  (ReorganizacionPanel gets no `locked` prop — delete stays enabled under a lock)
- Evidence: neither endpoint takes `participant_id` or calls
  `check_cell_lock`/`agent_claim_cell`; `refresh_reorg_deltas` then rewrites
  `reorg_doc_delta`/`reorg_worker_delta` on **both** cells (`_common.py:233-248`), which
  feed `compute_cell_count`/`compute_worker_count` directly.
- Failure scenario: Carla holds HRB|odi (its editor). Daniel creates/deletes a `move_file`
  op whose dest (or source) is HRB|odi → the cell's effective count changes under her, no
  409, no badge — the collision class the entire M3 track closed for the six write methods
  + apply-ratio + B1. The dest-cell case can't be prevented by UI gating alone (you can
  always move *into* a held cell).
- Fix direction: thread `participant_id` from the frontend; gate both source and dest
  (`check_cell_lock` ×2, or agent claim for the agent path) before
  `add_reorg_op`/`delete_reorg_op`; disable ReorganizacionPanel's delete under
  `cellLockHolder` (frontend half). `participant_id=None` stays inert (single-user
  unchanged). [Source: api-agent API-1 + frontend-agent FE-6; verified directly: the
  routes have no gate and the deltas rewrite both cells.]

### F4 — `refresh_reorg_deltas` get-then-set is not atomic → a concurrent op can vanish
- Severity: medium · Category: race · **VERIFY**
- Files: `api/routes/sessions/_common.py:216-248` (read `get_session_state` → compute →
  `set_reorg_state`, two separate lock acquisitions) · invoked from both reorg routes and
  the pase-1 `scan` route (`scan.py:184`)
- Evidence: the docstring claims safety because "the only writer to reorg_ops is the same
  synchronous HTTP tier" — but FastAPI runs `def` endpoints on a **threadpool**, so two
  requests interleave: T1 reads `ops=[A]`, T2 appends B + writes `[A,B]`, T1 writes `[A]`
  → **op B and its delta silently disappear**. Same window between `validate_op`'s overlap
  check and persist (two overlapping `extract_pages` can both land). Verified directly —
  the race is real; each `get_session_state` returns a fresh `json.loads` copy, so this is
  last-writer-wins loss, not aliasing corruption.
- Fix direction: make read-compute-write one `@_synchronized` manager method (recompute
  deltas inside the lock); move the overlap validation inside it too. Fix the docstring.
  [Source: api-agent API-2; self-verified.]

### F5 — Negative counts are reachable; nothing clamps at 0
- Severity: medium · Category: validation/bug · **VERIFY**
- Files: `frontend/src/components/InlineEditCount.jsx:54-76` (no `min`, only `v <= max`;
  `parseInt("-5")` commits) · `api/routes/sessions/writes.py:81-115`
  (`PerFileOverrideRequest.count: int`, only the upper page-cap is checked) ·
  `api/reorg.py:74-81` (`doc_count` validated ≤ pages, but pages ≫ the file's actual
  contribution) · `core/cell_count.py:107-108,126` + `cellCount.js:64-66` (base + delta,
  **no `max(0, …)`**)
- Failure scenarios: (a) operator types `-5` in a per-file count → persists → cell (and
  Excel) silently under-counts, no error; (b) a `move_file` op on a 10-page file that
  contributes 1 document accepts `doc_count=10` → source delta −10 on a base of 1-3 →
  **negative effective count** written to the RESUMEN.
- Fix direction: `min={0}` + reject `v < 0` client-side; `ge=0` on the Pydantic models
  (per-file override + reorg doc_count/worker_count); validate reorg `doc_count` against
  the file's current *contribution* (per_file_overrides|per_file), not its page count;
  clamp `compute_cell_count`/`compute_worker_count` at 0 in **both languages** + a
  cross-language fixture (negative-delta case).
  [Source: frontend-agent FE-2 (verified: input has no min) + core pass (reorg/clamp).]

### F6 — `revdocmaq` is latently mis-wired: its filename glob is dead config
- Severity: medium (latent — 0 sample files exist today, but this is exactly when it must
  be caught) · Category: bug · **VERIFY**
- Files: `core/scanners/patterns.py:839-847` · `core/scanners/utils/filename_glob.py:21-69`
- Evidence: **no code reads `PATTERNS[…]["filename_glob"]`** (grepped: the field is
  data-only, like the documented-informational `recursive_glob`/D7). Pase-1 counting is
  `extract_sigla`, which matches only **literal sigla tokens** from `SIGLAS` bounded by
  `[_\-.]`. The revdocmaq entry's `^.*(revision|documentacion).*\.pdf$` — and its comment
  claiming the token "never collides with maquinaria" — therefore do nothing.
- Failure scenario: real files appear named `REVISION_DOCUMENTACION_MAQUINARIA_X.pdf` →
  `extract_sigla` returns `"maquinaria"` (its token matches inside the name!) or `None` →
  the revdocmaq cell counts **0** with flag `some_files_unrecognized`, forever. Daniel
  believes the provisional glob covers this; it doesn't.
- Fix direction: either (a) implement per-sigla filename-token **aliases** in
  `extract_sigla` (e.g. `revdocmaq: ("revdocmaq", "revision documentacion", …)`) — which
  also fixes F14 — or (b) actually consume `filename_glob` in `count_pdfs_by_sigla`.
  (a) is smaller and keeps one matching mechanism. Either way: delete or honor the dead
  registry field so it can't mislead again; add a fixture test with realistic names the
  day the first real file lands.

### F7 — Pagination recovery can fabricate a document start at HIGH confidence
- Severity: medium (real-corpus edge — the benchmark's degraded-ART `+1` is this
  mechanism) · Category: bug (confidence model) · **VERIFY**
- Files: `core/scanners/utils/pagination_count.py:99-136,139-153` ·
  `core/scanners/pagination_scanner.py:84-91`
- Evidence: recovery fills a gap as `left % dom + 1`; when the left neighbor completed a
  dominant cycle (`left == dom`), the recovered page becomes `curr == 1` and **counts as a
  document start** (`count_starts` doesn't distinguish `recovered`). The
  "provably undercount-safe" claim holds only for **homogeneous totals**; in a mixed
  compilation (docs of 2 pages + docs of 5, `dom=2`), an unreadable corner after page 2 of
  a 5-pager is recovered as a spurious start → **over-count**. The per-PDF low-trust rule
  fires only on `failed_reads > 0`, recovery ratio > 30 %, or cover_code-with-recovery —
  a single recovered page in a 50-page PDF (2 %) sails through at **HIGH**.
- Fix direction: cheap, targeted guard — if any *counted start* has `status=="recovered"`
  (and no cover_code), mark the PDF low-trust (`recovered_start` → LOW) so the operator
  reviews; keep the count itself (review-routing, not derivation, changes). Optionally
  count recovered starts only when the totals are homogeneous (`len(set(totals)) == 1`).
  Re-run the pagination benchmark to confirm no HIGH-confidence cell flips its number.

### F8 — Anchors: a multi-page PDF with 0 matched covers yields count 0 at HIGH confidence
- Severity: medium · Category: bug (confidence model) · **VERIFY**
- Files: `core/scanners/anchors_scanner.py:64-120` · `core/scanners/ocr_scanner_base.py:193-195`
- Evidence: `PaginationScanner` treats `count==0` on a multi-page PDF as impossible
  (falls back to 1, low-trust — `pagination_scanner.py:82-83`); `AnchorsScanner` has **no
  such branch**: 0 covers, no error, no low-trust → the cell finishes 0 at **HIGH** (green
  "listo"). Live case: **senal 0/18** (landscape corner unreadable, known open follow-up)
  — the operator sees a green 0 instead of an amber "review me".
- Fix direction: mirror the pagination rule — a multi-page PDF whose anchors count is 0
  is low-trust (flag + LOW), routing to the keyboard counter. This changes only
  confidence/flags, not the number, but VERIFY the anchors siglas' green/amber states on a
  copy DB (charla/chintegral cells with legitimately-0 files would flip amber — which is
  arguably the honest state).

### F9 — Mirror divergence: JS `??` vs Python `or` in the legacy count fallback
- Severity: medium (latent — currently unreachable in production data) · Category:
  mirror-divergence · **VERIFY**
- Files: `frontend/src/lib/cellCount.js:25` vs `core/cell_count.py:72`
- Evidence: JS `cell?.ocr_count ?? cell?.filename_count ?? 0` treats `0` as present;
  Python `or` treats `0` as missing and falls through to `filename_count`. For
  `{ocr_count: 0, filename_count: 5, per_file: {}}`: **JS → 0, Python → 5** (UI would
  disagree with Excel/history). Unreachable today only because every scanner populates
  `per_file`; it goes live the moment any path writes a bare `ocr_count`.
- Fix direction: pick ONE semantics (recommend Python-side explicit
  `if ocr_count is not None` — an OCR result of 0 *is* information and should not fall
  through to filename_count either; that also fixes the legacy-cell misreport), mirror it,
  and add the `ocr_count=0, filename_count>0` cross-language fixture.
  [Source: frontend-agent FE-9 + core pass (both directions of the same wart).]

### F10 — Everything is keyed by PDF basename; duplicate basenames across empresa subfolders silently corrupt
- Severity: low-medium (needs a real-corpus check to grade) · Category: data-model
  assumption · **VERIFY**
- Files: `core/scanners/simple_factory.py:64-71` (`path_by_name` dict — last wins) ·
  `core/scanners/ocr_scanner_base.py:120-126,156` (`only`/`skip`/`per_file[pdf.name]`) ·
  `worker_marks`, `per_file_overrides`, `present_files` — all name-keyed
- Evidence: cells enumerate **recursively** across per-contractor subfolders (art, charla,
  …). Two files with the same basename in different subfolders: `per_file` keeps one entry
  (sum under-counts vs `count`), `_page_count` opens the wrong file, `only=` scans both,
  marks/overrides can't distinguish them.
- Failure scenario: `AGUASAN/2026-04_art.pdf` + `ALUMINIO/2026-04_art.pdf` → cell total
  diverges from the per-file sum with no warning.
- Fix direction (cheap first step): detect duplicates at enumeration
  (`enumerate_cell_pdfs`) and surface a `duplicate_basename` flag on the cell (amber +
  warning) instead of re-keying the world; a full rel-path keying is a bigger migration,
  only worth it if the corpus actually produces duplicates — **check the live corpus**
  (one PowerShell one-liner) before deciding.

### F11 — Reorg destination picker hardcodes the old 18-sigla list
- Severity: medium · Category: bug · **VERIFY** (affects where a reorg delta lands)
- Files: `frontend/src/components/WorkerCountViewer.jsx:28-32` (verified: local `SIGLAS`
  const missing `revdocmaq`/`espacios`; also duplicates `HOSPITALS`)
- Failure scenario: extract_pages from the visual range tool cannot target the 2 new
  categories (a "colado" espacios form inside another compilation can't be extracted to
  espacios).
- Fix direction: import `SIGLAS` from `lib/sigla-labels` (the canonical 20) and delete the
  local copies. Grep for other hardcoded sigla lists while at it.
  [Source: frontend-agent FE-1; verified directly.]

### F12 — `scan_file_ocr`'s B1 lock gate is entry-only; the deferred merge write is ungated
- Severity: low · Category: race (residual of B1) · **VERIFY**
- Files: `api/routes/sessions/scan.py:579` (gate) vs `:598` (merge on the pool thread,
  minutes later, no re-check)
- Failure scenario: operator starts single-file OCR on a big PDF, closes the tab; after
  the 45 s lease expiry another participant claims the cell; the OCR completes and merges
  onto the new editor's cell with no 409. Narrow (browser heartbeats every 15 s while
  open) but a real residual. Related: the single-file scan has **no cancel path at all**
  (`cancel_token` is created and never exposed — a 300-page charla file OCR cannot be
  stopped; see U6).
- Fix direction: re-check the lock at merge time inside `on_progress` (or hold an
  agent-style claim for the scan's duration). [Source: api-agent API-3.]

### F13 — Unvalidated hospital/sigla params create phantom cells that leak into history
- Severity: low · Category: robustness · **VERIFY** (phantoms reach `historical_counts`)
- Files: cell write routes (no `hospital ∈ HOSPITALS` / `sigla ∈ SIGLAS` check) →
  `state.py` `setdefault` chains persist junk cells → `api/routes/output.py:237` iterates
  `state["cells"]` (not the canonical grid) for the history UPSERT; `patch_worker_count`
  additionally 500s (`CATEGORY_FOLDERS[sigla]` KeyError outside its try) *after*
  persisting the phantom. `set_reorg_state` can also mint cells for arbitrary delta
  targets (ties into F3's ungated dest).
- Fix direction: validate both params at route entry (400), and make the history loop
  iterate the canonical grid ∪ known cells. [Source: api-agent API-5; mechanism confirmed
  against output.py during the core pass.]

### F14 — Filename-token alias asymmetry: `CPHS`-named files would not count for `chps`
- Severity: low (**needs a 2-minute corpus check to confirm or dismiss**) · Category:
  bug (latent) · **VERIFY**
- Files: `core/domain.py:79-81` (folder alias `chps→CPHS` exists) vs
  `core/scanners/utils/filename_glob.py:25-27` (token patterns built from `SIGLAS` only —
  no alias layer)
- Evidence: the Increment-A alias fixed the *folder* (`20.-CPHS` resolves), but a file
  named `2026-05_cphs_acta.pdf` yields `extract_sigla → None` → not counted, flag
  `some_files_unrecognized`. The 2026-06-23 smoke "restored the 6 to their real PDF
  counts", which suggests current chps files carry the `chps` token — but the corpus
  spells the committee `CPHS`, so future files are a coin-flip.
- Fix direction: same alias mechanism as F6-(a): per-sigla token aliases in
  `_SIGLA_PATTERNS` (`chps: ("chps", "cphs")`). Verify against the live corpus first.

### F15 — `cell_updated` snapshots replace a cell mid-optimistic-edit (no pending-save guard)
- Severity: low · Category: race · **VERIFY** (displayed values)
- Files: `frontend/src/store/session.js:862-879`
- Evidence/scenario: the handler blind-replaces the whole cell without consulting
  `_pendingSave`; a self-echo or scanner/agent write landing between an optimistic set and
  its POST resolution transiently clobbers the edit. Mostly masked by the M3 locks; the
  real window is bulk actions on unheld cells (e.g. "Marcar listas") racing a scan.
  Also the direct cause of F1's field-erasure (the snapshot lacks `worker_count`).
- Fix direction: skip/merge `cell_updated` for cells with a live pending controller;
  reconcile on POST resolution. [Source: frontend-agent FE-4.]

---

## 3. UX / robustness (U-series)

| ID | Finding | Severity | Files / evidence | Fix direction | Tag |
|----|---------|----------|------------------|---------------|-----|
| U1 | Lightbox per-file editor lacks lock-gating and the ≤pages cap that FileList has (over-cap → 422 → stale optimistic value) | low | `PDFLightbox.jsx:341-355` vs `FileList.jsx:362-364` | pass `disabled={isLocked}` + `max` | SAFE |
| U2 | Non-409 error on per-file save neither reverts the optimistic list nor refetches; sticky global `error` surfaces later in MonthOverview | low | `store/session.js:428-438` | bump `filesTick` + toast instead of global error | SAFE |
| U3 | Per-file count editable on `checks` (maquinaria) but never affects the tally — looks broken | low | `FileList.jsx:356-378`; `cell_count.py:63-64` | hide/read-only the editor for `showsWorkerCounter` siglas | SAFE |
| U4 | HospitalCard dot tooltip bypasses `computeCellCount` (ignores per-file overrides, reorg delta, checks tally) | cosmetic | `HospitalCard.jsx:64` | use `computeCellCount` | SAFE |
| U5 | ~~`saveWorkerCount` 409 branch omits `refetchSession`~~ **WITHDRAWN (plan review, 2026-07-02):** the branch already calls `get().refetchSession(sessionId)` at `store/session.js:604` — the original FE-13 claim was a misread, verified directly. | — | `store/session.js:604` | none needed | — |
| U6 | Single-file OCR can't be cancelled (token created, never exposed; no endpoint) — a 300-page charla "Revisar OCR" runs to completion | low-med | `scan.py:612-628` | wire a cancel handle (mirror batch cancel) | SAFE |
| U7 | `on_page` contract mismatch: anchors emits 0-based *before* the page, pagination emits 1-based *after* → single-file viewer progress on pagination siglas shows **"página N+1 de N"** | cosmetic | `header_band_anchors.py:203` vs `pagination_count.py:205-206` vs adapter `ocr_scan.py:70-80` (`page_idx + 1`) | unify the callback contract (document + fix one side) | SAFE |
| U8 | Generating the RESUMEN while the previous .xlsx is open in Excel → raw `PermissionError` 500 (Windows rename lock) | low | `core/excel/writer.py:96-100` | catch → 409 with "cierra el archivo en Excel" message | SAFE |
| U9 | OCR retry (FASE 5) re-emits `pdf_done` for files already ticked in the failed attempt → progress `done` inflates (display clamped by `min(done,total)`, so it stalls at 100 % early) | cosmetic | `ocr_worker.py:138-150` + `ocr_scan.py:181-189` | reset per-cell tick tracking on retry, or de-dup by name | SAFE |
| U10 | Month-switch leaves ghost presence (no `leave` for the old session; `leavePresence` store action is dead code) | low | `store/session.js:74,98,1058-1066` | call it in `openMonth` before reconnect | SAFE |
| U11 | Lifespan shutdown doesn't await single-file OCR dispatches; `_DISPATCH_POOL` never shut down (B3 residual) — a shutdown mid-scan silently loses that file's merge | low | `api/main.py:51-62`; `scan.py:627` | track dispatch futures like batches | SAFE |
| U12 | `useSpeechNumber` cleanup leaves `onresult` bound (post-unmount no-op in React 18, but tidy it) | cosmetic | `hooks/useSpeechNumber.js:60-65` | null `onresult` too | SAFE |

---

## 4. Performance opportunities (new instances only; P1-P4 of the 2026-06-21 audit remain deferred-by-decision)

| ID | Finding | Impact | Files | Tag |
|----|---------|--------|-------|-----|
| PF1 | **Interactive latency:** `patch_override` validates the ≤pages cap via `_cell_total_pages` → `cell_page_counts` → **opens every PDF in the folder** synchronously in the request (HPV/charla = 338 `fitz.open` per keystroke-commit). Same walk in `apply_ratio` and per-cell `refresh_all_reliable`. | medium (feels like slow saves on big cells) | `_common.py:114-128,255-258`; `writes.py` | VERIFY (validation source changes) |
| PF2 | Output generation re-walks + re-opens folders repeatedly in one request: `_build_cell_values` (checks), `_build_worker_values` (charla+chintegral+difpts ×4 hospitals), then the history loop (checks again) — each via its own `cell_page_counts`. | low-med (manual op, but scales with corpus) | `api/routes/output.py:97-260` | VERIFY |
| PF3 | Session-level caching seam: `cell_page_counts` is recomputed from disk everywhere; a per-(cell, mtime) memo (or the Incr-J deferred `per_file_pages` persistence its docstring anticipates) would collapse PF1+PF2 and part of old-P2. | medium (the structural fix behind PF1/PF2) | `_common.py:114` | VERIFY |
| PF4 | Store-wide subscriptions re-render the whole tree per `pdf_progress` tick (App/MonthOverview/HospitalDetail use bare `useSessionStore()`). | low (single-user LAN; visible jank on big scans) | `App.jsx:12`, views | SAFE |
| PF5 | Anchors two-pass OCR doubles per-page cost on every non-cover page (documented E6 tradeoff — listed for completeness, NOT recommended to change without a benchmark). | — | `header_band_anchors.py:204-217` | VERIFY |

---

## 5. Hygiene / docs / dead surface (D-series)

| ID | Finding | Files |
|----|---------|-------|
| D1 | `core/CLAUDE.md` is stale and self-contradictory: says "all 18 SIGLAS", "1 none / 6 anchors / 11 pagination" (now 2/6/12 of 20), and the V4 section claims V4 is "reached via PaginationScanner via utils/v4_count.py" while the Scanner-Architecture section correctly says V4 is unwired (quarantine). | `core/CLAUDE.md` |
| D2 | `api/CLAUDE.md` still documents 18 cells and a monolithic `routes/sessions.py`; env-var table fine. `months.py:83` + `siglas.py:21` docstrings say 18. | `api/CLAUDE.md`, `api/routes/months.py`, `api/routes/siglas.py` |
| D3 | `COUNT_TYPE_BY_SIGLA` comment says "el gate de completitud exige las 18" (it's 20); `count_type_for` docstring likewise. | `core/scanners/patterns.py:877,905-907` |
| D4 | `resolve_cell_value`'s legacy `cell["count"]` fallback is dead (v1→v2 migration pops `count` before any state reaches the writer) — and if it ever fired it would *override a legitimate 0* (e.g. `user_override=0`). Remove. | `core/excel/writer.py:31-33` |
| D5 | History UPSERT writes `confidence=cell.get("confidence", "high")` — never-counted cells (seeded `{}`) get **high-confidence 0 rows** in `historical_counts`. Default should be `"low"`/`"none"` or skip-if-empty. | `api/routes/output.py:257` |
| D6 | `patch_per_file_override` reaches into the private un-synchronized `mgr._load_and_migrate` (benign today; latent lock-free write) and omits `_validate_session_id` (404 instead of 400 — S5 residual). | `api/routes/sessions/writes.py:86-135` |
| D7 | D8/D9 of the previous audit persist: dead `SessionManager.apply_ocr_result` + unreachable `finalize`/`finalize_session`. Still deferred-by-decision; listed so they aren't forgotten. | `api/state.py` |
| D8 | `patterns.py` `filename_glob` field: dead config that actively misleads (see F6) — delete or wire. `recursive_glob` (old D7) same status. | `core/scanners/patterns.py` |
| D9 | `frontend/src/lib/flavorStub.js` + `constants.js` leftovers — confirm consumers, prune. | frontend/src/lib |

---

## 6. Tests / QA / docs sweep (Sonnet subagent; spot-verified)

**Suite baseline (all green):** pytest fast `-m "not slow"` = **701 passed / 0 failed /
51 skipped**, 162 s, **0 warnings** (genuine zero — no `filterwarnings` suppression
exists). vitest = **237 passed** (29 files, no `.skip`/`.todo`). ruff = clean. The 6 slow
tests reference `A:/informe mensual/ABRIL` (exists → runnable). Of the 51 skips: 39 are
the correct gitignored-fixture guard pattern; 12 are the E9 hard skips below.

### Coverage / test quality

| ID | Finding | Severity |
|----|---------|----------|
| QA-1 | **E8 still open, unaddressed**: the 8 per-sigla fixture-test files for the pagination-migrated siglas (art, andamios, herramientas_elec, irl+odi, exc, ext, caliente, bodega) still instantiate **only `AnchorsScanner`** — the unused path — while production runs `PaginationScanner`. `test_pattern_altura.py`/`insgral.py` already model the correct pattern (pure `PaginationScanner`); it was never back-applied to the original 9. | medium |
| QA-2 | **E9 still open**: the same 12 hard `@pytest.mark.skip` as the prior audit (byte-identical reason). 6 legitimate (charla/senal/maquinaria — still anchors), 6 wrong-premise (art/andamios/herramientas_elec — now pagination; "awaiting anchor fixture rebuild" can never resolve). Delete the 6 with QA-1's replacements. | low |
| QA-3 | **≥10 "fast"-tier test files hardcode `A:/informe mensual/ABRIL` with NO skip-guard and NO `slow` marker** (test_orchestrator*, test_simple_factory, test_filename_glob, test_page_count_heuristic, test_clear_near_matches, test_routes_output/sessions/months, test_state) — verified empirically: they pass by reading the live corpus. On a fresh clone or when Daniel's corpus lifecycle archives ABRIL they hard-**fail** instead of skipping, unlike the project's own 39 correctly-guarded tests. | medium |
| QA-4 | `test_abril_full_corpus_yields_72_cells` asserts 80 — name drifted from its own assertion (18→20 fan-out miss). | cosmetic |
| QA-5 | `sigla-labels.js` exports (`SIGLA_LABELS`, `siglaDisplay` incl. the chps→cphs override) have zero test coverage — the only per-sigla table without a completeness gate. | low |
| QA-6/7 | **`tools/capture_failures.py` + `tools/capture_all.py` have broken imports** (`core.analyzer` — module doesn't exist; `EASYOCR_DPI`/`_init_easyocr` from `core.ocr` — removed 2026-03-26). Masked by a skipif-gated fixture / zero coverage. Fix the imports or retire the tools. | medium |

### Packaging

| ID | Finding | Severity |
|----|---------|----------|
| QA-25 | **`openpyxl` absent from both requirements files** while `core/excel/writer.py`/`template.py` (the app's deliverable) import it — a clean `pip install -r requirements.txt` breaks Excel generation with `ModuleNotFoundError`. Verified directly against `requirements.txt`. Add `openpyxl==3.1.5` to the base tier. | **high** |
| QA-26 | `transformers>=4.40,<5` pinned in `requirements-gpu.txt` for the deleted `eval/pixel_density` DiT experiment — zero importers repo-wide. Drop. | low |
| QA-27 | `anthropic` + `requests` in base `requirements.txt` serve only the opt-in `vlm/` module — consider a `requirements-vlm.txt` or a comment. | low |

### Docs drift (the sweep found the module READMEs badly out of date; the CLAUDE.md files mostly current except the counts)

| ID | Finding | Severity |
|----|---------|----------|
| QA-11 | **Root `CLAUDE.md` intro + Tech Stack still frame the quarantined V4 engine as the primary pipeline** ("OCR + AI inference engine", "V4… Dempster-Shafer") — the first thing every agent/human reads, contradicting README.md and CLAUDE.md's own history sections. | high |
| QA-15/16 | **`core/README.md` describes the pre-triad V4-only architecture as current** and documents a `core/__init__.py` aggregate-export surface that is the *exact anti-pattern* (A1) deliberately removed in the 2026-06-21 audit — a reader following it could reintroduce the eager-import regression. The actual `__init__` says the opposite verbatim. | high |
| QA-18/19 | **`api/README.md` documents modules and endpoints that don't exist** (`database.py`, `websocket.py`, `worker.py`, `routes/pipeline.py`, `/api/start|stop|reset|correct|exclude|restore`, `data/sessions.db`) and omits 6 of the 8 real route modules. Replace with `api/CLAUDE.md`-aligned content. | high |
| QA-8 | `core/domain.py:104` docstring example is now false: `'13.-Revision Documentacion Maquinaria' -> None (unmodeled)` — it returns `'revdocmaq'` (its own test asserts so). Verified in the core pass. | medium |
| QA-9 | Stale "18 siglas / 18 cells / 11 pagination" in **10 locations** (`core/domain.py:13`, `patterns.py:4,877`, `simple_factory.py:3`, `api/routes/siglas.py:18`, `api/CLAUDE.md`, `core/CLAUDE.md`, root `README.md:47-48`, `data/templates/README.md:86`). Correct current distribution (re-derived from `PATTERNS`): **2 none / 6 anchors / 12 pagination = 20**. One grep-and-fix pass. | medium |
| QA-10 | Root `CLAUDE.md` structure tree: `core/` one-liner still "OCR pipeline, inference engine"; `models/` still lists the deleted `EDSR_x4.pb`. | medium |
| QA-12 | `CLAUDE.md` "Pending Work" frozen since ~March: omits the 2026-06-21 DEFERRED items and bug #2. | medium |
| QA-20 | `tools/README.md` documents the deleted `regex_pattern_test.py`, omits 4 existing scripts. | medium |
| QA-13/14/17/21/22/23/24 | Smaller drift: Key-Commands table missing frontend build/test; Links → deleted `eval/pixel_density/README.md`; `core/README.md` cites a nonexistent easyocr postmortem ×2; `vlm/README.md` cites a nonexistent spec; `api/reorg.py:3` references the pre-split `sessions.py`; `frontend/README.md` is unmodified Vite boilerplate; `eval/CLAUDE.md` table omits 2 files. | low/cosmetic |

### Verified-clean by the QA pass
No new large binaries (largest tracked file 709 KB; 612 tracked files); deleted eval
subprojects left zero dangling references; whole-repo `ast.parse` clean; the A+B increment
coverage (folder matching, v3→v4 reconcile, espacios pagination, chps exclusion) is genuinely
solid and **sigla-count-dynamic** (won't rot on the next growth); DB-mocking convention
honored (monkeypatch + real tmp SQLite only); the autouse **write-guard fixture** protecting
`A:\informe mensual` + `A:\estadistica mensual` is intact; `.claude` hooks + hookify rules
all resolve; `.gitignore` covers `observations.txt`/outputs/bak; `frontend/package.json`
deps all have real import sites; `torch` imports only from the quarantined `core/ocr.py`,
`easyocr` from nowhere; `docs/handoff/paso1-manifiesto-reorganizacion.md` is internally
consistent with `api/reorg.py`; `docs/archive/INDEX.md` matches its directory 1:1.

---

## 7. Verified-clean (worth knowing what was checked and held)

- **The counting cascade is correct**: `compute_cell_count`/`_base_count`/`_sum_marks`
  precedence (override > checks > per-file ∪ overrides > fallback), the Incr-J additive
  delta, A7/A8, the `file_result` merge guard (`method != filename_glob`), and the
  `_cell_has_work` clobber-guard were re-derived line by line — no regression.
- **M3a atomicity holds** for the six single-cell writes + apply-ratio: conflict-check and
  write share one `@_synchronized` acquisition; a lease cannot expire-and-be-reclaimed
  between check and write (re-claim also needs the RLock).
- **WS layer**: `_CONNECTIONS` touched only on the loop thread; broadcast snapshots before
  iterating; `_emit`/`_safe_broadcast` best-effort guards hold (the M1 regression fix
  stands).
- **DB**: WAL + autocommit; the direct `mgr._conn` uses in output/history cannot interleave
  partial transactions.
- **File serving**: two-layer `is_relative_to` containment (PDF ⊂ cell folder ⊂ corpus
  root); `scan_file_ocr` validates the filename against the real folder listing; reorg
  export refuses to write inside `INFORME_MENSUAL_ROOT`.
- **Zustand v5 selector footgun: eradicated** (every selector swept — defaults applied
  outside selectors).
- **Hook lifecycles clean**: pdf.js loadingTask destroy, ResizeObserver disconnect,
  debounce cancel, speech stop, WeakMap thumbnail caches, IntersectionObserver disconnect.
- **Reorg viewer mode provably cannot write worker marks** (all six gates verified).
- **No hardcoded backend hosts outside `lib/config.js`; no raw Tailwind palette classes;
  no voseo in microcopy; sigla tables complete at 20.**
- **Presence lease renewal covers the focused lock** (heartbeat renews the same record —
  the "lock lapses during a long count" hypothesis was tested and disproven).
- `enumerate_month`/`_find_category_folder` renumber-tolerance (Increment A) behaves as
  specified, including the `CPHS` folder alias and suffix matching; folder matching is
  deterministic-first-match (see F10/F14 for the residual name-level asymmetries).

---

## 8. Suggested remediation order (plan seed — not a plan)

0. **Same-day trivials** (SAFE, minutes): QA-25 (`openpyxl` into requirements.txt), F11
   (SIGLAS import in the reorg picker), QA-4 (test rename).
1. **Count integrity now** (one increment, VERIFY-gated on a copy DB): F1 (bug #2:
   consistency + orphan-marks UX), F5 (negative clamps + validation), F3+F4 (reorg locks +
   atomic refresh), F13 (param validation). These four close every known way a wrong
   number reaches the Excel.
2. **Scan robustness** (SAFE, small): F2 (cancel crash — includes the drain-stop `finally`),
   U6 (single-file cancel), U9, U11.
3. **Confidence honesty** (VERIFY, benchmark-backed): F7 (recovered-start → LOW), F8
   (anchors 0-at-HIGH), F12 (merge-time lock re-check).
4. **Latent/one-line preventions**: F6+F14 (token aliases — do before the next corpus
   month lands), F9 (mirror semantics + fixture), F15.
5. **Test hardening**: QA-1+QA-2 (the E8/E9 debt — per-sigla `PaginationScanner` fixtures,
   delete the 6 wrong-premise skips), QA-3 (guard or `slow`-mark the 10 real-corpus test
   files), QA-5, QA-6/7 (fix or retire the two broken tools).
6. **UX polish batch** (SAFE): U1-U5, U7, U8, U10, U12, PF4.
7. **Perf**: PF3 (page-count memo/persistence) subsumes PF1/PF2 — measure first.
8. **Docs/hygiene sweep** (SAFE): D1-D9 + QA-8..QA-24 (prioritize QA-11/15/16/18/19 — the
   high-drift files that actively mislead: root CLAUDE.md V4 framing, core/README.md,
   api/README.md) + QA-26/27.

---

*Method note: subagent outputs were treated as claims, not findings — the high-severity
ones (F2 empirically, F3/F4/F11/F5-input via direct code reads) were re-verified before
inclusion; per-finding source attribution is noted inline. The counting pipeline itself was
audited exclusively by the main agent, per project convention.*
