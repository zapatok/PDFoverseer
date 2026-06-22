# B1 — `scan_file_ocr` respects the M3 per-cell lock — Design Spec

**Date:** 2026-06-22
**Branch:** `po_overhaul`
**Status:** design → review → plan → SDD → smoke

## Goal

Close **B1** (the last M3 gap): the single-file **"Escanear con OCR"** action
(`scan_file_ocr`, the `PDFLightbox.jsx:298-310` button, icon `ScanSearch`) must not
start an OCR scan on a cell another participant is editing, so it can't clobber a
live edit. This is a **behavior change** (correctness fix), not a refactor — done
before the `po_overhaul → master` merge.

## Context

The M3a/M3b track gave every other write path a per-cell lock: the 6 single-cell
`patch_*` routes raise `CellLockedError`→409 on a contested write; `apply_ratio`
uses `check_cell_lock`; the **batch** OCR scanner (`scan_cells_ocr`) claims each
cell as the Claude agent and skips human-held cells. **`scan_file_ocr` was never
wired** — it takes no `participant_id`, never checks the lock, and the frontend
"Escanear con OCR" button is disabled only on `noOcr || !currentFile`
(`PDFLightbox.jsx:302`), not on read-only. So both layers miss it.

Bites only in real concurrent use (two humans, same cell, one hits "Escanear con
OCR"). Inert for single-user.

**Editorship-exclusivity holds here (verified):** the lightbox is reachable only from
`FileList`, which renders only the *selected* cell (`HospitalDetail.jsx:103`);
selecting a cell runs the focus effect (`HospitalDetail.jsx:23-26`) →
`api.presenceFocus`, and `focus` is an atomic claim (free → `editor`, held → `viewer`;
`presence.py:130-143`). So whoever can press the button is the cell's editor when it
was free, and a viewer (button will be disabled) otherwise — identical to
`apply_ratio`'s precondition.

## Design

Mirror the **`apply_ratio` human gate** exactly — `scan_file_ocr` is a human action
from the viewer, and the operator already **claimed** the cell by opening it
(`focus`), so editorship-exclusivity holds (a second participant who opens the same
cell becomes a *viewer*, never a competing editor). No agent path (it is not Claude).

### Backend — `api/routes/sessions/scan.py`

- `scan_file_ocr` gains an optional body carrying `participant_id`, following the
  `clear_near_matches` pattern:
  ```python
  class ScanFileOcrRequest(BaseModel):
      participant_id: str | None = None

  @router.post(".../files/{filename}/scan-ocr")
  def scan_file_ocr(request, session_id, hospital, sigla, filename,
                    body: ScanFileOcrRequest | None = Body(None),
                    mgr=Depends(get_manager)) -> dict:
      _validate_session_id(session_id)
      participant_id = body.participant_id if body else None
      ... # resolve state + folder + file-exists (unchanged)
      mgr.check_cell_lock(session_id, hospital, sigla, participant_id)  # → CellLockedError → 409
      ... # submit _run to _DISPATCH_POOL (unchanged)
  ```
- The `check_cell_lock` call goes **after** the session/folder/file-exists 404
  checks and **before** the `_DISPATCH_POOL.submit` — it gates *starting* the scan.
- `participant_id=None` (single-user / legacy) → `check_cell_lock` is inert (no
  enforcement), so existing behavior + all current tests are unchanged.
- **Async write left as-is (decision A1):** the background `apply_per_file_ocr_result`
  (on `file_scan_done`) stays unguarded. The request-time check covers the realistic
  case; the residual TOCTOU (triggerer holds the cell, leaves mid-OCR, another claims
  before the write lands) is the same risk class `check_cell_lock` already accepts for
  `apply_ratio` (documented in its docstring). Not closing it keeps the fix consistent
  and avoids a new "result discarded" event + UX.
- 409 body is the existing `CellLockedError` shape (`main.py` handler):
  `{detail: "cell_locked", hospital, sigla, lock_holder}`.

### Frontend — `lib/api.js`, `store/session.js`, `components/PDFLightbox.jsx`

- **`api.scanFileOcr`** (`api.js:146-150`) today does `.then(jsonOrThrow)` — which
  throws a plain `Error` with **no** `.status`/`.body`, so a 409 wouldn't carry the
  holder. Change it to take a `participantId` arg, POST `body:
  JSON.stringify({ participant_id: participantId ?? null })`, and swap to
  **`jsonOrThrowStructured`** (`api.js:12-24`) so the 409 carries `.status`/`.body`
  — byte-for-byte the `applyRatio` pattern (`api.js:154-159`).
- **`store.scanFileOcr`** (`session.js:156-162`) today has **no 409 branch** (only
  `set({ error })`). Rewrite it to read `const participantId = getParticipantId()`
  (already imported, `session.js:5`), pass it through, and add a
  `error.status === 409 → toast(error.body?.lock_holder?.name …) + return` branch
  mirroring `clearNearMatches` (`session.js:186-193`) — do **not** set the global
  error on 409. (No optimistic state to revert — the OCR simply never starts.)
- **`PDFLightbox`** disables the "Escanear con OCR" button when the cell is read-only.
  It currently subscribes to neither `presence` nor imports the lock helpers, so add:
  (a) a `presence` subscription with a **raw** selector `useSessionStore((s) =>
  s.presence)` — NOT a fresh `?? []` literal inside the selector (Zustand v5 footgun,
  React #185); (b) imports of `getParticipantId` + `cellLockHolder`; (c)
  `const isLocked = !!cellLockHolder(presence, lightbox.hospital, lightbox.sigla,
  getParticipantId())`. Mirrors `DetailPanel.jsx:267` / `FileList.jsx:242`. The
  button's `disabled` becomes `noOcr || !currentFile || isLocked`, with the same
  "Bloqueado por otro participante" affordance used elsewhere in M3a.

### Invariants preserved

- Single-user: `participant_id` is `None` end-to-end → no enforcement, byte-identical
  behavior. The 6 `patch_*` routes, `apply_ratio`, and the M3b batch scanner are
  untouched. No counting-logic change.

## Testing

- **Backend** (`tests/unit/api/`): with a presence registry where another participant
  holds `HRB|odi`: `scan_file_ocr` with a *different* `participant_id` → **409** with
  `lock_holder`; with the **holder's** id → 200 `{accepted}`; with a **free** cell →
  200; with `participant_id` omitted → 200 (legacy). Assert the OCR job is **not**
  submitted on the 409 path (no `file_scan_*` broadcast).
- **Frontend** (vitest): `cellLockHolder`-driven `disabled` for the lightbox button
  (pure selector test); store 409 handling toasts + no-ops.
- **Live**: 2-context browser smoke — Carla holds `HRB|odi`; Daniel opens a file in
  that cell → "Escanear con OCR" disabled; a forced API call → 409 with correct
  `lock_holder`; Daniel's own held cell → OCR runs normally. Run isolated (copy DB),
  verify real `overseer.db` byte-identical after.

## Out of scope

- The async write-time re-check (decision A1 — accepted residual, consistent with
  `apply_ratio`).
- Any other route (already gated by M3a/M3b).
- The batch OCR scanner (already handles locks via the agent-claim path).
