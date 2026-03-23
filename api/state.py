import os
import re as _re
import threading
from pathlib import Path
import uuid
import time
from fastapi import Header, Query, HTTPException

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL", "3600"))

_UUID_RE = _re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')

class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = threading.Lock()
        self.running: bool = False
        self.stop_requested: bool = False
        self.skip_current: bool = False
        self.skipped_pdfs: set[str] = set()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()

        self.pdf_list: list[Path] = []

        # Disk-buffered via database.py
        self.global_total_pages: int = 0
        self.global_done_pages: int = 0
        self.total_docs: int = 0
        self.total_complete: int = 0
        self.total_incomplete: int = 0
        self.total_inferred: int = 0
        self.issues: list[dict] = []
        self.issue_counter: int = 0
        self.start_time: float = 0.0
        self.pause_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.confidences: dict[str, float] = {}
        self.individual_metrics: dict[str, dict] = {}
        self.page_counts: dict[str, int] = {}
        self._metrics_dirty: bool = False

        self.last_accessed = time.time()

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def evict_stale(self) -> int:
        now = time.time()
        with self._lock:
            stale = [sid for sid, s in self._sessions.items()
                     if not s.running and (now - s.last_accessed) > SESSION_TTL_SECONDS]
            for sid in stale:
                del self._sessions[sid]
        return len(stale)

    def get_or_create(self, session_id: str = None) -> SessionState:
        if not session_id:
            session_id = str(uuid.uuid4())
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id)
            self._sessions[session_id].last_accessed = time.time()
            return self._sessions[session_id]

session_manager = SessionManager()

async def get_session(
    x_session_id: str = Header(None),
    session_id: str = Query(None)
) -> SessionState:
    sid = x_session_id or session_id
    if sid and not _UUID_RE.match(sid):
        raise HTTPException(400, "Invalid session ID format")
    return session_manager.get_or_create(sid)
