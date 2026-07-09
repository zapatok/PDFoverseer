# Conteo-session fixes — API footguns + irl cover_code — Design

**Date:** 2026-07-09
**Status:** DRAFT for review
**Author:** Claude (Fable 5) + Daniel
**Scope:** Backend + small frontend confirmation UI. No counting-algorithm changes,
no persisted-count changes, no Excel changes.

---

## Origin

On 2026-07-08/09 Claude worked the JUNIO session as a real participant (M3b),
counting documents by vision/logic across HRB/HLU/HLL. Working the app as a user
surfaced four defects. This spec fixes **only the app bugs/gaps** — the counting
*decisions* that session also raised (dif_pts unit criterion, HRB art recount,
colado extractions) are operational, stay with Daniel, and are explicitly out of
scope (§6).

All four items were decided with Daniel on 2026-07-09 (AskUserQuestion round):
cap → explicit confirmation; `extra="forbid"` → all write models.

---

## 1 · `irl` cover_code is wrong (`patterns.py`)

### Problem

`core/scanners/patterns.py` (irl entry, ~line 727):

```python
"irl": {
    "scan_strategy": "pagination",
    "cover_code": "F-CRS-ODI-01",   # ← wrong: this is odi's form code
    "cover_flavors": _IRL_ANCHORS,
},
```

The real IRL cover header reads **`F-CRS-IRL-01`** (verified by eye against the
JUNIO corpus: HRB/HLU/HLL irl packets all carry `F-CRS-IRL-01` on their cover).
With the wrong `cover_code`, a pase-2 pagination scan of an irl cell matches no
covers → undercounts to ~0 with LOW confidence. Today's persisted irl counts are
unaffected (they came from filename/pase-1 and manual work), but the bug bites
the next time anyone runs "Revisar OCR" on an irl cell.

### Fix

- Change the value to `"F-CRS-IRL-01"`. One line — **plus the three places
  that currently document the buggy value**:
  - `tests/unit/scanners/test_patterns_registry.py:116` —
    `test_irl_pagination_has_cover_code` asserts the **wrong** value
    (`== "F-CRS-ODI-01"`); flip the assertion to `"F-CRS-IRL-01"` and fix its
    docstring. (Without this the suite goes red on the fix.)
  - `core/scanners/patterns.py` `SiglaPattern` TypedDict docstring (~line
    48-50) uses `"F-CRS-ODI-01"` as its worked IRL example — update it.
  - `tests/unit/scanners/test_pattern_irl_odi.py` `test_irl_count_ocr_smoke`
    docstring (lines 24-32) explains the design with the wrong code — update
    (doc-only; the test skips without its gitignored fixture).
- Bump `SCANNER_PATTERNS_VERSION` (core/utils.py) `v6-token-aliases` →
  `v7-irl-cover` with a one-line comment, following the existing changelog
  convention. The constant is informational (no runtime consumer) — the bump
  documents the pattern change for drift tooling.
- Implementation check (plan task): with the corpus present, verify IRL
  continuation/appendix pages do **not** themselves carry the `F-CRS-IRL-01`
  substring in the corner band (cover_code is a substring match) — the same
  over-match class the V2 anti-colados survey found for the `F-CRS-LCH`
  family. The 2026-07-08 visual pass saw the code only on covers, but confirm
  on the 54-page HRB packet before shipping.

### Output safety

No persisted state is read or written differently. Pase-1 (filename) is
untouched. The change only affects a *future* pase-2 run on irl.

---

## 2 · Write endpoints silently ignore unknown JSON keys

### Problem

Every write-request Pydantic model uses the default `extra="ignore"`. Sending
`{"note": "...", "note_status": "..."}` to `PATCH …/note` (whose model fields
are `text`/`status`) returns **200** and — because `text` defaults to `None` —
**clears the stored note**. This destroyed a real note during the counting
session. The same silent-ignore applies to every other write model.

### Fix

Add `model_config = ConfigDict(extra="forbid")` to **all** request models on the
session-write surface, so an unknown key → **422** with an explicit Pydantic
error:

| File | Models |
|---|---|
| `api/routes/sessions/writes.py` | `PerFileOverrideRequest`, `ClearNearMatchBody`, `WorkerCountPatch`, `ReconcileWorkerMarksBody`, `NotePatch`, `ConfirmRequest`, `DismissColadoBody` |
| `api/routes/sessions/writes.py` — `patch_override` | currently takes a **raw `Body(...)` dict** — introduce `OverridePatch(BaseModel)` with `value: Any = None`, `manual: bool = False`, `participant_id: str | None = None`, `extra="forbid"` (+ `allow_over_pages`, §3) |
| `api/routes/sessions/scan.py` | `ApplyRatioRequest`, `ScanFileOcrRequest` |
| `api/routes/sessions/scan.py` — `scan` + `scan_ocr` | both currently take **raw `Body(...)` dicts** — introduce thin models (`ScanRequest`, `ScanOcrRequest`) with `Any`-typed fields + `extra="forbid"`, keeping today's manual validation (same trick as `OverridePatch` below) so existing 400 semantics don't shift to 422 |
| `api/routes/sessions/reorg.py` | `ReorgOpCreate`, `ReorgSource`, `ReorgDest` |
| `api/routes/presence.py` | `HeartbeatBody`, `FocusBody`, `LeaveBody` |

**`patch_override` behavior-preservation constraint:** the endpoint hand-rolls
`value` validation today (non-int → **400**, out-of-range → **400**). To keep
those status codes stable for existing clients/tests, `OverridePatch.value`
stays `Any` and the endpoint keeps its manual `isinstance`/range checks — the
model only adds the unknown-key guard (422) and typed `manual`/`participant_id`.
No other endpoint changes semantics: correct requests behave exactly as before.

### Tests

- One test per endpoint: POST/PATCH with a bogus key (e.g. `{"count": 1, "xyz": 1}`)
  → 422, and state unchanged.
- Regression pin for the incident: `PATCH …/note` with `{"note": "x", "note_status": "por_resolver"}`
  → 422 **and the stored note is not cleared**.
- Existing suite must stay green — it proves correct payloads still pass.

### Frontend audit

`frontend/src/lib/api.js` is the only in-repo client. **Already verified**
(2026-07-09 spec review, code-checked): `patchOverride`,
`patchPerFileOverride`, `patchWorkerCount`, `patchNote`, `clearNearMatches`,
`applyRatio`, `scanFileOcr`, `createReorgOp` (including every `opDraft.source`
producer) and the three presence calls all send exactly the fields their
target models declare — `extra="forbid"` is safe for every existing in-repo
caller. The plan should still grep `tests/` for any test that intentionally
posts an extra key expecting 200 (spot-checks found none). No frontend code
change expected from this item.

---

## 3 · `≤ pages` cap cannot express 2-docs-per-page (explicit confirmation)

### Problem

Incremento 2's cap rejects any documents override greater than the file/cell
page count (422 `{"error": "count_exceeds_pages", "max": N}`). The cap is a
good typo guard, but the corpus has legitimate violations: HLU insgral
"líneas de aire comprimido" scans **two forms per sheet** (12 docs in 6 pages).
The only workaround is a cell-level `user_override` + explanatory note, which
degrades per-file provenance.

Decision (Daniel, 2026-07-09): keep the cap as the default, add an **explicit
confirmation** escape hatch.

### Fix — backend

- `PerFileOverrideRequest` and the new `OverridePatch` gain
  `allow_over_pages: bool = False`.
- At both 422 sites (`writes.py` cell ~line 67, per-file ~line 120): if
  `allow_over_pages` is true, skip the cap and accept the value. Everything
  else (negatives blocked, `_MAX_REASONABLE_COUNT`, checks-cells exempt,
  `total_pages == 0` = unknown → never blocks) is unchanged.
- The stored override is just the number — `allow_over_pages` is a write-time
  gate, not persisted state. Green-dot / origin semantics unchanged (an
  accepted override is `Manual`, as today).

### Fix — frontend

**Reality check first:** the cap is enforced **client-side** today — the
backend 422 is unreachable from the UI. `frontend/src/lib/override-input.js::
parseOverrideInput` returns `valid: false` when `n > maxPages` and
`OverridePanel` only flushes valid values; `InlineEditCount`'s commit gate
(`v <= max`) blocks the per-file path the same way. There is also no existing
"422-revert" logic to reuse (`count_exceeds_pages` appears nowhere in
`frontend/src`; the store's `saveOverride` catch only special-cases 409). So
the confirmation is **client-triggered by the same client-side gates**, and
the backend flag remains the server-side authority for headless clients:

- `frontend/src/lib/override-input.js`: over-cap stops being a plain
  `valid: false` — `parseOverrideInput` distinguishes a new result state
  `over_cap` (n parses, exceeds `maxPages`) from genuinely invalid input.
- `OverridePanel.jsx` (cell) and `InlineEditCount.jsx` (per-file): on
  `over_cap`, instead of refusing silently, show an inline confirmation
  (po-* tokens, no browser `confirm()`):
  - Microcopy: **“El archivo tiene {max} páginas. ¿Confirmas {N}
    documentos?”** (cell variant: “La celda tiene {max} páginas…”), buttons
    **“Confirmar”** / **“Cancelar”**.
  - Confirmar → save with the flag. Cancelar → keep the previous value
    (today's refuse behavior).
- Plumbing (correct symbol names): the **store actions**
  `saveOverride`/`savePerFileOverride` (`frontend/src/store/session.js`)
  accept an `allowOverPages` option and pass it to the **api functions**
  `patchOverride`/`patchPerFileOverride` (`frontend/src/lib/api.js`), which
  include `allow_over_pages: true` in the body.
- If the server 422 ever surfaces anyway (race: pages changed between render
  and save), the store's existing generic error toast handles it — no new
  422 branch required.

### Tests

- Backend: over-pages without flag → 422 (unchanged); with flag → 200 and value
  persisted; checks sigla still uncapped; negatives still rejected even with
  the flag.
- Frontend (vitest): `parseOverrideInput` returns `over_cap` (not plain
  invalid) for n > maxPages; the confirm→save-with-flag flow at the component/
  store level; Cancelar keeps the previous value.

---

## 4 · Presence minor gaps

### 4a · No HTTP read of the presence snapshot

The snapshot only travels over the WS `presence` event. Headless clients (e.g.
Claude working as participant) and debugging need polling reads.

- Add `GET /api/sessions/{session_id}/presence` (in `api/routes/presence.py`)
  returning exactly the WS payload shape: `{"participants": [...]}` from
  `PresenceRegistry.snapshot()` via the manager pass-through. Session-id
  validated like the POST routes. No auth change (same trust model as the rest
  of the LAN API).

### 4b · Agent heartbeat creates a `kind="human"` record

`PresenceRegistry.heartbeat()` hardcodes `kind="human"` when creating a record;
only `agent_focus()` (reached from a *write*) creates `kind="agent"`. Result: a
heartbeating agent shows a human avatar (initials, no Bot icon) until its first
write — observed live this session.

- Fix in `heartbeat()`: if `participant_id == AGENT_PARTICIPANT_ID`, create the
  record with the agent identity (`AGENT_NAME`, `AGENT_COLOR`, `AGENT_KIND`),
  ignoring the caller-supplied name/color (single source for agent identity,
  as `agent_focus` already does). Existing records: also normalize `kind` on
  heartbeat so a human-created stale record heals.
- Tests: heartbeat as `claude` → snapshot shows `kind="agent"` + agent
  name/color; human heartbeat unchanged; heartbeat-then-write keeps one record.

---

## 5 · Acceptance criteria

1. `PATTERNS["irl"]["cover_code"] == "F-CRS-IRL-01"`; `SCANNER_PATTERNS_VERSION == "v7-irl-cover"`;
   `test_patterns_registry` asserts the corrected value.
2. Every body-taking endpoint in `writes.py`, `scan.py`, `reorg.py` and
   `presence.py` rejects an unknown JSON key with 422 (raw-dict bodies
   converted to forbid-extra models); the note-wipe repro now 422s and
   preserves the note.
3. `PATCH …/override` (cell), `scan` and `scan_ocr` keep their current 400
   semantics for bad values — the new models guard keys only.
4. Over-pages override: backend blocks without flag, accepts with
   `allow_over_pages`; the client-side gates (`parseOverrideInput`,
   `InlineEditCount`) surface the confirmation with the microcopy above and
   send the flag on Confirmar.
5. `GET /sessions/{id}/presence` returns the live snapshot; agent heartbeat
   yields `kind="agent"`.
6. Gates: full fast suite green (`pytest -m "not slow"`), vitest green,
   `ruff check .` = 0, frontend build OK. No rescan-diff expected (tooling
   `dump_counts` before/after on the real DB shows zero row changes).

## 6 · Out of scope (explicit)

- RN redesign / template-classifier (Viterbi) counting method — separate
  conversation.
- The JUNIO counting decisions left in `por_resolver` notes (HRB dif_pts
  criterion, HRB art recount, colado extractions) — Daniel handles manually.
- Corpus scan-quality findings (truncated scans) — paso-1/Carla territory.
- Any change to `compute_cell_count` / Excel / history.
