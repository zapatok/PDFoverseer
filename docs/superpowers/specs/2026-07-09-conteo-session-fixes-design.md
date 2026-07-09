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

- Change the value to `"F-CRS-IRL-01"`. One line.
- Bump `SCANNER_PATTERNS_VERSION` (core/utils.py) `v6-token-aliases` →
  `v7-irl-cover` with a one-line comment, following the existing changelog
  convention. The constant is informational (no runtime consumer) — the bump
  documents the pattern change for drift tooling.
- Test: a unit test in the existing per-sigla pattern-test idiom asserting
  `PATTERNS["irl"]["cover_code"] == "F-CRS-IRL-01"` (pin the regression).

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

`frontend/src/lib/api.js` is the only in-repo client. Audit each write method's
payload keys against its model during implementation (expected: already exact —
the bug was hit by an external client, Claude's script). No frontend code
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

- `api.js` `saveOverride`/`savePerFileOverride` accept an optional
  `allowOverPages` and include the flag in the body.
- In the two editing surfaces (per-file count in `FileList`, cell override in
  `OverridePanel`): on a 422 with `error === "count_exceeds_pages"`, show an
  inline confirmation (po-* tokens, no browser `confirm()`):
  - Microcopy: **“El archivo tiene {max} páginas. ¿Confirmas {N} documentos?”**
    (cell variant: “La celda tiene {max} páginas…”), buttons **“Confirmar”** /
    **“Cancelar”**.
  - Confirmar → resend with `allow_over_pages: true`. Cancelar → revert to the
    previous value (the existing 422-revert path).
- The store's structured-422 handling (`jsonOrThrowStructured`) already
  preserves the error body; the confirmation hooks into that path.

### Tests

- Backend: over-pages without flag → 422 (unchanged); with flag → 200 and value
  persisted; checks sigla still uncapped; negatives still rejected even with
  the flag.
- Frontend (vitest): the 422→confirm→resend flow on the store action level.

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

1. `PATTERNS["irl"]["cover_code"] == "F-CRS-IRL-01"`; `SCANNER_PATTERNS_VERSION == "v7-irl-cover"`.
2. Any session-write/presence/scan/reorg request with an unknown JSON key → 422;
   the note-wipe repro now 422s and preserves the note.
3. `PATCH …/override` (cell) keeps 400 semantics for bad `value` types/ranges.
4. Over-pages override: blocked without flag, accepted with `allow_over_pages`,
   confirmation UI wired in FileList + OverridePanel with the microcopy above.
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
