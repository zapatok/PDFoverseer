# Increment A — Robust category-folder matching — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make category-folder resolution tolerant of `NN.-` renumbering (and the `CHPS`/`CPHS` spelling) so the six siglas broken by the 20-folder corpus drift (`exc`, `altura`, `caliente`, `herramientas_elec`, `andamios`, `chps`) resolve again — restoring their file lists and scannability — without changing any Excel number.

**Architecture:** One match rule in `core/domain.py` (strip the numeric index, compare text by equality or `+" "` prefix, with a small per-sigla alias map), used by both `folder_to_sigla` (reverse) and `core/orchestrator/enumeration.py::_find_category_folder` (forward). `CATEGORY_FOLDERS` is left untouched, so no existing test/fixture/Excel-range changes. All folder-resolution consumers (file list, scan, Excel checks/workers filter) benefit transitively.

**Tech Stack:** Python 3.10+, pytest, ruff. Backend only.

**Spec:** `docs/superpowers/specs/2026-06-22-folder-match-robust-design.md`

**Hard constraint:** Excel-neutral. The six restored siglas are all `count_type="documents"`; their Excel value comes from stored state (`present_files=None`), not folder resolution. Only `checks`/`workers` paths re-resolve live, and those siglas are all pre-senal (unshifted). A fresh *scan* will now correctly count the six (that is the fix); generating the Excel from existing state moves nothing.

---

## Chunk 1: Robust folder matching (single chunk)

### Task 1: The shared match rule in `core/domain.py`

**Files:**
- Modify: `core/domain.py` (add `_folder_text`, `_SIGLA_FOLDER_ALIASES`, `_match_texts`; reimplement `folder_to_sigla`; remove `_FOLDER_TO_SIGLA`; `CATEGORY_FOLDERS`/`SIGLAS`/`sigla_to_folder` unchanged)
- Test: `tests/unit/test_domain.py` (add cases; existing cases stay green unchanged)

Current code for reference (`core/domain.py:55-76`):
```python
_FOLDER_TO_SIGLA: dict[str, str] = {v: k for k, v in CATEGORY_FOLDERS.items()}

def sigla_to_folder(sigla: str) -> str:
    return CATEGORY_FOLDERS[sigla]

def folder_to_sigla(folder_name: str) -> str | None:
    for canonical, sigla in _FOLDER_TO_SIGLA.items():
        if folder_name == canonical or folder_name.startswith(canonical + " "):
            return sigla
    return None
```

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_domain.py`)

```python
def test_folder_to_sigla_current_disk_numbering():
    # 20-folder corpus: exc..andamios shifted, chps spelled CPHS
    assert folder_to_sigla("14.-Excavaciones y Vanos") == "exc"
    assert folder_to_sigla("15.-Trabajos en Altura") == "altura"
    assert folder_to_sigla("16.-Inspeccion Trabajos en Caliente") == "caliente"
    assert folder_to_sigla("18.-Inspeccion Herramientas Electricas") == "herramientas_elec"
    assert folder_to_sigla("19.-Andamios") == "andamios"
    assert folder_to_sigla("20.-CPHS") == "chps"


def test_folder_to_sigla_legacy_numbering_still_works():
    assert folder_to_sigla("13.-Excavaciones y Vanos") == "exc"
    assert folder_to_sigla("18.-CHPS") == "chps"


def test_folder_to_sigla_compound_name_with_suffix():
    assert folder_to_sigla("4.-Charlas 0") == "charla"
    assert folder_to_sigla("5.-Charla Integral 0") == "chintegral"


def test_folder_to_sigla_unmodeled_corpus_folders_return_none():
    assert folder_to_sigla("13.-Revision Documentacion Maquinaria") is None
    assert folder_to_sigla("17.-Espacios Confinados") is None


def test_folder_match_texts_pairwise_distinct():
    # Load-bearing no-collision guarantee for the startswith(+" ") predicate.
    from core.domain import CATEGORY_FOLDERS, _SIGLA_FOLDER_ALIASES, _folder_text

    texts = [_folder_text(v) for v in CATEGORY_FOLDERS.values()]
    for aliases in _SIGLA_FOLDER_ALIASES.values():
        texts.extend(aliases)
    for i, a in enumerate(texts):
        for j, b in enumerate(texts):
            if i == j:
                continue
            assert a != b, f"duplicate match text: {a!r}"
            assert not a.startswith(b + " "), f"{a!r} starts with {b!r} + ' '"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/test_domain.py -q`
Expected: the new tests FAIL (e.g. `folder_to_sigla("14.-Excavaciones y Vanos")` returns `None` today; `_folder_text` import error). Existing 5 tests still pass.

- [ ] **Step 3: Implement the rule** (`core/domain.py`)

Add `import re` to the imports. Replace the `_FOLDER_TO_SIGLA` line + `folder_to_sigla` body with:

```python
# Strip a leading "NN.-" numeric index from a category folder name so matching
# survives corpus renumbering (the live corpus inserts categories mid-list).
_INDEX_RE = re.compile(r"^\s*\d+\s*\.\s*-?\s*")


def _folder_text(name: str) -> str:
    """Return a folder name without its leading ``NN.-`` numeric index.

    Examples:
        '14.-Excavaciones y Vanos' -> 'Excavaciones y Vanos'
        '7.-ART 934' -> 'ART 934'
    """
    return _INDEX_RE.sub("", name).strip()


# Extra folder-text spellings a sigla also matches, beyond its canonical text.
# 'CPHS' is the real spelling on disk (Comité Paritario); the canonical 'CHPS'
# is a transposition typo kept only as the nominal fallback path.
_SIGLA_FOLDER_ALIASES: dict[str, tuple[str, ...]] = {
    "chps": ("CPHS",),
}


def _match_texts(sigla: str) -> tuple[str, ...]:
    """All folder texts (canonical + aliases) that resolve to ``sigla``."""
    return (_folder_text(CATEGORY_FOLDERS[sigla]), *_SIGLA_FOLDER_ALIASES.get(sigla, ()))
```

And reimplement `folder_to_sigla` (keep `sigla_to_folder` as-is):

```python
def folder_to_sigla(folder_name: str) -> str | None:
    """Map a folder name (any numeric prefix, with or without TOTAL/' 0' suffix)
    back to its sigla, or None if it matches no modeled category.

    Examples:
        '7.-ART' -> 'art'
        '14.-Excavaciones y Vanos' -> 'exc'   (renumbered)
        '20.-CPHS' -> 'chps'                  (alias spelling)
        '7.-ART 934' -> 'art'
        '13.-Revision Documentacion Maquinaria' -> None  (unmodeled)
    """
    text = _folder_text(folder_name)
    for sigla in CATEGORY_FOLDERS:
        for canon in _match_texts(sigla):
            if text == canon or text.startswith(canon + " "):
                return sigla
    return None
```

Delete the `_FOLDER_TO_SIGLA = {...}` line entirely.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/test_domain.py -q`
Expected: ALL pass — the 5 existing (roundtrip, `+" 0"`/`+" 934"`, unknown→None, the unchanged `"18.-CHPS"` constant assertion) and the 5 new.

- [ ] **Step 5: Commit**

```bash
git add core/domain.py tests/unit/test_domain.py
git commit -m "fix(domain): renumber-tolerant folder_to_sigla (text match + CPHS alias)"
```
(Co-Authored-By trailer: `Claude Opus 4.8 <noreply@anthropic.com>`.)

---

### Task 2: Route `_find_category_folder` through the rule

**Files:**
- Modify: `core/orchestrator/enumeration.py` (import `folder_to_sigla`; rewrite the iterdir match in `_find_category_folder`)
- Test: `tests/unit/test_orchestrator.py` (add a renumbered-layout case)

Current code (`core/orchestrator/enumeration.py:28-51`): the `for sub in hosp_dir.iterdir()` loop matches `sub.name == canonical or sub.name.startswith(canonical + " ")`.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_orchestrator.py`)

```python
def test_find_category_folder_resolves_renumbered_corpus(tmp_path):
    from core.domain import SIGLAS
    from core.orchestrator import _find_category_folder

    hosp = tmp_path / "HRB"
    # The current 20-folder disk layout (two inserted categories shift exc..chps).
    layout = [
        "1.-Reunion Prevencion", "2.-Induccion IRL", "3.-ODI Visitas",
        "4.-Charlas", "5.-Charla Integral", "6.-Difusion PTS", "7.-ART",
        "8.-Inspecciones Generales", "9.-Inspeccion Bodega",
        "10.-Inspeccion de Maquinaria", "11.-Extintores", "12.-Senaleticas",
        "13.-Revision Documentacion Maquinaria", "14.-Excavaciones y Vanos",
        "15.-Trabajos en Altura", "16.-Inspeccion Trabajos en Caliente",
        "17.-Espacios Confinados", "18.-Inspeccion Herramientas Electricas",
        "19.-Andamios", "20.-CPHS",
    ]
    for name in layout:
        (hosp / name).mkdir(parents=True)

    # the six shifted/renamed siglas resolve to the right on-disk folder
    assert _find_category_folder(hosp, "exc").name == "14.-Excavaciones y Vanos"
    assert _find_category_folder(hosp, "altura").name == "15.-Trabajos en Altura"
    assert _find_category_folder(hosp, "caliente").name == "16.-Inspeccion Trabajos en Caliente"
    assert _find_category_folder(hosp, "herramientas_elec").name == "18.-Inspeccion Herramientas Electricas"
    assert _find_category_folder(hosp, "andamios").name == "19.-Andamios"
    assert _find_category_folder(hosp, "chps").name == "20.-CPHS"
    # pre-senal siglas unaffected
    assert _find_category_folder(hosp, "art").name == "7.-ART"
    assert _find_category_folder(hosp, "maquinaria").name == "10.-Inspeccion de Maquinaria"
    # the two unmodeled folders are never returned for any sigla
    returned = {_find_category_folder(hosp, s).name for s in SIGLAS}
    assert "13.-Revision Documentacion Maquinaria" not in returned
    assert "17.-Espacios Confinados" not in returned


def test_find_category_folder_absent_hospital_returns_nominal(tmp_path):
    from core.orchestrator import _find_category_folder

    missing = tmp_path / "NOPE"
    p = _find_category_folder(missing, "caliente")
    assert not p.exists()
    assert p.name == "15.-Inspeccion Trabajos en Caliente"  # nominal canonical
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/test_orchestrator.py -q -k "find_category_folder"`
Expected: `test_find_category_folder_resolves_renumbered_corpus` FAILS (exc/caliente/etc. resolve to the nominal non-existent path, `.name` is the old-numbered canonical, not the disk folder). The absent-hospital test passes already.

- [ ] **Step 3: Implement**

In `core/orchestrator/enumeration.py`, extend the domain import:
```python
from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS, folder_to_sigla
```
Replace the iterdir loop in `_find_category_folder` so the match goes through the shared rule:
```python
def _find_category_folder(hosp_dir: Path, sigla: str) -> Path:
    """Locate the folder for `sigla` inside a hospital dir, tolerating numeric
    renumbering and TOTAL/' 0' suffixes.

    Args:
        hosp_dir: Path to the hospital directory.
        sigla: The category sigla to look up.

    Returns:
        Path to the category folder (nominal canonical path even if absent).
    """
    canonical = CATEGORY_FOLDERS[sigla]
    direct = hosp_dir / canonical
    if direct.exists():
        return direct
    if not hosp_dir.exists():
        return direct  # nominal path when hospital dir is absent
    # Renumber-tolerant: return the subdirectory whose name resolves to this sigla.
    for sub in hosp_dir.iterdir():
        if sub.is_dir() and folder_to_sigla(sub.name) == sigla:
            return sub
    return direct  # nominal path even if it doesn't exist
```
(No import cycle: `domain` does not import `orchestrator`.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/test_orchestrator.py -q`
Expected: all pass (new cases + existing orchestrator tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add core/orchestrator/enumeration.py tests/unit/test_orchestrator.py
git commit -m "fix(orchestrator): renumber-tolerant _find_category_folder via folder_to_sigla"
```

---

### Task 3: Excel-neutrality guard + full verification

**Files:**
- Test: `tests/unit/api/test_routes_output.py` (add a resolution-independence test)

- [ ] **Step 1: Write the test** (append to `tests/unit/api/test_routes_output.py`)

```python
def test_document_excel_value_independent_of_folder_resolution(tmp_path):
    # A document cell's Excel value comes from stored state, not folder
    # resolution — so the renumber fix cannot move it. month_root is bogus
    # (folder can't resolve) yet the value still equals the pure count.
    from api.routes.output import _build_cell_values
    from api.state import compute_cell_count

    cell = {"per_file": {"a.pdf": 7, "b.pdf": 5}}
    state = {
        "month_root": str(tmp_path / "nonexistent"),
        "cells": {"HRB": {"caliente": cell}},
    }
    values = _build_cell_values(state)
    assert values["HRB_caliente_count"] == compute_cell_count(cell, "documents", None)
```

- [ ] **Step 2: Run to verify it passes immediately** (this is a characterization guard, not red→green)

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/unit/api/test_routes_output.py -q -k "independent_of_folder_resolution"`
Expected: PASS (document path never touches the folder). If it FAILS, the Excel-neutrality assumption is wrong — STOP and report.

- [ ] **Step 3: Full default suite + lint**

Run: `.venv-cuda/Scripts/python.exe -m pytest -m "not slow" -q -p no:faulthandler`
Expected: all pass (prior baseline 688 + the new tests, 0 failures).

Run: `.venv-cuda/Scripts/python.exe -m ruff check core/ api/ tests/`
Expected: `All checks passed!` (in particular, no unused `_FOLDER_TO_SIGLA`).

- [ ] **Step 4: Slow integration guard (scan path)**

Run: `.venv-cuda/Scripts/python.exe -m pytest tests/integration/test_abril_full_corpus.py -q -p no:faulthandler`
Expected: all pass. In particular `test_abril_empty_categories_return_zero` still passes — ABRIL `HRB/20.-CPHS` and `HLU/20.-CPHS` are empty (verified 0 PDFs), so `chps` stays 0 even though it now resolves. (The six shifted folders now count correctly; none of their counts are asserted here.)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/api/test_routes_output.py
git commit -m "test(output): guard document Excel values are folder-resolution-independent"
```

---

## Live verification (read-only, on a COPY DB — not an automated step)

After the three tasks, verify against the real corpus without touching the real DB:

1. Copy `data/overseer.db` → `data/_smoke_A_overseer.db`; record the real DB's sha256.
2. Start the backend on a copy DB + port (e.g. `OVERSEER_DB_PATH=…_smoke_A… PORT=8010 server.py`).
3. Hit the cell-files endpoint for MAYO/HRB and confirm the six now return their real PDFs:
   `exc=1, altura=4, caliente=9, herramientas_elec=9, andamios=6`; `senal=0`, `chps=0` (empty on disk — correct). (Pre-fix these were all 0.)
4. **Excel-neutrality smoke:** `POST /sessions/2026-05/output` and diff the named-range values against a RESUMEN generated from the pre-A commit — document values must be unchanged (the six only change after an operator re-scan, not from this generation).
5. Stop the backend, delete the copy DB, confirm `data/overseer.db` sha256 unchanged.

---

## Notes
- DRY: one match rule, used forward and reverse. YAGNI: no dynamic per-session resolution, no model change (the two new categories are Increment B). TDD: red→green per task.
- Out of scope (Increment B): modeling `Revision Documentacion Maquinaria` + `Espacios Confinados`, their Excel rows/ranges, and the `chps`-in-Excel question.
- Commits stage explicit paths only (never `git add -A`).
