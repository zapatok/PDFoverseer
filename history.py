"""
history.py  —  Persistent analysis history for PDFoverseer
==========================================================
Stores and retrieves analysis results as JSON, one entry per run.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# History file lives next to the script
_HISTORY_FILE = Path(__file__).parent / "history.json"


@dataclass
class PDFResult:
    name:       str
    path:       str
    total_docs: int
    complete:   int
    incomplete: int
    inferred:   int


@dataclass
class HistoryEntry:
    date:             str
    source:           str      # full path to folder or file
    source_name:      str      # display name
    is_folder:        bool
    total_docs:       int
    total_complete:   int
    total_incomplete: int
    total_inferred:   int
    pdfs:             list[PDFResult] = field(default_factory=list)
    is_session:       bool = False


def load_history() -> list[HistoryEntry]:
    """Lee el historial desde disco."""
    if not _HISTORY_FILE.exists():
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = []
        for d in data:
            pdfs = [PDFResult(**p) for p in d.pop("pdfs", [])]
            entries.append(HistoryEntry(**d, pdfs=pdfs))
        return entries
    except Exception:
        return []


def save_history(entries: list[HistoryEntry]):
    """Escribe el historial completo a disco."""
    data = [asdict(e) for e in entries]
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_entry(entry: HistoryEntry):
    """Agrega una entrada al historial y persiste."""
    history = load_history()
    history.insert(0, entry)  # newest first
    save_history(history)


def clear_history():
    """Borra todo el historial."""
    save_history([])
