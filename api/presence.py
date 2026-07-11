"""In-memory participant registry for multiplayer presence (M2 + M3a).

Ephemeral collaboration state — NEVER persisted to the session blob (spec §9).
Pure logic + injectable clock; thread-safety is the caller's job (SessionManager
serializes every call under its RLock, spec §6.1).

M3a: `focus` is now an atomic claim — free cell → caller becomes ``"editor"``;
already-held cell → caller becomes ``"viewer"`` (the existing editor keeps
``"editor"``). At-most-one editor per cell is guaranteed because every call runs
under the caller's (SessionManager's) single RLock. `lock_holder` exposes the
current editor of a cell for conflict checks.
"""

from __future__ import annotations

import time
from collections.abc import Callable

PRESENCE_TTL_SECONDS = 45.0
PRESENCE_HEARTBEAT_SECONDS = 15.0

# ── Claude agent identity (M3b) ───────────────────────────────────────────────

AGENT_PARTICIPANT_ID = "claude"
AGENT_NAME = "Claude"
AGENT_COLOR = "#0ea5e9"  # cian/sky — outside the 6 human colors in identity.js
AGENT_KIND = "agent"


def is_agent(participant_id: str | None) -> bool:
    """Return True iff ``participant_id`` belongs to the Claude agent."""
    return participant_id == AGENT_PARTICIPANT_ID


# Fields exposed in the presence snapshot (the `expires_at` lease is internal).
_PUBLIC_FIELDS = ("participant_id", "name", "color", "kind", "focused_cell", "mode")


class CellLockedError(Exception):
    """Raised when a write targets a cell held by a different participant (M3a)."""

    def __init__(self, hospital: str, sigla: str, holder: dict):
        self.hospital = hospital
        self.sigla = sigla
        self.holder = holder
        super().__init__(f"{hospital}|{sigla} locked by {holder.get('name')}")


class PresenceRegistry:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        # session_id -> participant_id -> record
        self._participants: dict[str, dict[str, dict]] = {}

    def heartbeat(
        self,
        session_id: str,
        participant_id: str,
        *,
        name: str,
        color: str,
        kind: str = "human",
    ) -> bool:
        """Create (join) or renew a participant's lease. Returns True iff the
        roster changed (join, or expiry purge happened) -> caller should broadcast.

        A heartbeat from the Claude agent's own id is always normalized to the
        AGENT_* identity, on both create and renew — a heartbeat that lands
        before the agent's first write must not wear a human avatar (regression
        2026-07-08).
        """
        if is_agent(participant_id):
            name, color, kind = AGENT_NAME, AGENT_COLOR, AGENT_KIND
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        existing = members.get(participant_id)
        if existing is None:
            members[participant_id] = {
                "participant_id": participant_id,
                "name": name,
                "color": color,
                "kind": kind,
                "focused_cell": None,
                "mode": "editor",  # default; overwritten by focus() claim logic (M3a)
                "expires_at": self._now() + PRESENCE_TTL_SECONDS,
            }
            return True
        existing["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        record_changed = False
        if existing["name"] != name or existing["color"] != color:
            existing["name"] = name
            existing["color"] = color
            record_changed = True
        if existing["kind"] != kind:
            existing["kind"] = kind
            record_changed = True
        return record_changed or changed

    def focus(self, session_id: str, participant_id: str, cell: str | None) -> bool:
        """Focus = atomic claim (caller holds the RLock). Free cell -> editor; held
        cell -> viewer (the holder keeps editor). cell=None releases. Returns True
        iff the roster changed."""
        changed = self._purge_expired(session_id)
        rec = self._participants.setdefault(session_id, {}).get(participant_id)
        if rec is None:
            return changed  # focus before heartbeat: ignore, be forgiving
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if cell is None:
            new_mode = "editor"  # mode is moot when not focused; reset to default
        else:
            new_mode = (
                "viewer" if self._editor_of(session_id, cell, exclude=participant_id) else "editor"
            )
        if rec["focused_cell"] != cell or rec["mode"] != new_mode:
            rec["focused_cell"] = cell
            rec["mode"] = new_mode
            return True
        return changed

    def agent_focus(self, session_id: str, cell: str | None) -> bool:
        """Register/refresh the Claude agent focused on ``cell`` (claim under the
        caller's RLock). Free cell -> agent is editor; held by another -> viewer
        (never steals). cell=None releases. Returns True iff the roster changed.

        The agent record carries the same keys as :meth:`heartbeat` so
        :meth:`snapshot` projects it cleanly through ``_PUBLIC_FIELDS``.
        """
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        rec = members.get(AGENT_PARTICIPANT_ID)
        if rec is None:
            rec = members[AGENT_PARTICIPANT_ID] = {
                "participant_id": AGENT_PARTICIPANT_ID,
                "name": AGENT_NAME,
                "color": AGENT_COLOR,
                "kind": AGENT_KIND,
                "focused_cell": None,
                "mode": "editor",
                "expires_at": self._now() + PRESENCE_TTL_SECONDS,
            }
            changed = True
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if cell is None:
            new_mode = "editor"  # mode is moot when not focused; mirror focus() release
        else:
            new_mode = (
                "viewer"
                if self._editor_of(session_id, cell, exclude=AGENT_PARTICIPANT_ID)
                else "editor"
            )
        if rec["focused_cell"] != cell or rec["mode"] != new_mode:
            rec["focused_cell"] = cell
            rec["mode"] = new_mode
            return True
        return changed

    def demote_to_viewer(self, session_id: str, cell: str, participant_id: str) -> bool:
        """Drop ``participant_id`` from editor to viewer on ``cell`` (lock lend).

        Used only by the self-lend path (``SessionManager.agent_claim_cell`` with
        ``lend_from``): the scan launcher voluntarily yields their own editorship
        so the agent's claim can win. Caller holds the RLock. Returns True iff
        the record changed.
        """
        rec = self._participants.get(session_id, {}).get(participant_id)
        if rec is None or rec["focused_cell"] != cell or rec["mode"] != "editor":
            return False
        rec["mode"] = "viewer"
        return True

    def promote_to_editor(self, session_id: str, cell: str, participant_id: str) -> bool:
        """Re-promote ``participant_id`` from viewer back to editor on ``cell``
        (self-lend v1.1, §B2 — undo of :meth:`demote_to_viewer` at scan end).

        Only when ``participant_id`` is still present, still focused on
        ``cell``, and NOT already the editor there; and only when the cell
        currently has NO editor. Never dethrones a different live editor (e.g.
        another human claimed the cell while the agent held it). Caller holds
        the RLock. Returns True iff the record changed.
        """
        self._purge_expired(session_id)
        rec = self._participants.get(session_id, {}).get(participant_id)
        if rec is None or rec["focused_cell"] != cell or rec["mode"] == "editor":
            return False
        if self._editor_of(session_id, cell) is not None:
            return False
        rec["mode"] = "editor"
        return True

    def _editor_of(self, session_id: str, cell: str, exclude: str | None = None) -> str | None:
        """participant_id of the live editor of `cell`, or None. Caller purges first."""
        for pid, r in self._participants.get(session_id, {}).items():
            if pid == exclude:
                continue
            if r["focused_cell"] == cell and r["mode"] == "editor":
                return pid
        return None

    def lock_holder(self, session_id: str, cell: str, exclude: str | None = None) -> dict | None:
        """Public snapshot of the cell's editor (excluding `exclude`), or None if free."""
        self._purge_expired(session_id)
        pid = self._editor_of(session_id, cell, exclude=exclude)
        if pid is None:
            return None
        r = self._participants[session_id][pid]
        return {k: r[k] for k in _PUBLIC_FIELDS}

    def leave(self, session_id: str, participant_id: str) -> bool:
        changed = self._purge_expired(session_id)
        members = self._participants.get(session_id, {})
        if participant_id in members:
            del members[participant_id]
            return True
        return changed

    def snapshot(self, session_id: str) -> list[dict]:
        self._purge_expired(session_id)
        members = self._participants.get(session_id, {})
        return [{k: rec[k] for k in _PUBLIC_FIELDS} for rec in members.values()]

    def _purge_expired(self, session_id: str) -> bool:
        members = self._participants.get(session_id)
        if not members:
            return False
        now = self._now()
        dead = [pid for pid, r in members.items() if r["expires_at"] <= now]
        for pid in dead:
            del members[pid]
        return bool(dead)
