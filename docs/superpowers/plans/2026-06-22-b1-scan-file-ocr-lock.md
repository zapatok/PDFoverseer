# B1 — scan_file_ocr respects the M3 lock — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The single-file "Escanear con OCR" action can't start an OCR scan on a cell
another participant is editing (closes B1, the last M3 gap).

**Architecture:** Mirror `apply_ratio`'s human gate — request-time
`check_cell_lock(session_id, hospital, sigla, participant_id)` in `scan_file_ocr`
(→ `CellLockedError` → existing 409 handler), plus frontend: thread
`participant_id`, disable the button when read-only, handle the 409. No async
write-time re-check (decision A1, consistent with `apply_ratio`).

**Tech Stack:** FastAPI + pydantic (backend), React + Zustand v5 + vitest (frontend).
Spec: `docs/superpowers/specs/2026-06-22-b1-scan-file-ocr-lock-design.md`.

**Constraint:** behavior-preserving for single-user (`participant_id=None` → the gate
is inert). No counting-logic change.

---

## File Structure

- Modify: `api/routes/sessions/scan.py` — `scan_file_ocr` gains a `ScanFileOcrRequest`
  body + the `check_cell_lock` gate.
- Test: `tests/unit/api/test_lock_enforcement.py` — add the endpoint 409 test.
- Modify: `frontend/src/lib/api.js` — `scanFileOcr` takes `participantId`, posts the
  body, uses `jsonOrThrowStructured`.
- Modify: `frontend/src/store/session.js` — `scanFileOcr` threads `getParticipantId()`
  + adds the 409 branch.
- Modify: `frontend/src/components/PDFLightbox.jsx` — disable the button when locked.

---

## Chunk 1: Backend lock gate

### Task 1: gate `scan_file_ocr` with `check_cell_lock`

**Files:**
- Modify: `api/routes/sessions/scan.py` (the `scan_file_ocr` route + a new request model)
- Test: `tests/unit/api/test_lock_enforcement.py`

- [ ] **Step 1: Write the failing endpoint tests.** Append to
  `tests/unit/api/test_lock_enforcement.py`. **CRITICAL:** `scan_file_ocr` checks the
  file exists (404) *before* the lock check, so the test MUST set up a real month_root
  + a real 1-page `a.pdf` under `HRB/3.-ODI Visitas/` — otherwise the request 404s and
  never reaches the gate. Copy the setup verbatim from
  `tests/test_cell_files_endpoint.py::test_scan_file_ocr_endpoint_accept_and_404`
  (`:347-367`). Add a local `_make_pdf` helper (copy the 6-line `fitz` version from
  `tests/test_cell_files_endpoint.py:12-24`) so the test module stays self-contained.

  ```python
  def _make_pdf(path, pages: int) -> None:
      import fitz
      doc = fitz.open()
      for _ in range(pages):
          doc.new_page()
      doc.save(str(path))
      doc.close()


  def test_scan_file_ocr_endpoint_409_when_locked_by_another(tmp_path, monkeypatch):
      monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
      monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "b1.db"))
      app = create_app()
      with TestClient(app) as c:
          from pathlib import Path

          mgr = app.state.manager
          sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
          folder = tmp_path / "HRB" / "3.-ODI Visitas"
          folder.mkdir(parents=True)
          _make_pdf(folder / "a.pdf", 1)

          # Carla (p2) holds HRB|odi
          c.post(f"/api/sessions/{sid}/presence/heartbeat",
                 json={"participant_id": "p2", "name": "Carla", "color": "#b"})
          c.post(f"/api/sessions/{sid}/presence/focus",
                 json={"participant_id": "p2", "cell": "HRB|odi"})

          # Daniel (p1) tries to OCR a file in Carla's cell → 409
          r = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr",
                     json={"participant_id": "p1"})
          assert r.status_code == 409, r.text
          assert r.json()["lock_holder"]["name"] == "Carla"


  def test_scan_file_ocr_endpoint_allows_editor_and_legacy(tmp_path, monkeypatch):
      monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
      monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "b1b.db"))
      app = create_app()
      with TestClient(app) as c:
          from pathlib import Path

          mgr = app.state.manager
          sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
          folder = tmp_path / "HRB" / "3.-ODI Visitas"
          folder.mkdir(parents=True)
          _make_pdf(folder / "a.pdf", 1)

          c.post(f"/api/sessions/{sid}/presence/heartbeat",
                 json={"participant_id": "p1", "name": "Daniel", "color": "#a"})
          c.post(f"/api/sessions/{sid}/presence/focus",
                 json={"participant_id": "p1", "cell": "HRB|odi"})

          # editor (p1) → 200
          ed = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr",
                      json={"participant_id": "p1"})
          assert ed.status_code == 200, ed.text
          # legacy no-body → 200 (unenforced)
          legacy = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
          assert legacy.status_code == 200, legacy.text
  ```
  (1-page `a.pdf` → the background OCR takes the A7 path, no real OCR; the route returns
  200 immediately anyway — these assert the **gate**, not the scan result.)

- [ ] **Step 2: Run — expect FAIL.**
  Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/api/test_lock_enforcement.py -q -k scan_file_ocr`
  Expected: the 409 test FAILS (currently returns 200 — no gate yet).

- [ ] **Step 3: Implement the gate** in `api/routes/sessions/scan.py`.
  Add the request model next to `ApplyRatioRequest`:
  ```python
  class ScanFileOcrRequest(BaseModel):
      participant_id: str | None = None
  ```
  Change the `scan_file_ocr` signature to accept the optional body and add the gate
  after the file-exists 404, before `_DISPATCH_POOL.submit`:
  ```python
  def scan_file_ocr(
      request: Request,
      session_id: str,
      hospital: str,
      sigla: str,
      filename: str,
      body: ScanFileOcrRequest | None = Body(None),
      mgr: SessionManager = Depends(get_manager),
  ) -> dict:
      _validate_session_id(session_id)
      participant_id = body.participant_id if body else None
      try:
          state = mgr.get_session_state(session_id)
      except KeyError as exc:
          raise HTTPException(404, f"Session not found: {session_id}") from exc
      folder = _find_category_folder(Path(state.get("month_root", "")) / hospital, sigla)
      if not folder.exists() or filename not in {p.name for p in folder.rglob("*.pdf")}:
          raise HTTPException(404, f"File not found in cell: {filename}")
      # B1: gate starting the scan on the M3 per-cell lock (apply_ratio's human gate;
      # editorship-exclusivity holds — the operator focus-claimed the cell by selecting
      # it). check_cell_lock raises CellLockedError -> 409 via the main.py handler.
      mgr.check_cell_lock(session_id, hospital, sigla, participant_id)
      app = request.app
      ...  # rest unchanged
  ```
  `Body`, `BaseModel`, `check_cell_lock` need no new imports (`Body`/`BaseModel`
  already imported for `ApplyRatioRequest`; `check_cell_lock` is a `mgr` method;
  `CellLockedError` is raised inside it). The 409 handler already exists (`main.py`).

- [ ] **Step 4: Run — expect PASS.**
  Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/api/test_lock_enforcement.py tests/test_cell_files_endpoint.py -q`
  Expected: new gate tests PASS; the existing `test_scan_file_ocr_endpoint_accept_and_404`
  (no-body POST) still PASS (legacy path unenforced).

- [ ] **Step 5: ruff + commit.**
  ```bash
  .venv-cuda/Scripts/python.exe -m ruff check api/routes/sessions/scan.py tests/unit/api/test_lock_enforcement.py
  git add api/routes/sessions/scan.py tests/unit/api/test_lock_enforcement.py
  git commit -m "fix(api): gate scan_file_ocr on the M3 per-cell lock (B1)"
  ```

---

## Chunk 2: Frontend — thread participant_id + disable-on-locked

### Task 2: `api.scanFileOcr` + `store.scanFileOcr`

**Files:**
- Modify: `frontend/src/lib/api.js` (`scanFileOcr`, ~146-150)
- Modify: `frontend/src/store/session.js` (`scanFileOcr`, ~156-162)

- [ ] **Step 1: api.js** — change `scanFileOcr` to mirror `applyRatio` (`api.js:154-159`):
  ```js
  scanFileOcr: (sessionId, hospital, sigla, filename, participantId) =>
    fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/scan-ocr`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ participant_id: participantId ?? null }),
      },
    ).then(jsonOrThrowStructured),
  ```

- [ ] **Step 2: store/session.js** — rewrite `scanFileOcr` to thread the id + handle 409,
  mirroring `clearNearMatches` (`session.js:186-193`):
  ```js
  scanFileOcr: async (sessionId, hospital, sigla, filename) => {
    try {
      await api.scanFileOcr(sessionId, hospital, sigla, filename, getParticipantId());
    } catch (error) {
      if (error.status === 409) {
        const who = error.body?.lock_holder?.name ?? "otro participante";
        toast.error(`${who} está editando esta celda`);
        return;
      }
      set({ error: String(error) });
    }
  },
  ```
  (`getParticipantId` is already imported at `session.js:5`; `toast` is already used
  by the other 409 branches — match their import + message style exactly.)

- [ ] **Step 3: Verify the store 409 path (vitest, if a store test harness exists).**
  Run: `cd frontend && npx vitest run src/store` (or the repo's store test path).
  If there is no store-action test harness, rely on the browser smoke (Task 4) for the
  409 path and note it. Do NOT invent a heavy harness for this.

- [ ] **Step 4: Commit.**
  ```bash
  git add frontend/src/lib/api.js frontend/src/store/session.js
  git commit -m "fix(web): thread participant_id + handle 409 in scanFileOcr (B1)"
  ```

### Task 3: PDFLightbox disable-on-locked

**Files:**
- Modify: `frontend/src/components/PDFLightbox.jsx` (button ~298-310)

- [ ] **Step 1: Add the lock derivation.** Mirror `DetailPanel.jsx` / `FileList.jsx`.
  Add the two imports (confirm exact paths from `DetailPanel.jsx` — expected
  `../lib/presence` + `../lib/identity` relative to `src/components/`):
  ```js
  import { cellLockHolder } from "../lib/presence";
  import { getParticipantId } from "../lib/identity";
  ```
  Subscribe to presence with a **raw** selector (Zustand v5 footgun — no fresh `?? []`
  literal inside the selector; the store already initializes `presence: []`), and
  derive `isLocked` where `lightbox.hospital`/`lightbox.sigla` are in scope:
  ```js
  const presence = useSessionStore((s) => s.presence);
  // cellLockHolder(participants, hospital, sigla, selfId) → holder|null
  const isLocked = !!cellLockHolder(presence, lightbox.hospital, lightbox.sigla, getParticipantId());
  ```

- [ ] **Step 2: Gate the button + affordance.** Change the "Escanear con OCR" button's
  `disabled={noOcr || !currentFile}` (`PDFLightbox.jsx:302`) to
  `disabled={noOcr || !currentFile || isLocked}`, and show the same
  "Bloqueado por otro participante" affordance used in `FileList`/`DetailPanel` when
  `isLocked` (tooltip/title or inline note — match the existing M3a treatment).

- [ ] **Step 3: Build + (if present) the presence selector vitest.**
  Run: `cd frontend && npm run build` (must succeed) and
  `npx vitest run src/lib/presence.test.js` (the `cellLockHolder` selector is already
  covered there — confirm still green).

- [ ] **Step 4: Commit.**
  ```bash
  git add frontend/src/components/PDFLightbox.jsx
  git commit -m "fix(web): disable single-file OCR button when cell is read-only (B1)"
  ```

---

## Chunk 3: Verification

### Task 4: full suite + build + 2-context browser smoke

- [ ] **Step 1: Full fast suite + ruff.**
  Run: `.venv-cuda/Scripts/python.exe -m pytest -m "not slow" -q` (0 failed) and
  `.venv-cuda/Scripts/python.exe -m ruff check .` (0).

- [ ] **Step 2: Frontend build + vitest.**
  Run: `cd frontend && npm run build` (OK) and `npx vitest run` (all green).

- [ ] **Step 3: 2-context browser smoke (Brave debug, chrome-devtools MCP).** Run
  **isolated** on a copy DB (the M3a/M3b smoke pattern): two browser contexts on the
  same month; Carla focuses `HRB|odi`; Daniel opens a PDF in that cell → the
  "Escanear con OCR" button is **disabled** with the read-only affordance; a forced
  API call (or the store action) → **409** with `lock_holder.name == "Carla"`; Daniel
  on his **own** focused cell → OCR runs normally. Confirm the real `overseer.db`
  sha256 is unchanged afterward.

- [ ] **Step 4: Final commit (if smoke surfaced fixes) + push.**
  ```bash
  git push origin po_overhaul
  ```

---

## Done criteria
- `scan_file_ocr` returns 409 when another participant holds the cell; 200 for the
  editor / free cell / legacy no-body call.
- The "Escanear con OCR" button is disabled when the cell is read-only; the store
  toasts on a 409 without setting the global error.
- Full suite + vitest + build green; 2-context browser smoke passes; `overseer.db`
  untouched. No counting-logic change.
