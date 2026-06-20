# PDFoverseer

**PDF document analyzer** that counts internal documents in lecture PDFs (CRS) using an OCR + AI inference engine.

## Quick Start

```bash
# Backend (inference + API)
source .venv-cuda/Scripts/activate  # or: .\.venv-cuda\Scripts\activate (Windows)
python server.py                     # FastAPI on http://localhost:8000

# Frontend (React UI)
cd frontend && npm run dev           # Vite on http://localhost:5173

# Tests
pytest
```

## Installation

```bash
# CPU-only (Tesseract + PyMuPDF)
pip install -r requirements.txt

# GPU (adds PyTorch CUDA for SR Tier 2 bicubic upscaling)
pip install -r requirements-gpu.txt
```

## Tech Stack

- **Backend:** Python 3.10+ with CUDA GPU, FastAPI, PyMuPDF, Tesseract
- **Frontend:** React + Vite, react-zoom-pan-pinch
- **OCR Pipeline:** V4 (6 parallel Tesseract workers, Tier 1 direct + Tier 2 SR-GPU)
- **Inference:** 5-phase engine with Dempster-Shafer post-validation
- **VLM Module:** Vision-Language Model benchmark/sweep for OCR comparison

## Project Structure

```
├── core/           # OCR pipeline, inference engine, constants (see core/CLAUDE.md)
├── api/            # FastAPI routes, sessions, WebSocket (see api/CLAUDE.md)
├── vlm/            # VLM benchmark + sweep module (see vlm/CLAUDE.md)
├── eval/           # Evaluation harness: sweeps, fixtures, tests (see eval/CLAUDE.md)
├── tools/          # Standalone utilities (capture, pattern eval, regex test)
├── frontend/       # React UI (components, hooks, store)
├── tests/          # Integration + unit tests
├── models/         # Super-resolution models (FSRCNN_x4.pb, EDSR_x4.pb)
├── data/samples/   # 22 source PDFs for scan + fixture extraction
├── docs/           # Active research notes + referenced plans/postmortems
├── server.py       # FastAPI entry point
└── requirements.txt
```

## Development

### Git Info

- **Main branch:** `master`
- **Working branch:** `po_overhaul` — the single active branch (see "Consolidación" below). Work here directly; push at the end of each round.

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Convention:** Work directly on `po_overhaul` in the main checkout. Do **not** leave feature worktrees unmerged — that debt has bitten us before. If a worktree is used for isolation, fast-forward it into `po_overhaul`, push, and delete it before calling the work done.

**Old foreign worktrees** (NOT merged into `po_overhaul` — predate the consolidation, unrelated to current work; kept only as branch refs):
- `feature/crop-selector` — UI crop region selector (unmerged MVP)
- `feature/ocr-matcher` — fuzzy OCR pattern generator (unmerged)

**Other branches:**
- `research/pixel-density` — pixel density research (no worktree, checked out directly when needed)

**Setup:** Use `superpowers:using-git-worktrees` skill to create isolated workspaces.

### Key Commands

| Command | Purpose |
|---------|---------|
| `python server.py` | Start FastAPI backend + WebSocket |
| `cd frontend && npm run dev` | Start React dev server |
| `pytest` | Run test suite |
| `ruff check .` | Lint (must be 0 violations before commit) |

## Conventions

### Git & Workflow
- **Commits:** English, format: `type(scope): message`
  - Examples: `feat(ocr): add SR tier 2`, `fix(inference): D-S calibration`
- **Branches:** Work directly on `po_overhaul` (the single active branch); only branch off for genuinely isolated experiments, and fast-forward + delete them when done
- **Tests:** Always pass before merge (no skipped/pending tests)
- **DB mocking:** Avoid mocking in tests — use real fixtures where possible
- **Worktrees:** Use `.worktrees/<name>` only for isolated experiments, and close them (FF → push → delete) before declaring done — do not accumulate unmerged worktrees

### Code Quality
- **Linting:** `ruff check .` must report **0 violations** before committing
  - Config in `pyproject.toml`; rules: E, F, W, I (isort), UP (pyupgrade)
  - Intentional late imports (after `sys.path` manipulation): suppress with `# noqa: E402`
- **Dead code:** Remove unused imports, variables, and unreachable assignments — never commit them
- **No bare `except:`** — catch specific types (`except ValueError`, `except Exception` at minimum)
- **No `print()` in library code** — use `logging.getLogger(__name__)`; `print()` only in CLI entry points and standalone tools

### Types & Docstrings
- **Type annotations:** Use Python 3.10+ syntax: `X | None` not `Optional[X]`, `list[X]` not `List[X]`
- **Docstrings:** Public entry points (functions callable from outside the module) need Google-style docstrings with `Args:` and `Returns:` sections

### Architecture
- **Constants:** Magic numbers belong in `core/utils.py` (pipeline/inference config) or at module level — never inline
- **One responsibility per file:** Each module has a single clear purpose; if a file is doing two things, split it
- **Module docs:** New packages/modules get a `README.md` explaining their purpose, files, and usage
- **Frontend design tokens:** Always use `po-*` tokens in JSX (defined in `frontend/tailwind.config.js`), never raw `bg-slate-*`/`bg-indigo-*`/etc. 8 shared primitives live under `frontend/src/ui/`; `Badge.jsx` tones `iris/jade/amber` map to the existing `po-override-*`/`po-confidence-high-*`/`po-suspect-*` tokens. See `CategoryRow` + `DetailPanel` for reference usage.

### Guardrails & Hooks

**Hookify rules** (`.claude/hookify.*.local.md`) enforce code quality + safety at file write time:

| Rule | Type | Purpose |
|------|------|---------|
| **eval-before-core** | warn | Inference changes must be prototyped in `eval/inference_tuning/inference.py` first |
| **no-bare-except** | **BLOCK** | All exception handlers must catch specific types |
| **no-shell-true** | **BLOCK** | Never use `shell=True` in subprocess calls |
| **no-sql-fstrings** | **BLOCK** | SQL queries must use `?` parameterized form |
| **no-print-in-libs** | warn | Use `logging.getLogger(__name__)` in library code |
| **ruff-before-done** | warn | Verify `ruff check .` passes before stopping |
| **no-legacy-typing** | warn | Use Python 3.10+ syntax (`X \| None` not `Optional[X]`) |
| **bump-version-tags** | **BLOCK** | Bump a version tag in `core/utils.py` before editing `core/{pipeline,ocr,inference,image}.py` or `vlm/*.py` |
| **constants-in-utils** | warn | Pipeline constants belong in `core/utils.py` |
| **no-db-mocking** | warn | Never mock database in tests |
| **torch-try-except** | warn | Torch imports must be wrapped in try/except |

**Native hooks** (`.claude/settings.json`):
- **PreToolUse** (Write|Edit): Guards hand-editable deliverables (`.xlsx/.docx/.pptx/.pdf`). If the target already exists, makes a dated `<file>.bak-<ts>` backup and returns `permissionDecision: ask` so the overwrite is confirmed — never lose hand-edited work again (`guard-editable-deliverables.py`)
- **PostToolUse** (Edit|Write): Auto-runs `ruff format` on `.py` files (format only — `--fix` was removed so the autofix can't strip an import mid-edit; lint reporting is left to `ruff-before-done` + the pre-commit `ruff check .` gate)
- **PostToolUse** (WebFetch|WebSearch): Injects an "untrusted web content" prompt-injection warning next to fetched content
- **PostCompact**: Re-injects `.claude/context-essentials.txt` after context compaction
- **Stop**: Non-blocking reminder when the current branch is ahead of its remote (`origin/<branch>`) — surfaces "N commits sin pushear" via `systemMessage`, honoring the push-at-close convention (`remind-push.py`)

## Compaction

When compacting, preserve:
- Complete list of files modified in this session
- Errors encountered and how they were resolved
- Architectural decisions made during the session
- Current task progress and next steps

## Links

- **VLM integration postmortem:** `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`
- **Pixel density README:** `eval/pixel_density/README.md`
- **Eval README:** `eval/README.md`
- **Core README:** `core/README.md`

## Documentation Access (AgentSearch)

When you need current documentation for any library used in this project, use `npx nia-docs` to query it directly:

```bash
npx nia-docs <docs-url> -c "tree -L 1"     # Browse structure
npx nia-docs <docs-url> -c "cat <page>.md"  # Read a page
npx nia-docs <docs-url> -c "grep -rl '<term>' ."  # Search
```

Common URLs: [PyMuPDF](https://pymupdf.readthedocs.io) | [FastAPI](https://fastapi.tiangolo.com) | [Tesseract](https://tesseract-ocr.github.io/tessdoc/) | [React](https://react.dev) | [Vite](https://vite.dev/guide/)

## Pending Work

- **INS_31:** ~~Last-page inference gap~~ FIXED (2026-03-26). Tray UX improvements still pending.
- **VLM integration:** ~~Attempted~~ REVERTED (2026-03-30). See postmortem in Links.
- **Browse UX:** `/api/browse` uses server-side tkinter chooser — only works with local display

## Consolidación de `po_overhaul` — rama única, sincronizada con origin (2026-06-03)

`po_overhaul` es la **rama única** del proyecto, con **todos** los avances
(ocr-per-sigla, worker-viewer-ux, y conteo-confiable MVP + rev-1 + rev-2) y
**pusheada a origin** (`origin/po_overhaul` == local, tags `conteo-confiable-*` +
demás milestones en origin). `crop-selector`/`ocr-matcher` son ramas viejas ajenas.

**Convención de trabajo (para que la deuda de merges no reaparezca):** trabajar
**directo en `po_overhaul`** en el repo principal y **pushear al cierre de cada
ronda**. NO abrir feature worktrees que quedan sin mergear. Si se usa un worktree
para algo aislado, cerrarlo (fast-forward a po_overhaul + push + borrar) antes de
darlo por terminado.

## Project history

Shipped milestones on `po_overhaul`, newest first. The full narrative (smoke notes,
"bugs caught", bundle deltas, new deps) lives in the per-milestone memory files
(`~/.claude/projects/.../memory/project_*`) and the git tags; specs/plans under
`docs/superpowers/{specs,plans}/`.

- **2026-06-20 · tag `multiplayer-m3b`** — **multiplayer M3b: Claude as a full participant + scanner that respects locks** (closes the M3 stage / the whole multiplayer track; spec `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` §6.4/§8/§9/§10, plan `docs/superpowers/plans/2026-06-20-multiplayer-m3b-claude-participante.md`). Two parts unified by **one registry primitive**. **(1) Claude as a participant:** an API write with `participant_id="claude"` to a **free** cell auto-claims it (Claude becomes its `editor` → its badge shows + everyone else goes **read-only** via the *existing* M3a gating, zero new gating code — `cellLockHolder` is identity-agnostic); a write to a cell held by **another** → **409**. **(2) Scanner respects locks:** the OCR (pase-2) + filename (pase-1) scanner acts as that same `claude` agent — per cell it **claims** (free) or **skips** (held by a human), never clobbering a live edit. **Backend:** fixed agent identity in `api/presence.py` (`AGENT_PARTICIPANT_ID="claude"`, `AGENT_NAME="Claude"`, `AGENT_COLOR="#0ea5e9"`, `AGENT_KIND="agent"`, `is_agent()`) + `PresenceRegistry.agent_focus(session_id, cell)` (claim, mirrors `focus`'s lease/release); `SessionManager.agent_claim_cell` (`@_synchronized`, **atomic** check-or-claim: holder dict if held by another, else claims + None) + `agent_leave`. The **6 write methods** auto-claim for the agent (one line after the M3a conflict check — the 409 path is unchanged; humans never auto-claim, their browser `focus`-claimed first); `apply_ratio` uses `agent_claim_cell`→`CellLockedError`. Each write route broadcasts a `presence` snapshot after an agent write so the badge appears. The **scanner** is a module-level `_handle_scan_progress(mgr, sid, event, ctx, emit)` (extracted for testability) wired into `scan_ocr`'s `on_progress` with a **route-scoped `ctx`** so the **crash-path** in `_run` also releases the agent: at `cell_scanning` it `agent_claim_cell`s → on a human holder it records the skip + emits **one** `cell_skipped {hospital,sigla,reason:"locked",lock_holder}`, drops that cell's later events (`pdf_progress`/`file_result`/`cell_done`); on terminal it `agent_leave`s + enriches `scan_complete` with `skipped:[…]` (cancel gets no `skipped`). Pase-1 `scan` route check-and-skips (`presence_lock_holder(exclude=AGENT_PARTICIPANT_ID)`) + returns `skipped` in its JSON (no badge claim — it's a 4 s bulk pass). Accepted: a cosmetic `pdf_progress` multi-worker race (decision 4) + pase-1 skips not surfaced in the UI (pase-1 runs only on first month-open). **No lock-lending endpoint** (§8 — the "user has the cell open" edge is conversational). **Frontend:** store handles `cell_skipped` (accumulate, don't touch `session.cells`) + `scan_complete.skipped` (de-duped; suppresses the 5 s auto-dismiss when skips exist); **ScanProgress** shows a persistent suspect-tone "N saltadas (en edición)" summary + the cell list + a **"Re-escanear saltadas"** button; **PresenceBadge** renders a lucide **Bot** icon for `kind==="agent"` (using `participant.color`, not hardcoded). **Inert for single-user** (no human → scanner skips nothing, `scan_complete.skipped==[]`; no agent → initials as before). Per-chunk 2-stage review (all **Sonnet**) + holistic (Opus) = **Ready to ship**; reviews caught a spec-gap (handler had no direct tests → added 4), tests reaching into `mgr._presence` (→ public pass-throughs), the `cell_skipped` stale-snapshot updater (→ functional), a missing de-dup test, + doc/naming nits. **A Chunk-3 implementer subagent went off-protocol** (used a git worktree despite instructions, cherry-picked → **duplicate agent defs**, and pushed autonomously) — caught by verifying git state; the dedup (`b12f187`) was confirmed clean (each symbol once, `AGENT_COLOR` correct) before continuing. Suite **837 passed / 0f** (`-m "not slow"`, incl. eval/tests), vitest **232**, build OK, ruff 0. **Live API smoke 5/5** (Claude→held=409 w/ lock_holder; Claude→free=200 + presence shows `claude` editor `kind=agent`; pase-1 `skipped:[HRB|odi]`, agent-held cell NOT skipped) + **live 2-context browser smoke PASSED** (Brave debug, isolated copy DB `:8010` + fetch/WS `:8000→:8010` rewrite: Claude claims HRB|irl via API → Carla sees the **cyan Bot avatar** in the roster + on the row + the read-only banner "Claude está editando esta celda" + every control disabled + FileList "Bloqueado por otro participante"; lease auto-recovers; screenshot-confirmed). Real `overseer.db` byte-identical (sha256 `e661a8c5…`). No version bump. Memory: `project_multiplayer_m3b_shipped`. **Multiplayer track COMPLETE (M1→M2→M3a→M3b).**
- **2026-06-20 · tag `multiplayer-m3a`** — **multiplayer M3a: hard per-cell locks (human-collision core)** (3rd stage, split into M3a humans / M3b Claude+scanner; spec `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` §6, plan `docs/superpowers/plans/2026-06-19-multiplayer-m3a-locks-duros.md`). Two humans editing the same month can't clobber each other: opening a cell **claims** it (you become its `editor`); anyone else who opens it sees it **read-only** with the owner's badge + a notice; a contested write is **409**'d and the frontend reverts. Built on the M2 `PresenceRegistry`. **Backend:** M2's `focus` becomes an **atomic claim** — free cell → caller `mode="editor"`, held cell → `"viewer"` (holder keeps editor); at-most-one editor per cell guaranteed by `SessionManager`'s single `RLock`. New `_editor_of`/`lock_holder` (`api/presence.py`) + `CellLockedError`; manager gains a `presence_lock_holder` pass-through + a **non-decorated** `_editor_conflict` helper (called from *inside* each `@_synchronized` write so check+write are atomic, no TOCTOU). The **six single-cell write methods** (`apply_user_override`, `set_note`, `apply_per_file_override`, `apply_worker_count`, `apply_confirmed`, `clear_near_matches`) take a trailing `participant_id: str | None = None` and **raise `CellLockedError` as their first statement** when the cell is held by a *different* participant; apply-ratio uses a separate `check_cell_lock` gate (its loop calls scanner methods that must stay unguarded — safe by **editorship exclusivity**: the operator already claimed the cell). A `main.py` exception handler maps `CellLockedError`→**409** `{detail:"cell_locked",hospital,sigla,lock_holder}`. **Enforcement bites only on a real collision** (different editor holds it) — free cells + `participant_id=None` (legacy/no-presence) are inert, so **no existing test changed** and the single-user path is untouched. **Frontend:** pure `cellLockHolder(presence,h,s,selfId)` selector (editor-other-than-me or null); `api.js` adds `jsonOrThrowStructured` (preserves the 409 body) + threads `participant_id` (`getParticipantId()`) on all 7 writes; the store's 7 write actions, on a 409, toast the holder's name + `refetchSession` (revert optimistic) + clean pending-save bookkeeping, **without** setting the global error. **Read-only UI:** DetailPanel + FileList show a suspect-tone notice ("{name} está editando esta celda" + `PresenceBadge`) and disable every edit control (SegmentedToggle, ratio cluster, OverridePanel, NotePanel, worker-count button, near-match write actions; per-file count + ReorgMenu + "usar conteo por archivos"); CategoryRow marks the editor's row badge + disables its inline count. Gating derives purely from the live `presence` snapshot → **auto-recovers** when the holder leaves (lease TTL). New props: `InlineEditCount.disabled`, `NotePanel.locked`, `SegmentedToggle.disabled`. **Zustand v5 footgun avoided** (raw `(s) => s.presence`, no `?? []` inside selectors). **Deferred to M3b** (separate plan): Claude as a per-cell participant (agent auto-claim) + scanner skipping locked cells (`cell_skipped`) — the `_editor_conflict` seam is the extension point. Per-chunk 2-stage review (all **Sonnet**) + holistic = Ready to ship; reviews caught a stale comment, the `check_cell_lock` over-claimed-atomicity docstring, a per-file 409 `filesTick` re-sync, the ratio-N Cancelar gate, and a `ReorgMenu <summary>` keyboard-bypass A11y gap. Suite **807 passed / 0f** (`-m "not slow"`, incl. eval/tests), vitest **221**, build OK, ruff 0. **Live API lock smoke 6/6** + **live 2-context LAN browser smoke PASSED** (Brave debug, isolated contexts on ABRIL: Daniel claims HRB|odi → Carla sees read-only banner + his badge + all controls disabled + ReorgMenu "Bloqueado por otro participante"; Carla's forced write → live 409 with correct `lock_holder`; Daniel leaves → Carla's panel auto-re-enables; consoles clean). Ran **fully isolated** on a copy DB (`:8010` + a fetch/WS `:8000→:8010` rewrite); real `overseer.db` verified byte-identical (sha256 `e661a8c5…`). No version bump. Memory: `project_multiplayer_m3a_shipped`. Next: **M3b** (Claude + scanner-skip).
- **2026-06-19 · tag `multiplayer-m2`** — **multiplayer M2: presence** (2nd of 3 stages; see the M1 entry + `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` §5–§9, plan `docs/superpowers/plans/2026-06-19-multiplayer-m2-presencia.md`). Two humans on the same month **see each other's identity + which cell each is in, live — no locking, no read-only gating** (that is M3). Backend: an in-memory `PresenceRegistry` (`api/presence.py`, injectable clock, ephemeral — **never persisted**, spec §9) housed in `SessionManager` and reached via `@_synchronized` pass-throughs so it shares the one `RLock`; HTTP up-channel `POST /sessions/{id}/presence/{heartbeat,focus,leave}` (`api/routes/presence.py`) renews a **lease** (TTL 45s; purged on access) and the WS carries a **full `presence` snapshot** down on any roster change (reusing the M1 `_emit` bridge — moved to `ws.py` and shared; `_validate_session_id` extracted from the inline regex at 12 sites). The seam is load-bearing: `focus` only records `focused_cell`, `mode` is a non-load-bearing `"editor"` placeholder, write endpoints take no `participant_id` and never 409, the scanner never skips, Claude isn't wired — **all M3**. Frontend: `lib/identity.js` (participant_id + name + color in localStorage), pure `lib/presence.js` selectors (`participantsInCell` self-excluded / `rosterParticipants` / `initials`), `api.js` presence methods (+ `beaconLeave` via `sendBeacon`), store gains `presence` state + a `presence` WS case + a single idempotent `startPresence()`/`setFocus`/`leavePresence` lifecycle wired into `openMonth` (heartbeat interval + `pagehide` beacon cleaned up alongside `_ws`/`_visHandler`); UI = a Carla-friendly **IdentityDialog** (Spanish-neutro, non-dismissible until named), a header **PresenceRoster** (overlapping avatars), and a per-cell **PresenceBadge** in CategoryRow's reserved G4 slot, with focus driven by a `useEffect` on `[hospital, selected]` in HospitalDetail. **Zustand v5 footgun fix shipped first this session**: the MAYO blank-screen (React #185) from a fresh-literal `?? []` selector in DetailPanel (`077a4d5`, see `reference_zustand_v5_selector_footgun`). Per-chunk 2-stage review (all **Sonnet**) + holistic = Ready to ship. Suite **787 passed / 0f** (`-m "not slow"`, incl. eval/tests; slow corpus unchanged), vitest **205**, build OK, ruff 0. **Live 2-context LAN smoke PASSED** (Brave debug, isolated contexts on ABRIL: roster syncs both ways, B focuses HRB|odi → A sees B's badge on that row, self-excluded, no gating; console clean). No version bump. Memory: `project_multiplayer_m2_shipped`.
- **2026-06-18 · tag `multiplayer-m1`** — **multiplayer M1: live-sync foundation** (first of 3 stages: M1 sync → M2 presence → M3 hard per-cell locks; full design in `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md`). **Broadcast-on-write** over the existing per-session WS: every single-cell write endpoint broadcasts `cell_updated` carrying the **full cell snapshot** (`actor:None`); the frontend **replaces the whole cell** (not the 6-field `cell_done` merge — a remote edit can touch any field). Pase-1 `scan` + reorg op create/delete broadcast `session_refresh` (client re-fetches); pase-2 `scan_ocr`/`scan_file_ocr` emit `cell_updated` per finished cell. All handlers are sync `def`, so broadcasts marshal onto `app.state.loop` via `asyncio.run_coroutine_threadsafe` in `_emit` — **best-effort, no-ops when the loop is absent** (a `TestClient` without `with` never fires the startup that sets it; this was a real 5-test regression the full suite caught after the implementer subagent returned early). Frontend: new `frontend/src/lib/config.js` derives the backend host from `window.location.hostname` (kills the 3 hardcoded `127.0.0.1` sources in `ws.js`/`api.js`/`constants.js`, so a LAN client hits the server, not its own localhost); the store gains `cell_updated`/`session_refresh` cases + a `refetchSession` action; **auto-heal** re-fetches on WS reconnect (new `onReconnect` in `ws.js`, fires only on a real reconnect) and on tab refocus (`visibilitychange` in `openMonth`). Ephemeral collaboration state only — nothing persisted; single-process constraint (never `--workers N`). **No presence, no locks** (M2/M3). Per-chunk 2-stage review (all Sonnet) + holistic = ready to ship; caught the `_emit` regression + the `scan_file_ocr` background-broadcast placement. Suite **782/0f**, vitest **185**, build OK, ruff 0. Browser 2-client LAN smoke is **manual, not yet run** (MCP can't reach Brave). No version bump. Memory: `project_multiplayer_m1_shipped`.
- **2026-06-17 · tag `incremento-J`** — **reorganización vía manifiesto al paso 1**. The operator marks reorg ops — `move_file` (whole file to another cell; reclassify = move to a different sigla), `extract_pages` (page-range X–Y of a compilation → another cell, the "colado" doc), `split_in_place`, `rotate` — that **carry document + worker counts across cells** via an **additive delta** baked into `core/cell_count.py::compute_cell_count` (`_base_count(...) + reorg_doc_delta`, additive for all count_types) and `compute_worker_count` (+ JS mirrors `cellCount.js`/`worker-count.js::cellWorkerCount`), so corrected counts flow to UI/Excel(`resolve_cell_value`)/history with no caller changes. `state["reorg_ops"]` is the single source (ids `op_NNN` via `reorg_seq`; no SQL migration); per-cell `reorg_doc_delta`/`reorg_worker_delta` are recomputed caches via `refresh_reorg_deltas` (the `refresh_all_reliable` pattern, **session-wide**). Lifecycle is **evidence-based**: an op's delta is dropped (`status→applied`) when its `source.file` is gone on a pase-1 re-scan (the move is now physical → counting both would double-count); the manifest `status` is informative only. Pure validation/defaults/manifest helpers live in `api/reorg.py` (`validate_op`/`resolve_op_defaults` [`_set_if_none` because `model_dump` emits explicit None]/`build_manifest`); endpoints `POST`/`DELETE /reorg/ops` + `POST /reorg/export` write a **versioned JSON manifest** to `OVERSEER_OUTPUT_DIR` (atomic; **guarded never to write under the read-only `INFORME_MENSUAL_ROOT`**). Frontend: `ReorganizacionPanel` (REORGANIZACIÓN section in DetailPanel — in/out ops, net delta, session-wide export), a FileList "Reorganizar" menu (whole-file ops), and a viewer **reorg mode** (`WorkerCountViewer mode="reorg"` visual page-range selection via the pure `reorg-range.js`, three load-bearing gates so it never writes worker marks) reachable from the inspect lightbox's "Reorganizar páginas" button. `split_in_place`/`rotate` keep `dest == source`. Deliverable: a static paso-1 contract `docs/handoff/paso1-manifiesto-reorganizacion.md` (the manifest **consumer in paso 1 is a cross-project follow-up**). Per-chunk 2-stage review (all Sonnet) + holistic caught: nested `source.page_range` (extract_pages 422 via endpoint), `rotation_deg:null` 422, unreachable reorg mode, delta-blind `worker-count.js`, missing export guard, dest=source for in-place ops. Suite **775/0f**, vitest **175**, build OK; **live API smoke 20/20 on ABRIL** (`overseer.db` restored by hash `699c28d9…`, MAYO untouched). No version bump. Memory: `project_incremento_J_shipped`.
- **2026-06-17 · tag `incremento-3b`** — **dif_pts = worker-counting + N15 mapping**. dif_pts (already `documents_workers`) now shows the keyboard worker counter (with voice, like charla/chintegral); the DetailPanel module gate is now **count_type-driven** via the pure helper `showsWorkerCounter(countType)` (in `cell-status.js`, vitest-tested — no render infra). The **HPV** dif_pts worker total flows into Excel **N15** (HH-capacitación) as a **raw headcount**, **0 with no fallback** when uncounted (the `=M15*0.5` formula was removed from N15): a new named range `HPV_workers_difpts → N15`, and `_build_worker_values` **always emits** `{hosp}_workers_difpts` for hospitals in `DIFPTS_WORKER_HOSPITALS={"HPV"}` (a loop kept **separate** from the charla/chintegral one — no "never counted → skip" guard). A **pending warning** (`_build_worker_warnings`, has-PDFs + not-terminado) is load-bearing since N15 is 0/formula-less. **Hospital-scoped + extensible**: enabling another obra is a documented 3-step change (set + named range + clear that cell's formula); the other hospitals keep their `col*0.5`. dif_pts's **cell number stays its document count** (history UPSERT stores documents, not the worker total → no 3A-style divergence). Conducted smoke OK (counted 7+5=12 live → N15=12, M15=19, others' formulas intact); suite 722/0f, vitest 134. No version bump. Memory: `project_incremento_3b_shipped`.
- **2026-06-16 · tag `incremento-3a`** — maquinaria = **check-counting** cell + **F1 filter fix**. maquinaria is now `count_type=checks`: its number is the **manual check tally** from the keyboard counter (not documents), via a `checks` branch in `compute_cell_count(cell, count_type, present_files)` → `_sum_marks` (+ JS mirror + cross-lang fixtures); green only on `worker_status=="terminado"` (`compute_settled` checks branch); Excel via `resolve_cell_value(count_type)`. The counter viewer is parametrized ("chequeos", no voice); `DetailPanel` hides the document-counting controls for checks (**NOT dif_pts** — its HH/N15 wiring is 3B). **F1:** the worker/check total filters by **files present in the cell folder** (not `per_file` keys), backend as source of truth (`compute_worker_count(present_files)`) — fixes the viewer-vs-detail/Excel divergence. Conducted smoke OK; suite 709/0f. Memory: `project_incremento_3a_shipped`.
- **2026-06-16 · tag `incremento-2`** — RN + block treatments + ≤pages cap: **`apply-ratio` endpoint** sets each *Pendiente* file to `round(pages/N)` (method `ratio_n`, chip **RN**, pending-only clobber-guard; `finalize` preserves `cell.method`), **"Aplicar R1" = N=1**; honest green dot via a backend **`all_reliable`** signal (`compute_settled`, 1B-legacy fallback for un-migrated MAYO cells, closes the per-file-override gap); **`≤ pages` cap** on cell + per-file overrides for `documents`/`documents_workers` (checks exempt, only when pages>0). Pages are **lazy** (`cell_page_counts`, not persisted — deferred to Incr J). Memory: `project_incremento_2_shipped`.
- **2026-06-15 · tag `incremento-1b`** — Frontend honesto: green dot by **per-file provenance** (`cell-status.js`, OCR no longer lights green alone → amber), **`Por archivos · Manual` toggle** (reversible cell↔files override, Variant C) + inline amber hint, override validation (negatives/0). Confidence badge removed. No backend change. Memory: `project_incremento_1b_shipped`.
- **2026-06-11 · tag `incremento-1a`** — Backend counting foundation: full-cell OCR now **merges per-file + writes incrementally** (cancel keeps partial; `finalize_cell_ocr` = metadata only), **`count_type` per sigla** (documents/workers/checks — foundation for 1B/Incr 3), complete **`per_file_method` provenance + RLock**. Multi-worker race removed (worker enqueues `cell_meta` after `pdf_done` on one queue → FIFO drain). Merge guard = OCR methods only (`filename_glob`/A7/none stay progress-only — pase-1 owns that truth, clobber-guard). `cell_done` contract unchanged → no frontend change. Memory: `project_incremento_1a_shipped`.
- **2026-06-06** — `core/cell_count.py` = single source of truth for counts (UI/Excel/history converge); Excel dynamic month title + 0 in uncounted cells, coordinate-safe. Memory: `project_excel_count_consolidation`.
- **2026-06-05** — First live MAYO: bulk filename re-scan clobbered OCR'd cells; fixed with the `_cell_has_work` guard in `apply_filename_result` (verified live 2026-06-06). Memory: `project_rescan_clobber_incident`.
- **2026-06-04** — Refinement batches: filelist polish (alignment, chips → red dot), Excel `#REF!` fix + `no-store`, CPHS visible-only rename, V4 double-pass OCR preprocessing. Memory: `project_refinements_2026_06_04`.
- **2026-06-03 · tags `conteo-confiable-{mvp,rev-1,rev-2}`** — Per-file count as source of truth: honest "ready" model, `FIXED_PAGE_SIGLAS`, `per_file_method` chips, per-file OCR from the viewer, per-sigla cards (p25–p75 corpus range). Memory: `project_conteo_confiable_shipped`, `project_conteo_confiable_revision_planned`.
- **2026-06-02 · tag `worker-viewer-ux-mvp`** — Worker-count viewer UX: thumbnail column (lazy + WeakMap), fit-to-window + manual zoom, persistent shortcut legend, partial-count→0 fix (`compute_worker_count`).
- **2026-05-23 · tag `ocr-per-sigla-mvp`** — Per-sigla OCR flavors (22 verbatim) + Fase A/B calibration; audited 2026-06-01 (7 findings fixed). Memory: `project_ocr_per_sigla_shipped`.
- **2026-05-17 · tag `conteo-trabajadores-mvp`** — Feature 1: assisted worker-signer count; pdf.js viewer, keyboard + voice (es-CL via Web Speech). Memory: `project_feature1_shipped`.
- **2026-05-15 · tag `fase-5-mvp`** — History drill-in (`HistoryDrawer`), page-level cancel (<3 s), OCR auto-retry. Memory: `project_fase5_shipped`.
- **2026-05-14 · tag `fase-4-mvp`** — HLL manual entry, per-file docs in FileList, multi-month trend (SparkGrid). Memory: `project_fase4_shipped`.
- **2026-05-13 · tag `fase-3-polish`** — Design system (`po-*` tokens, 8 primitives), inline-edit cells, autosave indicator, sonner toasts. Memory: `project_fase3_shipped`.
- **2026-05-12 · tag `fase-2-mvp`** — Pass 1 (`filename_glob`, ~4 s on ABRIL) + pass 2 (OCR per cell, opt-in) + manual override + PDF lightbox; cell-state cascade (`filename_count`/`ocr_count`/`user_override`) resolved by the Excel writer.
- **2026-05-11 · tag `fase-1-mvp`** — Folder-driven overhaul: open `A:\informe mensual\<MES>\` → count 4 hospitals × 18 categories with filename-glob → write `RESUMEN_<YYYY>-<MM>.xlsx` from `data/templates/RESUMEN_template_v1.xlsx`.

**Voice (Feature 1):** Chrome + cloud Web Speech works (validated 2026-05-18); Brave impossible (strips Google's voice key, no SODA); on-device discarded. Keyboard counting works everywhere. Detail in `project_feature1_shipped`.

**Reverted/parked:** VLM integration (reverted 2026-03-30 — see postmortem in Links); Feature 2 boundary badges (parked — see `project_feature2_boundary_badges`).
