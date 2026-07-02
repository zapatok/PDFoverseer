"""SessionManager — bridge between API requests and DB."""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from pathlib import Path

from api.presence import (
    AGENT_PARTICIPANT_ID,
    CellLockedError,
    PresenceRegistry,
    is_agent,
)
from api.reorg import overlap_errors
from core.cell_count import (  # noqa: F401  re-exported for api consumers
    _sum_marks,
    compute_cell_count,
    compute_worker_count,
)
from core.db.sessions_repo import (
    SessionRecord,
    create_session,
    finalize_session,
    get_session,
    update_session_state,
)
from core.orchestrator import _find_category_folder
from core.scanners.base import ScanResult
from core.state.migrations import (
    migrate_state_v1_to_v2,
    migrate_state_v2_to_v3,
    migrate_state_v3_to_v4,
)


def _cell_has_work(cell: dict) -> bool:
    """True when a cell carries OCR results or user edits that a bulk filename
    re-scan must not overwrite.

    A pase-1 re-scan ("Escanear todos los hospitales", e.g. to add a new
    hospital) runs over every cell. For a cell that was already counted by OCR
    or touched by the user, overwriting ``per_file`` with filename counts would
    silently revert its total (which sums ``per_file``) — the 2026-06-05
    incident. A cell is considered worked when it has any of: a full-cell OCR
    count, a cell-level override, a manual "marcar listo", a per-file override,
    a per-file OCR method (a single file OCR'd from the viewer leaves
    ``ocr_count`` None, so the per-file methods must be inspected too), or
    worker-signer marks (Feature 1 charla/chintegral counting, which
    ``compute_worker_count`` links to ``per_file`` — clobbering per_file would
    orphan the marks).
    """
    if cell.get("ocr_count") is not None:
        return True
    if cell.get("user_override") is not None:
        return True
    if cell.get("confirmed"):
        return True
    if cell.get("per_file_overrides"):
        return True
    if cell.get("worker_marks"):
        return True
    per_file_method = cell.get("per_file_method") or {}
    return any(m and m != "filename_glob" for m in per_file_method.values())


def _apply_reorg_deltas(state: dict, deltas: dict[tuple[str, str], dict]) -> None:
    """Zero every cell's reorg delta cache, then apply ``deltas`` in place.

    Shared by ``set_reorg_state`` and ``recompute_reorg_deltas`` (identical
    zero-all + apply loops — extracted so the two can't drift). Non-decorated:
    pure state mutation, callers hold the RLock and persist.
    """
    for siglas in state.get("cells", {}).values():
        for cell in siglas.values():
            cell["reorg_doc_delta"] = 0
            cell["reorg_worker_delta"] = 0
    for (hosp, sigla), d in deltas.items():
        cell = state.setdefault("cells", {}).setdefault(hosp, {}).setdefault(sigla, {})
        cell["reorg_doc_delta"] = d.get("doc", 0)
        cell["reorg_worker_delta"] = d.get("worker", 0)


def _synchronized(method):
    """Serializa el método bajo ``self._lock`` (RLock): protege el
    read-modify-write del blob de sesión contra escrituras concurrentes (merge
    incremental por-PDF desde el hilo de drain + ediciones HTTP durante un scan).

    RLock (no Lock): ``apply_cell_result`` delega en ``apply_filename_result``,
    así que un hilo re-adquiere el mismo lock — con un Lock no reentrante eso
    deadlockea.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SessionManager:
    """Wrap session DB operations + maintain in-memory cell state."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()
        self._presence = PresenceRegistry()

    @_synchronized
    def open_session(
        self,
        *,
        year: int,
        month: int,
        month_root: Path,
    ) -> dict:
        """Open or create a session for (year, month).

        Args:
            year: Calendar year of the session.
            month: Calendar month (1-12).
            month_root: Root directory for the monthly report.

        Returns:
            Session state dict with ``session_id``, ``status``, ``month_root``,
            and ``cells`` keys.
        """
        rec = get_session(self._conn, f"{year:04d}-{month:02d}")
        if rec is None:
            empty_state = {"month_root": month_root.as_posix(), "cells": {}}
            rec = create_session(
                self._conn,
                year=year,
                month=month,
                state_json=json.dumps(empty_state),
            )
        state = json.loads(rec.state_json)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    @_synchronized
    def get_session_state(self, session_id: str) -> dict:
        """Return full session state dict for an existing session.

        Args:
            session_id: The session identifier (e.g. ``"2026-04"``).

        Returns:
            Session state dict with ``session_id``, ``status``, ``month_root``,
            and ``cells`` keys.

        Raises:
            KeyError: If no session with that ID exists.
        """
        state, rec = self._load_and_migrate(session_id)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def _load_and_migrate(self, session_id: str) -> tuple[dict, SessionRecord]:
        """Load session state, run lazy migrations, return (state, record).

        Internal helper used by all setters + getter. Chains v1→v2, v2→v3, then
        v3→v4 (reconcile: seed missing siglas). Persists migrated state back via
        update_session_state only when at least one migration actually changed
        something — idempotent on subsequent calls (all return changed=False on
        already-migrated/reconciled sessions).
        """
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        state, changed1 = migrate_state_v1_to_v2(state)
        state, changed2 = migrate_state_v2_to_v3(state)
        state, changed3 = migrate_state_v3_to_v4(state)
        if changed1 or changed2 or changed3:
            update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return state, rec

    @_synchronized
    def apply_filename_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist a filename_glob scanner result. Touches the filename pass
        fields and shared metadata (method, confidence, flags, errors,
        breakdown). Never touches ocr_count, user_override, note, or note_status.

        A bulk re-scan runs over every cell, including ones already counted by
        OCR or edited by the user (e.g. "Escanear todos los hospitales" to add a
        new hospital). For those (see :func:`_cell_has_work`) only the plain
        filename hint and scan telemetry are refreshed; ``per_file``,
        ``per_file_method``, ``near_matches`` and the OCR/manual state are left
        intact so the displayed count never silently regresses (2026-06-05).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})

        if _cell_has_work(cell):
            cell["filename_count"] = result.count
            cell["files_scanned"] = result.files_scanned
            cell["duration_ms_filename"] = result.duration_ms
            cell.setdefault("per_file_overrides", {})
            cell.setdefault("manual_entry", False)
            cell.setdefault("ocr_count", None)
            cell.setdefault("user_override", None)
            cell.setdefault("excluded", False)
            cell.setdefault("confirmed", False)
            cell.setdefault("all_reliable", False)
            update_session_state(self._conn, session_id, state_json=json.dumps(state))
            return

        cell["filename_count"] = result.count
        cell["confidence"] = result.confidence.value
        cell["method"] = result.method
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["files_scanned"] = result.files_scanned
        cell["duration_ms_filename"] = result.duration_ms
        cell["per_file"] = result.per_file
        # Each file carries how it was counted (rev-2 §3) so _origin_for picks the
        # per-file chip without depending on the cell-level method.
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
        # Pase 1 produces no near-matches; clear any left over from a prior OCR
        # run so the DetailPanel never points "Ver portada" at a PDF that the
        # fresh per_file no longer contains (Bug B).
        cell["near_matches"] = []
        # all_reliable shortcut (Incr 2 §6.3): HIGH ⟺ every filename_glob file is
        # single-page (= all R1) for the non-OCR scanners. bool(per_file) guards the
        # empty/missing-folder case (simple_factory returns HIGH + per_file={}) so a
        # cell with no PDFs is NOT 'listo', matching compute_settled.
        cell["all_reliable"] = result.confidence.value == "high" and bool(result.per_file)
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("ocr_count", None)
        cell.setdefault("user_override", None)
        cell.setdefault("excluded", False)
        # Preserve a manual "marcar listo" across re-scans (never clear it here).
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def apply_ocr_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist an OCR scanner result (whole-cell ``per_file`` replacement).

        .. deprecated:: Incr. 1A — el OCR de celda fusiona por archivo
            (:meth:`apply_per_file_ocr_result`) + :meth:`finalize_cell_ocr` para la
            metadata. Se mantiene para compat de tests legacy (migrar en Task 9).

        Touches ocr_count, method,
        confidence, flags, errors, breakdown, duration_ms_ocr. method =
        ``result.method`` (header_detect, corner_count, page_count_pure, or
        filename_glob when the OCR scanner fell back internally).

        flags/errors/breakdown are written unconditionally — an empty list/dict
        means "no flags this run" (NOT "preserve previous"). Stale data from
        a previous OCR run is overwritten, which is the correct semantic for
        a fresh scan.

        A14: near_matches from result.telemetry are persisted so the UI can
        surface them in the DetailPanel "Casi-matches" section.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["ocr_count"] = result.count
        cell["confidence"] = result.confidence.value
        cell["method"] = result.method
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["duration_ms_ocr"] = result.duration_ms
        cell["per_file"] = result.per_file
        # Each file carries how it was counted (rev-2 §3); for a full-cell OCR run
        # that is this run's OCR method for every scanned file.
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
        # A14: persist near-match telemetry so the UI can surface candidates.
        telemetry = result.telemetry
        cell["near_matches"] = (
            [
                {
                    "pdf_name": nm.pdf_name,
                    "page_index": nm.page_index,
                    "flavor_name": nm.flavor_name,
                    "matched_anchors": list(nm.matched_anchors),
                    "missing_anchors": list(nm.missing_anchors),
                }
                for nm in telemetry.near_matches
            ]
            if telemetry
            else []
        )
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("filename_count", None)
        cell.setdefault("user_override", None)
        cell.setdefault("excluded", False)
        # Preserve a manual "marcar listo" across re-scans (never clear it here).
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def finalize_cell_ocr(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> dict:
        """Finaliza la metadata de celda tras un OCR de celda *incremental* (Incr. 1A).

        NO toca ``per_file``/``per_file_method``: esos se fusionaron por archivo vía
        :meth:`apply_per_file_ocr_result` a medida que cada PDF terminó. Aquí solo se
        escribe metadata de la corrida (método/confianza/flags/errores/duración) y un
        ``ocr_count`` belt-and-suspenders = suma del ``per_file`` actual (fallback de
        ``compute_cell_count``; el total real sale de ``per_file``). Preserva
        user_override, per_file_overrides, manual_entry, confirmed, worker_marks,
        filename_count.

        Args:
            session_id: sesión objetivo.
            hospital: sigla del hospital.
            sigla: sigla de la categoría.
            result: ScanResult de metadata de la corrida (su ``per_file`` se ignora).

        Returns:
            El dict de la celda ya fusionada y finalizada. La ruta lo usa para emitir
            el ``cell_done`` con el snapshot autoritativo (``per_file`` completo —
            incluidos los archivos saltados —, ``ocr_count`` y ``near_matches``), sin
            una segunda lectura del estado.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["method"] = result.method
        cell["confidence"] = result.confidence.value
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["duration_ms_ocr"] = result.duration_ms
        # Fallback only — compute_cell_count prioriza per_file. Suma del per_file
        # YA fusionado por archivo, no el del result (que se ignora).
        cell["ocr_count"] = sum((cell.get("per_file") or {}).values())
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("user_override", None)
        cell.setdefault("excluded", False)
        cell.setdefault("confirmed", False)
        cell.setdefault("all_reliable", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return cell

    @_synchronized
    def apply_user_override(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        value: int | None,
        manual: bool = False,
        participant_id: str | None = None,
    ) -> None:
        """Set or clear the user override count.

        Never touches ``note`` or ``note_status`` — use :meth:`set_note` for
        that. When ``value=None``, ``user_override`` is cleared.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HLL"``).
            sigla: Category code (e.g. ``"reunion"``).
            value: Override count (int) or None to clear.
            manual: When True, marks ``cell.manual_entry = True`` to indicate
                the value was entered via the HLL manual-entry flow (no scan
                data available). Defaults to False, preserving FASE 2 behavior.
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: an agent write to a FREE cell claims it (Claude becomes editor → its
        # badge shows + others go read-only). The conflict check above guarantees no
        # OTHER participant holds it. Humans don't auto-claim (their browser focus-
        # claimed first); no-op for non-agents.
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["user_override"] = value
        cell.setdefault("filename_count", None)
        cell.setdefault("ocr_count", None)
        cell.setdefault("excluded", False)
        cell.setdefault("manual_entry", False)
        if manual:
            cell["manual_entry"] = True
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def set_note(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        text: str | None,
        status: str | None,
        participant_id: str | None = None,
    ) -> None:
        """Set or clear the cell note independently of the override count.

        Replaces both ``note`` and ``note_status`` atomically. Passing
        ``text=None`` and ``status=None`` clears the note entirely.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HPV"``).
            sigla: Category code (e.g. ``"odi"``).
            text: Note text or None to clear.
            status: ``"por_resolver"`` | ``"resuelto"`` | None.
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        stripped = text.strip() if text else None
        cell["note"] = stripped or None
        cell["note_status"] = status if stripped else None
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def apply_per_file_override(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        filename: str,
        count: int,
        participant_id: str | None = None,
    ) -> None:
        """Persist per-file count override. Spec §5.2.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HRB"``).
            sigla: Category code (e.g. ``"odi"``).
            filename: PDF filename to override.
            count: New count value (0 is valid — discards the file's contribution).
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).

        Raises:
            KeyError: if (hospital, sigla) cell is not in session state.
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cells = state.setdefault("cells", {})
        if hospital not in cells or sigla not in cells.get(hospital, {}):
            raise KeyError(f"Cell ({hospital}, {sigla}) not in session {session_id}")
        cell = cells[hospital][sigla]
        cell.setdefault("per_file_overrides", {})
        cell["per_file_overrides"][filename] = count
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def apply_per_file_ocr_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        filename: str,
        *,
        count: int,
        method: str,
        near_matches: list[dict],
    ) -> None:
        """Merge a single-file OCR scan into the cell (rev-2 #1 / §4.2).

        Updates only this file's ``per_file`` count and ``per_file_method``, and
        replaces its near-matches while keeping the others' — leaving the rest of
        the cell untouched (other files, overrides, confirmed, cell-level method).
        The cell total is derived elsewhere via ``compute_cell_count``.

        Args:
            session_id: target session.
            hospital: hospital code.
            sigla: category code.
            filename: the scanned PDF's name.
            count: documents found in that file (0 is valid → its chip reads Revisar).
            method: the OCR method used (e.g. ``"header_band_anchors"``).
            near_matches: serialized near-match dicts for this file (may be empty).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        # per_file may be an explicit None (a filename scan can leave it unset),
        # so setdefault is not enough — coerce to a dict before assigning.
        per_file = cell["per_file"] = cell.get("per_file") or {}
        per_file[filename] = count
        per_file_method = cell["per_file_method"] = cell.get("per_file_method") or {}
        per_file_method[filename] = method
        others = [nm for nm in (cell.get("near_matches") or []) if nm.get("pdf_name") != filename]
        cell["near_matches"] = others + list(near_matches or [])
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def clear_near_matches(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        pdf_name: str | None = None,
        page_index: int | None = None,
        participant_id: str | None = None,
    ) -> None:
        """Drop near-match suspects from a cell — one entry or the whole list (E5).

        A near-match is only a maintenance hint (a candidate for a new flavor), so
        clearing it never changes a count. When ``pdf_name``/``page_index`` identify
        an entry, only that one is dropped; otherwise the whole list is cleared.
        No-op when the cell or its list is absent.

        Args:
            session_id: target session.
            hospital: hospital code.
            sigla: category code.
            pdf_name: with ``page_index``, the specific entry to drop.
            page_index: page index of the entry to drop.
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cell = (state.get("cells", {}).get(hospital, {}) or {}).get(sigla)
        if not cell or not cell.get("near_matches"):
            return
        if pdf_name is None and page_index is None:
            cell["near_matches"] = []
        else:
            cell["near_matches"] = [
                nm
                for nm in cell["near_matches"]
                if not (nm.get("pdf_name") == pdf_name and nm.get("page_index") == page_index)
            ]
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def apply_worker_count(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        marks: dict | None = None,
        status: str | None = None,
        cursor: dict | None = None,
        participant_id: str | None = None,
    ) -> None:
        """Mezcla los campos de conteo de trabajadores en una celda.

        Patch parcial: cada argumento que no sea ``None`` se escribe; los que
        son ``None`` se dejan intactos. Para vaciar las marcas, pasar
        ``marks={}``. La celda se crea si no existe.

        Args:
            session_id: id de la sesión (``YYYY-MM``).
            hospital: sigla del hospital (HLL/HLU/HRB/HPV).
            sigla: la sigla de la celda (``charla`` o ``chintegral``).
            marks: dict ``{archivo: [{page, count}, ...]}``, o None.
            status: ``"en_progreso"`` | ``"terminado"``, o None.
            cursor: ``{file, page}`` con la última posición, o None.
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        if marks is not None:
            cell["worker_marks"] = marks
        if status is not None:
            cell["worker_status"] = status
        if cursor is not None:
            cell["worker_cursor"] = cursor
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def reconcile_worker_marks(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        action: str,
        from_file: str,
        to_file: str | None = None,
        participant_id: str | None = None,
    ) -> None:
        """Reconcile orphan worker/check marks (F1): re-key them onto a present
        file (``migrate``) or drop them (``discard``).

        When a PDF is renamed or merged during a corpus reorganization its marks
        become orphaned — ``_sum_marks`` filters them out of the present-filtered
        total, so the counted work silently vanishes from the Excel. This makes
        that recoverable instead of lost.

        ``migrate`` appends ``from_file``'s marks to ``to_file``'s existing list
        and removes the ``from_file`` key. The page numbers are kept verbatim:
        after a merge they are historical evidence of the counted work, not live
        viewer anchors, so re-numbering them would be meaningless. ``discard``
        simply removes the ``from_file`` key.

        Args:
            session_id: Target session (``YYYY-MM``).
            hospital: Hospital code (HLL/HLU/HRB/HPV).
            sigla: The worker/checks sigla (charla/chintegral/dif_pts/maquinaria).
            action: ``"migrate"`` or ``"discard"``.
            from_file: The orphaned filename whose marks are moved/dropped.
            to_file: Destination filename for ``"migrate"`` (ignored by discard).
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).

        Raises:
            CellLockedError: if the cell is held by a different participant.
            KeyError: if ``from_file`` has no marks in the cell.
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        marks = cell.get("worker_marks") or {}
        if from_file not in marks:
            raise KeyError(from_file)
        if action == "migrate":
            marks.setdefault(to_file, []).extend(marks.pop(from_file))
        else:  # discard
            marks.pop(from_file)
        cell["worker_marks"] = marks
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def apply_confirmed(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        confirmed: bool,
        participant_id: str | None = None,
    ) -> None:
        """Set the manual 'confirmed' (marcar listo) flag on a cell.

        The flag is preserved across re-scans: both apply_filename_result and
        apply_ocr_result re-assert it via ``setdefault``, so confirming a cell
        survives a later pase-1 or OCR scan.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HRB"``).
            sigla: Category code (e.g. ``"exc"``).
            confirmed: New flag value.
            participant_id: Caller's participant id for lock enforcement (M3a).
                ``None`` disables enforcement (legacy / no-presence callers).

        Raises:
            KeyError: if the (hospital, sigla) cell is not in session state.
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
        # M3b: agent auto-claim on write (see apply_user_override for full comment).
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
        state, _ = self._load_and_migrate(session_id)
        cells = state.setdefault("cells", {})
        if hospital not in cells or sigla not in cells.get(hospital, {}):
            raise KeyError(f"Cell ({hospital}, {sigla}) not in session {session_id}")
        cells[hospital][sigla]["confirmed"] = confirmed
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def set_all_reliable(self, session_id: str, hospital: str, sigla: str, value: bool) -> None:
        """Persist the honest 'all files reliable' flag for the green dot (Incr 2 §6)."""
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["all_reliable"] = bool(value)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def add_reorg_op(self, session_id: str, op: dict) -> dict:
        """Append a reorg op with a stable, monotonic id (``op_NNN``).

        The id counter (``state["reorg_seq"]``) never reuses numbers across
        deletes, so an op's id stays meaningful for the manifest.

        Args:
            session_id: Target session identifier.
            op: Op dict (must include ``op_type``, ``source``, ``dest``).

        Returns:
            The op dict with its assigned ``id`` field.
        """
        state, _ = self._load_and_migrate(session_id)
        seq = state.get("reorg_seq", 0) + 1
        state["reorg_seq"] = seq
        op = {**op, "id": f"op_{seq:03d}"}
        state.setdefault("reorg_ops", []).append(op)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return op

    @_synchronized
    def delete_reorg_op(self, session_id: str, op_id: str) -> bool:
        """Remove a reorg op by id. Returns True if one was removed.

        Args:
            session_id: Target session identifier.
            op_id: The op id to remove (e.g. ``"op_001"``).

        Returns:
            True if an op was found and removed; False otherwise.
        """
        state, _ = self._load_and_migrate(session_id)
        ops = state.get("reorg_ops", [])
        kept = [o for o in ops if o.get("id") != op_id]
        removed = len(kept) != len(ops)
        state["reorg_ops"] = kept
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return removed

    @_synchronized
    def set_reorg_state(
        self,
        session_id: str,
        *,
        ops: list[dict],
        deltas: dict[tuple[str, str], dict],
    ) -> None:
        """Replace the op list and rewrite every cell's reorg delta cache.

        Zeros ``reorg_doc_delta``/``reorg_worker_delta`` on all cells, then
        applies ``deltas`` (keyed by (hospital, sigla)). ``deltas`` is in-memory
        only — never serialized — so tuple keys are fine.

        Args:
            session_id: Target session identifier.
            ops: Replacement op list (replaces ``state["reorg_ops"]`` in full).
            deltas: Per-cell delta dict keyed by (hospital, sigla) tuples with
                ``{"doc": int, "worker": int}`` values.
        """
        state, _ = self._load_and_migrate(session_id)
        state["reorg_ops"] = ops
        _apply_reorg_deltas(state, deltas)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def recompute_reorg_deltas(self, session_id: str, *, check_applied: bool = False) -> None:
        """Atomically recompute every cell's reorg delta from ``state["reorg_ops"]``.

        ONE ``_load_and_migrate`` → mutate ops/deltas → ONE ``update_session_state``,
        all under the single RLock — so a concurrent ``add_reorg_op``/``delete`` can
        never be lost to a get-then-set race (F4; the old two-call
        ``get_session_state`` + ``set_reorg_state`` released the lock in between).

        ``check_applied=True`` (pase-1 re-scan only) marks a pending op ``applied``
        when its ``source.file`` is gone from disk. Uses only PDF *names*
        (``folder.rglob`` name set) — never opens a PDF while holding the lock.

        Args:
            session_id: Target session identifier.
            check_applied: When True, retire pending ops whose source file moved.
        """
        state, _ = self._load_and_migrate(session_id)
        ops = state.get("reorg_ops", [])
        month_root = Path(state.get("month_root", ""))

        if check_applied:
            for op in ops:
                if op.get("status") != "pending":
                    continue
                src = op["source"]
                file = src.get("file")
                if file is None:
                    continue  # malformed op (validation requires a file); never auto-apply
                folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
                # names only — no fitz.open inside the lock
                present = {p.name for p in folder.rglob("*.pdf")} if folder.exists() else set()
                if file not in present:
                    op["status"] = "applied"

        deltas: dict[tuple[str, str], dict] = {}
        for op in ops:
            if op.get("status") != "pending":
                continue
            src_key = (op["source"]["hospital"], op["source"]["sigla"])
            dst_key = (op["dest"]["hospital"], op["dest"]["sigla"])
            doc = op.get("doc_count") or 0
            wrk = op.get("worker_count") or 0
            for key in (src_key, dst_key):
                deltas.setdefault(key, {"doc": 0, "worker": 0})
            deltas[src_key]["doc"] -= doc
            deltas[src_key]["worker"] -= wrk
            deltas[dst_key]["doc"] += doc
            deltas[dst_key]["worker"] += wrk

        state["reorg_ops"] = ops
        _apply_reorg_deltas(state, deltas)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def add_reorg_op_validated(self, session_id: str, op: dict) -> dict:
        """Append a reorg op after an atomic overlap re-check, then recompute deltas.

        The whole sequence — overlap check against fresh ``state["reorg_ops"]``,
        id assignment + append, and the delta recompute — runs under one RLock
        acquisition (F4), so two concurrent creates can't both pass a stale
        overlap check nor lose each other's op.

        Args:
            session_id: Target session identifier.
            op: The op dict (page-bounds already validated by the route via
                ``validate_op``, which needs PDF page counts).

        Returns:
            The created op (with its assigned ``id``).

        Raises:
            ValueError: If the op overlaps an existing pending op on the same file.
        """
        state, _ = self._load_and_migrate(session_id)
        errors = overlap_errors(op, state.get("reorg_ops", []))
        if errors:
            raise ValueError("; ".join(errors))
        created = self.add_reorg_op(session_id, op)  # append + persist (re-entrant lock)
        self.recompute_reorg_deltas(session_id)  # recompute + persist (same lock)
        return created

    @_synchronized
    def delete_reorg_op_and_refresh(self, session_id: str, op_id: str) -> bool:
        """Delete a reorg op and recompute deltas atomically (F4).

        Both steps run under one RLock acquisition so no concurrent op edit is
        lost between the delete and the refresh. Returns True iff an op was removed.
        """
        removed = self.delete_reorg_op(session_id, op_id)
        self.recompute_reorg_deltas(session_id)
        return removed

    @_synchronized
    def apply_cell_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        result: ScanResult,
    ) -> None:
        """Deprecated. Use apply_filename_result for pase 1 results."""
        self.apply_filename_result(session_id, hospital, sigla, result)

    @_synchronized
    def finalize(self, session_id: str) -> None:
        """Mark a session as finalized.

        Args:
            session_id: Target session identifier.
        """
        finalize_session(self._conn, session_id)

    # ── Presence (M2) — ephemeral, shares this manager's RLock (spec §6.1) ──

    @_synchronized
    def presence_heartbeat(
        self, session_id: str, participant_id: str, *, name: str, color: str, kind: str = "human"
    ) -> bool:
        return self._presence.heartbeat(
            session_id, participant_id, name=name, color=color, kind=kind
        )

    @_synchronized
    def presence_focus(self, session_id: str, participant_id: str, cell: str | None) -> bool:
        return self._presence.focus(session_id, participant_id, cell)

    @_synchronized
    def presence_leave(self, session_id: str, participant_id: str) -> bool:
        return self._presence.leave(session_id, participant_id)

    @_synchronized
    def presence_snapshot(self, session_id: str) -> list[dict]:
        return self._presence.snapshot(session_id)

    @_synchronized
    def presence_lock_holder(
        self, session_id: str, cell: str, exclude: str | None = None
    ) -> dict | None:
        """Return the public snapshot of the cell's editor (excluding ``exclude``),
        or None if the cell is free."""
        return self._presence.lock_holder(session_id, cell, exclude=exclude)

    @_synchronized
    def agent_claim_cell(self, session_id: str, hospital: str, sigla: str) -> dict | None:
        """Atomic claim for the Claude scanner/agent (M3b).

        Returns the human holder dict if the cell is held by a DIFFERENT
        participant (caller should skip/409), else claims the cell for the
        agent and returns None. Running under the single RLock guarantees no
        TOCTOU between the check and the claim.

        Args:
            session_id: Target session identifier (e.g. ``"2026-04"``).
            hospital: Hospital code (e.g. ``"HRB"``).
            sigla: Category code (e.g. ``"odi"``).

        Returns:
            None if the claim succeeded; the holder's public-fields dict if the
            cell was already held by a human participant.
        """
        cell = f"{hospital}|{sigla}"
        holder = self._presence.lock_holder(session_id, cell, exclude=AGENT_PARTICIPANT_ID)
        if holder is not None:
            return holder
        self._presence.agent_focus(session_id, cell)
        return None

    @_synchronized
    def agent_leave(self, session_id: str) -> bool:
        """Drop the Claude agent's presence entry (scanner cleanup at scan end, M3b).

        Args:
            session_id: Target session identifier.

        Returns:
            True iff the roster changed (agent was present).
        """
        return self._presence.leave(session_id, AGENT_PARTICIPANT_ID)

    def _editor_conflict(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        participant_id: str | None,
    ) -> dict | None:
        """Return the lock_holder dict if ``hospital|sigla`` is held by a DIFFERENT
        participant, else None. ``participant_id=None`` disables enforcement (legacy /
        tests without a participant context).

        MUST be called only from inside an already-``@_synchronized`` method so the
        check + write is atomic under the held RLock (spec §6.4).
        """
        if participant_id is None:
            return None
        return self._presence.lock_holder(session_id, f"{hospital}|{sigla}", exclude=participant_id)

    @_synchronized
    def check_cell_lock(
        self, session_id: str, hospital: str, sigla: str, participant_id: str | None
    ) -> None:
        """Raise CellLockedError if the cell is held by a different participant (M3a).

        Thin gate for routes that do not delegate to the per-method guards (e.g.
        apply-ratio, which loops ``apply_per_file_ocr_result`` — a scanner method
        that must remain unenforced). The check itself runs under the RLock, but
        the caller's subsequent writes happen in their own lock acquisitions, so
        this is NOT a single atomic check-and-write like the per-method guards.
        It is safe for apply-ratio because of editorship exclusivity: the operator
        reached that route by selecting the cell in the UI (a ``focus`` claim), so
        they are the cell's editor; a second participant who opens the same cell
        becomes a *viewer*, never a competing editor — there is no other holder
        that could appear mid-loop. Do not reuse this for a route where the caller
        has not already claimed the cell.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code.
            sigla: Category code.
            participant_id: Caller's participant id; ``None`` disables enforcement.

        Raises:
            CellLockedError: if the cell is held by a different participant.
        """
        holder = self._editor_conflict(session_id, hospital, sigla, participant_id)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
