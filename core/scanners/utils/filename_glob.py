"""Filename-based counting: walk a folder, count PDFs by sigla in the filename."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.domain import SIGLAS

# Token-boundary pattern for lax sigla extraction (A10).
#
# A sigla is recognised when it appears in the filename stem (without the
# .pdf extension) surrounded by token separators: start-of-string, end-of-
# string, or one of the characters [_\-.].  This is "lax" in that there is
# no date-prefix requirement — it captures HLL mega-compilation files like
# `2026-04_andamios.pdf` (no day component) and arbitrary-casing files like
# `REUNION_OLD.PDF` — while still rejecting false positives where a sigla
# name is an embedded substring of an unrelated word (e.g. `ext` inside
# `extra`).
_TOKEN_SEP = r"(?:^|(?<=[_\-.]))"  # zero-width: start-of-string OR after a separator
_TOKEN_END = r"(?:$|(?=[_\-.]))"  # zero-width: end-of-string OR before a separator

# Extra filename tokens that resolve to a sigla, beyond its literal name
# (F6/F14a — Fase 5 corpus matching). Phrases use [_\-.\s]+ between words so
# both "revision_documentacion" and "revision documentacion" match. Values
# are raw regex fragments (NOT re.escape'd — revdocmaq's alias is a real
# pattern), mirroring core.domain._SIGLA_FOLDER_ALIASES in spirit.
_SIGLA_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "chps": (r"cphs",),  # real ABRIL file spells the Comité Paritario acronym correctly
    "revdocmaq": (r"revision[_\-.\s]+documentacion",),  # real files carry no "revdocmaq" token
}


def _compile_sigla_patterns() -> dict[str, list[re.Pattern[str]]]:
    """Build {sigla: [literal-token pattern, *alias patterns]}."""
    compiled: dict[str, list[re.Pattern[str]]] = {}
    for sigla in SIGLAS:
        raw_tokens = [re.escape(sigla), *_SIGLA_TOKEN_ALIASES.get(sigla, ())]
        compiled[sigla] = [re.compile(_TOKEN_SEP + tok + _TOKEN_END) for tok in raw_tokens]
    return compiled


# Compiled per-sigla patterns keyed by sigla string. Each sigla maps to a
# list: its literal token pattern first, then any alias patterns (F6/F14a).
_SIGLA_PATTERNS: dict[str, list[re.Pattern[str]]] = _compile_sigla_patterns()


@dataclass(frozen=True)
class GlobCountResult:
    count: int
    method: str
    files_scanned: int
    flags: list[str] = field(default_factory=list)
    matched_filenames: list[str] = field(default_factory=list)


def extract_sigla(filename: str) -> str | None:
    """Extract the sigla from a filename via lax matching (A10) + per-sigla
    token aliases (F6/F14a).

    Lax: the sigla name — or one of its aliases, see ``_SIGLA_TOKEN_ALIASES``
    — may appear anywhere in the filename stem, bounded by token separators
    (``^``, ``$``, ``_``, ``-``, ``.``). For each sigla, the earliest match
    across its own patterns (literal token + aliases) is taken as that
    sigla's candidate. Returns the sigla whose candidate match starts
    earliest (left-most) overall; ties broken by the longest matched text
    (not the sigla name's length — a phrase alias like revdocmaq's
    "revision_documentacion" must win a tie over a shorter literal token).
    Case-insensitive.

    Handles substring overlaps: ``2026-04_chps_acta_reunion.pdf`` resolves to
    ``chps`` (appears before ``reunion``), not ``reunion``.

    Aliases let a sigla match filenames that never carry its own name:
    ``2026-04-30_cphs_acta_reunion.pdf`` resolves to ``chps`` (the real-corpus
    "cphs" spelling is aliased, and still starts before "reunion"), and
    ``REVISION_DOCUMENTACION_MAQUINARIA_AGUASAN.pdf`` resolves to
    ``revdocmaq`` (its real-corpus files carry no "revdocmaq" token at all —
    only the "revision"+"documentacion" phrase).

    No date-prefix requirement — captures HLL mega-compilation files like
    ``2026-04_andamios.pdf`` (no day component) and arbitrary-casing files
    like ``REUNION_OLD.PDF``.
    """
    fn_lower = filename.lower()
    if not fn_lower.endswith(".pdf"):
        return None
    # Strip the .pdf extension so end-of-string anchors work on the stem.
    stem = fn_lower[: -len(".pdf")]
    candidates: list[tuple[int, int, str]] = []  # (match_start, -match_length, sigla)
    for sigla, patterns in _SIGLA_PATTERNS.items():
        best: tuple[int, int] | None = None  # (match_start, -match_length)
        for pattern in patterns:
            m = pattern.search(stem)
            if m is None:
                continue
            key = (m.start(), -(m.end() - m.start()))
            if best is None or key < best:
                best = key
        if best is not None:
            candidates.append((*best, sigla))
    if not candidates:
        return None
    # Earliest position wins; ties broken by longest matched text (most specific).
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[0][2]


def count_pdfs_by_sigla(folder: Path, *, sigla: str) -> GlobCountResult:
    """Count PDFs (recursively) where filename contains the given sigla token.

    A8: if ``folder`` does not exist, returns count=0 with flag
    ``'folder_missing'``; no exception raised.

    Args:
        folder: Directory to search (may or may not exist).
        sigla: Canonical sigla string to match (e.g. ``"art"``).

    Returns:
        GlobCountResult with count, method, files_scanned, and flags.
    """
    if not folder.exists():
        return GlobCountResult(
            count=0,
            method="filename_glob",
            files_scanned=0,
            flags=["folder_missing"],
            matched_filenames=[],
        )
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
        matched_filenames=[p.name for p in matched],
    )


def per_empresa_breakdown(folder: Path) -> dict[str, int]:
    """Return {empresa_subfolder_name: pdf_count}. Includes only direct subfolders.

    Args:
        folder: Parent directory whose immediate subdirectories are empresa folders.

    Returns:
        Mapping of subfolder name to total PDF count within that subfolder (recursive).
        Empty dict if folder doesn't exist.
    """
    if not folder.exists():
        return {}
    breakdown: dict[str, int] = {}
    for sub in folder.iterdir():
        if not sub.is_dir():
            continue
        breakdown[sub.name] = len(list(sub.rglob("*.pdf")))
    return breakdown
