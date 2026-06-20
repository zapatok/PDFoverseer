"""In-memory participant registry for multiplayer presence (M2).

Ephemeral collaboration state — NEVER persisted to the session blob (spec §9).
Pure logic + injectable clock; thread-safety is the caller's job (SessionManager
serializes every call under its RLock, spec §6.1).

M2 seam: `focus` only records `focused_cell` for presence. There is no exclusivity
and `mode` is a non-load-bearing placeholder ("editor"); the hard lock / editor
arbitration is M3. Do not add enforcement here.
"""

from __future__ import annotations

import time
from collections.abc import Callable

PRESENCE_TTL_SECONDS = 45.0
PRESENCE_HEARTBEAT_SECONDS = 15.0

# Fields exposed in the presence snapshot (the `expires_at` lease is internal).
_PUBLIC_FIELDS = ("participant_id", "name", "color", "kind", "focused_cell", "mode")


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
        roster changed (join, or expiry purge happened) -> caller should broadcast."""
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
                "mode": "editor",  # M2 placeholder; not load-bearing until M3
                "expires_at": self._now() + PRESENCE_TTL_SECONDS,
            }
            return True
        existing["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if existing["name"] != name or existing["color"] != color:
            existing["name"] = name
            existing["color"] = color
            return True
        return changed

    def focus(self, session_id: str, participant_id: str, cell: str | None) -> bool:
        """Record the participant's focused cell (M2: presence only, no claim).
        Returns True iff something changed."""
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        rec = members.get(participant_id)
        if rec is None:
            return changed  # focus before heartbeat: ignore, be forgiving
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if rec["focused_cell"] != cell:
            rec["focused_cell"] = cell
            return True
        return changed

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
