import threading
from pathlib import Path

class ServerState:
    def __init__(self):
        self._lock = threading.Lock()  # Guards non-atomic read-modify-write ops

        self.running: bool = False
        self.stop_requested: bool = False
        self.skip_current: bool = False
        self.skipped_pdfs: set[str] = set()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()

        self.pdf_list: list[Path] = []
        self.pdf_reads: dict[str, list] = {}

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
        self.loop = None

state = ServerState()
