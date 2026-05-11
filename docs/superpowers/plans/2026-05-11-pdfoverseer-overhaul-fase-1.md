# PDFoverseer Overhaul — FASE 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-PDF-session UX with a folder-driven orchestrator. Open `A:\informe mensual\<MES>\`, see 4 hospitals × 18 categories with trivial filename-glob counts, generate `RESUMEN_<MES>_<AÑO>.xlsx` from a templated workbook.

**Architecture:** 5 layers (Frontend → API → Orchestrator → Scanners/Storage → Excel writer). Scanners auto-register via a sigla-keyed registry. `simple_filename_scanner` factory builds the 14 trivial sigla scanners; the 4 sigla that need custom techniques (art, irl, odi, charla) use the same factory in FASE 1 and get specialized in FASE 2. SQLite WAL-mode for sessions + historical counts. Excel writer uses named ranges so the template can evolve without breaking code.

**Tech Stack:** Python 3.10+ (FastAPI, openpyxl, multiprocessing) · React 18 + Vite · SQLite · pytest

**Spec:** `docs/superpowers/specs/2026-05-11-pdfoverseer-overhaul-design.md`

**Branch:** `research/pixel-density`

---

## File Structure

### Created in FASE 1

```
core/
├── db/
│   ├── __init__.py            (≤20 LOC — re-exports)
│   ├── connection.py          (≤120 LOC — WAL connection lifecycle)
│   ├── migrations.py          (≤80 LOC — init schema)
│   ├── sessions_repo.py       (≤200 LOC — sessions CRUD)
│   └── historical_repo.py     (≤200 LOC — historical CRUD)
├── excel/
│   ├── __init__.py            (≤20 LOC)
│   ├── template.py            (≤150 LOC — load template, list named ranges)
│   └── writer.py              (≤300 LOC — fill cells + atomic rename)
├── scanners/
│   ├── __init__.py            (≤60 LOC — registry + bulk-register call)
│   ├── base.py                (≤80 LOC — Protocol + ScanResult + ConfidenceLevel)
│   ├── simple_factory.py      (≤150 LOC — make_simple_scanner builder)
│   └── utils/
│       ├── __init__.py        (≤10 LOC)
│       ├── filename_glob.py   (≤120 LOC — glob + sigla filter + per-empresa)
│       └── page_count_heuristic.py  (≤100 LOC — flag suspect compilations)
├── orchestrator.py            (≤350 LOC — enumerate + dispatch + collect)
└── domain.py                  (≤150 LOC — HOSPITALS, SIGLAS, CATEGORY_FOLDERS canonical lists)

api/
├── routes/
│   ├── __init__.py            (≤20 LOC)
│   ├── months.py              (≤120 LOC)
│   ├── sessions.py            (≤250 LOC)
│   ├── output.py              (≤120 LOC)
│   └── ws.py                  (≤200 LOC)
├── state.py                   (≤200 LOC — session_manager singleton)
└── main.py                    (≤150 LOC — FastAPI app + lifespan)

data/
├── templates/
│   └── RESUMEN_template_v1.xlsx   (manual artifact — see Task 6)
├── outputs/                       (gitignored, generated files)
└── overseer.db                    (gitignored, SQLite)

tests/
├── conftest.py                    (≤100 LOC — write-guard + tmp_path fixtures)
├── unit/
│   ├── db/
│   │   ├── test_sessions_repo.py
│   │   └── test_historical_repo.py
│   ├── excel/
│   │   ├── test_template.py
│   │   └── test_writer.py
│   ├── scanners/
│   │   ├── test_filename_glob.py
│   │   ├── test_page_count_heuristic.py
│   │   └── test_simple_factory.py
│   └── test_orchestrator.py
├── integration/
│   └── test_abril_full_corpus.py
└── e2e/
    └── test_smoke.py

frontend/src/
├── App.jsx                    (≤120 LOC — view router)
├── lib/
│   ├── api.js                 (≤200 LOC — REST client)
│   ├── ws.js                  (≤120 LOC — WS client)
│   └── format.js              (≤80 LOC — helpers)
├── store/
│   └── session.js             (≤200 LOC — Zustand slice)
├── hooks/
│   ├── useMonths.js           (≤80 LOC)
│   ├── useSession.js          (≤150 LOC)
│   └── useScanProgress.js     (≤120 LOC)
├── views/
│   ├── MonthOverview.jsx      (≤200 LOC)
│   └── HospitalDetail.jsx     (≤200 LOC)
└── components/
    ├── HospitalCard.jsx       (≤120 LOC)
    ├── CategoryRow.jsx        (≤150 LOC)
    ├── ScanIndicator.jsx      (≤80 LOC)
    ├── ConfidenceBadge.jsx    (≤60 LOC)
    ├── ScanControls.jsx       (≤120 LOC)
    ├── ProgressFooter.jsx     (≤120 LOC)
    └── GenerateOutputButton.jsx  (≤100 LOC)
```

### Modified in FASE 1

- `.gitignore` — add `data/overseer.db`, `data/outputs/`, `frontend/dist/`
- `pyproject.toml` — add `openpyxl>=3.1` to dependencies if not present
- `frontend/package.json` — add `zustand`, `react-router-dom` (or simpler view-switch) if missing

### Untouched in FASE 1

- `core/ocr.py`, `core/utils.py`, `core/inference.py`, `core/phases/*` — used by future scanners, no edits now
- `eval/`, `vlm/`, `tools/` — research/standalone modules
- `data/sessions.db` — old DB stays untouched (legacy app on master uses it)

---

## Chunk 1: Foundation — DB + Excel + write-guard

### Task 1: Add gitignore entries + create `data/` subdirs

**Files:**
- Modify: `.gitignore`
- Create: `data/templates/.gitkeep`, `data/outputs/.gitkeep`

- [ ] **Step 1: Update `.gitignore`**

Append to `.gitignore`:
```
# FASE 1 overhaul artifacts
data/overseer.db
data/overseer.db-shm
data/overseer.db-wal
data/outputs/
frontend/dist/
```

- [ ] **Step 2: Create directory placeholders**

```bash
mkdir -p data/templates data/outputs
touch data/templates/.gitkeep data/outputs/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore data/templates/.gitkeep data/outputs/.gitkeep
git commit -m "chore: add FASE 1 data directories + gitignore overlay"
```

---

### Task 2: Test write-guard fixture

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_write_guard.py`

- [ ] **Step 1: Write the failing test**

`tests/test_write_guard.py`:
```python
import pytest
from pathlib import Path

def test_write_to_informe_mensual_raises(tmp_path):
    """The autouse write-guard should raise when a test attempts to write
    inside A:\\informe mensual\\ or A:\\estadistica mensual\\."""
    forbidden = Path("A:/informe mensual/test_should_not_exist.txt")
    with pytest.raises(PermissionError, match="write-guard"):
        forbidden.write_text("nope")


def test_write_to_tmp_path_allowed(tmp_path):
    """Writes to tmp_path are allowed."""
    target = tmp_path / "allowed.txt"
    target.write_text("ok")
    assert target.read_text() == "ok"
```

- [ ] **Step 2: Run to verify it fails (no conftest yet)**

Run: `pytest tests/test_write_guard.py -v`
Expected: FAIL — the forbidden write succeeds because no guard exists.

- [ ] **Step 3: Implement `tests/conftest.py`**

```python
"""Pytest fixtures for PDFoverseer tests.

Critical fixture: write-guard. Any attempt to write inside
A:\\informe mensual\\ or A:\\estadistica mensual\\ fails LOUD so tests
cannot accidentally corrupt the source corpus.
"""

from pathlib import Path
import shutil
import os
import pytest

_FORBIDDEN_ROOTS = (
    Path("A:/informe mensual").resolve(),
    Path("A:/estadistica mensual").resolve(),
)


def _is_forbidden(target: os.PathLike | str) -> bool:
    try:
        resolved = Path(target).resolve()
    except (OSError, ValueError):
        return False
    return any(
        str(resolved).lower().startswith(str(root).lower())
        for root in _FORBIDDEN_ROOTS
    )


@pytest.fixture(autouse=True)
def _write_guard(monkeypatch):
    """Block writes targeting the source corpus folders."""
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_unlink = Path.unlink
    original_copy = shutil.copy
    original_copy2 = shutil.copy2
    original_copytree = shutil.copytree
    original_move = shutil.move
    original_rename = os.rename
    original_replace = os.replace

    def _guard_write_text(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: writes to {self} are forbidden in tests")
        return original_write_text(self, *args, **kwargs)

    def _guard_write_bytes(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: writes to {self} are forbidden in tests")
        return original_write_bytes(self, *args, **kwargs)

    def _guard_unlink(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: unlink of {self} is forbidden in tests")
        return original_unlink(self, *args, **kwargs)

    def _guard_copy(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copy to {dst} is forbidden in tests")
        return original_copy(src, dst, *args, **kwargs)

    def _guard_copy2(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copy2 to {dst} is forbidden in tests")
        return original_copy2(src, dst, *args, **kwargs)

    def _guard_copytree(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copytree to {dst} is forbidden in tests")
        return original_copytree(src, dst, *args, **kwargs)

    def _guard_move(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: move to {dst} is forbidden in tests")
        return original_move(src, dst, *args, **kwargs)

    def _guard_rename(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: rename to {dst} is forbidden in tests")
        return original_rename(src, dst, *args, **kwargs)

    def _guard_replace(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: replace to {dst} is forbidden in tests")
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _guard_write_text)
    monkeypatch.setattr(Path, "write_bytes", _guard_write_bytes)
    monkeypatch.setattr(Path, "unlink", _guard_unlink)
    monkeypatch.setattr(shutil, "copy", _guard_copy)
    monkeypatch.setattr(shutil, "copy2", _guard_copy2)
    monkeypatch.setattr(shutil, "copytree", _guard_copytree)
    monkeypatch.setattr(shutil, "move", _guard_move)
    monkeypatch.setattr(os, "rename", _guard_rename)
    monkeypatch.setattr(os, "replace", _guard_replace)
    yield
```

- [ ] **Step 4: Run to verify both tests pass**

Run: `pytest tests/test_write_guard.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_write_guard.py
git commit -m "test: add write-guard autouse fixture to protect source corpus"
```

---

### Task 3: Canonical domain constants

**Files:**
- Create: `core/domain.py`
- Create: `tests/unit/test_domain.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_domain.py`:
```python
from core.domain import HOSPITALS, SIGLAS, CATEGORY_FOLDERS, sigla_to_folder, folder_to_sigla


def test_hospitals_are_the_four_codes():
    assert HOSPITALS == ("HPV", "HRB", "HLU", "HLL")


def test_siglas_are_the_18_canonical():
    expected = (
        "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
        "insgral", "bodega", "maquinaria", "ext", "senal", "exc",
        "altura", "caliente", "herramientas_elec", "andamios", "chps",
    )
    assert SIGLAS == expected
    assert len(SIGLAS) == 18


def test_category_folders_map_to_numbered_names():
    assert CATEGORY_FOLDERS["reunion"] == "1.-Reunion Prevencion"
    assert CATEGORY_FOLDERS["art"] == "7.-ART"
    assert CATEGORY_FOLDERS["chps"] == "18.-CHPS"
    assert len(CATEGORY_FOLDERS) == 18


def test_sigla_to_folder_and_back():
    for sigla in SIGLAS:
        folder = sigla_to_folder(sigla)
        assert folder_to_sigla(folder) == sigla
        # also accepts " 0" suffix used for empty categories
        assert folder_to_sigla(folder + " 0") == sigla
        assert folder_to_sigla(folder + " 934") == sigla


def test_folder_to_sigla_unknown_returns_none():
    assert folder_to_sigla("99.-Unknown Category") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_domain.py -v`
Expected: ImportError (module doesn't exist yet).

- [ ] **Step 3: Implement `core/domain.py`**

```python
"""Canonical domain constants — hospitals, siglas, category folder names.

These come from A:\\informe mensual\\.serena\\memories\\ conventions.
Single source of truth: do not duplicate these lists anywhere else.
"""

from __future__ import annotations

HOSPITALS: tuple[str, ...] = ("HPV", "HRB", "HLU", "HLL")

# 18 canonical siglas (order matches the 18 prevention categories)
SIGLAS: tuple[str, ...] = (
    "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
    "insgral", "bodega", "maquinaria", "ext", "senal", "exc",
    "altura", "caliente", "herramientas_elec", "andamios", "chps",
)

# Sigla → canonical folder name (without TOTAL/" 0" suffix)
CATEGORY_FOLDERS: dict[str, str] = {
    "reunion":           "1.-Reunion Prevencion",
    "irl":               "2.-Induccion IRL",
    "odi":               "3.-ODI Visitas",
    "charla":            "4.-Charlas",
    "chintegral":        "5.-Charla Integral",
    "dif_pts":           "6.-Difusion PTS",
    "art":               "7.-ART",
    "insgral":           "8.-Inspecciones Generales",
    "bodega":            "9.-Inspeccion Bodega",
    "maquinaria":        "10.-Inspeccion de Maquinaria",
    "ext":               "11.-Extintores",
    "senal":             "12.-Senaleticas",
    "exc":               "13.-Excavaciones y Vanos",
    "altura":            "14.-Trabajos en Altura",
    "caliente":          "15.-Inspeccion Trabajos en Caliente",
    "herramientas_elec": "16.-Inspeccion Herramientas Electricas",
    "andamios":          "17.-Andamios",
    "chps":              "18.-CHPS",
}

_FOLDER_TO_SIGLA: dict[str, str] = {v: k for k, v in CATEGORY_FOLDERS.items()}


def sigla_to_folder(sigla: str) -> str:
    """Return the canonical folder base name for a sigla."""
    return CATEGORY_FOLDERS[sigla]


def folder_to_sigla(folder_name: str) -> str | None:
    """Map a folder name (with or without TOTAL/' 0' suffix) back to its sigla.

    Examples:
        '7.-ART' → 'art'
        '7.-ART 934' → 'art'
        '12.-Senaleticas 0' → 'senal'
        '99.-Unknown' → None
    """
    # strip suffix after the canonical name
    for canonical, sigla in _FOLDER_TO_SIGLA.items():
        if folder_name == canonical or folder_name.startswith(canonical + " "):
            return sigla
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_domain.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/domain.py tests/unit/test_domain.py
git commit -m "feat(core): add canonical HOSPITALS, SIGLAS, CATEGORY_FOLDERS constants"
```

---

### Task 4: DB connection + migrations

**Files:**
- Create: `core/db/__init__.py`, `core/db/connection.py`, `core/db/migrations.py`
- Create: `tests/unit/db/__init__.py`, `tests/unit/db/test_connection.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/db/test_connection.py`:
```python
import sqlite3
from pathlib import Path

import pytest

from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


def test_open_connection_creates_db_file(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    assert db_path.exists()
    assert isinstance(conn, sqlite3.Connection)
    close_all()


def test_open_connection_enables_wal(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    cursor = conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"
    close_all()


def test_init_schema_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    init_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "sessions" in tables
    assert "historical_counts" in tables
    close_all()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/db/test_connection.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/db/connection.py`**

```python
"""SQLite connection lifecycle for PDFoverseer.

Single connection per process (orchestrator owns it). WAL mode for
crash safety. close_all() called from FastAPI lifespan shutdown.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import threading

_CONNECTIONS: dict[Path, sqlite3.Connection] = {}
_LOCK = threading.Lock()


def open_connection(db_path: Path) -> sqlite3.Connection:
    """Open or return cached connection. Enables WAL mode + foreign keys."""
    db_path = Path(db_path).resolve()
    with _LOCK:
        if db_path in _CONNECTIONS:
            return _CONNECTIONS[db_path]
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        _CONNECTIONS[db_path] = conn
        return conn


def close_all() -> None:
    """Close all cached connections — call from app shutdown."""
    with _LOCK:
        for conn in _CONNECTIONS.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _CONNECTIONS.clear()
```

- [ ] **Step 4: Implement `core/db/migrations.py`**

```python
"""Schema initialization for PDFoverseer DB. Idempotent."""

from __future__ import annotations

import sqlite3

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_modified TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'finalized'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON sessions(status, last_modified);

CREATE TABLE IF NOT EXISTS historical_counts (
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    hospital TEXT NOT NULL,
    sigla TEXT NOT NULL,
    count INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    method TEXT NOT NULL,
    finalized_at TEXT NOT NULL,
    PRIMARY KEY (year, month, hospital, sigla)
);

CREATE INDEX IF NOT EXISTS idx_historical_year
    ON historical_counts(year, month);

CREATE INDEX IF NOT EXISTS idx_historical_sigla
    ON historical_counts(sigla, year);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indices if missing. Idempotent."""
    conn.executescript(_SCHEMA_SQL)
```

- [ ] **Step 5: Implement `core/db/__init__.py`**

```python
"""DB layer re-exports for convenience."""

from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema

__all__ = ["open_connection", "close_all", "init_schema"]
```

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/unit/db/test_connection.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add core/db/ tests/unit/db/__init__.py tests/unit/db/test_connection.py
git commit -m "feat(db): SQLite connection lifecycle + WAL + schema init"
```

---

### Task 5: Sessions repository

**Files:**
- Create: `core/db/sessions_repo.py`
- Create: `tests/unit/db/test_sessions_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/db/test_sessions_repo.py`:
```python
import json

import pytest

from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema
from core.db.sessions_repo import (
    create_session,
    get_session,
    update_session_state,
    finalize_session,
    SessionRecord,
)


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    yield conn
    close_all()


def test_create_session_persists(conn):
    rec = create_session(conn, year=2026, month=4, state_json='{"cells":{}}')
    assert rec.session_id == "2026-04"
    assert rec.status == "active"
    fetched = get_session(conn, "2026-04")
    assert fetched == rec


def test_get_session_missing_returns_none(conn):
    assert get_session(conn, "1999-12") is None


def test_update_state_changes_last_modified(conn):
    create_session(conn, year=2026, month=4, state_json='{"v":1}')
    update_session_state(conn, "2026-04", state_json='{"v":2}')
    rec = get_session(conn, "2026-04")
    assert json.loads(rec.state_json) == {"v": 2}


def test_finalize_session_changes_status(conn):
    create_session(conn, year=2026, month=4, state_json='{"v":1}')
    finalize_session(conn, "2026-04")
    rec = get_session(conn, "2026-04")
    assert rec.status == "finalized"


def test_create_session_existing_active_returns_same(conn):
    rec1 = create_session(conn, year=2026, month=4, state_json='{"v":1}')
    rec2 = create_session(conn, year=2026, month=4, state_json='{"v":99}')
    # second call returns existing, does not overwrite
    assert rec1.session_id == rec2.session_id
    assert json.loads(rec2.state_json) == {"v": 1}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/db/test_sessions_repo.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/db/sessions_repo.py`**

```python
"""Sessions table CRUD."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    year: int
    month: int
    state_json: str
    created_at: str
    last_modified: str
    status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_id(year: int, month: int) -> str:
    if not (1 <= month <= 12):
        raise ValueError(f"month out of range: {month}")
    return f"{year:04d}-{month:02d}"


def create_session(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
    state_json: str,
) -> SessionRecord:
    """Create or return existing active session for (year, month)."""
    sid = _session_id(year, month)
    existing = get_session(conn, sid)
    if existing is not None:
        return existing
    now = _now_iso()
    conn.execute(
        "INSERT INTO sessions "
        "(session_id, year, month, state_json, created_at, last_modified, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active')",
        (sid, year, month, state_json, now, now),
    )
    return SessionRecord(sid, year, month, state_json, now, now, "active")


def get_session(conn: sqlite3.Connection, session_id: str) -> SessionRecord | None:
    row = conn.execute(
        "SELECT session_id, year, month, state_json, created_at, last_modified, status "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return SessionRecord(**dict(row))


def update_session_state(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    state_json: str,
) -> None:
    conn.execute(
        "UPDATE sessions SET state_json = ?, last_modified = ? WHERE session_id = ?",
        (state_json, _now_iso(), session_id),
    )


def finalize_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET status = 'finalized', last_modified = ? WHERE session_id = ?",
        (_now_iso(), session_id),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/db/test_sessions_repo.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/db/sessions_repo.py tests/unit/db/test_sessions_repo.py
git commit -m "feat(db): sessions repository with create/get/update/finalize"
```

---

### Task 6: Historical counts repository

**Files:**
- Create: `core/db/historical_repo.py`
- Create: `tests/unit/db/test_historical_repo.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/db/test_historical_repo.py`:
```python
import pytest

from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema
from core.db.historical_repo import (
    upsert_count,
    get_counts_for_month,
    query_range,
)


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "h.db")
    init_schema(conn)
    yield conn
    close_all()


def test_upsert_inserts_new(conn):
    upsert_count(conn, year=2026, month=4, hospital="HPV", sigla="art",
                 count=767, confidence="high", method="filename_glob")
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert len(rows) == 1
    assert rows[0].count == 767


def test_upsert_updates_existing(conn):
    upsert_count(conn, year=2026, month=4, hospital="HPV", sigla="art",
                 count=767, confidence="high", method="filename_glob")
    upsert_count(conn, year=2026, month=4, hospital="HPV", sigla="art",
                 count=800, confidence="manual", method="manual")
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert len(rows) == 1
    assert rows[0].count == 800
    assert rows[0].method == "manual"


def test_query_range_across_months(conn):
    for month in (3, 4, 5):
        upsert_count(conn, year=2026, month=month, hospital="HPV", sigla="art",
                     count=100 * month, confidence="high", method="filename_glob")
    rows = query_range(conn, from_year=2026, from_month=3, to_year=2026, to_month=5)
    assert len(rows) == 3
    counts = sorted(r.count for r in rows)
    assert counts == [300, 400, 500]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/db/test_historical_repo.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/db/historical_repo.py`**

```python
"""Historical counts table CRUD + cross-month queries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HistoricalCount:
    year: int
    month: int
    hospital: str
    sigla: str
    count: int
    confidence: str
    method: str
    finalized_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_count(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
    hospital: str,
    sigla: str,
    count: int,
    confidence: str,
    method: str,
) -> None:
    conn.execute(
        "INSERT INTO historical_counts "
        "(year, month, hospital, sigla, count, confidence, method, finalized_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(year, month, hospital, sigla) DO UPDATE SET "
        "count = excluded.count, confidence = excluded.confidence, "
        "method = excluded.method, finalized_at = excluded.finalized_at",
        (year, month, hospital, sigla, count, confidence, method, _now_iso()),
    )


def get_counts_for_month(
    conn: sqlite3.Connection, *, year: int, month: int
) -> list[HistoricalCount]:
    rows = conn.execute(
        "SELECT year, month, hospital, sigla, count, confidence, method, finalized_at "
        "FROM historical_counts WHERE year = ? AND month = ?",
        (year, month),
    ).fetchall()
    return [HistoricalCount(**dict(r)) for r in rows]


def query_range(
    conn: sqlite3.Connection,
    *,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> list[HistoricalCount]:
    """Inclusive on both ends."""
    from_key = from_year * 12 + from_month
    to_key = to_year * 12 + to_month
    rows = conn.execute(
        "SELECT year, month, hospital, sigla, count, confidence, method, finalized_at "
        "FROM historical_counts WHERE (year * 12 + month) BETWEEN ? AND ? "
        "ORDER BY year, month, hospital, sigla",
        (from_key, to_key),
    ).fetchall()
    return [HistoricalCount(**dict(r)) for r in rows]
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/db/test_historical_repo.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/db/historical_repo.py tests/unit/db/test_historical_repo.py
git commit -m "feat(db): historical_counts repository with upsert + cross-month query"
```

---

### Task 7: Excel template (manual artifact creation)

**Files:**
- Create: `data/templates/RESUMEN_template_v1.xlsx` (manual, see steps)
- Create: `data/templates/README.md`

- [ ] **Step 1: Copy the sample as base** (Windows PowerShell)

```powershell
Copy-Item "A:\PROJECTS\PDFoverseer\data\output_sample\RESUMEN_ABRIL_2026.xlsx" `
          "A:\PROJECTS\PDFoverseer\data\templates\RESUMEN_template_v1.xlsx"
```

Or via Bash on Git-Bash:
```bash
cp "A:/PROJECTS/PDFoverseer/data/output_sample/RESUMEN_ABRIL_2026.xlsx" \
   "A:/PROJECTS/PDFoverseer/data/templates/RESUMEN_template_v1.xlsx"
```

- [ ] **Step 2: Open template in Excel and add named ranges**

Manual step. Open `data/templates/RESUMEN_template_v1.xlsx` in Excel and add named ranges for each of the 72 cantidad cells. For sheet "Cump. Programa Prevención":

Naming convention: `<HOSPITAL>_<SIGLA>_count`. Examples:
- `HLL_reunion_count` → cell G10
- `HLL_irl_count` → cell G11
- `HLU_reunion_count` → cell I10
- `HRB_art_count` → cell K16
- `HPV_chps_count` → cell M28

Plus 2 workforce input ranges per hospital:
- `HLL_workers_chgen` → cell G29 (Cantidad Trabajadores ch general)
- `HLL_workers_chintegral` → cell G30
- (and same for HLU, HRB, HPV)

Also blank the existing data values in those cells (so the template doesn't ship with ABRIL's numbers).

Use Formulas → Name Manager → New for each. This is tedious; consider scripting it post-MVP.

- [ ] **Step 3: Create `data/templates/README.md`**

```markdown
# RESUMEN Excel Templates

## RESUMEN_template_v1.xlsx

Source for monthly Cumplimiento Programa Prevención workbook.

Single sheet: "Cump. Programa Prevención".

Named ranges (72 cantidad cells + 8 workforce cells):

| Range pattern | Refers to | Count |
|---------------|-----------|-------|
| `<HOSP>_<SIGLA>_count` | Cantidad Realizada cell per (hospital, sigla) | 72 |
| `<HOSP>_workers_chgen` | Workforce for charlas generales (cell row 29) | 4 |
| `<HOSP>_workers_chintegral` | Workforce for charla integral (cell row 30) | 4 |

`<HOSP>` ∈ {HLL, HLU, HRB, HPV} (mind the column order: G/H, I/J, K/L, M/N).
`<SIGLA>` ∈ the 18 canonical siglas (see `core/domain.py`).

To upgrade the template: bump version (`_v2.xlsx`), keep `_v1.xlsx` for backward compat, update `core/excel/template.py:DEFAULT_TEMPLATE`.
```

- [ ] **Step 4: Commit**

```bash
git add data/templates/RESUMEN_template_v1.xlsx data/templates/README.md
git commit -m "feat(excel): RESUMEN_template_v1.xlsx with 80 named ranges"
```

---

### Task 8: Excel template loader

**Files:**
- Create: `core/excel/__init__.py`, `core/excel/template.py`
- Create: `tests/unit/excel/__init__.py`, `tests/unit/excel/test_template.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/excel/test_template.py`:
```python
from pathlib import Path

import pytest

from core.excel.template import load_template, list_named_ranges, DEFAULT_TEMPLATE


def test_default_template_exists():
    assert DEFAULT_TEMPLATE.exists()


def test_load_template_returns_workbook():
    wb = load_template(DEFAULT_TEMPLATE)
    assert "Cump. Programa Prevención" in wb.sheetnames or any(
        "Cump" in s for s in wb.sheetnames
    )


def test_list_named_ranges_includes_expected_count_cells():
    wb = load_template(DEFAULT_TEMPLATE)
    names = list_named_ranges(wb)
    # 72 cantidad cells expected
    cantidad_names = [n for n in names if n.endswith("_count")]
    assert len(cantidad_names) == 72
    assert "HPV_art_count" in names
    assert "HLL_reunion_count" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/excel/test_template.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/excel/template.py`**

```python
"""Excel template loader using named ranges (workbook-level defined names)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "templates" / "RESUMEN_template_v1.xlsx"
)


def load_template(path: Path = DEFAULT_TEMPLATE) -> Workbook:
    """Load a template Excel workbook. Use copy-and-modify in writer."""
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return load_workbook(path)


def list_named_ranges(wb: Workbook) -> list[str]:
    """Return all workbook-level defined names."""
    return list(wb.defined_names)


def get_range_cell(wb: Workbook, name: str) -> tuple[str, str]:
    """Resolve a named range to (sheet_name, cell_address). Single-cell only."""
    dn = wb.defined_names[name]
    destinations = list(dn.destinations)
    if len(destinations) != 1:
        raise ValueError(f"Range {name!r} resolves to {len(destinations)} cells")
    sheet, coord = destinations[0]
    return sheet, coord
```

- [ ] **Step 4: Implement `core/excel/__init__.py`**

```python
from core.excel.template import DEFAULT_TEMPLATE, load_template, list_named_ranges
__all__ = ["DEFAULT_TEMPLATE", "load_template", "list_named_ranges"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/excel/test_template.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add core/excel/__init__.py core/excel/template.py tests/unit/excel/
git commit -m "feat(excel): template loader + named-range introspection"
```

---

### Task 9: Excel writer with atomic write-then-rename

**Files:**
- Create: `core/excel/writer.py`
- Create: `tests/unit/excel/test_writer.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/excel/test_writer.py`:
```python
import shutil
from pathlib import Path

import openpyxl
import pytest

from core.excel.template import DEFAULT_TEMPLATE
from core.excel.writer import generate_resumen, ExcelGenerationResult


def test_generate_writes_atomic_file(tmp_path):
    output = tmp_path / "RESUMEN_TEST.xlsx"
    cell_values = {
        "HPV_art_count": 767,
        "HRB_irl_count": 92,
    }
    result = generate_resumen(
        cell_values=cell_values,
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert isinstance(result, ExcelGenerationResult)
    assert output.exists()
    # no leftover tmp file
    assert not Path(str(output) + ".tmp").exists()
    assert result.cells_written == 2


def test_generated_file_has_correct_values(tmp_path):
    output = tmp_path / "RESUMEN_VALUES.xlsx"
    generate_resumen(
        cell_values={"HPV_art_count": 767},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    wb = openpyxl.load_workbook(output)
    sheet_name, coord = next(iter(wb.defined_names["HPV_art_count"].destinations))
    assert wb[sheet_name][coord].value == 767


def test_existing_target_is_backed_up(tmp_path):
    output = tmp_path / "RESUMEN_BAK.xlsx"
    shutil.copy(DEFAULT_TEMPLATE, output)  # pre-existing file
    generate_resumen(
        cell_values={"HPV_art_count": 100},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert output.exists()
    assert (output.parent / (output.name + ".bak")).exists()


def test_unknown_range_emits_warning(tmp_path):
    output = tmp_path / "RESUMEN_WARN.xlsx"
    result = generate_resumen(
        cell_values={"NONEXISTENT_RANGE": 42},
        output_path=output,
        template_path=DEFAULT_TEMPLATE,
    )
    assert any("NONEXISTENT_RANGE" in w for w in result.warnings)
    assert result.cells_written == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/excel/test_writer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/excel/writer.py`**

```python
"""Excel writer: fill named ranges + atomic write-then-rename."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from core.excel.template import DEFAULT_TEMPLATE, get_range_cell


@dataclass(frozen=True)
class ExcelGenerationResult:
    output_path: Path
    cells_written: int
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0


def generate_resumen(
    *,
    cell_values: dict[str, int | float | str],
    output_path: Path,
    template_path: Path = DEFAULT_TEMPLATE,
) -> ExcelGenerationResult:
    """Fill named ranges in a template and write atomically to output_path.

    Behavior:
    1. Load template (copy in memory, do NOT modify on disk)
    2. For each (named_range, value) in cell_values: set the cell
    3. Save to <output_path>.tmp
    4. If <output_path> exists, rename it to <output_path>.bak
    5. Rename <output_path>.tmp → <output_path>
    """
    start = time.perf_counter()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(template_path)
    warnings: list[str] = []
    cells_written = 0

    for name, value in cell_values.items():
        if name not in wb.defined_names:
            warnings.append(f"named range not found: {name}")
            continue
        try:
            sheet_name, coord = get_range_cell(wb, name)
        except ValueError as exc:
            warnings.append(f"{name}: {exc}")
            continue
        wb[sheet_name][coord] = value
        cells_written += 1

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    wb.save(tmp_path)

    bak_path = output_path.with_suffix(output_path.suffix + ".bak")
    if output_path.exists():
        if bak_path.exists():
            bak_path.unlink()
        output_path.rename(bak_path)
    tmp_path.rename(output_path)

    duration_ms = int((time.perf_counter() - start) * 1000)
    return ExcelGenerationResult(
        output_path=output_path,
        cells_written=cells_written,
        warnings=warnings,
        duration_ms=duration_ms,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/excel/test_writer.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/excel/writer.py tests/unit/excel/test_writer.py
git commit -m "feat(excel): atomic writer with backup + named-range filling"
```

---

## Chunk 2: Scanners — base + factory + utils

### Task 10: Scanner Protocol + ScanResult + ConfidenceLevel

**Files:**
- Create: `core/scanners/__init__.py`, `core/scanners/base.py`
- Create: `tests/unit/scanners/__init__.py`, `tests/unit/scanners/test_base.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/scanners/test_base.py`:
```python
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult


def test_confidence_levels_values():
    assert ConfidenceLevel.HIGH.value == "high"
    assert ConfidenceLevel.MEDIUM.value == "medium"
    assert ConfidenceLevel.LOW.value == "low"
    assert ConfidenceLevel.MANUAL.value == "manual"


def test_scan_result_is_frozen_dataclass():
    r = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=5,
    )
    assert r.count == 5
    import dataclasses
    assert dataclasses.is_dataclass(r)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/scanners/test_base.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/scanners/base.py`**

```python
"""Scanner Protocol + supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"


@dataclass(frozen=True)
class ScanResult:
    count: int
    confidence: ConfidenceLevel
    method: str
    breakdown: dict[str, int] | None
    flags: list[str]
    errors: list[str]
    duration_ms: int
    files_scanned: int


@runtime_checkable
class Scanner(Protocol):
    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult: ...
```

- [ ] **Step 4: Implement `core/scanners/__init__.py` (registry)**

```python
"""Scanner registry. Scanners auto-register on import."""

from __future__ import annotations

from typing import Iterator

from core.scanners.base import Scanner, ScanResult, ConfidenceLevel

_REGISTRY: dict[str, Scanner] = {}


def register(scanner: Scanner) -> None:
    if scanner.sigla in _REGISTRY:
        raise ValueError(f"duplicate scanner sigla: {scanner.sigla}")
    _REGISTRY[scanner.sigla] = scanner


def get(sigla: str) -> Scanner:
    return _REGISTRY[sigla]


def has(sigla: str) -> bool:
    return sigla in _REGISTRY


def all_siglas() -> list[str]:
    return sorted(_REGISTRY.keys())


def all_scanners() -> Iterator[Scanner]:
    yield from _REGISTRY.values()


def clear() -> None:
    """For tests only."""
    _REGISTRY.clear()


__all__ = [
    "Scanner", "ScanResult", "ConfidenceLevel",
    "register", "get", "has", "all_siglas", "all_scanners", "clear",
]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/scanners/test_base.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/__init__.py core/scanners/base.py tests/unit/scanners/
git commit -m "feat(scanners): Protocol + registry + ScanResult dataclass"
```

---

### Task 11: filename_glob util

**Files:**
- Create: `core/scanners/utils/__init__.py`, `core/scanners/utils/filename_glob.py`
- Create: `tests/unit/scanners/test_filename_glob.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/scanners/test_filename_glob.py`:
```python
from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import count_pdfs_by_sigla, per_empresa_breakdown


# Real fixtures from ABRIL HPV
ABRIL_ROOT = Path("A:/informe mensual/ABRIL")


def test_count_art_in_hpv():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    result = count_pdfs_by_sigla(folder, sigla="art")
    # HPV ART has 767 PDFs across 13 empresa subfolders as of 2026-05-11 audit
    # We don't pin to 767 exactly (corpus may evolve); just bound it
    assert 700 <= result.count <= 900
    assert result.method == "filename_glob"


def test_count_zero_when_folder_empty(tmp_path):
    empty = tmp_path / "1.-Reunion Prevencion 0"
    empty.mkdir()
    result = count_pdfs_by_sigla(empty, sigla="reunion")
    assert result.count == 0


def test_count_zero_when_folder_missing(tmp_path):
    missing = tmp_path / "doesnotexist"
    result = count_pdfs_by_sigla(missing, sigla="reunion")
    assert result.count == 0
    assert "folder_missing" in result.flags


def test_per_empresa_breakdown_for_hpv_art():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    breakdown = per_empresa_breakdown(folder)
    # Some empresa subfolders should exist; CRS is typically the largest
    assert len(breakdown) >= 5
    assert any("CRS" in name.upper() for name in breakdown)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/scanners/test_filename_glob.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/scanners/utils/filename_glob.py`**

```python
"""Filename-based counting: walk a folder, count PDFs by sigla in the filename."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FILENAME_SIGLA_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}_(?P<sigla>[a-z_]+?)(?:_|\.)",
)


@dataclass(frozen=True)
class GlobCountResult:
    count: int
    method: str
    files_scanned: int
    flags: list[str]


def extract_sigla(filename: str) -> str | None:
    """Extract the sigla from a canonical filename like
    `2026-04-01_art_crs_andamios.pdf`. Returns None if format doesn't match.
    """
    m = _FILENAME_SIGLA_RE.match(filename)
    return m.group("sigla") if m else None


def count_pdfs_by_sigla(folder: Path, *, sigla: str) -> GlobCountResult:
    """Count PDFs (recursively) where filename starts with the given sigla.

    Returns count=0 with flag 'folder_missing' if folder doesn't exist.
    """
    if not folder.exists():
        return GlobCountResult(count=0, method="filename_glob",
                               files_scanned=0, flags=["folder_missing"])
    pdfs = list(folder.rglob("*.pdf"))
    matched = [p for p in pdfs if extract_sigla(p.name) == sigla]
    flags: list[str] = []
    if pdfs and not matched:
        flags.append("no_matching_sigla_in_folder")
    if len(matched) < len(pdfs):
        flags.append("some_files_unrecognized")
    return GlobCountResult(
        count=len(matched),
        method="filename_glob",
        files_scanned=len(pdfs),
        flags=flags,
    )


def per_empresa_breakdown(folder: Path) -> dict[str, int]:
    """Return {empresa_subfolder_name: pdf_count}. Includes only direct subfolders."""
    if not folder.exists():
        return {}
    breakdown: dict[str, int] = {}
    for sub in folder.iterdir():
        if not sub.is_dir():
            continue
        breakdown[sub.name] = len(list(sub.rglob("*.pdf")))
    return breakdown
```

- [ ] **Step 4: Implement `core/scanners/utils/__init__.py`**

```python
from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla, per_empresa_breakdown, extract_sigla, GlobCountResult,
)
__all__ = ["count_pdfs_by_sigla", "per_empresa_breakdown",
           "extract_sigla", "GlobCountResult"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/scanners/test_filename_glob.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/utils/ tests/unit/scanners/test_filename_glob.py
git commit -m "feat(scanners): filename_glob util — count by sigla + empresa breakdown"
```

---

### Task 12: page_count_heuristic util

**Files:**
- Create: `core/scanners/utils/page_count_heuristic.py`
- Create: `tests/unit/scanners/test_page_count_heuristic.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/scanners/test_page_count_heuristic.py`:
```python
from pathlib import Path

from core.scanners.utils.page_count_heuristic import (
    flag_compilation_suspect, EXPECTED_PAGES_PER_DOC,
)


ABRIL = Path("A:/informe mensual/ABRIL")


def test_hpv_odi_individualized_not_suspect():
    """HPV ODI Visitas has 90 individual PDFs of ~2 pages each — no compilation."""
    flagged = flag_compilation_suspect(ABRIL / "HPV" / "3.-ODI Visitas", sigla="odi")
    assert flagged is False


def test_hrb_odi_single_pdf_is_suspect():
    """HRB ODI Visitas has 1 PDF of 34 pages — compilation suspected."""
    flagged = flag_compilation_suspect(ABRIL / "HRB" / "3.-ODI Visitas", sigla="odi")
    assert flagged is True


def test_hlu_odi_single_pdf_is_suspect():
    flagged = flag_compilation_suspect(ABRIL / "HLU" / "3.-ODI Visitas", sigla="odi")
    assert flagged is True


def test_expected_pages_per_doc_table_covers_all_siglas():
    from core.domain import SIGLAS
    for sigla in SIGLAS:
        assert sigla in EXPECTED_PAGES_PER_DOC
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/scanners/test_page_count_heuristic.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/scanners/utils/page_count_heuristic.py`**

```python
"""Heuristic: flag a folder as containing a likely compilation.

We use page-count anomaly: if one PDF in the folder is much longer than
the expected per-document length for that sigla, that PDF is probably a
compilation of multiple documents (not a single document).

The actual COUNTING of internal documents is FASE 2 work via OCR scanners.
This util only produces a boolean flag for the badge.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

# Tentative thresholds — calibrate per sigla as needed. Conservative
# defaults; better to flag false positives than miss real compilations.
EXPECTED_PAGES_PER_DOC: dict[str, int] = {
    "reunion":           4,
    "irl":               2,
    "odi":               2,
    "charla":            3,
    "chintegral":        8,
    "dif_pts":           3,
    "art":               4,
    "insgral":           3,
    "bodega":            2,
    "maquinaria":        2,
    "ext":               2,
    "senal":             2,
    "exc":               2,
    "altura":            2,
    "caliente":          2,
    "herramientas_elec": 2,
    "andamios":          2,
    "chps":              4,
}

_TIGHT_FACTOR = 5  # PDF is suspect if pages > expected × factor


def _page_count(pdf_path: Path) -> int:
    try:
        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except (fitz.FileDataError, OSError):
        return 0


def flag_compilation_suspect(folder: Path, *, sigla: str) -> bool:
    """Return True if at least one PDF in folder has page-count
    >> expected for this sigla (likely compilation)."""
    if not folder.exists():
        return False
    expected = EXPECTED_PAGES_PER_DOC.get(sigla, 5)
    threshold = expected * _TIGHT_FACTOR
    for pdf in folder.rglob("*.pdf"):
        if _page_count(pdf) > threshold:
            return True
    return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/scanners/test_page_count_heuristic.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/page_count_heuristic.py tests/unit/scanners/test_page_count_heuristic.py
git commit -m "feat(scanners): page_count_heuristic — flag compilation suspects"
```

---

### Task 13: simple_filename_scanner factory + registry wiring for all 18 siglas

**Files:**
- Create: `core/scanners/simple_factory.py`
- Modify: `core/scanners/__init__.py` (register all 18)
- Create: `tests/unit/scanners/test_simple_factory.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/scanners/test_simple_factory.py`:
```python
from pathlib import Path

import pytest

from core.domain import SIGLAS
from core.scanners import get, has, all_siglas
from core.scanners.base import ConfidenceLevel
from core.scanners.simple_factory import make_simple_scanner


ABRIL = Path("A:/informe mensual/ABRIL")


def test_all_18_siglas_registered():
    registered = set(all_siglas())
    assert set(SIGLAS) <= registered


def test_simple_scanner_counts_correctly_in_hpv_art():
    scanner = get("art")
    result = scanner.count(ABRIL / "HPV" / "7.-ART")
    assert result.count > 0
    assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
    assert result.method == "filename_glob"


def test_simple_scanner_handles_missing_folder(tmp_path):
    scanner = get("reunion")
    result = scanner.count(tmp_path / "does_not_exist")
    assert result.count == 0
    assert "folder_missing" in result.flags


def test_simple_scanner_flags_compilation_in_hrb_odi():
    scanner = get("odi")
    result = scanner.count(ABRIL / "HRB" / "3.-ODI Visitas")
    # Count is 1 (the compilation PDF) but flag must be set
    assert "compilation_suspect" in result.flags


def test_factory_builds_independently():
    scanner = make_simple_scanner("art")
    assert scanner.sigla == "art"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/scanners/test_simple_factory.py -v`
Expected: ImportError or AssertionError.

- [ ] **Step 3: Implement `core/scanners/simple_factory.py`**

```python
"""Factory for trivial filename-glob scanners.

In FASE 1 ALL 18 siglas use this factory. In FASE 2, 4 of them
(art, irl, odi, charla) get replaced with specialized scanners.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult, Scanner
from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla, per_empresa_breakdown,
)
from core.scanners.utils.page_count_heuristic import flag_compilation_suspect


@dataclass
class SimpleFilenameScanner:
    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult:
        start = time.perf_counter()
        glob_result = count_pdfs_by_sigla(folder, sigla=self.sigla)
        breakdown = per_empresa_breakdown(folder)
        flags = list(glob_result.flags)

        is_compilation = flag_compilation_suspect(folder, sigla=self.sigla)
        if is_compilation:
            flags.append("compilation_suspect")
            confidence = ConfidenceLevel.LOW
        elif "folder_missing" in flags:
            confidence = ConfidenceLevel.HIGH  # 0 is correct for missing
        else:
            confidence = ConfidenceLevel.HIGH

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ScanResult(
            count=glob_result.count,
            confidence=confidence,
            method="filename_glob",
            breakdown=breakdown if breakdown else None,
            flags=flags,
            errors=[],
            duration_ms=duration_ms,
            files_scanned=glob_result.files_scanned,
        )


def make_simple_scanner(sigla: str) -> Scanner:
    return SimpleFilenameScanner(sigla=sigla)
```

- [ ] **Step 4: Wire registry in `core/scanners/__init__.py`**

Append to `core/scanners/__init__.py`:
```python
from core.domain import SIGLAS as _SIGLAS
from core.scanners.simple_factory import make_simple_scanner as _make


def register_defaults() -> None:
    """Register all 18 sigla scanners. Idempotent — safe to call after clear()."""
    for sigla in _SIGLAS:
        if not has(sigla):
            register(_make(sigla))


register_defaults()
```

Update `__all__` to include `register_defaults` so tests can re-register after `clear()`.

- [ ] **Step 5: Run to verify all tests pass**

Run: `pytest tests/unit/scanners/test_simple_factory.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/simple_factory.py core/scanners/__init__.py tests/unit/scanners/test_simple_factory.py
git commit -m "feat(scanners): simple_filename_scanner factory + auto-register 18 siglas"
```

---

## Chunk 3: Orchestrator + API

### Task 14: Orchestrator — month enumeration

**Files:**
- Create: `core/orchestrator.py`
- Create: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_orchestrator.py`:
```python
from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, MonthInventory


ABRIL = Path("A:/informe mensual/ABRIL")


def test_enumerate_month_returns_4_hospitals():
    inv = enumerate_month(ABRIL)
    assert sorted(inv.hospitals_present) == ["HLU", "HPV", "HRB"]  # HLL not normalized
    assert "HLL" in inv.hospitals_missing


def test_enumerate_month_populates_18_categories_per_hospital():
    inv = enumerate_month(ABRIL)
    for hosp in ("HPV", "HRB", "HLU"):
        assert len(inv.cells[hosp]) == 18


def test_enumerate_month_returns_zero_for_missing_category(tmp_path):
    (tmp_path / "HPV").mkdir()  # empty hospital folder
    inv = enumerate_month(tmp_path)
    assert "HPV" in inv.hospitals_present
    # all 18 categories should be present (as missing folders)
    assert len(inv.cells["HPV"]) == 18
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_orchestrator.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `core/orchestrator.py` (skeleton + enumerate)**

```python
"""Orchestrator: enumerate month folder + dispatch scans to scanners."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.domain import HOSPITALS, SIGLAS, CATEGORY_FOLDERS


@dataclass(frozen=True)
class CellInventory:
    hospital: str
    sigla: str
    folder_path: Path
    folder_exists: bool
    pdf_count_hint: int  # quick rglob count, no parsing


@dataclass(frozen=True)
class MonthInventory:
    month_root: Path
    hospitals_present: list[str]
    hospitals_missing: list[str]
    cells: dict[str, list[CellInventory]]  # hospital → list of 18 cells


def _find_category_folder(hosp_dir: Path, sigla: str) -> Path:
    """Locate the folder for `sigla` inside a hospital dir, tolerating
    TOTAL/' 0' suffixes."""
    canonical = CATEGORY_FOLDERS[sigla]
    direct = hosp_dir / canonical
    if direct.exists():
        return direct
    # search for matches with suffix
    for sub in hosp_dir.iterdir():
        if not sub.is_dir():
            continue
        if sub.name == canonical or sub.name.startswith(canonical + " "):
            return sub
    return direct  # nominal path even if it doesn't exist


def enumerate_month(month_root: Path) -> MonthInventory:
    if not month_root.exists():
        raise FileNotFoundError(f"Month folder not found: {month_root}")
    present: list[str] = []
    missing: list[str] = []
    cells: dict[str, list[CellInventory]] = {}
    for hosp in HOSPITALS:
        hosp_dir = month_root / hosp
        if not hosp_dir.exists():
            missing.append(hosp)
            continue
        present.append(hosp)
        cell_list: list[CellInventory] = []
        for sigla in SIGLAS:
            folder = _find_category_folder(hosp_dir, sigla)
            exists = folder.exists()
            pdf_hint = len(list(folder.rglob("*.pdf"))) if exists else 0
            cell_list.append(CellInventory(
                hospital=hosp, sigla=sigla, folder_path=folder,
                folder_exists=exists, pdf_count_hint=pdf_hint,
            ))
        cells[hosp] = cell_list
    return MonthInventory(
        month_root=month_root,
        hospitals_present=present,
        hospitals_missing=missing,
        cells=cells,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_orchestrator.py::test_enumerate_month_returns_4_hospitals -v`
Run: `pytest tests/unit/test_orchestrator.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat(orchestrator): enumerate month → MonthInventory of 4x18 cells"
```

---

### Task 15: Orchestrator — scan_cell + scan_month with parallelism

**Files:**
- Modify: `core/orchestrator.py`
- Create: `tests/unit/test_orchestrator_scan.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_orchestrator_scan.py`:
```python
from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, scan_cell, scan_month
from core.scanners.base import ConfidenceLevel


ABRIL = Path("A:/informe mensual/ABRIL")


def test_scan_cell_hpv_art_returns_count():
    inv = enumerate_month(ABRIL)
    cell = next(c for c in inv.cells["HPV"] if c.sigla == "art")
    result = scan_cell(cell)
    assert result.count > 0
    assert result.method == "filename_glob"


def test_scan_month_returns_result_per_cell():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # 3 hospitals × 18 cats = 54 cells
    assert len(results) == 54
    # All have a count (possibly zero)
    for (hosp, sigla), r in results.items():
        assert r.count >= 0


def test_scan_month_flags_known_compilations():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # HRB ODI and HLU ODI are known compilations
    assert "compilation_suspect" in results[("HRB", "odi")].flags
    assert "compilation_suspect" in results[("HLU", "odi")].flags
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_orchestrator_scan.py -v`
Expected: ImportError (functions don't exist yet).

- [ ] **Step 3: Append to `core/orchestrator.py`**

```python
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor

from core import scanners as scanner_registry
from core.scanners.base import ScanResult


def scan_cell(cell: CellInventory) -> ScanResult:
    """Run the registered scanner for this cell's sigla."""
    scanner = scanner_registry.get(cell.sigla)
    return scanner.count(cell.folder_path)


def _scan_cell_worker(cell_tuple):
    """Pool worker entry — re-imports happen in subprocess."""
    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    return (hosp, sigla, scanner.count(folder))


def scan_month(
    inv: MonthInventory,
    *,
    max_workers: int | None = None,
) -> dict[tuple[str, str], ScanResult]:
    """Scan all cells in parallel. Returns dict keyed by (hospital, sigla)."""
    if max_workers is None:
        max_workers = max(1, min(8, (os.cpu_count() or 4) - 1))
    cell_tuples = [
        (c.hospital, c.sigla, str(c.folder_path))
        for cells in inv.cells.values()
        for c in cells
    ]
    results: dict[tuple[str, str], ScanResult] = {}
    if max_workers == 1:
        for ct in cell_tuples:
            hosp, sigla, r = _scan_cell_worker(ct)
            results[(hosp, sigla)] = r
        return results
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for hosp, sigla, r in pool.map(_scan_cell_worker, cell_tuples):
            results[(hosp, sigla)] = r
    return results
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_orchestrator_scan.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator.py tests/unit/test_orchestrator_scan.py
git commit -m "feat(orchestrator): parallel scan_month with ProcessPoolExecutor"
```

---

### Task 16: API state — session manager

**Files:**
- Create: `api/state.py`
- Create: `tests/unit/api/__init__.py`, `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/api/test_state.py`:
```python
import json
from pathlib import Path

import pytest

from api.state import SessionManager
from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "api.db")
    init_schema(conn)
    yield conn
    close_all()


def test_open_session_creates_new_if_not_exists(conn):
    mgr = SessionManager(conn=conn)
    state = mgr.open_session(year=2026, month=4,
                             month_root=Path("A:/informe mensual/ABRIL"))
    assert state["session_id"] == "2026-04"
    assert state["month_root"] == "A:/informe mensual/ABRIL"


def test_open_session_returns_existing(conn):
    mgr = SessionManager(conn=conn)
    s1 = mgr.open_session(year=2026, month=4,
                          month_root=Path("A:/informe mensual/ABRIL"))
    s2 = mgr.open_session(year=2026, month=4,
                          month_root=Path("A:/informe mensual/ABRIL"))
    assert s1["session_id"] == s2["session_id"]


def test_apply_cell_result_persists(conn):
    from core.scanners.base import ScanResult, ConfidenceLevel
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4,
                     month_root=Path("A:/informe mensual/ABRIL"))
    result = ScanResult(
        count=767, confidence=ConfidenceLevel.HIGH, method="filename_glob",
        breakdown=None, flags=[], errors=[], duration_ms=10, files_scanned=767,
    )
    mgr.apply_cell_result("2026-04", "HPV", "art", result)
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HPV"]["art"]["count"] == 767
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_state.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `api/state.py`**

```python
"""SessionManager — bridge between API requests and DB."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from core.db.sessions_repo import (
    create_session, get_session, update_session_state, finalize_session,
)
from core.scanners.base import ScanResult


class SessionManager:
    """Wrap session DB operations + maintain in-memory cell state."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def open_session(
        self, *, year: int, month: int, month_root: Path,
    ) -> dict:
        rec = get_session(self._conn, f"{year:04d}-{month:02d}")
        if rec is None:
            empty_state = {"month_root": str(month_root), "cells": {}}
            rec = create_session(
                self._conn, year=year, month=month,
                state_json=json.dumps(empty_state),
            )
        state = json.loads(rec.state_json)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def get_session_state(self, session_id: str) -> dict:
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def apply_cell_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult,
    ) -> None:
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        cells = state.setdefault("cells", {})
        hosp_cells = cells.setdefault(hospital, {})
        hosp_cells[sigla] = {
            "count": result.count,
            "confidence": result.confidence.value,
            "method": result.method,
            "breakdown": result.breakdown,
            "flags": result.flags,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
            "files_scanned": result.files_scanned,
            "user_override": None,
            "excluded": False,
        }
        update_session_state(
            self._conn, session_id, state_json=json.dumps(state),
        )

    def apply_user_override(
        self, session_id: str, hospital: str, sigla: str, override: int | None,
    ) -> None:
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        cell = state["cells"].setdefault(hospital, {}).setdefault(sigla, {})
        cell["user_override"] = override
        update_session_state(
            self._conn, session_id, state_json=json.dumps(state),
        )

    def finalize(self, session_id: str) -> None:
        finalize_session(self._conn, session_id)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_state.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/
git commit -m "feat(api): SessionManager — DB-backed session state"
```

---

### Task 17: API routes — months + sessions

**Files:**
- Create: `api/routes/__init__.py`, `api/routes/months.py`, `api/routes/sessions.py`
- Create: `tests/unit/api/test_routes_months.py`, `tests/unit/api/test_routes_sessions.py`

- [ ] **Step 1: Write the failing test (months route)**

`tests/unit/api/test_routes_months.py`:
```python
import pytest
from fastapi.testclient import TestClient

from api.routes.months import router
from fastapi import FastAPI


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_get_months_returns_list(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months")
    assert response.status_code == 200
    data = response.json()
    assert "months" in data
    assert any(m["name"] == "ABRIL" for m in data["months"])


def test_get_month_returns_inventory(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months/2026-04")
    assert response.status_code == 200
    inv = response.json()
    assert "hospitals_present" in inv
    assert len(inv["hospitals_present"]) >= 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_routes_months.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `api/routes/months.py`**

```python
"""GET /api/months and /api/months/{year}-{month}."""

from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from core.orchestrator import enumerate_month

router = APIRouter()


def _informe_root() -> Path:
    return Path(os.environ.get("INFORME_MENSUAL_ROOT", "A:/informe mensual"))


_MONTH_NAMES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


@router.get("/months")
def list_months() -> dict:
    root = _informe_root()
    if not root.exists():
        return {"months": []}
    months = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        upper = sub.name.upper()
        m_num = _MONTH_NAMES.get(upper)
        if m_num is None:
            continue
        # Year inferred from current year — Daniel works on current year by default;
        # future enhancement: parse from a YYYY parent folder.
        from datetime import datetime
        year = datetime.now().year
        months.append({
            "name": sub.name,
            "year": year,
            "month": m_num,
            "session_id": f"{year:04d}-{m_num:02d}",
            "path": str(sub),
        })
    return {"months": months}


_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@router.get("/months/{session_id}")
def get_month(session_id: str) -> dict:
    m = _SESSION_ID_RE.match(session_id)
    if not m:
        raise HTTPException(400, f"Invalid session_id format: {session_id}")
    year, month = int(m.group(1)), int(m.group(2))
    # Find matching month folder by name
    root = _informe_root()
    target_name = next(
        (name for name, num in _MONTH_NAMES.items() if num == month), None,
    )
    if target_name is None:
        raise HTTPException(404, f"Unknown month: {month}")
    month_dir = next(
        (p for p in root.iterdir() if p.is_dir() and p.name.upper() == target_name),
        None,
    )
    if month_dir is None:
        raise HTTPException(404, f"Month folder not found: {target_name}")
    inv = enumerate_month(month_dir)
    return {
        "session_id": session_id,
        "month_root": str(inv.month_root),
        "hospitals_present": inv.hospitals_present,
        "hospitals_missing": inv.hospitals_missing,
        "cells": {
            hosp: [
                {
                    "hospital": c.hospital,
                    "sigla": c.sigla,
                    "folder_path": str(c.folder_path),
                    "folder_exists": c.folder_exists,
                    "pdf_count_hint": c.pdf_count_hint,
                }
                for c in cell_list
            ]
            for hosp, cell_list in inv.cells.items()
        },
    }
```

- [ ] **Step 4: Run to verify months route passes**

Run: `pytest tests/unit/api/test_routes_months.py -v`
Expected: 2 passed.

- [ ] **Step 5: Write the failing test (sessions route)**

`tests/unit/api/test_routes_sessions.py`:
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.sessions import router, get_manager
from api.state import SessionManager
from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    conn = open_connection(tmp_path / "api_sessions.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(router, prefix="/api")
    yield TestClient(app)
    close_all()


def test_create_session(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["session_id"] == "2026-04"


def test_get_session(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.get("/api/sessions/2026-04")
    assert response.status_code == 200
    assert response.json()["session_id"] == "2026-04"


def test_scan_session_populates_cells(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
    assert response.status_code == 200
    state = client.get("/api/sessions/2026-04").json()
    assert "cells" in state
    assert "HPV" in state["cells"]
```

- [ ] **Step 6: Implement `api/routes/sessions.py`**

```python
"""Sessions endpoints: create/get + trigger scan."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.state import SessionManager
from core.orchestrator import enumerate_month, scan_month

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

_MONTH_NAMES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def _informe_root() -> Path:
    return Path(os.environ.get("INFORME_MENSUAL_ROOT", "A:/informe mensual"))


def _resolve_month_dir(year: int, month: int) -> Path:
    target_name = next(
        (name for name, num in _MONTH_NAMES.items() if num == month), None,
    )
    if target_name is None:
        raise HTTPException(400, f"Invalid month: {month}")
    for p in _informe_root().iterdir():
        if p.is_dir() and p.name.upper() == target_name:
            return p
    raise HTTPException(404, f"Month folder not found: {target_name}")


def get_manager() -> SessionManager:
    """Dependency placeholder — overridden in tests + main.py."""
    raise RuntimeError("get_manager not configured")


@router.post("/sessions")
def create(
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    year = body.get("year")
    month = body.get("month")
    if not isinstance(year, int) or not isinstance(month, int):
        raise HTTPException(400, "year and month required (integers)")
    month_dir = _resolve_month_dir(year, month)
    return mgr.open_session(year=year, month=month, month_root=month_dir)


@router.get("/sessions/{session_id}")
def get(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        return mgr.get_session_state(session_id)
    except KeyError:
        raise HTTPException(404, f"Session not found: {session_id}")


@router.post("/sessions/{session_id}/scan")
def scan(
    session_id: str,
    body: dict = Body(default={"scope": "all"}),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError:
        raise HTTPException(404, f"Session not found: {session_id}")
    month_root = Path(state["month_root"])
    try:
        inv = enumerate_month(month_root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    results = scan_month(inv)
    for (hosp, sigla), r in results.items():
        mgr.apply_cell_result(session_id, hosp, sigla, r)
    return {
        "scanned": len(results),
        "summary": {
            f"{hosp}_{sigla}": r.count
            for (hosp, sigla), r in results.items()
        },
    }
```

- [ ] **Step 7: Implement `api/routes/__init__.py`** (only modules that exist at this stage)

```python
"""API routes — modules added incrementally per task."""
from api.routes import months, sessions
__all__ = ["months", "sessions"]
```

Tasks 18 and 19 will extend this when `output` and `ws` modules are created.

- [ ] **Step 8: Run to verify**

Run: `pytest tests/unit/api/test_routes_sessions.py -v`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add api/routes/months.py api/routes/sessions.py api/routes/__init__.py tests/unit/api/test_routes_months.py tests/unit/api/test_routes_sessions.py
git commit -m "feat(api): /api/months + /api/sessions endpoints"
```

---

### Task 18: API routes — output (generate RESUMEN)

**Files:**
- Create: `api/routes/output.py`
- Create: `tests/unit/api/test_routes_output.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/api/test_routes_output.py`:
```python
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.sessions import router as sessions_router, get_manager
from api.routes.output import router as output_router
from api.state import SessionManager
from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "outputs"))
    app = FastAPI()
    conn = open_connection(tmp_path / "out.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(sessions_router, prefix="/api")
    app.include_router(output_router, prefix="/api")
    yield TestClient(app)
    close_all()


def test_generate_output_creates_xlsx(client, tmp_path):
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
    response = client.post("/api/sessions/2026-04/output", json={})
    assert response.status_code == 200
    data = response.json()
    assert Path(data["output_path"]).exists()
    assert data["output_path"].endswith(".xlsx")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `api/routes/output.py`**

```python
"""POST /api/sessions/{session_id}/output → generate RESUMEN xlsx."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.routes.sessions import get_manager
from api.state import SessionManager
from core.excel.writer import generate_resumen

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _output_dir() -> Path:
    return Path(os.environ.get(
        "OVERSEER_OUTPUT_DIR",
        "A:/PROJECTS/PDFoverseer/data/outputs",
    ))


def _build_cell_values(state: dict) -> dict[str, int]:
    """Translate session.cells into named-range-keyed dict for the writer."""
    out: dict[str, int] = {}
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, cell in sigla_map.items():
            if cell.get("excluded"):
                continue
            value = cell.get("user_override")
            if value is None:
                value = cell.get("count")
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out


@router.post("/sessions/{session_id}/output")
def generate(
    session_id: str,
    body: dict = Body(default={}),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError:
        raise HTTPException(404, f"Session not found: {session_id}")
    cell_values = _build_cell_values(state)
    output_dir = _output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"RESUMEN_{session_id}.xlsx"
    result = generate_resumen(
        cell_values=cell_values,
        output_path=output_path,
    )
    return {
        "output_path": str(result.output_path),
        "cells_written": result.cells_written,
        "warnings": result.warnings,
        "duration_ms": result.duration_ms,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/api/test_routes_output.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(api): /api/sessions/.../output → generate RESUMEN xlsx"
```

---

### Task 19: WebSocket route + main app wiring

**Files:**
- Create: `api/routes/ws.py`
- Create: `api/main.py`
- Modify (replace): `server.py` to use new app

- [ ] **Step 1: Implement `api/routes/ws.py` (lightweight FASE 1 — no progress events yet)**

`api/routes/ws.py`:
```python
"""WebSocket endpoint. FASE 1: just keeps connection alive + sends pings.
FASE 2 will broadcast scan progress events."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        while True:
            # FASE 1: just keep connection alive
            await asyncio.sleep(15)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        return
```

- [ ] **Step 2: Implement `api/main.py`**

```python
"""FastAPI app factory + lifespan."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import months, sessions, output, ws
from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


def _db_path() -> Path:
    return Path(os.environ.get(
        "OVERSEER_DB_PATH",
        "A:/PROJECTS/PDFoverseer/data/overseer.db",
    ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = open_connection(_db_path())
    init_schema(conn)
    manager = SessionManager(conn=conn)
    app.dependency_overrides[get_manager] = lambda: manager
    yield
    close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="PDFoverseer", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(months.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(output.router, prefix="/api")
    app.include_router(ws.router)
    return app


app = create_app()
```

- [ ] **Step 3: Replace `server.py`**

```python
"""Entry point for PDFoverseer FASE 1 backend."""

import uvicorn

from api.main import app

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
```

- [ ] **Step 4: Smoke test the server** (Windows PowerShell)

```powershell
# Start in background
Start-Process -FilePath "python" -ArgumentList "server.py" -NoNewWindow -PassThru | Tee-Object -Variable proc
Start-Sleep -Seconds 5
# Probe
Invoke-WebRequest -Uri "http://localhost:8000/api/months" -UseBasicParsing | Select-Object -ExpandProperty Content
# Stop
Stop-Process -Id $proc.Id -Force
```

Or skip this step — Task 25 E2E test exercises the same surface via FastAPI TestClient. Mark step done after running pytest.

Expected: JSON response with months array.

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/routes/ws.py server.py
git commit -m "feat(api): main app + lifespan + WS skeleton + server.py rewrite"
```

---

## Chunk 4: Frontend

### Task 20: Tear down old frontend + scaffold

**Files:**
- Modify: `frontend/src/App.jsx`
- Delete: existing component files that don't fit new architecture
- Create: `frontend/src/lib/format.js`

- [ ] **Step 1: Delete old components** (use `git rm` for clean tracking)

```bash
git rm frontend/src/components/Terminal.jsx
git rm frontend/src/components/IssueInbox.jsx
git rm frontend/src/components/CorrectionPanel.jsx
git rm frontend/src/components/HistoryModal.jsx
git rm frontend/src/components/ConfirmModal.jsx
# Keep: ProgressBar.jsx, HeaderBar.jsx, Sidebar.jsx (reusable, refactor later if needed)
```

On Windows PowerShell, `git rm` works the same. If git is not invoked, `Remove-Item <path>` per file.

- [ ] **Step 2: Install zustand if not present**

```bash
cd frontend
npm install zustand
```

- [ ] **Step 3: Replace `frontend/src/App.jsx`**

```jsx
import { useEffect, useState } from "react";
import { useSessionStore } from "./store/session";
import MonthOverview from "./views/MonthOverview";
import HospitalDetail from "./views/HospitalDetail";

export default function App() {
  const { view, hospital, setView } = useSessionStore();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="px-6 py-4 border-b border-slate-800 flex justify-between items-center">
        <h1 className="text-lg font-semibold">PDFoverseer</h1>
        <span className="text-sm text-slate-400">FASE 1 MVP</span>
      </header>
      <main className="p-6">
        {view === "month" && <MonthOverview />}
        {view === "hospital" && (
          <HospitalDetail hospital={hospital} onBack={() => setView("month")} />
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Commit teardown**

```bash
git add -A frontend/src/
git commit -m "chore(frontend): tear down single-PDF-session UI for FASE 1 overhaul"
```

---

### Task 21: API client + Zustand store

**Files:**
- Create: `frontend/src/lib/api.js`
- Create: `frontend/src/store/session.js`

- [ ] **Step 1: Implement `frontend/src/lib/api.js`**

```js
const BASE = "http://127.0.0.1:8000/api";

async function jsonOrThrow(res) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export const api = {
  listMonths: () => fetch(`${BASE}/months`).then(jsonOrThrow),
  getMonth: (sessionId) => fetch(`${BASE}/months/${sessionId}`).then(jsonOrThrow),
  createSession: (year, month) =>
    fetch(`${BASE}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month }),
    }).then(jsonOrThrow),
  getSession: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}`).then(jsonOrThrow),
  scanSession: (sessionId, scope = "all") =>
    fetch(`${BASE}/sessions/${sessionId}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope }),
    }).then(jsonOrThrow),
  generateOutput: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/output`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).then(jsonOrThrow),
};
```

- [ ] **Step 2: Implement `frontend/src/store/session.js`**

```js
import { create } from "zustand";
import { api } from "../lib/api";

export const useSessionStore = create((set, get) => ({
  view: "month",         // "month" | "hospital"
  hospital: null,        // currently-selected hospital
  months: [],
  session: null,
  loading: false,
  error: null,

  setView: (view) => set({ view }),

  loadMonths: async () => {
    set({ loading: true, error: null });
    try {
      const { months } = await api.listMonths();
      set({ months, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  openMonth: async (sessionId, year, month) => {
    set({ loading: true, error: null });
    try {
      await api.createSession(year, month);
      const session = await api.getSession(sessionId);
      set({ session, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  selectHospital: (hospital) => set({ view: "hospital", hospital }),

  runScan: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      await api.scanSession(sessionId);
      const session = await api.getSession(sessionId);
      set({ session, loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  generateOutput: async (sessionId) => {
    set({ loading: true, error: null });
    try {
      const result = await api.generateOutput(sessionId);
      set({ loading: false });
      return result;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },
}));
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/store/session.js
git commit -m "feat(frontend): API client + Zustand session store"
```

---

### Task 22: MonthOverview view + HospitalCard component

**Files:**
- Create: `frontend/src/views/MonthOverview.jsx`
- Create: `frontend/src/components/HospitalCard.jsx`

- [ ] **Step 1: Implement `frontend/src/components/HospitalCard.jsx`**

```jsx
export default function HospitalCard({ hospital, total, status, onClick }) {
  const isMissing = status === "missing";
  return (
    <button
      onClick={onClick}
      disabled={isMissing}
      className={`block w-full text-left rounded-lg border p-4 transition
        ${isMissing
          ? "border-slate-800 bg-slate-900/50 opacity-50 cursor-not-allowed"
          : "border-slate-700 bg-slate-900 hover:bg-slate-800 cursor-pointer"
        }`}
    >
      <div className="flex justify-between items-baseline">
        <h3 className="text-lg font-semibold">{hospital}</h3>
        <span className="text-sm text-slate-400">
          {isMissing ? "no normalizado" : ""}
        </span>
      </div>
      <p className="text-3xl font-bold mt-3">{isMissing ? "—" : total}</p>
      <p className="text-xs text-slate-400 mt-1">total documentos</p>
    </button>
  );
}
```

- [ ] **Step 2: Implement `frontend/src/views/MonthOverview.jsx`**

```jsx
import { useEffect } from "react";
import { useSessionStore } from "../store/session";
import HospitalCard from "../components/HospitalCard";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

export default function MonthOverview() {
  const {
    months, session, loading, error,
    loadMonths, openMonth, selectHospital, runScan, generateOutput,
  } = useSessionStore();

  useEffect(() => {
    loadMonths();
  }, [loadMonths]);

  const activeMonth = session?.session_id;
  const cells = session?.cells || {};

  const totalsByHospital = Object.fromEntries(
    HOSPITALS.map((h) => {
      const hospCells = cells[h] || {};
      const total = Object.values(hospCells).reduce(
        (s, cell) => s + (cell.user_override ?? cell.count ?? 0),
        0,
      );
      return [h, total];
    }),
  );

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-sm uppercase text-slate-400 mb-2">Mes</h2>
        <div className="flex gap-2 flex-wrap">
          {months.map((m) => (
            <button
              key={m.session_id}
              onClick={() => openMonth(m.session_id, m.year, m.month)}
              className={`px-3 py-1.5 rounded text-sm border transition
                ${activeMonth === m.session_id
                  ? "bg-indigo-600 border-indigo-500"
                  : "bg-slate-900 border-slate-700 hover:bg-slate-800"
                }`}
            >
              {m.name} {m.year}
            </button>
          ))}
        </div>
      </section>

      {session && (
        <>
          <section className="flex gap-3">
            <button
              onClick={() => runScan(session.session_id)}
              disabled={loading}
              className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? "Escaneando…" : "Escanear todo"}
            </button>
            <button
              onClick={async () => {
                const r = await generateOutput(session.session_id);
                alert(`Generado: ${r.output_path}`);
              }}
              disabled={loading}
              className="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50"
            >
              Generar Resumen
            </button>
          </section>

          <section>
            <h2 className="text-sm uppercase text-slate-400 mb-2">Hospitales</h2>
            <div className="grid grid-cols-4 gap-4">
              {HOSPITALS.map((h) => (
                <HospitalCard
                  key={h}
                  hospital={h}
                  total={totalsByHospital[h]}
                  status={cells[h] ? "present" : "missing"}
                  onClick={() => selectHospital(h)}
                />
              ))}
            </div>
          </section>
        </>
      )}

      {error && <p className="text-red-400">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/MonthOverview.jsx frontend/src/components/HospitalCard.jsx
git commit -m "feat(frontend): MonthOverview view + HospitalCard"
```

---

### Task 23: HospitalDetail view + CategoryRow + ScanIndicator + ConfidenceBadge

**Files:**
- Create: `frontend/src/views/HospitalDetail.jsx`
- Create: `frontend/src/components/CategoryRow.jsx`
- Create: `frontend/src/components/ScanIndicator.jsx`
- Create: `frontend/src/components/ConfidenceBadge.jsx`

- [ ] **Step 1: Implement `frontend/src/components/ScanIndicator.jsx`**

```jsx
const ICONS = {
  pending: { icon: "○", color: "text-slate-500" },
  scanning: { icon: "●", color: "text-blue-400 animate-pulse" },
  done_high: { icon: "✓", color: "text-emerald-400" },
  done_review: { icon: "⚠", color: "text-amber-400" },
  error: { icon: "✕", color: "text-red-400" },
  manual: { icon: "✎", color: "text-purple-400" },
};

export default function ScanIndicator({ status }) {
  const { icon, color } = ICONS[status] || ICONS.pending;
  return <span className={`text-lg ${color}`} aria-label={status}>{icon}</span>;
}
```

- [ ] **Step 2: Implement `frontend/src/components/ConfidenceBadge.jsx`**

```jsx
const COLORS = {
  high: "bg-emerald-700/30 text-emerald-300 border-emerald-700",
  medium: "bg-amber-700/30 text-amber-300 border-amber-700",
  low: "bg-red-700/30 text-red-300 border-red-700",
  manual: "bg-purple-700/30 text-purple-300 border-purple-700",
};

export default function ConfidenceBadge({ confidence }) {
  if (!confidence) return null;
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${COLORS[confidence] || COLORS.low}`}>
      {confidence.toUpperCase()}
    </span>
  );
}
```

- [ ] **Step 3: Implement `frontend/src/components/CategoryRow.jsx`**

```jsx
import ScanIndicator from "./ScanIndicator";
import ConfidenceBadge from "./ConfidenceBadge";

function deriveStatus(cell) {
  if (!cell) return "pending";
  if (cell.user_override != null) return "manual";
  if (cell.errors?.length) return "error";
  if (cell.flags?.includes("compilation_suspect")) return "done_review";
  if (cell.confidence === "high") return "done_high";
  return "done_review";
}

export default function CategoryRow({ sigla, cell, selected, onClick }) {
  const count = cell?.user_override ?? cell?.count ?? 0;
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded transition
        ${selected ? "bg-slate-800" : "hover:bg-slate-900"}`}
    >
      <ScanIndicator status={deriveStatus(cell)} />
      <span className="flex-1 text-left font-mono text-sm">{sigla}</span>
      <ConfidenceBadge confidence={cell?.confidence} />
      <span className="text-right tabular-nums font-semibold w-16">{count}</span>
    </button>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/views/HospitalDetail.jsx`**

```jsx
import { useState } from "react";
import { useSessionStore } from "../store/session";
import CategoryRow from "../components/CategoryRow";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
  "insgral", "bodega", "maquinaria", "ext", "senal", "exc",
  "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const [selected, setSelected] = useState(null);

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.count ?? 0), 0,
  );

  const selectedCell = selected ? cells[selected] : null;

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-200">
          ← Volver
        </button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-slate-400">Total: {total}</span>
      </header>

      <div className="grid grid-cols-2 gap-6">
        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Categorías</h3>
          <div className="space-y-0.5">
            {SIGLAS.map((s) => (
              <CategoryRow
                key={s}
                sigla={s}
                cell={cells[s]}
                selected={selected === s}
                onClick={() => setSelected(s)}
              />
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Detalle</h3>
          {!selectedCell && <p className="text-slate-500">Selecciona una categoría</p>}
          {selectedCell && (
            <div className="space-y-2 text-sm">
              <p><span className="text-slate-400">Sigla:</span> {selected}</p>
              <p><span className="text-slate-400">Count:</span> {selectedCell.count}</p>
              <p><span className="text-slate-400">Method:</span> {selectedCell.method}</p>
              <p><span className="text-slate-400">Confidence:</span> {selectedCell.confidence}</p>
              {selectedCell.flags?.length > 0 && (
                <p><span className="text-slate-400">Flags:</span> {selectedCell.flags.join(", ")}</p>
              )}
              {selectedCell.breakdown && (
                <div>
                  <p className="text-slate-400 mt-3">Subcarpetas:</p>
                  <ul className="ml-3 mt-1">
                    {Object.entries(selectedCell.breakdown).map(([k, v]) => (
                      <li key={k} className="font-mono text-xs">
                        · {k}: {v}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Manual smoke test**

```bash
# Backend in terminal 1
python server.py

# Frontend in terminal 2
cd frontend && npm run dev

# Open browser http://localhost:5173
# - Click ABRIL chip → loads
# - Click "Escanear todo" → waits → cells populate
# - Click HPV card → drill into HospitalDetail
# - Click a category row → side panel shows detail
# - Back to month → click Generar Resumen → alert with file path
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/HospitalDetail.jsx frontend/src/components/
git commit -m "feat(frontend): HospitalDetail view + CategoryRow + status badges"
```

---

## Chunk 5: Integration + DoD

### Task 24: ABRIL full corpus integration test

**Files:**
- Create: `tests/integration/__init__.py`, `tests/integration/test_abril_full_corpus.py`

- [ ] **Step 1: Write the integration test**

`tests/integration/test_abril_full_corpus.py`:
```python
from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, scan_month
from core.scanners.base import ConfidenceLevel


ABRIL = Path("A:/informe mensual/ABRIL")


@pytest.mark.slow
def test_abril_full_corpus_yields_54_cells():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    assert len(results) == 54


@pytest.mark.slow
def test_abril_hpv_art_high_count():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    r = results[("HPV", "art")]
    # 2026-05-11 corpus snapshot has 767; bound liberally
    assert 700 <= r.count <= 900
    assert r.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_abril_known_compilations_flagged():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    assert "compilation_suspect" in results[("HRB", "odi")].flags
    assert "compilation_suspect" in results[("HLU", "odi")].flags


@pytest.mark.slow
def test_abril_empty_categories_return_zero():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # 18.-CHPS for HRB and HLU is empty in 2026-05-11 snapshot
    assert results[("HRB", "chps")].count == 0
    assert results[("HLU", "chps")].count == 0
```

- [ ] **Step 2: Run the integration test**

```bash
pytest tests/integration/test_abril_full_corpus.py -v -m slow
```

Expected: 4 passed (may take 30-60 seconds due to parallel scans).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_abril_full_corpus.py
git commit -m "test(integration): ABRIL full corpus → 54 cells, expected counts + flags"
```

---

### Task 25: E2E smoke test (HTTP)

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/test_smoke.py`

- [ ] **Step 1: Write the smoke test**

`tests/e2e/test_smoke.py`:
```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.connection import open_connection, close_all
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "smoke.db"))
    app = create_app()
    conn = open_connection(tmp_path / "smoke.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    yield TestClient(app)
    close_all()


@pytest.mark.slow
def test_end_to_end_abril_flow(client, tmp_path):
    import openpyxl

    # 1) list months
    months = client.get("/api/months").json()["months"]
    abril = next(m for m in months if m["name"].upper() == "ABRIL")

    # 2) create session
    r = client.post("/api/sessions", json={
        "year": abril["year"], "month": abril["month"],
    })
    assert r.status_code in (200, 201)

    # 3) scan
    scan_result = client.post(
        f"/api/sessions/{abril['session_id']}/scan", json={"scope": "all"},
    ).json()
    assert scan_result["scanned"] == 54

    # 4) generate output
    out = client.post(
        f"/api/sessions/{abril['session_id']}/output", json={},
    ).json()
    output_path = Path(out["output_path"])
    assert output_path.exists()
    assert out["cells_written"] >= 50

    # 5) verify the actual Excel contents match scan results (spec §1.5 acceptance #2)
    wb = openpyxl.load_workbook(output_path)
    summary = scan_result["summary"]
    matched = 0
    for name in wb.defined_names:
        if not name.endswith("_count"):
            continue
        # name e.g. "HPV_art_count" → key "HPV_art"
        prefix = name[:-len("_count")]
        if prefix not in summary:
            continue
        destinations = list(wb.defined_names[name].destinations)
        sheet, coord = destinations[0]
        cell_value = wb[sheet][coord].value
        if cell_value is not None:
            assert cell_value == summary[prefix], (
                f"Cell {name} = {cell_value} but scan said {summary[prefix]}"
            )
            matched += 1
    # At least 50 of the 54 non-compilation cells should match
    assert matched >= 50, f"Only {matched} cells matched the scan result"
```

- [ ] **Step 2: Run**

```bash
pytest tests/e2e/test_smoke.py -v -m slow
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/__init__.py tests/e2e/test_smoke.py
git commit -m "test(e2e): smoke test for full ABRIL flow via HTTP"
```

---

### Task 26: README + memory updates

**Files:**
- Modify: `README.md` (add FASE 1 section)
- Modify: `CLAUDE.md` (note FASE 1 done)
- Update memory: `project_pdfoverseer_purpose.md`

- [ ] **Step 1: Update README.md**

Append a "FASE 1 MVP" section with quick start:

```markdown
## FASE 1 MVP (overhaul branch)

The `research/pixel-density` branch ships a folder-driven overhaul. Open
a month folder in `A:\informe mensual\<MES>\` and the app enumerates 4
hospitals × 18 categories, counts with filename-glob, and writes
`RESUMEN_<YYYY>-<MM>.xlsx` in `data/outputs/`.

Quick start:

```bash
python server.py            # backend :8000
cd frontend && npm run dev  # frontend :5173
```

For full design: `docs/superpowers/specs/2026-05-11-pdfoverseer-overhaul-design.md`.
```

- [ ] **Step 2: Update memory** (via Serena, not direct file edit)

The user's auto-memory should be updated via the appropriate memory tool, not direct file editing. Append a "FASE 1 status" section to `project_pdfoverseer_purpose.md` noting that the MVP shipped on `research/pixel-density` with tag `fase-1-mvp`. If using `mcp__serena__write_memory`, write to `domain_workflow_purpose` (Serena memory) too.

- [ ] **Step 3: Final ruff check**

```bash
ruff check .
```

Expected: 0 violations.

- [ ] **Step 4: Run full test suite**

```bash
pytest -m "not slow"     # fast tier
pytest -m slow           # slow tier (OCR + corpus reads)
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: FASE 1 MVP shipping notes + memory update"
```

---

### Task 27: FASE 1 DoD verification

- [ ] **Step 1: Manual verification checklist against spec §1.5**

Spec §1.5 "Success criteria FASE 1" requires:

1. [ ] Usuario abre la app, pica una carpeta de mes, ve los 4 hospitales con sus 18 categorías y conteos triviales en < 30 segundos
2. [ ] Genera el archivo Excel con valores correctos en las 54 celdas no-compiladas de ABRIL (HPV+HRB+HLU)
3. [ ] Ningún test de regresión existente falla
4. [ ] Sin OCR ejecutado en FASE 1 (todos los scanners son filename-glob)

Manual procedure:
- Time the workflow with a stopwatch
- Compare 5-10 sample cells against manual counts from RESUMEN sample
- Run full test suite (already done in Task 26)
- Grep `core/scanners/` for `import fitz` and `import pytesseract` — should appear only in `page_count_heuristic.py` (PyMuPDF for page-count, no Tesseract calls)

- [ ] **Step 2: Tag the milestone**

```bash
git tag -a fase-1-mvp -m "FASE 1 MVP shipped: filesystem-first orchestrator + filename scanners + Excel template output"
```

- [ ] **Step 3: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "chore: FASE 1 MVP DoD verified" --allow-empty
```

---

## Done condition for FASE 1

- All 27 tasks complete with their commits
- `pytest` (fast tier) is green
- `pytest -m slow` is green
- `ruff check .` reports 0 violations
- Manual smoke flow takes < 30 seconds to first count display
- Tag `fase-1-mvp` exists

Next: write FASE 2 implementation plan (OCR scanners for compilations + manual correction UI + WebSocket progress). Out of scope for THIS plan.
