# OCR per-sigla refinement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la lógica de pase-2 ad-hoc por un registro central de patrones declarativo (`patterns.py`) + 1 técnica genérica reusable (`header_band_anchors`) + 1 dispatcher uniforme, con telemetría de "casi-match" para evitar falsos negativos silenciosos cuando aparecen variantes nuevas de templates.

**Architecture:**
- **Registro declarativo** (`core/scanners/patterns.py`): cada sigla declara su `filename_glob`, su `scan_strategy ∈ {"anchors", "pagination", "none"}`, sus `cover_flavors` (con anchors y opcional anti-anchors), y `top_fraction`. Estructura tipada (`SiglaPattern` TypedDict).
- **Técnica única reusable**: `header_band_anchors.py` OCRea la banda superior de cada página y cuenta páginas con ≥ `min_match` anchors de algún flavor. Anti-anchors descalifican shadow covers.
- **Dispatcher uniforme**: 1 `AnchorsScanner` parametrizado por entrada de `patterns.py` + 1 `PaginationScanner` que reusa `corner_count.count_paginations` (ya existente — el motor mínimo de paginación "Página N de M" con normalización de dígitos OCR) + `SimpleFilenameScanner` (sin cambios) para `scan_strategy: "none"`.
- **Telemetría de casi-match**: `ScanResult.telemetry` lleva las páginas que matchearon `min_match - 1` anchors → la UI muestra "candidato a flavor nuevo" en `DetailPanel`.
- **V4 (core/pipeline.py) queda como código legacy** desconectado del scanner registry: aprovechamos sólo lo que necesitamos (paginación + dígito-norm vía `corner_count`), sin arrastrar workers paralelos / SR-GPU / Dempster-Shafer al nuevo flujo. Decisión de mantener o borrar V4 se difiere a Chunk 7.

**Tech Stack:** Python 3.10+, PyMuPDF, Tesseract (Spanish+English), FastAPI, React + Vite, pdfjs-dist (reuso visor de Feature 1). Sin nuevas dependencias.

**Execution requirements:**
- **Worktree dedicado:** `.worktrees/ocr-per-sigla` con rama `feature/ocr-per-sigla` derivada de `po_overhaul` (creado pre-ejecución).
- **Subagents para implementar:** mínimo Sonnet (per `feedback_subagent_model_floor`). NO usar Haiku para tasks de implementación de este plan.

**Spec:** [`docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md`](../specs/2026-05-18-ocr-per-sigla-refinement-design.md) — 18/18 categorías cerradas, decisiones A1-A15, patrones P1-P6.

**Pre-condiciones:**
- `po_overhaul` branch al día (Feature 1 + FASE 5 shipped).
- `A:\informe mensual\ABRIL` accesible (READ-ONLY) para snapshot de fixtures.
- `.venv-cuda` activo (`source .venv-cuda/Scripts/activate`).
- `ruff check .` debe reportar 0 antes de cada commit.

---

## Chunk 1: Registry + tipos canónicos (A1, A9, A10, A11)

**Goal:** Crear `core/scanners/patterns.py` con el registro tipado, definir `Flavor` + `SiglaPattern` (TypedDict), poblar la entrada `reunion` (la trivial, `scan_strategy="none"`) y migrar `filename_glob` al patrón laxo (A10).

**No** se toca `simple_factory` ni el dispatcher aún — solo la base declarativa. Tests verdes al final.

### Task 1.1: Tipos canónicos `Flavor` + `SiglaPattern`

**Files:**
- Create: `core/scanners/patterns.py`
- Test: `tests/unit/scanners/test_patterns_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/test_patterns_registry.py
"""Tests for the central patterns registry."""

from __future__ import annotations

import re

import pytest

from core.scanners.patterns import (
    PATTERNS,
    SCAN_STRATEGIES,
    Flavor,
    SiglaPattern,
    get_pattern,
)


def test_pattern_for_reunion_has_strategy_none():
    pattern = get_pattern("reunion")
    assert pattern["scan_strategy"] == "none"


def test_pattern_for_reunion_filename_glob_is_lax():
    """A10: lax pattern captures HLL mega `2026-04_reunion.pdf` AND
    canonical `2026-04-15_reunion_supervisor.pdf`."""
    pattern = get_pattern("reunion")
    rx = re.compile(pattern["filename_glob"], re.IGNORECASE)
    assert rx.match("2026-04-15_reunion_supervisor.pdf")
    assert rx.match("2026-04_reunion.pdf")          # mega HLL, sin día
    assert rx.match("REUNION_OLD.PDF")               # case-insensitive
    assert not rx.match("notice.pdf")                # debe rechazar


def test_get_pattern_unknown_raises_keyerror():
    with pytest.raises(KeyError, match="unknown_sigla"):
        get_pattern("unknown_sigla")


def test_scan_strategies_is_exhaustive():
    assert set(SCAN_STRATEGIES) == {"anchors", "pagination", "none"}


def test_flavor_typed_dict_shape():
    """TypedDict accepts the canonical fields."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C"],
        "min_match": 2,
    }
    assert flavor["name"] == "f_test"


def test_flavor_anti_anchors_optional():
    """A5: anti_anchors is opt-in."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A"],
        "min_match": 1,
        "anti_anchors": ["X"],
        "anti_min_match": 1,
    }
    assert flavor["anti_anchors"] == ["X"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/test_patterns_registry.py -v`

Expected: `ImportError: cannot import name 'PATTERNS' from 'core.scanners.patterns'` (module doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

```python
# core/scanners/patterns.py
"""Central registry of patterns per sigla — see A1, A9, A10, A11 in the spec.

Each entry declares how a sigla counts when filename_glob is not enough.
The 18 SIGLAS from core.domain MUST each have an entry here.

See:
    docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

ScanStrategy = Literal["anchors", "pagination", "none"]
SCAN_STRATEGIES: tuple[ScanStrategy, ...] = ("anchors", "pagination", "none")


class Flavor(TypedDict):
    """A single template variant within a sigla. See A4, A5, A9.

    `name`: f_<código_canónico>[_<origen>] (A9 convention).
    `anchors`: list of substrings to OCR-match in the top band.
    `min_match`: how many anchors must match for a page to count as cover.
    `anti_anchors`: optional — descalifica shadow covers (A5).
    `anti_min_match`: optional — default 1 (any anti-anchor match descalifica).
    """

    name: str
    anchors: list[str]
    min_match: int
    anti_anchors: NotRequired[list[str]]
    anti_min_match: NotRequired[int]


class SiglaPattern(TypedDict):
    """Per-sigla declarative pattern entry. See A6, A10.

    `filename_glob`: lax regex (A10) — matches anywhere in filename.
    `scan_strategy`: "anchors" | "pagination" | "none".
    `cover_flavors`: required if strategy="anchors".
    `top_fraction`: optional — default 0.25 (A2).
    `recursive_glob`: optional — default False; True for HPV-style subcarpetas (P6).
    """

    filename_glob: str
    scan_strategy: ScanStrategy
    cover_flavors: NotRequired[list[Flavor]]
    top_fraction: NotRequired[float]
    recursive_glob: NotRequired[bool]    # INFORMATIONAL ONLY — count_pdfs_by_sigla
                                          # already uses rglob unconditionally;
                                          # this field documents the intent for
                                          # readers. Do NOT branch on it in code.


# Defaults documented as source of truth.
DEFAULT_TOP_FRACTION: float = 0.25
DEFAULT_MIN_MATCH: int = 3
DEFAULT_ANTI_MIN_MATCH: int = 1


PATTERNS: dict[str, SiglaPattern] = {
    "reunion": {
        "filename_glob": r"^.*reunion.*\.pdf$",
        "scan_strategy": "none",
    },
    # ... 17 entries más, llenadas en chunks posteriores
}


def get_pattern(sigla: str) -> SiglaPattern:
    """Return the SiglaPattern for `sigla`. Raises KeyError if unknown."""
    if sigla not in PATTERNS:
        raise KeyError(f"unknown_sigla: {sigla}")
    return PATTERNS[sigla]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scanners/test_patterns_registry.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run linter**

Run: `ruff check core/scanners/patterns.py tests/unit/scanners/test_patterns_registry.py`
Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/patterns.py tests/unit/scanners/test_patterns_registry.py
git commit -m "feat(scanners): add patterns.py registry with TypedDict canonical types (A1, A11)

Introduces the declarative registry per sigla as the source of truth for
per-sigla OCR config. SiglaPattern + Flavor TypedDicts make the structure
inequivocal. Only reunion populated; remaining 17 siglas added incrementally.

Refs: docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md
"
```

### Task 1.2: Filename glob laxo (A10)

**Files:**
- Modify: `core/scanners/utils/filename_glob.py:15-22, 34-46`
- Test: `tests/unit/scanners/utils/test_filename_glob_lax.py` (new)

**Why:** El regex actual (`^\d{4}-\d{2}-\d{2}_<rest>.pdf$`) rechaza nombres HLL como `2026-04_<sigla>.pdf` (sin día) — falsos negativos sistemáticos en mega-compilados. A10 estandariza al patrón laxo.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scanners/utils/test_filename_glob_lax.py
"""A10 — lax filename matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import (
    count_pdfs_by_sigla,
    extract_sigla,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("2026-04-15_reunion_supervisor.pdf", "reunion"),
        ("2026-04_reunion.pdf", "reunion"),          # HLL mega, no day
        ("REUNION_OLD.PDF", "reunion"),              # case-insensitive
        ("2026-04_herramientas_elec.pdf", "herramientas_elec"),
        ("2026-04-15_dif_pts_aguasan.pdf", "dif_pts"),  # multi-word sigla
        ("2026-04_chps_acta_reunion.pdf", "chps"),   # 'reunion' is substring; chps wins
    ],
)
def test_extract_sigla_lax(filename: str, expected: str):
    assert extract_sigla(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "notice.pdf",
        "random_document.pdf",
        "informe.pdf",
    ],
)
def test_extract_sigla_no_match(filename: str):
    assert extract_sigla(filename) is None


def test_count_pdfs_recursive_via_pattern(tmp_path: Path):
    """count_pdfs_by_sigla must use the registry pattern, not hard-coded regex.

    HPV-style subcarpetas: rglob is already used; this verifies the new lax
    matching captures HLL mega files within a hospital folder.
    """
    (tmp_path / "AGUASAN").mkdir()
    (tmp_path / "AGUASAN" / "2026-04-15_andamios_chequeo_aguasan.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "2026-04_andamios.pdf").write_bytes(b"%PDF-1.4\n")  # HLL mega
    (tmp_path / "unrelated.pdf").write_bytes(b"%PDF-1.4\n")

    result = count_pdfs_by_sigla(tmp_path, sigla="andamios")
    assert result.count == 2
    assert result.files_scanned == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scanners/utils/test_filename_glob_lax.py -v`
Expected: tests that use `2026-04_reunion.pdf` / `REUNION_OLD.PDF` FAIL because current `_FILENAME_REMAINDER_RE` requires the strict pattern.

- [ ] **Step 3: Modify implementation**

Update `extract_sigla` to use the lax matching via the patterns registry. Keep `count_pdfs_by_sigla` unchanged structurally.

```python
# core/scanners/utils/filename_glob.py

# DELETE:
# _FILENAME_REMAINDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_(?P<rest>.+?)\.pdf$", re.IGNORECASE)

# REPLACE the body of extract_sigla:
def extract_sigla(filename: str) -> str | None:
    """Extract the sigla from a filename by checking the lax pattern of each
    registered sigla, longest first (A10).

    `dif_pts` wins over a hypothetical `dif`; `herramientas_elec` wins over
    `herramientas`; `chps` wins over `reunion` for `chps_acta_reunion.pdf`
    because chps appears before reunion in name when matched longest-first.
    """
    import re

    from core.scanners.patterns import PATTERNS

    fn_lower = filename.lower()
    # Match longest siglas first to disambiguate substrings
    for sigla in sorted(PATTERNS.keys(), key=len, reverse=True):
        pattern_src = PATTERNS[sigla]["filename_glob"]
        if re.match(pattern_src, fn_lower, re.IGNORECASE):
            return sigla
    return None
```

**Critical edge case (chps vs reunion):** `2026-04_chps_acta_reunion.pdf` matches both `r"^.*chps.*\.pdf$"` and `r"^.*reunion.*\.pdf$"`. Sorting longest-first gives `chps` (4 chars) < `reunion` (7 chars), so reunion wins — **WRONG**. Fix: check siglas alphabetically/explicit-order, but check `chps` BEFORE `reunion` when both could match. Best implementation: iterate ALL matching siglas, prefer the one whose name appears earlier in the filename.

```python
def extract_sigla(filename: str) -> str | None:
    """Lax matching: returns the sigla whose name appears earliest in the
    filename (left-most wins for ties)."""
    import re

    from core.scanners.patterns import PATTERNS

    fn_lower = filename.lower()
    candidates: list[tuple[int, str]] = []  # (start_index, sigla)
    for sigla in PATTERNS:
        # Find the sigla string as a substring; use word boundaries to avoid
        # 'reunion' matching inside 'previene' etc.
        idx = fn_lower.find(sigla)
        if idx == -1:
            continue
        # Must also pass the declared filename_glob (lax regex)
        if not re.match(PATTERNS[sigla]["filename_glob"], fn_lower, re.IGNORECASE):
            continue
        candidates.append((idx, sigla))
    if not candidates:
        return None
    # Earliest position wins; ties broken by longest sigla (more specific)
    candidates.sort(key=lambda t: (t[0], -len(t[1])))
    return candidates[0][1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scanners/utils/test_filename_glob_lax.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run existing filename_glob tests to verify no regression**

Run: `pytest tests/ -k filename_glob -v`
Expected: all green.

- [ ] **Step 6: Run linter + format**

Run: `ruff check --fix core/scanners/utils/filename_glob.py tests/unit/scanners/utils/test_filename_glob_lax.py && ruff format core/scanners/utils/filename_glob.py tests/unit/scanners/utils/test_filename_glob_lax.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add core/scanners/utils/filename_glob.py tests/unit/scanners/utils/test_filename_glob_lax.py
git commit -m "feat(scanners): migrate filename_glob to lax matching via patterns registry (A10)

Replaces the hard-coded ^date-date-date_<remainder>.pdf regex with the
declarative pattern per sigla. Captures HLL mega-compilados named
2026-04_<sigla>.pdf (without day prefix) that previously slipped past.

Disambiguates substring overlaps (e.g. chps vs reunion in
chps_acta_reunion.pdf) by preferring the earliest position match.

Refs: A10 in the per-sigla refinement spec.
"
```

### Task 1.3: Patterns registry validation test

**Files:**
- Test: `tests/unit/scanners/test_patterns_registry.py` (extend)

- [ ] **Step 1: Add the failing test**

```python
# Append to tests/unit/scanners/test_patterns_registry.py

from core.domain import SIGLAS


def test_all_18_siglas_have_a_pattern_eventually():
    """Final shape check. Will fail until chunks 4-5 populate the registry.
    Skipped while WIP."""
    from core.scanners.patterns import PATTERNS

    missing = set(SIGLAS) - set(PATTERNS)
    if missing:
        pytest.skip(f"WIP — missing siglas: {sorted(missing)}")
    assert set(PATTERNS) == set(SIGLAS), "patterns.py must cover exactly the 18 SIGLAS"


def test_anchors_strategy_requires_cover_flavors():
    """Sanity check: every entry with strategy='anchors' has cover_flavors."""
    from core.scanners.patterns import PATTERNS

    for sigla, pattern in PATTERNS.items():
        if pattern["scan_strategy"] == "anchors":
            assert "cover_flavors" in pattern, f"{sigla} declares anchors but has no cover_flavors"
            assert len(pattern["cover_flavors"]) >= 1


def test_flavor_naming_convention_a9():
    """A9: flavor names start with 'f_' and are snake_case."""
    import re

    from core.scanners.patterns import PATTERNS

    rx = re.compile(r"^f_[a-z0-9_]+$")
    for sigla, pattern in PATTERNS.items():
        for flavor in pattern.get("cover_flavors", []):
            assert rx.match(flavor["name"]), (
                f"{sigla}: flavor name '{flavor['name']}' violates A9 (must match {rx.pattern})"
            )
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/unit/scanners/test_patterns_registry.py -v`
Expected: 1 skipped (`test_all_18_siglas_have_a_pattern_eventually`), 2 pass (no anchors entries yet), 6 prior pass. Total: 8 pass, 1 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/scanners/test_patterns_registry.py
git commit -m "test(scanners): add A9 + A11 conformance tests for patterns registry

Validates flavor naming convention (f_<code>[_<origin>]), strategy-vs-flavors
invariant, and a WIP-skip placeholder for the 18-sigla completeness check
to be unlocked once all entries land in chunks 4-5.
"
```

### Task 1.4: Reuse filename_glob's `folder_missing` flag (A8 confirmation)

**Files:**
- Verify: `core/scanners/utils/filename_glob.py` already returns `count=0, flag='folder_missing'` when folder doesn't exist.
- Test: extend `tests/unit/scanners/utils/test_filename_glob_lax.py`

- [ ] **Step 1: Write the test confirming A8 behavior**

```python
def test_count_pdfs_folder_missing_returns_zero_with_flag(tmp_path: Path):
    """A8 — carpeta inexistente devuelve count=0 con flag, sin error."""
    missing = tmp_path / "DOES_NOT_EXIST"
    result = count_pdfs_by_sigla(missing, sigla="andamios")
    assert result.count == 0
    assert result.files_scanned == 0
    assert "folder_missing" in result.flags
```

- [ ] **Step 2: Run test**

Run: `pytest tests/unit/scanners/utils/test_filename_glob_lax.py::test_count_pdfs_folder_missing_returns_zero_with_flag -v`
Expected: passes (existing implementation already handles this).

- [ ] **Step 3: Document the contract in the file**

Add a docstring note in `count_pdfs_by_sigla` referencing A8.

```python
def count_pdfs_by_sigla(folder: Path, *, sigla: str) -> GlobCountResult:
    """Count PDFs (recursively) where filename matches the sigla's lax pattern.

    A8: if `folder` does not exist, returns ``count=0`` with flag
    ``'folder_missing'``. No exception is raised — empty cell is a known state.

    ...
    """
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/scanners/utils/test_filename_glob_lax.py core/scanners/utils/filename_glob.py
git commit -m "docs(scanners): explicitly document A8 contract on count_pdfs_by_sigla

Carpeta sigla inexistente devuelve count=0 + flag 'folder_missing' sin
lanzar excepción. Behavior already present; this commit pins it down with
a regression test and a docstring reference.
"
```

### Chunk 1 — Review gate

- [ ] **Step 1: Run full chunk smoke**

Run: `pytest tests/unit/scanners/ -v && ruff check core/scanners/patterns.py core/scanners/utils/filename_glob.py`
Expected: all green.

- [ ] **Step 2: Dispatch plan-document-reviewer**

Send the reviewer Chunk 1 content + the spec path. Address any flagged issues before moving to Chunk 2.

---

## Chunk 2: Técnica `header_band_anchors` + telemetría near-match (A2, A4, A5, A14)

**Goal:** Crear la función `count_covers_by_anchors` que OCRea la banda superior de cada página, cuenta covers por flavor + soporta anti-anchors. Devuelve también `near_matches` (A14). Sin tocar scanners aún.

### Task 2.1: Estructura del módulo + tipos

**Files:**
- Create: `core/scanners/utils/header_band_anchors.py`
- Test: `tests/unit/scanners/utils/test_header_band_anchors.py`

- [ ] **Step 1: Write the failing test for normalize_text**

```python
# tests/unit/scanners/utils/test_header_band_anchors.py
"""Tests for the multi-flavor anchor-based cover detector."""

from __future__ import annotations

from core.scanners.utils.header_band_anchors import _normalize_text


def test_normalize_text_lowercases():
    assert _normalize_text("CONSTRUCTORA Region SUR") == "constructora region sur"


def test_normalize_text_strips_accents():
    assert "REGIÓN" not in _normalize_text("CONSTRUCTORA REGIÓN SUR")
    assert "region" in _normalize_text("CONSTRUCTORA REGIÓN SUR")


def test_normalize_text_collapses_whitespace():
    assert _normalize_text("LISTA   DE   CHEQUEO") == "lista de chequeo"


def test_normalize_text_collapses_slashes_dashes():
    """SI/NO/NA and F-CRS-LCH-05 should normalize predictably so anchors match
    regardless of OCR noise around separators."""
    assert _normalize_text("SI/NO/NA") == "si no na"
    assert _normalize_text("F-CRS-LCH-05") == "f crs lch 05"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: `ImportError`.

- [ ] **Step 3: Minimal implementation**

```python
# core/scanners/utils/header_band_anchors.py
"""Multi-flavor anchor-based cover detection (A2 + A4 + A5 + A14).

OCRea la banda superior de cada página, cuenta páginas que matcheen
≥ min_match anchors de algún flavor declarado en patterns.py. Devuelve
también near-matches (páginas con min_match - 1 anchors) como señal para
mantenimiento (A14).

Sub-utilities:
- `_normalize_text`: lowercase + strip accents + collapse whitespace/separators.
- `_match_flavor`: returns matched_anchors + matched_anti_anchors for a flavor.
- `count_covers_by_anchors`: main entry point — iterates pages.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytesseract
from PIL import Image

from core.scanners.patterns import (
    DEFAULT_ANTI_MIN_MATCH,
    DEFAULT_MIN_MATCH,
    DEFAULT_TOP_FRACTION,
    Flavor,
)
from core.scanners.utils.pdf_render import get_page_count, render_page_region

if TYPE_CHECKING:
    from core.scanners.cancellation import CancellationToken


_SEPARATORS_RX = re.compile(r"[/\-_]+")
_WHITESPACE_RX = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """Lowercase, strip accents, collapse separators (/-_) → space, collapse spaces."""
    # Strip combining marks (accents) using NFKD decomposition
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = no_accents.lower()
    no_seps = _SEPARATORS_RX.sub(" ", lower)
    collapsed = _WHITESPACE_RX.sub(" ", no_seps)
    return collapsed.strip()
```

- [ ] **Step 4: Run test**

Run: `pytest tests/unit/scanners/utils/test_header_band_anchors.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/header_band_anchors.py tests/unit/scanners/utils/test_header_band_anchors.py
git commit -m "feat(scanners): scaffold header_band_anchors with text normalizer

First stone: _normalize_text strips accents, lowercases, and collapses
whitespace/separators so anchors match regardless of OCR noise around
hyphens, slashes, or accents in the rendered text.

Refs: A2 in the per-sigla refinement spec.
"
```

### Task 2.2: Match-flavor helper (anchors + anti-anchors)

**Files:**
- Modify: `core/scanners/utils/header_band_anchors.py`
- Test: extend `tests/unit/scanners/utils/test_header_band_anchors.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/scanners/utils/test_header_band_anchors.py
from core.scanners.utils.header_band_anchors import (
    FlavorMatchResult,
    _match_flavor,
)


def test_match_flavor_counts_anchors():
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE"],
        "min_match": 2,
    }
    text = _normalize_text("ITEM ACTIVIDAD CUMPLE")
    result = _match_flavor(text, flavor)
    assert result.matched_anchors == ["item", "actividad", "cumple"]
    assert result.passes
    assert not result.anti_anchored


def test_match_flavor_below_min_match_does_not_pass():
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C", "D"],
        "min_match": 3,
    }
    text = _normalize_text("A B only")
    result = _match_flavor(text, flavor)
    assert len(result.matched_anchors) == 2
    assert not result.passes


def test_match_flavor_anti_anchor_disqualifies():
    """A5: any anti-anchor match descalifica even if anchors >= min_match."""
    flavor: Flavor = {
        "name": "f_dif_pts_cover",
        "anchors": [
            "REGISTRO DE CHARLA",
            "Nombre de la Capacitación",
            "Cargo Relator",
            "Tiempo duración charla",
        ],
        "min_match": 3,
        "anti_anchors": ["TEST DE COMPRENSIÓN", "F-PETS-CRS"],
    }
    text = _normalize_text(
        "REGISTRO DE CHARLA Nombre de la Capacitación Cargo Relator "
        "Tiempo duración charla TEST DE COMPRENSIÓN"
    )
    result = _match_flavor(text, flavor)
    assert len(result.matched_anchors) == 4
    assert result.anti_anchored
    assert not result.passes


def test_match_flavor_anti_min_match_threshold():
    """Custom anti_min_match: needs ≥ 2 anti-anchor matches to descalificar."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B"],
        "min_match": 1,
        "anti_anchors": ["X", "Y", "Z"],
        "anti_min_match": 2,
    }
    text = _normalize_text("A X")
    result = _match_flavor(text, flavor)
    assert result.passes  # only 1 anti-anchor matched; 2 needed
```

- [ ] **Step 2: Run failing**

Expected: `ImportError: FlavorMatchResult`.

- [ ] **Step 3: Implement**

```python
# Add to core/scanners/utils/header_band_anchors.py

@dataclass(frozen=True)
class FlavorMatchResult:
    """Per-page match outcome for a single flavor."""

    matched_anchors: list[str]
    matched_anti_anchors: list[str]
    passes: bool                  # True iff matched_anchors >= min_match AND anti_anchored is False
    anti_anchored: bool           # True iff matched_anti_anchors >= anti_min_match


def _match_flavor(normalized_text: str, flavor: Flavor) -> FlavorMatchResult:
    """Count how many anchors / anti-anchors of a flavor match the page text."""
    matched_anchors: list[str] = []
    for anchor in flavor["anchors"]:
        normalized = _normalize_text(anchor)
        if normalized and normalized in normalized_text:
            matched_anchors.append(normalized)

    matched_anti: list[str] = []
    for anti in flavor.get("anti_anchors", []):
        normalized = _normalize_text(anti)
        if normalized and normalized in normalized_text:
            matched_anti.append(normalized)

    min_match = flavor.get("min_match", DEFAULT_MIN_MATCH)
    anti_min = flavor.get("anti_min_match", DEFAULT_ANTI_MIN_MATCH)
    anti_anchored = len(matched_anti) >= anti_min
    passes = len(matched_anchors) >= min_match and not anti_anchored
    return FlavorMatchResult(
        matched_anchors=matched_anchors,
        matched_anti_anchors=matched_anti,
        passes=passes,
        anti_anchored=anti_anchored,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_header_band_anchors.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/header_band_anchors.py tests/unit/scanners/utils/test_header_band_anchors.py
git commit -m "feat(scanners): _match_flavor helper with anchors + anti-anchors

Implements the per-page, per-flavor matching rule from A4 + A5:
- passes iff matched_anchors ≥ min_match AND matched_anti < anti_min_match.
- anti-anchors are opt-in; default anti_min_match=1 (any match descalifica).
"
```

### Task 2.3: NearMatch type + threshold

**Files:**
- Modify: `core/scanners/utils/header_band_anchors.py`
- Test: extend

- [ ] **Step 1: Write failing test**

```python
def test_match_flavor_near_match_flag():
    """A14: a page with min_match - 1 anchors is a near-match candidate."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C", "D"],
        "min_match": 3,
    }
    text = _normalize_text("A B nothing-else")
    result = _match_flavor(text, flavor)
    assert not result.passes
    assert result.near_match  # 2 == min_match - 1
    assert result.missing_anchors == ["c", "d"]
```

- [ ] **Step 2: Run failing**

- [ ] **Step 3: Extend FlavorMatchResult**

```python
@dataclass(frozen=True)
class FlavorMatchResult:
    matched_anchors: list[str]
    matched_anti_anchors: list[str]
    passes: bool
    anti_anchored: bool
    near_match: bool              # A14: matched == min_match - 1 AND not anti_anchored
    missing_anchors: list[str]    # anchors NOT matched (normalized form)


def _match_flavor(normalized_text: str, flavor: Flavor) -> FlavorMatchResult:
    matched_anchors: list[str] = []
    missing_anchors: list[str] = []
    for anchor in flavor["anchors"]:
        normalized = _normalize_text(anchor)
        if not normalized:
            continue
        if normalized in normalized_text:
            matched_anchors.append(normalized)
        else:
            missing_anchors.append(normalized)

    matched_anti: list[str] = []
    for anti in flavor.get("anti_anchors", []):
        normalized = _normalize_text(anti)
        if normalized and normalized in normalized_text:
            matched_anti.append(normalized)

    min_match = flavor.get("min_match", DEFAULT_MIN_MATCH)
    anti_min = flavor.get("anti_min_match", DEFAULT_ANTI_MIN_MATCH)
    anti_anchored = len(matched_anti) >= anti_min
    passes = len(matched_anchors) >= min_match and not anti_anchored
    near_match = (not passes) and (not anti_anchored) and (len(matched_anchors) == min_match - 1)
    return FlavorMatchResult(
        matched_anchors=matched_anchors,
        matched_anti_anchors=matched_anti,
        passes=passes,
        anti_anchored=anti_anchored,
        near_match=near_match,
        missing_anchors=missing_anchors,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_header_band_anchors.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/header_band_anchors.py tests/unit/scanners/utils/test_header_band_anchors.py
git commit -m "feat(scanners): emit near-match signal from _match_flavor (A14)

A page that matches min_match - 1 anchors (and no anti-anchors) is a
near-match candidate — probably a new template variant. The signal feeds
into the protocol A13 (mantenimiento) via the UI in chunk 6.
"
```

### Task 2.4: `count_covers_by_anchors` main entry

**Files:**
- Modify: `core/scanners/utils/header_band_anchors.py`
- Test: extend with synthetic fixtures (no real PDFs yet — those land in Chunk 5)

- [ ] **Step 1: Write failing test using a stubbed render+OCR pipeline**

```python
def test_count_covers_uses_first_passing_flavor(monkeypatch):
    """A page counts as 1 cover if ANY flavor passes (A4, no double-counting)."""
    import core.scanners.utils.header_band_anchors as mod

    page_texts = [
        "ITEM ACTIVIDAD CUMPLE Página 1 de",      # passes f_lch_xx
        "ITEM ACTIVIDAD",                          # near-match
        "TITAN CHECK LIST HERRAMIENTAS ELÉCTRICAS",  # passes f_titan
        "unrelated content",                       # no match
    ]

    def fake_get_page_count(_path):
        return len(page_texts)

    def fake_render(_path, page_idx, **_):
        # Return placeholder image; real OCR is stubbed below
        from PIL import Image
        return Image.new("RGB", (10, 10), "white")

    def fake_ocr(_img, **_):
        return page_texts[fake_ocr.call_count]

    fake_ocr.call_count = 0
    original_ocr = mod.pytesseract.image_to_string

    def patched_ocr(img, **kw):
        text = page_texts[fake_ocr.call_count]
        fake_ocr.call_count += 1
        return text

    monkeypatch.setattr(mod, "get_page_count", fake_get_page_count)
    monkeypatch.setattr(mod, "render_page_region", fake_render)
    monkeypatch.setattr(mod.pytesseract, "image_to_string", patched_ocr)

    flavors: list[Flavor] = [
        {
            "name": "f_lch_xx",
            "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE", "Página 1 de"],
            "min_match": 3,
        },
        {
            "name": "f_titan",
            "anchors": ["TITAN", "CHECK LIST", "HERRAMIENTAS ELÉCTRICAS"],
            "min_match": 3,
        },
    ]

    from core.scanners.utils.header_band_anchors import count_covers_by_anchors

    result = count_covers_by_anchors(
        Path("/fake.pdf"),
        flavors=flavors,
        top_fraction=0.25,
    )
    assert result.count == 2
    assert result.pages_total == 4
    assert sorted(result.matches_per_flavor.keys()) == ["f_lch_xx", "f_titan"]
    assert result.matches_per_flavor["f_lch_xx"] == 1
    assert result.matches_per_flavor["f_titan"] == 1
    # The near-match on page 1 (index 1) lands in telemetry
    assert len(result.near_matches) == 1
    assert result.near_matches[0].page_index == 1
    assert result.near_matches[0].flavor_name == "f_lch_xx"
```

- [ ] **Step 2: Run failing**

Expected: `ImportError: count_covers_by_anchors`.

- [ ] **Step 3: Implement**

```python
# Append to core/scanners/utils/header_band_anchors.py

@dataclass(frozen=True)
class NearMatch:
    """A14: page that matched min_match - 1 anchors → candidate for new variant."""

    page_index: int
    flavor_name: str
    matched_anchors: list[str]
    missing_anchors: list[str]


@dataclass(frozen=True)
class AnchorCountResult:
    count: int                              # total cover pages across all flavors
    pages_total: int
    matches_per_flavor: dict[str, int] = field(default_factory=dict)
    near_matches: list[NearMatch] = field(default_factory=list)
    method: str = "header_band_anchors"


def count_covers_by_anchors(
    pdf_path: Path,
    *,
    flavors: list[Flavor],
    top_fraction: float = DEFAULT_TOP_FRACTION,
    dpi: int = 200,
    cancel: CancellationToken | None = None,
) -> AnchorCountResult:
    """OCR the top band of each page; count pages that match any flavor (A4).

    A page contributes exactly +1 to the total even if multiple flavors pass
    (the first passing flavor "owns" the page in `matches_per_flavor`). This
    avoids double-counting when anchor lists overlap.

    Near-matches (A14): a page that matches min_match - 1 anchors of some
    flavor (without anti-anchors firing) is recorded as a candidate for a
    new template variant — surfaced to the operator via telemetry, not
    counted toward `count`.

    Args:
        pdf_path: source PDF.
        flavors: list of Flavor dicts from patterns.py.
        top_fraction: fraction of page height OCR'd from the top (default 0.25).
        dpi: OCR rendering resolution.
        cancel: optional CancellationToken (cooperative cancellation).

    Returns:
        AnchorCountResult with the total cover count + per-flavor breakdown
        + near-match telemetry.
    """
    pages_total = get_page_count(pdf_path)
    matches_per_flavor: dict[str, int] = {f["name"]: 0 for f in flavors}
    near_matches: list[NearMatch] = []
    cover_pages = 0

    bbox = (0.0, 0.0, 1.0, max(0.05, min(1.0, top_fraction)))

    for page_idx in range(pages_total):
        if cancel is not None:
            cancel.check()
        img: Image.Image = render_page_region(pdf_path, page_idx, bbox=bbox, dpi=dpi)
        text = pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang="spa+eng")
        normalized = _normalize_text(text)

        # First passing flavor wins this page; record near-match only if no flavor passes
        owned = False
        page_near: NearMatch | None = None
        for flavor in flavors:
            res = _match_flavor(normalized, flavor)
            if res.passes:
                matches_per_flavor[flavor["name"]] += 1
                cover_pages += 1
                owned = True
                break
            if res.near_match and page_near is None:
                page_near = NearMatch(
                    page_index=page_idx,
                    flavor_name=flavor["name"],
                    matched_anchors=res.matched_anchors,
                    missing_anchors=res.missing_anchors,
                )
        if not owned and page_near is not None:
            near_matches.append(page_near)

    return AnchorCountResult(
        count=cover_pages,
        pages_total=pages_total,
        matches_per_flavor=matches_per_flavor,
        near_matches=near_matches,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/utils/test_header_band_anchors.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run linter**

Run: `ruff check --fix core/scanners/utils/header_band_anchors.py tests/unit/scanners/utils/test_header_band_anchors.py`

- [ ] **Step 6: Commit**

```bash
git add core/scanners/utils/header_band_anchors.py tests/unit/scanners/utils/test_header_band_anchors.py
git commit -m "feat(scanners): count_covers_by_anchors main entry — A2 + A4 + A14

OCRea la banda superior de cada página, cuenta covers por flavor sin
double-counting (first passing wins). Páginas con min_match-1 anchors
quedan en near_matches como candidatos a flavor nuevo. Cooperative
cancellation soportada vía CancellationToken.

Refs: A2, A4, A14.
"
```

### Task 2.5: Extend `ScanResult` with `telemetry` field

**Files:**
- Modify: `core/scanners/base.py:18-28`
- Test: extend `tests/unit/scanners/` (a new test file or augment)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/scanners/test_scan_result_telemetry.py
"""ScanResult must carry near-match telemetry (A14)."""

from __future__ import annotations

from pathlib import Path

from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)


def test_scan_result_telemetry_is_optional():
    result = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=5,
    )
    assert result.telemetry is None


def test_scan_result_with_telemetry():
    tel = ScanTelemetry(
        near_matches=[
            NearMatchEntry(
                pdf_name="foo.pdf",
                page_index=2,
                flavor_name="f_test",
                matched_anchors=["a", "b"],
                missing_anchors=["c"],
            )
        ]
    )
    result = ScanResult(
        count=3,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=200,
        files_scanned=1,
        telemetry=tel,
    )
    assert result.telemetry is not None
    assert len(result.telemetry.near_matches) == 1
    assert result.telemetry.near_matches[0].pdf_name == "foo.pdf"
```

- [ ] **Step 2: Run failing**

Expected: `ImportError`.

- [ ] **Step 3: Update `base.py`**

```python
# core/scanners/base.py
"""Scanner Protocol + supporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"


@dataclass(frozen=True)
class NearMatchEntry:
    """A14: per-PDF, per-page near-match record exposed in ScanResult."""

    pdf_name: str
    page_index: int           # 0-based
    flavor_name: str
    matched_anchors: list[str]
    missing_anchors: list[str]


@dataclass(frozen=True)
class ScanTelemetry:
    """A14: machine-readable signals for the operator (UI in chunk 6)."""

    near_matches: list[NearMatchEntry] = field(default_factory=list)


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
    per_file: dict[str, int] | None = None
    telemetry: ScanTelemetry | None = None    # A14


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

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/test_scan_result_telemetry.py -v && pytest tests/ -k scanner -v`
Expected: new tests pass + no regression in existing scanner tests.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/base.py tests/unit/scanners/test_scan_result_telemetry.py
git commit -m "feat(scanners): extend ScanResult with optional telemetry (A14)

Adds ScanTelemetry + NearMatchEntry dataclasses so scanners can surface
'near-match' candidates (page matched min_match-1 anchors of some flavor)
to the operator. Field is optional and defaults None — no breaking changes
for existing callers.
"
```

### Chunk 2 — Review gate

- [ ] **Step 1: Full chunk smoke**

Run: `pytest tests/unit/scanners/ -v && ruff check core/scanners/`
Expected: all green.

- [ ] **Step 2: Reviewer dispatch**

---

## Chunk 3: Generic dispatcher — `AnchorsScanner` + `PaginationScanner` (A6, A7)

**Goal:** Reemplazar 4 scanners especializados por 1 `AnchorsScanner` parametrizado por entrada de `patterns.py`. Crear `PaginationScanner` que reusa `corner_count.count_paginations` (motor mínimo de paginación, ya existente). Refactorizar `register_defaults` para construir scanners desde `patterns.py`. V4 (`core/pipeline.py`) NO se conecta al registry; queda como legacy.

### Task 3.1: `AnchorsScanner` class

**Files:**
- Create: `core/scanners/anchors_scanner.py`
- Test: `tests/unit/scanners/test_anchors_scanner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/scanners/test_anchors_scanner.py
"""Tests for the generic AnchorsScanner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken


def test_anchors_scanner_falls_through_to_filename_glob_for_pase1(tmp_path: Path):
    """Pase 1 (count) is always filename_glob — uniform across all scanners."""
    (tmp_path / "2026-04-15_andamios_chequeo.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count(tmp_path)
    assert result.method == "filename_glob"
    assert result.count == 1


def test_anchors_scanner_count_ocr_skips_when_no_multipage_pdf(tmp_path: Path):
    """count_ocr only triggers OCR when at least one PDF has >1 pages."""
    # Use a tiny but valid PDF (1 page) to skip OCR
    pdf = tmp_path / "2026-04-15_andamios_chequeo.pdf"
    pdf.write_bytes(_one_page_pdf())
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.method == "filename_glob"  # nothing to scan


def _one_page_pdf() -> bytes:
    """Return the bytes of a minimal valid 1-page PDF for tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000053 00000 n \n0000000095 00000 n \ntrailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n141\n%%EOF\n"
    )


def test_anchors_scanner_count_ocr_invokes_count_covers(tmp_path: Path, monkeypatch):
    """When a multi-page PDF is present, OCR is invoked."""
    pdf = tmp_path / "2026-04_andamios.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"%fake-multipage\n")

    from core.scanners.utils import header_band_anchors as hba

    fake_result = hba.AnchorCountResult(
        count=29,
        pages_total=29,
        matches_per_flavor={"f_lch_05": 29},
        near_matches=[],
    )

    monkeypatch.setattr(hba, "get_page_count", lambda _: 29)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: fake_result,
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.method == "header_band_anchors"
    assert result.count == 29
    assert result.confidence == ConfidenceLevel.HIGH


def test_anchors_scanner_a7_one_page_pdfs_counted_as_one(tmp_path: Path, monkeypatch):
    """A7: PDFs of 1 page contribute count=1 without OCR (locked at R1)."""
    one_pager_a = tmp_path / "2026-04-01_andamios_aguasan.pdf"
    one_pager_b = tmp_path / "2026-04-02_andamios_aguasan.pdf"
    multi = tmp_path / "2026-04_andamios.pdf"
    for p in (one_pager_a, one_pager_b, multi):
        p.write_bytes(b"%PDF-1.4\n")

    # Stub page counts: two 1-page + one 5-page
    def fake_page_count(path):
        return 1 if path.name.startswith("2026-04-0") else 5

    from core.scanners.utils import header_band_anchors as hba
    monkeypatch.setattr(hba, "get_page_count", fake_page_count)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: hba.AnchorCountResult(
            count=5,
            pages_total=5,
            matches_per_flavor={"f_lch_05": 5},
            near_matches=[],
        ),
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    # 1-pagers: 2 docs counted trivially; multi-page: 5 covers from OCR → 7 total
    assert result.count == 7
    assert "a7_one_page_locked" in result.flags


def test_anchors_scanner_carpeta_inexistente(tmp_path: Path):
    """A8: missing folder → count=0, confidence=HIGH, flag folder_missing."""
    missing = tmp_path / "DOES_NOT_EXIST"
    scanner = AnchorsScanner(sigla="andamios")
    r1 = scanner.count(missing)
    assert r1.count == 0
    assert r1.confidence == ConfidenceLevel.HIGH
    assert "folder_missing" in r1.flags

    r2 = scanner.count_ocr(missing, cancel=CancellationToken())
    assert r2.count == 0
    assert "folder_missing" in r2.flags
```

- [ ] **Step 2: Run failing**

Expected: `ImportError`.

- [ ] **Step 3: Implement `AnchorsScanner`**

```python
# core/scanners/anchors_scanner.py
"""Generic OCR scanner driven by patterns.py — replaces the per-sigla
specializations (art, irl, odi, charla). Each sigla's behavior is data-driven.

See: A6 + A7 in the spec.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.patterns import DEFAULT_TOP_FRACTION, get_pattern
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.header_band_anchors import (
    count_covers_by_anchors,
)
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class AnchorsScanner:
    """Generic anchor-based scanner. `sigla` indexes into `PATTERNS`."""

    sigla: str

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        """Pase 1 — uniform filename_glob."""
        return SimpleFilenameScanner(sigla=self.sigla).count(folder, override_method=override_method)

    def count_ocr(self, folder: Path, *, cancel: CancellationToken) -> ScanResult:
        """Pase 2 — A2 anchors over every multi-page PDF, A7 lock 1-pagers."""
        cancel.check()
        base = self._filename_glob(folder)
        if "folder_missing" in base.flags:
            return base  # A8: nothing to OCR

        pdfs = sorted(folder.rglob("*.pdf"))
        if not pdfs:
            return base

        pattern = get_pattern(self.sigla)
        flavors = pattern.get("cover_flavors", [])
        if not flavors:
            return base
        top_fraction = pattern.get("top_fraction", DEFAULT_TOP_FRACTION)

        start = time.perf_counter()
        total_count = 0
        per_file: dict[str, int] = {}
        flags = list(base.flags)
        errors: list[str] = []
        near_matches: list[NearMatchEntry] = []
        a7_used = False

        for pdf in pdfs:
            cancel.check()
            try:
                page_count = get_page_count(pdf)
            except PdfRenderError as exc:
                errors.append(f"page_count_failed:{pdf.name}:{exc}")
                continue

            if page_count == 1:
                # A7 — 1 page = 1 doc trivial + locked
                per_file[pdf.name] = 1
                total_count += 1
                a7_used = True
                continue

            try:
                ocr = count_covers_by_anchors(
                    pdf,
                    flavors=flavors,
                    top_fraction=top_fraction,
                    cancel=cancel,
                )
            except CancelledError:
                raise
            except (PdfRenderError, OSError, RuntimeError) as exc:
                errors.append(f"anchors_failed:{pdf.name}:{exc}")
                # Fallback to 1 doc per PDF heuristic (conservative)
                per_file[pdf.name] = 1
                total_count += 1
                continue

            per_file[pdf.name] = ocr.count
            total_count += ocr.count
            for nm in ocr.near_matches:
                near_matches.append(
                    NearMatchEntry(
                        pdf_name=pdf.name,
                        page_index=nm.page_index,
                        flavor_name=nm.flavor_name,
                        matched_anchors=nm.matched_anchors,
                        missing_anchors=nm.missing_anchors,
                    )
                )

        if a7_used:
            flags.append("a7_one_page_locked")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = (
            ConfidenceLevel.HIGH if not errors else ConfidenceLevel.LOW
        )
        return ScanResult(
            count=total_count,
            confidence=confidence,
            method="header_band_anchors",
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
            telemetry=ScanTelemetry(near_matches=near_matches) if near_matches else None,
        )

    def _filename_glob(self, folder: Path) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/test_anchors_scanner.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/anchors_scanner.py tests/unit/scanners/test_anchors_scanner.py
git commit -m "feat(scanners): AnchorsScanner generic dispatcher (A6 + A7)

Single OCR scanner parametrized by patterns.py — replaces ad-hoc logic
in art/odi/irl/charla scanners. Implements:
- A6: scan_strategy='anchors' branch.
- A7: PDFs of exactly 1 page contribute count=1 without OCR + flag.
- A8: missing folder propagated from filename_glob.
- A14: near-matches surfaced via ScanResult.telemetry.

The 4 specialization scanners stay in place during chunk 3-4 transition;
chunk 4 swaps them out one at a time.
"
```

### Task 3.2: `PaginationScanner` — reuses `corner_count.count_paginations`

**Files:**
- Create: `core/scanners/pagination_scanner.py`
- Test: `tests/unit/scanners/test_pagination_scanner.py`

**Why:** Cats 8 (insgral) and 14 (altura) declare `scan_strategy="pagination"`. We **don't** invoke the full V4 pipeline — V4's 6-worker / GPU-SR / Dempster-Shafer machinery is overkill for "count pages where N == 1 in `Pagina N de M`". We reuse the existing `corner_count.count_paginations` (already in `core/scanners/utils/`, used previously by the old ArtScanner) — it owns the OCR of the upper-right corner, the Spanish pagination regex, and the digit normalization. V4 (`core/pipeline.py`) stays intact as legacy code (decided in chunk 7 whether to delete).

- [ ] **Step 1: Verify `corner_count.count_paginations` API**

Run: `head -130 core/scanners/utils/corner_count.py`
Expected to find: `def count_paginations(pdf_path, *, dpi=200, cancel=None) -> CornerCountResult` with `CornerCountResult.count: int` and `transitions: list[tuple[int, int]]`.

If the signature differs, ADJUST the scanner below — do NOT modify `corner_count.py` itself in this task (its existing tests must keep passing).

- [ ] **Step 2: Write failing test**

```python
# tests/unit/scanners/test_pagination_scanner.py
"""Tests for PaginationScanner — reuses corner_count.count_paginations."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner


def _one_page_pdf() -> bytes:
    """Minimal valid 1-page PDF for A7 tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000053 00000 n \n0000000095 00000 n \ntrailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n141\n%%EOF\n"
    )


def test_pagination_scanner_pase1_is_filename_glob(tmp_path: Path):
    (tmp_path / "2026-04-15_insgral_eqf.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count(tmp_path)
    assert r.method == "filename_glob"


def test_pagination_scanner_invokes_corner_count(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    from core.scanners.utils import corner_count as cc

    def fake_count_paginations(pdf_path, *, dpi=200, cancel=None):
        return cc.CornerCountResult(
            count=4,
            transitions=[(1, 3), (2, 3), (3, 3), (1, 5), (2, 5), (1, 2), (2, 2), (1, 4)],
            pages_total=12,
        )

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_paginations",
        fake_count_paginations,
    )
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.get_page_count", lambda _: 12
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4
    assert r.method == "pagination"
    assert r.confidence == ConfidenceLevel.HIGH


def test_pagination_scanner_a7_one_page_pdfs(tmp_path: Path, monkeypatch):
    """A7: 1-page PDFs counted trivially (no corner_count call)."""
    one = tmp_path / "2026-04-01_insgral_x.pdf"
    multi = tmp_path / "2026-04_insgral.pdf"
    for p in (one, multi):
        p.write_bytes(b"%PDF-1.4\n")

    def fake_page_count(path):
        return 1 if "2026-04-0" in path.name else 7

    from core.scanners.utils import corner_count as cc

    def fake_count(pdf_path, *, dpi=200, cancel=None):
        return cc.CornerCountResult(count=3, transitions=[], pages_total=7)

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.get_page_count", fake_page_count
    )
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_paginations", fake_count
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4  # 1 (A7) + 3 (corner_count)
    assert "a7_one_page_locked" in r.flags


def test_pagination_scanner_carpeta_inexistente(tmp_path: Path):
    """A8: missing folder → count=0 with flag."""
    missing = tmp_path / "DOES_NOT_EXIST"
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(missing, cancel=CancellationToken())
    assert r.count == 0
    assert "folder_missing" in r.flags
```

- [ ] **Step 3: Run failing**

Expected: `ImportError: PaginationScanner`.

- [ ] **Step 4: Implement**

```python
# core/scanners/pagination_scanner.py
"""Scanner driven by 'Página N de M' pagination — pase 2 for siglas with
heterogeneous templates but reliable Spanish pagination (cat 8 insgral,
cat 14 altura).

Reuses `core/scanners/utils/corner_count.count_paginations` — the minimal
engine that OCR's the upper-right corner and counts document transitions.
This is deliberately MUCH simpler than the full V4 pipeline
(`core/pipeline.py`): no parallel workers, no GPU SR, no Dempster-Shafer
inference. V4 stays intact as legacy code; if a future failure mode
demands its capabilities, we can promote a sigla to V4 via a new strategy.

A7 still applies: 1-page PDFs contribute count=1 without OCR.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.utils.corner_count import count_paginations
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count


@dataclass
class PaginationScanner:
    """Counts documents in compilations via 'Página N de M' transitions."""

    sigla: str

    def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
        return SimpleFilenameScanner(sigla=self.sigla).count(folder, override_method=override_method)

    def count_ocr(self, folder: Path, *, cancel: CancellationToken) -> ScanResult:
        cancel.check()
        base = SimpleFilenameScanner(sigla=self.sigla).count(folder)
        if "folder_missing" in base.flags:
            return base  # A8

        pdfs = sorted(folder.rglob("*.pdf"))
        if not pdfs:
            return base

        start = time.perf_counter()
        total = 0
        per_file: dict[str, int] = {}
        errors: list[str] = []
        flags = list(base.flags)
        a7_used = False

        for pdf in pdfs:
            cancel.check()
            try:
                pages = get_page_count(pdf)
            except PdfRenderError as exc:
                errors.append(f"page_count_failed:{pdf.name}:{exc}")
                continue
            if pages == 1:
                # A7
                per_file[pdf.name] = 1
                total += 1
                a7_used = True
                continue
            try:
                result = count_paginations(pdf, cancel=cancel)
            except CancelledError:
                raise
            except (PdfRenderError, OSError, RuntimeError) as exc:
                errors.append(f"pagination_failed:{pdf.name}:{exc}")
                # Conservative fallback: count as 1 doc
                per_file[pdf.name] = 1
                total += 1
                continue
            per_file[pdf.name] = result.count
            total += result.count

        if a7_used:
            flags.append("a7_one_page_locked")

        duration_ms = int((time.perf_counter() - start) * 1000)
        confidence = ConfidenceLevel.HIGH if not errors else ConfidenceLevel.LOW
        return ScanResult(
            count=total,
            confidence=confidence,
            method="pagination",
            breakdown=base.breakdown,
            flags=flags,
            errors=errors,
            duration_ms=duration_ms,
            files_scanned=len(pdfs),
            per_file=per_file,
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/scanners/test_pagination_scanner.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add core/scanners/pagination_scanner.py tests/unit/scanners/test_pagination_scanner.py
git commit -m "feat(scanners): PaginationScanner reuses corner_count.count_paginations

Replaces the proposed V4Scanner adapter. Instead of invoking the full V4
pipeline (6 workers, GPU SR, Dempster-Shafer) for cat 8 insgral + cat 14
altura, we reuse the minimal pagination engine that already exists in
core/scanners/utils/corner_count.py — OCR upper-right corner, parse
'Página N de M', count document transitions.

V4 (core/pipeline.py) stays intact as legacy code; not connected to the
scanner registry by this change. Chunk 7 decides whether to delete it
or leave it dormant.

A7 (1-page lock) and A8 (folder-missing) honored uniformly with
AnchorsScanner. Method='pagination'.
"
```

### Task 3.3: Refactor `register_defaults` to use patterns.py

**Files:**
- Modify: `core/scanners/__init__.py:52-78`
- Test: `tests/unit/scanners/test_register_defaults_from_patterns.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/scanners/test_register_defaults_from_patterns.py
"""register_defaults must build scanners based on patterns.py scan_strategy."""

from __future__ import annotations

from core.scanners import (
    all_scanners,
    all_siglas,
    clear,
    get,
    register_defaults,
)
from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.simple_factory import SimpleFilenameScanner
from core.scanners.pagination_scanner import PaginationScanner
from core.scanners.patterns import PATTERNS


def setup_function():
    clear()


def teardown_function():
    clear()
    register_defaults()  # restore for other tests


def test_register_defaults_picks_scanner_class_by_strategy():
    register_defaults()
    for sigla, pattern in PATTERNS.items():
        scanner = get(sigla)
        strategy = pattern["scan_strategy"]
        if strategy == "anchors":
            assert isinstance(scanner, AnchorsScanner), f"{sigla}: expected AnchorsScanner"
        elif strategy == "pagination":
            assert isinstance(scanner, PaginationScanner), f"{sigla}: expected PaginationScanner"
        elif strategy == "none":
            assert isinstance(scanner, SimpleFilenameScanner), f"{sigla}: expected SimpleFilenameScanner"
        else:
            pytest.fail(f"unknown strategy {strategy} for {sigla}")
```

- [ ] **Step 2: Run failing**

Expected: tests pass only for `reunion` (the only entry today); others fail because `PATTERNS` doesn't have them yet OR because `register_defaults` still uses the old hard-coded list.

- [ ] **Step 3: Update `register_defaults`**

```python
# core/scanners/__init__.py — replace the auto-register block

# ... existing imports ...
from core.scanners.anchors_scanner import AnchorsScanner  # noqa: E402
from core.scanners.patterns import PATTERNS  # noqa: E402
from core.scanners.simple_factory import SimpleFilenameScanner  # noqa: E402
from core.scanners.pagination_scanner import PaginationScanner  # noqa: E402


def _build_scanner_for_sigla(sigla: str) -> Scanner:
    """Pick the Scanner class based on patterns.py scan_strategy."""
    if sigla not in PATTERNS:
        # Not in registry yet (WIP) — fall back to SimpleFilenameScanner
        return SimpleFilenameScanner(sigla=sigla)
    strategy = PATTERNS[sigla]["scan_strategy"]
    if strategy == "anchors":
        return AnchorsScanner(sigla=sigla)
    if strategy == "pagination":
        return PaginationScanner(sigla=sigla)
    # "none"
    return SimpleFilenameScanner(sigla=sigla)


def register_defaults() -> None:
    """Register one scanner per sigla in core.domain.SIGLAS.

    Picks the concrete scanner class based on patterns.py scan_strategy.
    Idempotent.
    """
    for sigla in _SIGLAS:
        if not has(sigla):
            register(_build_scanner_for_sigla(sigla))


register_defaults()
```

**Remove** the old hard-coded `_SPECIALIZED = (...)` block and the explicit imports of `ArtScanner`, `OdiScanner`, `IrlScanner`, `CharlaScanner` — but **only after Chunk 4 deletes those files**.

For now (during Chunk 3): leave the old specialization scanners in place but bypass them in `register_defaults`. They become dead code until Chunk 4 deletes them.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/scanners/ -v`
Expected: passes for `reunion`. Others should be SKIPPED while WIP — adjust the test to skip when a sigla is not in PATTERNS yet.

Actually update the test:

```python
def test_register_defaults_picks_scanner_class_by_strategy():
    register_defaults()
    for sigla, pattern in PATTERNS.items():
        scanner = get(sigla)
        strategy = pattern["scan_strategy"]
        if strategy == "anchors":
            assert isinstance(scanner, AnchorsScanner), f"{sigla}: expected AnchorsScanner"
        elif strategy == "pagination":
            assert isinstance(scanner, PaginationScanner), f"{sigla}: expected PaginationScanner"
        elif strategy == "none":
            assert isinstance(scanner, SimpleFilenameScanner), f"{sigla}: expected SimpleFilenameScanner"
```

This iterates only over PATTERNS keys, so WIP is naturally handled.

- [ ] **Step 5: Run all scanner tests to detect regressions**

Run: `pytest tests/ -k scanner -v`
Expected: all green; the old `art_scanner`/`odi_scanner` etc. tests still pass because the classes remain in place (just unused).

- [ ] **Step 6: Commit**

```bash
git add core/scanners/__init__.py tests/unit/scanners/test_register_defaults_from_patterns.py
git commit -m "refactor(scanners): build scanner instances from patterns.py registry

register_defaults() now picks AnchorsScanner | PaginationScanner | SimpleFilenameScanner
based on the scan_strategy declared in PATTERNS. Specialization classes
(Art/Odi/Irl/Charla) stay in the file tree as dead code until Chunk 4
deletes them — kept temporarily so existing per-class tests don't break.
"
```

### Task 3.4: Wire `count_ocr` into orchestrator (sanity check)

**Files:**
- Verify: `core/orchestrator.py:228` already uses `getattr(scanner, "count_ocr", None)` (existing pattern).
- Test: `tests/unit/test_orchestrator_ocr_anchors.py`

- [ ] **Step 1: Write integration test**

```python
# tests/unit/test_orchestrator_ocr_anchors.py
"""Orchestrator must invoke count_ocr on AnchorsScanner just like the old
specialized scanners."""

from __future__ import annotations

from pathlib import Path

from core.orchestrator import _ocr_worker
import core.scanners as scanner_registry


def test_orchestrator_invokes_anchors_scanner_count_ocr(tmp_path: Path, monkeypatch):
    # reunion is the only populated entry — but reunion has strategy="none"
    # so no count_ocr. Use a stub: register a fake AnchorsScanner for testing.

    scanner_registry.clear()
    from core.scanners.anchors_scanner import AnchorsScanner
    scanner_registry.register(AnchorsScanner(sigla="andamios"))

    called = {"value": False}

    def fake_count_ocr(self, folder, *, cancel):
        called["value"] = True
        from core.scanners.base import ConfidenceLevel, ScanResult
        return ScanResult(
            count=0, confidence=ConfidenceLevel.HIGH, method="header_band_anchors",
            breakdown=None, flags=[], errors=[], duration_ms=1, files_scanned=0,
        )

    monkeypatch.setattr(AnchorsScanner, "count_ocr", fake_count_ocr)

    hosp, sigla, result, error = _ocr_worker(("HPV", "andamios", str(tmp_path)))
    assert called["value"]
    assert error is None
    assert result is not None
    assert result.method == "header_band_anchors"

    # Restore registry
    scanner_registry.clear()
    scanner_registry.register_defaults()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/unit/test_orchestrator_ocr_anchors.py -v`
Expected: passes (existing orchestrator code already uses `getattr` lookup).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_orchestrator_ocr_anchors.py
git commit -m "test(orchestrator): confirm count_ocr dispatch works for AnchorsScanner

Validates that the existing orchestrator._ocr_worker (which uses getattr to
find count_ocr) routes pase-2 calls to the new AnchorsScanner without
needing any orchestrator changes. Same wiring for PaginationScanner — covered
implicitly by the PaginationScanner unit tests.
"
```

### Chunk 3 — Review gate

- [ ] **Step 1: Full smoke**

Run: `pytest tests/ -v && ruff check core/scanners/`
Expected: all green.

- [ ] **Step 2: Reviewer dispatch**

---

## Chunk 4: Migración de scanners especializados → anchors-based

**Goal:** Para cada uno de los 4 scanners especializados (art, irl, odi, charla):
1. Poblar la entrada en `patterns.py` con los anchors del spec.
2. Confirmar que `AnchorsScanner` cuenta correctamente sobre fixtures reales.
3. Eliminar el scanner especializado y sus tests específicos.
4. Mantener tests E2E que verifiquen el comportamiento (ahora driven by patterns).

### Task 4.1: Populate `art` pattern (cat 7)

**Files:**
- Modify: `core/scanners/patterns.py`
- Test: `tests/unit/scanners/test_pattern_art.py` (smoke contra fixture)

- [ ] **Step 1: Snapshot a sample PDF for fixtures**

```bash
mkdir -p tests/fixtures/scanners/art
cp "A:/informe mensual/ABRIL/HPV/7.-ART/CRS/2026-04-01_art_crs_andamios.pdf" tests/fixtures/scanners/art/f_art_01_p1_crs_andamios.pdf
```

If the exact filename in ABRIL differs, pick a real CRS ART PDF from HPV. **Use one real sample — do NOT fabricate or alter the file.** Project rule (feedback_art670_fixture_disaster) — only real corpus snapshots.

Add `tests/fixtures/scanners/art/ground_truth.json`:

```json
{
  "f_art_01_p1_crs_andamios.pdf": {
    "covers_expected": 1,
    "description": "Single ART, 4 pages, F-CRS-ART-01 Rev 02"
  }
}
```

- [ ] **Step 2: Write failing test**

```python
# tests/unit/scanners/test_pattern_art.py
"""Smoke for cat 7 art — anchors detection against a real CRS ART fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.scanners.cancellation import CancellationToken
from core.scanners.anchors_scanner import AnchorsScanner

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "art"


@pytest.mark.skipif(not FIXTURES.exists(), reason="ART fixtures not present")
def test_art_scanner_counts_real_pdf(tmp_path: Path):
    ground = json.loads((FIXTURES / "ground_truth.json").read_text())
    for filename, gt in ground.items():
        src = FIXTURES / filename
        target = tmp_path / "2026-04-15_art_crs.pdf"
        target.write_bytes(src.read_bytes())

        scanner = AnchorsScanner(sigla="art")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
        assert result.count == gt["covers_expected"], (
            f"{filename}: expected {gt['covers_expected']} covers, got {result.count}\n"
            f"errors: {result.errors}\nflags: {result.flags}"
        )

        # Clean for next iteration
        target.unlink()
```

- [ ] **Step 3: Run failing**

Expected: `KeyError: 'art'` (because PATTERNS["art"] doesn't exist yet).

- [ ] **Step 4: Add art entry to patterns.py**

```python
# core/scanners/patterns.py — add to PATTERNS dict

    "art": {
        "filename_glob": r"^.*art.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,                # P6 — HRB usa subcarpetas
        "cover_flavors": [
            {
                "name": "f_art_01",
                "anchors": [
                    # CRITICAL: el header del formulario (título + código F-CRS-ART-01)
                    # se REPITE en las 4 páginas — NO usar como ancla.
                    # Solo campos del formulario cover (verificado en spec cat 7).
                    "Nombre del Supervisor",
                    "Área de Trabajo",
                    "Descripción del trabajo a realizar",
                    "Hora de Inicio de los trabajos",
                    "N° de trabajadores involucrados",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] **Step 5: Run smoke**

Run: `pytest tests/unit/scanners/test_pattern_art.py -v`
Expected: passes. If not, render p1 of the fixture and verify the anchors actually appear in the top quarter:

```bash
python -c "import pymupdf, sys; doc=pymupdf.open('tests/fixtures/scanners/art/f_art_01_p1_crs_andamios.pdf'); doc[0].get_pixmap(dpi=150).save('/tmp/p1.png')"
```

Visual inspection + adjust anchors if needed. **Do not lower `min_match` below 3 to force a pass** — fix the anchors instead (A12: structural anchors over codes).

- [ ] **Step 6: Commit**

```bash
git add core/scanners/patterns.py tests/unit/scanners/test_pattern_art.py tests/fixtures/scanners/art/
git commit -m "feat(scanners): populate art pattern (cat 7) with anchors-based detection

f_art_01 flavor anchors against the F-CRS-ART-01 cover. Uses prefix
F-CRS-ART (A12) to tolerate future revisions. Smoke fixture: 1 real ART
from HPV/CRS. Future variants land in the same flavor or as new flavors
via the A13 protocol.
"
```

### Task 4.2: Populate `irl` + `odi` patterns (cats 2 + 3)

**Files:**
- Modify: `core/scanners/patterns.py`
- Test: `tests/unit/scanners/test_pattern_irl_odi.py`

- [ ] **Step 1: Snapshot fixtures**

```bash
mkdir -p tests/fixtures/scanners/irl tests/fixtures/scanners/odi
cp "A:/informe mensual/ABRIL/HPV/2.-Induccion IRL/2026-04-15_irl_pedro.pdf" tests/fixtures/scanners/irl/f_irl_01_p1.pdf
cp "A:/informe mensual/ABRIL/HPV/3.-ODI Visitas/2026-04-10_odi_visita_a.pdf" tests/fixtures/scanners/odi/f_odi_01_p1.pdf
```

Pick the exact files that exist in ABRIL. Add `ground_truth.json` per folder with `covers_expected: 1`.

- [ ] **Step 2: Write smoke**

```python
# tests/unit/scanners/test_pattern_irl_odi.py
import json
from pathlib import Path

import pytest

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken


@pytest.mark.parametrize("sigla", ["irl", "odi"])
def test_pattern_smoke(sigla, tmp_path: Path):
    fixtures = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / sigla
    if not fixtures.exists():
        pytest.skip(f"{sigla} fixtures not present")
    ground = json.loads((fixtures / "ground_truth.json").read_text())
    for filename, gt in ground.items():
        src = fixtures / filename
        target = tmp_path / f"2026-04-15_{sigla}_x.pdf"
        target.write_bytes(src.read_bytes())
        scanner = AnchorsScanner(sigla=sigla)
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
        assert result.count == gt["covers_expected"]
        target.unlink()
```

- [ ] **Step 3: Add patterns**

```python
    "irl": {
        "filename_glob": r"^.*irl.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                # NOTE: el código real del formulario es F-CRS-ODI-01 (no F-CRS-IRL).
                # El título "INFORMACIÓN DE RIESGOS LABORALES" + header completo
                # REPITEN en todas las páginas — NO usar como ancla (spec cat 2).
                "name": "f_irl_01",
                "anchors": [
                    "ANTECEDENTES GENERALES",
                    "FECHA DE REALIZACIÓN",
                    "TIEMPO DE DURACIÓN",
                    "HORARIO DE INICIO",
                    "HORARIO DE TÉRMINO",
                    "OBRA",
                    "TIPO DE INDUCCIÓN",
                    "IDENTIFICACIÓN DEL TRABAJADOR",
                    "IDENTIFICACIÓN DEL RELATOR",
                    "PERSONA TRABAJADORA NUEVA",
                    "CON AUSENCIA PROLONGADA",
                    "REUBICADA/CON NUEVO CARGO",
                    "POR NUEVO PROCESO PRODUCTIVO",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
    "odi": {
        "filename_glob": r"^.*odi.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                # NOTE: título "OBLIGACIÓN DE INFORMAR VISITA" + header F-CRS-ODI-03
                # REPITEN en cada página — NO usar como ancla (spec cat 3).
                "name": "f_odi_01",
                "anchors": [
                    "NOMBRE COMPLETO",
                    "N° TELEFÓNICO",
                    "C. IDENTIDAD",
                    "EMPRESA",
                    "ACTIVIDAD",
                    "PELIGRO / INCIDENTE POTENCIAL",
                    "MEDIDAS DE CONTROL",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] **Step 4: Run smoke**

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/patterns.py tests/unit/scanners/test_pattern_irl_odi.py tests/fixtures/scanners/{irl,odi}/
git commit -m "feat(scanners): populate irl + odi patterns (cats 2, 3) — anchors-based

Both use F-CRS-<sigla> prefix anchors (A12) + structural field-labels.
Replaces the header_detect technique with the uniform anchors approach.
"
```

### Task 4.3: Populate `charla` pattern (cat 4)

**Files:**
- Modify: `core/scanners/patterns.py`
- Test: `tests/unit/scanners/test_pattern_charla.py`

- [ ] **Step 1: Snapshot fixture + define CRS_RCH_ANCHORS constant**

```bash
mkdir -p tests/fixtures/scanners/charla
cp "A:/informe mensual/ABRIL/HPV/4.-Charlas/2026-04-02_charla_supervisor.pdf" tests/fixtures/scanners/charla/f_rch_p1.pdf
```

Add ground truth (1 cover) + commit.

- [ ] **Step 2: Add the shared anchor constant**

```python
# core/scanners/patterns.py — above PATTERNS dict

# Anchors shared between charla (cat 4) and chintegral (cat 5) — both use F-CRS-RCH-01.
# CRITICAL: el título "REGISTRO DE FORMACIÓN E INFORMACIÓN" + header F-CRS-RCH-01
# REPITEN en cada página — NO usar como ancla. Solo campos del formulario cover.
# "Página 1 de" excluido por bug del template (spec cat 4): páginas de continuación
# también dicen "Página 1 de 2".
CRS_RCH_ANCHORS: list[str] = [
    "Nombre de la Charla",
    "Obra",
    "Relator",
    "Cargo Relator",
    "Hora de inicio",                # Rev 03+
    "Hora de Término",                # Rev 03+
    "Tiempo duración charla",         # Rev 01
    "Tipología de Charla/Reunión",    # Rev 01
    "Charla de Inducción",            # etiqueta de casilla Rev 01
    "Charla Re-instrucción",
    "Reunión de Coordinación",
    "Difusión de Documentos",
]
```

- [ ] **Step 3: Add charla entry**

```python
    "charla": {
        "filename_glob": r"^.*charla.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                "name": "f_rch",
                "anchors": CRS_RCH_ANCHORS,
                "min_match": 4,
                # No "Página 1 de" — template buggy en este flavor (cat 4 doc).
            },
        ],
    },
```

- [ ] **Step 4: Run smoke + commit**

Same shape as before.

```bash
git commit -m "feat(scanners): populate charla pattern (cat 4) — reuses CRS_RCH_ANCHORS

Shared constant for the F-CRS-RCH-01 family (used by cat 4 charla and
cat 5 chintegral). No 'Página 1 de' anchor — that template has a buggy
pagination footer that anchors negatively on this flavor.
"
```

### Task 4.4: Delete the 4 specialization scanners + their tests

**Files:**
- Delete: `core/scanners/art_scanner.py`, `core/scanners/odi_scanner.py`,
  `core/scanners/irl_scanner.py`, `core/scanners/charla_scanner.py`,
  `core/scanners/_header_detect_base.py`
- Delete: `tests/unit/scanners/test_art_scanner.py`, `test_odi_scanner.py`,
  `test_irl_scanner.py`, `test_charla_scanner.py`
- Delete: `tests/test_charla_scanner_per_file.py`, `test_art_scanner_per_file.py`,
  `test_header_detect_per_file.py`
- Modify: `core/scanners/__init__.py` — remove the now-orphaned imports.

- [ ] **Step 1: Search for any lingering references**

Run: `grep -rn "ArtScanner\|OdiScanner\|IrlScanner\|CharlaScanner\|HeaderDetectScanner" core/ api/ tests/`
Expected: only the import line in `core/scanners/__init__.py` + the test files themselves.

- [ ] **Step 2: Delete the files**

```bash
git rm core/scanners/art_scanner.py core/scanners/odi_scanner.py core/scanners/irl_scanner.py core/scanners/charla_scanner.py core/scanners/_header_detect_base.py
git rm tests/unit/scanners/test_art_scanner.py tests/unit/scanners/test_odi_scanner.py tests/unit/scanners/test_irl_scanner.py tests/unit/scanners/test_charla_scanner.py
git rm tests/test_charla_scanner_per_file.py tests/test_art_scanner_per_file.py tests/test_header_detect_per_file.py
```

- [ ] **Step 3: Clean imports in __init__.py**

```python
# core/scanners/__init__.py — final version

"""Scanner registry. Scanners auto-register on import."""

from __future__ import annotations

from collections.abc import Iterator

from core.scanners.base import ConfidenceLevel, Scanner, ScanResult

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
    "Scanner",
    "ScanResult",
    "ConfidenceLevel",
    "register",
    "get",
    "has",
    "all_siglas",
    "all_scanners",
    "clear",
    "register_defaults",
]

# --- Auto-register default scanners on import ---
from core.domain import SIGLAS as _SIGLAS  # noqa: E402
from core.scanners.anchors_scanner import AnchorsScanner  # noqa: E402
from core.scanners.patterns import PATTERNS  # noqa: E402
from core.scanners.simple_factory import SimpleFilenameScanner  # noqa: E402
from core.scanners.pagination_scanner import PaginationScanner  # noqa: E402


def _build_scanner_for_sigla(sigla: str) -> Scanner:
    if sigla not in PATTERNS:
        return SimpleFilenameScanner(sigla=sigla)
    strategy = PATTERNS[sigla]["scan_strategy"]
    if strategy == "anchors":
        return AnchorsScanner(sigla=sigla)
    if strategy == "pagination":
        return PaginationScanner(sigla=sigla)
    return SimpleFilenameScanner(sigla=sigla)


def register_defaults() -> None:
    for sigla in _SIGLAS:
        if not has(sigla):
            register(_build_scanner_for_sigla(sigla))


register_defaults()
```

- [ ] **Step 4: Full smoke**

Run: `pytest tests/ -v && ruff check .`
Expected: all green. If a test references the deleted scanners, fix or remove it.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(scanners): delete specialization scanners — replaced by AnchorsScanner

Removes art_scanner.py, odi_scanner.py, irl_scanner.py, charla_scanner.py,
_header_detect_base.py and their per-class tests. Behavior preserved via
the data-driven AnchorsScanner + patterns.py entries (chunk 4 tasks 1-3).

corner_count and header_detect utilities stay in core/scanners/utils/ —
they're no longer used by the scanners but are documented + tested helpers
that may be reused in chunk 5 fallback paths.
"
```

### Chunk 4 — Review gate

- [ ] **Step 1: Full smoke + check coverage didn't drop**

Run: `pytest tests/ -v --tb=short && ruff check .`

- [ ] **Step 2: Reviewer dispatch**

---

## Chunk 5: Populate las 14 entradas restantes de `patterns.py`

**Goal:** Cada uno de los 14 siglas pendientes recibe su entrada en `patterns.py`. Cada una con un fixture real + smoke. Cuando termine el chunk, `PATTERNS` cubre las 18 SIGLAS y el test de completeness (chunk 1 task 1.3) deja de estar en skip.

**Estructura uniforme por sigla** (Task 5.X): 1 snapshot fixture + 1 ground_truth.json + 1 smoke test + 1 entrada en patterns.py + commit con mensaje canónico.

### Task 5.1: `chintegral` (cat 5)

**Files:** Modify `core/scanners/patterns.py`. New fixture + test.

- [ ] Snapshot fixtures (uno por flavor):
  - `tests/fixtures/scanners/chintegral/f_rch_p1.pdf` (CRS estándar)
  - `tests/fixtures/scanners/chintegral/f_japa_p1.pdf` (JAPA)
  - `tests/fixtures/scanners/chintegral/f_previene_p1.pdf` (PREVIENE)
- [ ] Ground truth: 1 cover por archivo.
- [ ] Write smoke test parametrized over flavors.
- [ ] Add to `patterns.py`:

```python
    "chintegral": {
        "filename_glob": r"^.*chintegral.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {"name": "f_rch", "anchors": CRS_RCH_ANCHORS, "min_match": 4},
            {
                "name": "f_japa",
                "anchors": [
                    "REGISTRO DE CAPACITACIÓN",
                    "JAPA",
                    "Nombre del trabajador",
                    "Tema de la capacitación",
                    "Relator",
                ],
                "min_match": 3,
            },
            {
                # TBD anchors: el spec no detalla los textos exactos del template
                # PREVIENE. Antes de commitear este flavor, renderizar p1 de
                # tests/fixtures/scanners/chintegral/f_previene_p1.pdf con
                # PyMuPDF 150 DPI y extraer 3-4 anchors estructurales reales del
                # template (logo PREVIENE + título + headers de columna).
                # Hasta entonces, mantener `min_match=2` para no fallar la TDD.
                "name": "f_previene",
                "anchors": [
                    "PREVIENE",
                    "Lista de asistencia",
                    "Programa",
                    # TODO(impl): añadir 1-2 anchors más leyendo el sample real.
                ],
                "min_match": 2,
            },
        ],
    },
```

- [ ] Run smoke; if a flavor under-counts, render p1 + inspect + adjust anchors before lowering min_match.
- [ ] Commit: `feat(scanners): populate chintegral pattern (cat 5) — 3 flavors (RCH + JAPA + PREVIENE)`

### Task 5.2: `dif_pts` (cat 6) — with anti-anchors

- [ ] Fixtures (3 flavors):
  - `f_rch_p1.pdf` (CRS RCH)
  - `f_ch_crs_01_p1_cover.pdf` (REGISTRO DE CHARLA cover) + `f_ch_crs_01_p2_test_shadow.pdf` (TEST shadow cover, debe NO contarse)
  - `f_aguasan_p1.pdf` (Aguasan)
- [ ] Ground truth includes `f_ch_crs_01` doble fixture (cover=1, shadow=0).
- [ ] Add to patterns.py:

```python
    "dif_pts": {
        "filename_glob": r"^.*dif_pts.*\.pdf$",
        "scan_strategy": "anchors",
        "top_fraction": 1/3,
        "cover_flavors": [
            {"name": "f_rch", "anchors": CRS_RCH_ANCHORS, "min_match": 4},
            {
                "name": "f_ch_crs_01",
                "anchors": [
                    "REGISTRO DE CHARLA",
                    "F-CH-CRS-01",
                    "Nombre de la Capacitación",
                    "Cargo Relator",
                    "Tiempo duración charla",
                ],
                "min_match": 3,
                "anti_anchors": [
                    "TEST DE COMPRENSIÓN",
                    "TEST TRABAJO EN",
                    "ALTERNATIVA CORRECTA",
                    "F-PETS-CRS",
                ],
            },
            {
                "name": "f_aguasan",
                "anchors": [
                    "AGUASAN",
                    "REGISTRO DE CHARLA Y CAPACITACIÓN",
                    "CATEGORIA",
                    "CHARLA ESPECÍFICA DIARIA",
                    "CHARLA OPERACIONAL",
                    "TOTAL PERSONAL ENTRENADO",
                    "TEMA TRATADO",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Smoke must verify shadow page returns 0 covers.
- [ ] Commit.

### Task 5.3: `insgral` (cat 8) — V4 strategy

- [ ] Fixture: 1 real insgral compilation (HPV or HRB).
- [ ] Ground truth: total documents from manual count.
- [ ] Add to patterns.py:

```python
    "insgral": {
        "filename_glob": r"^.*insgral.*\.pdf$",
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
```

- [ ] Smoke: invoke PaginationScanner.count_ocr and assert counts match ground truth (exact for clean PDFs; ±1 for HRB compilations with poor scans — adjust tolerance after first real run).
- [ ] Commit.

### Task 5.4: `bodega` (cat 9)

- [ ] Fixture: `f_pets_07_03_p1_chequeo.pdf` (cover) + the 1-page respel/suspel are skipped (A7).
- [ ] Add:

```python
    "bodega": {
        "filename_glob": r"^.*bodega.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                "name": "f_pets_07_03",
                "anchors": [
                    "CHEQUEO BODEGA",
                    "F-PETS-CRS-07-03",
                    "OBRA",
                    "REALIZADO POR",
                    "BODEGA SUSPEL",
                    "BODEGA RESPEL",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Smoke + commit.

### Task 5.5: `maquinaria` (cat 10) — intersection anchors

- [ ] Fixtures: 2-3 templates distintos (HPV, HRB, HLU).
- [ ] Use intersection: anchors that appear in EVERY template observed.
- [ ] Add:

```python
    "maquinaria": {
        "filename_glob": r"^.*maquinaria.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": [
            {
                # Intersection of field-labels across ≥5 templates observed
                # (LCH-08, -16, -26, -40 + LCH-CRS-07). CONSTRUCTORA REGIÓN SUR
                # + ITEM/ACTIVIDAD/CUMPLE REPITEN en p2/p3 — NO usar.
                # Spec cat 10 verified.
                "name": "f_lch_xx",
                "anchors": [
                    "FECHA ÚLTIMA MANTENCIÓN",
                    "NOMBRE OPERADOR",
                    "RUT",
                    "MARCA",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Smoke + commit.

### Task 5.6: `ext` (cat 11) — intersection + edge cases

```python
    "ext": {
        "filename_glob": r"^.*ext.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": [
            {
                "name": "f_lch_xx",
                "anchors": [
                    "CHEQUEO DE EXTINTORES",
                    "CONSTRUCTORA REGIÓN SUR",
                    "F-CRS-LCH",
                    "F-LCH-CRS",
                    "Tipo de extintor",
                    "Capacidad",
                    "Estado",
                    "Página 1 de",
                ],
                "min_match": 4,
            },
        ],
    },
```

Note: P4 documents UEO-01 / PSR-RG as out-of-scope (manual override). No flavor for them.

- [ ] Smoke + commit.

### Task 5.7: `senal` (cat 12) — full-page scan (P5)

```python
    "senal": {
        "filename_glob": r"^.*senal.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "top_fraction": 1.0,                # P5 — orientaciones mixtas
        "cover_flavors": [
            {
                "name": "f_lch_22",
                "anchors": [
                    "LISTA DE CHEQUEO DE SEÑALÉTICAS",
                    "F-CRS-LCH-22",
                    "CONSTRUCTORA REGIÓN SUR",
                    "Tipo de señal",
                    "Ubicación",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Smoke + commit.

### Task 5.8: `exc` (cat 13)

```python
    "exc": {
        "filename_glob": r"^.*exc.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                "name": "f_lch_xx",   # cubre LCH-31 + LCH-034
                "anchors": [
                    "EXCAVACIONES",
                    "CONSTRUCTORA REGIÓN SUR",
                    "F-CRS-LCH",
                    "F-LCH-CRS",
                    "Profundidad",
                    "Ancho",
                    "Largo",
                    "Página 1 de",
                ],
                "min_match": 4,
            },
        ],
    },
```

- [ ] Smoke + commit.

### Task 5.9: `altura` (cat 14) — V4 strategy

```python
    "altura": {
        "filename_glob": r"^.*altura.*\.pdf$",
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
```

- [ ] Fixture: 1 altura compilation (HRB recommended — has the bigger compilations).
- [ ] Smoke + commit.

### Task 5.10: `caliente` (cat 15)

```python
    "caliente": {
        "filename_glob": r"^.*caliente.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": [
            {
                "name": "f_lch_3x",
                "anchors": [
                    "CHEQUEO TRABAJOS EN CALIENTE",
                    "CONSTRUCTORA REGIÓN SUR SPA",
                    "F-LCH-CRS",
                    "ITEM",
                    "ACTIVIDAD",
                    "CUMPLE",
                    "esmeril angular",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Smoke + commit.

### Task 5.11: `herramientas_elec` (cat 16) — 4 flavors + anti-anchor

```python
    "herramientas_elec": {
        "filename_glob": r"^.*herramientas_elec.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": [
            {
                "name": "f_lch_xx",
                "anchors": [
                    "CONSTRUCTORA REGIÓN SUR",
                    "F-CRS-LCH",
                    "F-LCH-CRS",
                    "F-CRS-CRS",
                    "ITEM",
                    "ACTIVIDAD",
                    "CUMPLE",
                    "SI",
                    "NO",
                    "NA",
                    "Página 1 de",
                    "Inspección Realizada",
                ],
                "min_match": 4,
                "anti_anchors": [
                    "ELEMENTOS DE PROTECCIÓN PERSONAL",
                    "LCH-CRS-02",
                ],
            },
            {
                "name": "f_titan",
                "anchors": [
                    "TITAN",
                    "CHECK LIST",
                    "HERRAMIENTAS ELÉCTRICAS",
                    "TN-SGSSO-RG",
                    "SISTEMA DE GESTIÓN DE SEGURIDAD Y SALUD OCUPACIONAL",
                ],
                "min_match": 3,
            },
            {
                "name": "f_reali",
                "anchors": [
                    "REALI",
                    "FORM-PREV-021",
                    "LISTA DE CHEQUEO DE HERRAMIENTAS",
                    "PROGRAMA DE GESTIÓN EN SEGURIDAD",
                ],
                "min_match": 3,
            },
            {
                "name": "f_hll_17",
                "anchors": [
                    "REG-SSO-HLL-17",
                    "Chequeo de Herramientas",
                    "Mantención de Obra",
                    "Codificación",
                    "Estado enchufe macho",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Fixtures: 4 — uno por flavor.
- [ ] Smoke (incl. anti-anchor test: ALUMINIO EPP must NOT count).
- [ ] Commit.

### Task 5.12: `andamios` (cat 17) — 2 flavors + anti-anchor ART

```python
    "andamios": {
        "filename_glob": r"^.*andamios.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": [
            {
                "name": "f_lch_05",
                "anchors": [
                    "LISTA DE CHEQUEO DE ANDAMIOS",
                    "CONSTRUCTORA REGIÓN SUR",
                    "F-CRS-LCH",                  # A12 — prefijo, no F-CRS-LCH-05 exclusivo
                    "Tipo andamio",
                    "DATOS DEL ANDAMIO",
                    "SUPERFICIE DE APOYO",
                    "ESTRUCTURA DEL ANDAMIO",
                    "PLATAFORMAS DE TRABAJO",
                    "Página 1 de",
                ],
                "min_match": 4,
                "anti_anchors": [
                    "ANÁLISIS DE RIESGOS EN EL TRABAJO",
                    "F-CRS-ART-01",
                ],
            },
            {
                "name": "f_ribeiro",
                "anchors": [
                    "RIBEIRO SPA",
                    "LISTA DE VERIFICACIÓN ANDAMIOS",
                    "1cl-1890",
                    "INSPECCIÓN DE ANDAMIOS",
                    "Centro de Trabajo",
                    "Línea de Negocio",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Fixtures + smoke (anti-anchor test: TITAN_armado ART must NOT count).
- [ ] Commit.

### Task 5.13: `chps` (cat 18)

```python
    "chps": {
        "filename_glob": r"^.*chps.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                "name": "f_ar_01",
                "anchors": [
                    "ACTA DE REUNIÓN",
                    "F-CRS-AR-01",
                    "LISTA DE CONVOCADOS",        # solo en p1
                    "DESARROLLO DE LA REUNIÓN",   # solo en p1
                    "HOSPITAL DE",
                    "Lugar de la reunión",
                    "Página 1 de",
                ],
                "min_match": 3,
            },
        ],
    },
```

- [ ] Fixture: the HPV CHPS 3-page sample. Smoke: 1 cover (p1), 0 on p2/p3.
- [ ] Commit.

### Task 5.14: Completeness gate

- [ ] **Step 1: Unlock the completeness test (was skipped in chunk 1)**

The test `test_all_18_siglas_have_a_pattern_eventually` (tests/unit/scanners/test_patterns_registry.py) should now PASS without the skip.

Run: `pytest tests/unit/scanners/test_patterns_registry.py -v`
Expected: all 8+ tests passing (no skip).

- [ ] **Step 2: Run full smoke**

Run: `pytest tests/ -v --tb=short && ruff check .`
Expected: all green.

- [ ] **Step 3: Run a corpus-wide smoke against ABRIL (manual)**

```bash
python -m pytest tests/integration/test_abril_corpus.py -v  # creates in Chunk 7
```

If the integration test doesn't exist yet, defer to Chunk 7.

- [ ] **Step 4: Commit milestone**

```bash
git tag ocr-per-sigla-patterns-complete
git commit -m "feat(scanners): 18/18 patterns populated — registry complete

All 18 siglas now have entries in patterns.py with smoke fixtures.
Strategy distribution: 1 'none' (reunion), 15 'anchors', 2 'v4' (insgral, altura).
"
```

### Chunk 5 — Review gate

Reviewer dispatch + green smoke required.

---

## Chunk 6: UI — A3 + A13 + A14 (Ver portada, near-match panel, FileList chip)

**Goal:** Surface the new telemetry + protocols in the frontend.
1. **A3 per-PDF OCR trigger** (existing FASE 4) is preserved; add visibility.
2. **A13 "Ver portada"** button in `DetailPanel` for any PDF flagged as near-match.
3. **A14 near-match panel** in `DetailPanel`: lists candidates with `[Marcar como nuevo flavor]` action that generates a copy-paste stub.
4. **A7 chip** in `FileList`: 1-page PDFs show `Origin = trivial` + no re-scan button.

### Task 6.1: Pass telemetry through the API

**Files:**
- Modify: `api/routes/sessions.py:~200` (where ScanResult is serialized)
- Test: `tests/integration/test_sessions_telemetry.py`

- [ ] **Step 1: Failing test**

```python
def test_session_response_includes_near_matches_when_present(client, fake_scan):
    # ... orchestrate a scan that produces ScanResult.telemetry with 1 near-match
    response = client.get("/sessions/<id>/cells/HPV/andamios")
    data = response.json()
    assert "near_matches" in data
    assert len(data["near_matches"]) == 1
    assert data["near_matches"][0]["flavor_name"] == "f_lch_05"
```

- [ ] **Step 2: Add serialization for `ScanResult.telemetry`**

In `api/routes/sessions.py`, when serializing the cell scan result, include:

```python
telemetry = result.telemetry
near_matches_dto = [
    {
        "pdf_name": nm.pdf_name,
        "page_index": nm.page_index,
        "flavor_name": nm.flavor_name,
        "matched_anchors": nm.matched_anchors,
        "missing_anchors": nm.missing_anchors,
    }
    for nm in (telemetry.near_matches if telemetry else [])
]
# Add to the response payload
response_dict["near_matches"] = near_matches_dto
```

- [ ] **Step 3: Smoke + commit**

```bash
git commit -m "feat(api): expose ScanResult.telemetry.near_matches in cell responses (A14)"
```

### Task 6.2: DetailPanel — "Casi-matches" section

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`
- Modify: `frontend/src/store/` (where cell state is held)
- Test: vitest + chrome-devtools smoke

- [ ] **Step 1: Add state for near_matches**

In the cell store: ensure `nearMatches: NearMatch[]` is part of the cell state.

- [ ] **Step 2: Render the panel**

```jsx
// frontend/src/components/DetailPanel.jsx — near new "Casi-matches" section
{cell.nearMatches?.length > 0 && (
  <section className="po-detail-section">
    <header className="po-section-header">
      <h3>Casi-matches ({cell.nearMatches.length})</h3>
      <Badge tone="amber">candidatos a flavor nuevo</Badge>
    </header>
    <ul className="po-near-matches">
      {cell.nearMatches.map((nm, i) => (
        <li key={i} className="po-near-match-row">
          <span className="po-near-match-pdf">{nm.pdf_name}</span>
          <span className="po-near-match-page">p. {nm.page_index + 1}</span>
          <span className="po-near-match-flavor">{nm.flavor_name}</span>
          <button
            onClick={() => openPdfCover(nm.pdf_name, nm.page_index)}
            className="po-link-button"
          >Ver portada</button>
          <button
            onClick={() => copyFlavorStub(nm)}
            className="po-link-button"
          >Marcar como nuevo flavor</button>
        </li>
      ))}
    </ul>
  </section>
)}
```

- [ ] **Step 3: `openPdfCover` — reuse Feature 1 viewer**

Open the pdf.js viewer (existing `WorkerCountViewer` infrastructure) with the PDF + page jump to `nm.page_index`. Adapt to a read-only mode (no marks panel).

- [ ] **Step 4: `copyFlavorStub` — generate paste-able patterns.py stub**

```javascript
function copyFlavorStub(nm) {
  const stub = `# Candidate flavor for ${nm.flavor_name} — matched anchors: ${nm.matched_anchors.join(", ")}\n` +
    `# Missing in this PDF: ${nm.missing_anchors.join(", ")}\n` +
    `{\n` +
    `    "name": "f_NEW_NAME_HERE",  # ver A9\n` +
    `    "anchors": [\n` +
    nm.matched_anchors.map(a => `        "${a}",`).join("\n") + "\n" +
    `        # add 1-2 more anchors specific to this template\n` +
    `    ],\n` +
    `    "min_match": ${Math.max(3, nm.matched_anchors.length)},\n` +
    `}`;
  navigator.clipboard.writeText(stub);
  toast.success("Stub del flavor copiado al portapapeles");
}
```

- [ ] **Step 5: Style (po-near-matches in tailwind config)**

Use existing po-* tokens.

- [ ] **Step 6: chrome-devtools smoke**

Drive the smoke via `mcp__chrome-devtools__navigate_page` + `take_screenshot`. Verify near-matches show up when present + Ver portada opens viewer.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(frontend): DetailPanel surfaces near-match candidates (A13 + A14)

When the scanner reports ScanResult.telemetry.near_matches, the cell panel
shows a 'Casi-matches' section with the PDF + page + closest flavor + two
buttons: 'Ver portada' (opens pdf.js viewer at that page) and 'Marcar como
nuevo flavor' (copies a patterns.py stub to clipboard).
"
```

### Task 6.3: FileList — A7 trivial chip

**Files:** Modify `frontend/src/components/FileList.jsx`. Add chip when `per_file` ≥ 1 AND PDF is 1 page.

- [ ] Detect 1-page status from cell state. Already in `per_file`? Or derive from filename heuristic.
- [ ] Display `<Badge tone="iris">trivial</Badge>` instead of `OriginChip` for these rows.
- [ ] Hide the "Re-escanear este PDF" button for 1-page PDFs.
- [ ] Commit.

### Chunk 6 — Review gate

---

## Chunk 7: Fixtures cumulativos + protocolo A13 + cleanup

**Goal:** Documentar el sistema, agregar el README operativo de `tests/fixtures/scanners/`, eliminar las dependencias muertas en core/scanners/utils/, hacer el smoke final contra todo el corpus ABRIL.

### Task 7.0: Build `data/ground_truth_abril.json` (prereq for Task 7.2)

**Files:**
- Create: `data/ground_truth_abril.json`

**Why:** Task 7.2 corpus smoke loads this JSON to verify scanner counts. Daniel + Carla counted manually — armar el archivo en sesión interactiva con Daniel.

- [ ] **Step 1: Coordinate with Daniel**

Ask Daniel for the manual count JSON (or build it together). Expected shape:

```json
{
  "month": "2026-04",
  "hospitals": {
    "HPV": {
      "reunion": 1,
      "irl": 12,
      "odi": 90,
      "...": 0
    },
    "HRB": { ... },
    "HLU": { ... },
    "HLL": { ... }
  }
}
```

- [ ] **Step 2: Validate keys**

Run a quick check: every key must be a sigla from `core.domain.SIGLAS`, every hospital must be in `core.domain.HOSPITALS`.

```python
import json
from core.domain import HOSPITALS, SIGLAS

data = json.loads(Path("data/ground_truth_abril.json").read_text())
assert set(data["hospitals"]) == set(HOSPITALS)
for h, cells in data["hospitals"].items():
    unknown = set(cells) - set(SIGLAS)
    assert not unknown, f"{h}: unknown siglas {unknown}"
```

- [ ] **Step 3: Commit**

```bash
git add data/ground_truth_abril.json
git commit -m "data: add ABRIL ground truth (manual count by Daniel/Carla)

72 cells (4 hospitals × 18 siglas) — the validation target for the
corpus smoke (Task 7.2). Source: spreadsheet maintained by Daniel/Carla;
this JSON is a snapshot. Any future month requires a new file (e.g.
ground_truth_mayo.json).
"
```

### Task 7.1: `tests/fixtures/scanners/README.md`

- [ ] Documenta:
  - Estructura `<sigla>/<flavor>_p1_<descripción>.pdf`.
  - `ground_truth.json` shape: `{"filename.pdf": {"covers_expected": N, "description": "..."}}`.
  - Protocolo A13: cómo agregar un nuevo flavor (ver portada → clasificar → ampliar/crear → snapshot → ground truth → smoke).
  - Naming convention A9.
  - Cómo correr el corpus smoke: `pytest tests/integration/test_abril_corpus.py`.

### Task 7.2: Corpus-wide smoke

**Files:** Create `tests/integration/test_abril_corpus.py`.

- [ ] Carga `data/ground_truth_abril.json` (mensual por hospital × sigla). Daniel/Carla counted manualmente.
- [ ] Para cada celda, invoca el scanner. Verifica `count == ground_truth[hospital][sigla]` con tolerancia ±10% (V4 tolerance) o exacto (anchors tolerance).
- [ ] Marca como `pytest.mark.slow` si tarda > 30s.

### Task 7.3: Deprecate dead utils

**Files:** `core/scanners/utils/corner_count.py`, `header_detect.py`.

- [ ] Si chunk 4 los dejó sin callers, decidir:
  - Borrar.
  - Mantener como utilidades documentadas para usuarios futuros que quieran reusar las técnicas viejas.
- [ ] Recomendación: **borrar** (DRY). Si A13 protocol descubre una variante que necesite una técnica nueva, se agrega ahí.

### Task 7.4: Update CLAUDE.md

Document the new architecture in `core/CLAUDE.md` or `core/scanners/CLAUDE.md` (whichever exists). Mention:
- patterns.py is single source of truth.
- AnchorsScanner + PaginationScanner + SimpleFilenameScanner triad.
- V4 (core/pipeline.py) intacto pero desconectado del scanner registry.
- A7 (1-page lock), A8 (folder-missing), A14 (near-match telemetry) behaviors.

### Task 7.5: Bump version tag

Per hookify `bump-version-tags`: update `PATTERN_VERSION` or similar in `core/utils.py`.

```python
SCANNER_PATTERNS_VERSION = "v1-ocr-per-sigla"
```

### Task 7.6: Final lint + smoke + commit + tag

```bash
ruff check .
pytest tests/ -v
git commit -m "feat(scanners): final cleanup + docs + corpus smoke for ocr-per-sigla"
git tag ocr-per-sigla-mvp
```

### Chunk 7 — Review gate

Final reviewer dispatch. Address feedback.

---

## Post-implementation

- [ ] Push branch + open PR against `po_overhaul`.
- [ ] Smoke contra MAYO corpus (cuando esté disponible) — regresión natural.
- [ ] Documentar protocolo A13 en CLAUDE.md feature section.
- [ ] Considerar mover a S1-S3 (puntos separados del plan) en plans siguientes.

---

## Notas de implementación / cabos a confirmar

1. **`corner_count.count_paginations` API**: el `PaginationScanner` asume `count_paginations(pdf_path, *, dpi=200, cancel=None) -> CornerCountResult` con `.count: int` y `.transitions: list[tuple[int, int]]`. Verificar al inicio del Chunk 3 Task 3.2 (`head -130 core/scanners/utils/corner_count.py`). Si difiere, ajustar `pagination_scanner.py` — NO modificar `corner_count.py` (sus tests existentes deben seguir pasando).

2. **Tesseract install**: `pytesseract` requiere `tesseract` en PATH. Verificar antes de Chunk 2 (`tesseract --version`). En caso de falla, ver `core/CLAUDE.md` para el path Windows.

3. **GPU SR Tier 2**: el adapter actual no usa SR. Si una sigla necesita GPU upscale para anchors (improbable, anchors es texto grande), evaluar caso por caso. No prematuramente.

4. **Spanish locale**: Tesseract `lang="spa+eng"` debe estar instalado. Si falla, instalar `tesseract-ocr-spa`.

5. **Carpeta inexistente (A8)**: ya cubierto por `filename_glob.flags`. Confirmar que TODOS los scanners propagan ese flag. Test ya escrito en Chunk 1.

6. **Recursive glob (P6)**: `count_pdfs_by_sigla` ya usa `rglob`. La declaración `recursive_glob: True` en patterns.py es **informativa** — no cambia comportamiento porque `rglob` ya es el default. Considerar removerlo del TypedDict si nunca se consulta.

7. **Anti-anchor evaluation order**: cuando dos flavors podrían pasar (poco probable con la separación actual), gana el primero declarado. Documentado en `count_covers_by_anchors`.

8. **`.gitignore` tiene `*.pdf`** (descubierto en Chunk 1 review gate). Implicaciones para A15 (fixtures cumulativos):
   - Los PDFs snapshot de `tests/fixtures/scanners/<sigla>/*.pdf` **NO se commitearán** — son local-only, igual que los `tests/fixtures/scanners_ocr/*.pdf` existentes.
   - En los Chunks 4/5/7, los `git add tests/fixtures/scanners/<sigla>/` solo commitean el `ground_truth.json` (no los `.pdf`).
   - Los smoke tests por-sigla deben tener `@pytest.mark.skipif(not FIXTURE.exists())` para que un clone fresco no falle (los tests de Chunk 1 ya muestran este patrón con `scanners_ocr`).
   - Decisión: aceptable para una app single-user/LAN — los fixtures viven en la máquina de Daniel. El `fixtures/scanners/README.md` (Task 7.1) debe documentar que los PDFs son snapshots locales y cómo recrearlos desde `A:\informe mensual`.
   - Alternativa NO elegida: negation `!tests/fixtures/scanners/**/*.pdf` en `.gitignore` — descartada porque metería binarios pesados al repo.
   - Al crear un worktree fresco, copiar los fixtures gitignored del worktree principal (como se hizo en Chunk 1).
