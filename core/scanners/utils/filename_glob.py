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

# Compiled per-sigla patterns keyed by sigla string.
_SIGLA_PATTERNS: dict[str, re.Pattern[str]] = {
    s: re.compile(_TOKEN_SEP + re.escape(s) + _TOKEN_END) for s in SIGLAS
}


@dataclass(frozen=True)
class GlobCountResult:
    count: int
    method: str
    files_scanned: int
    flags: list[str] = field(default_factory=list)
    matched_filenames: list[str] = field(default_factory=list)


def extract_sigla(filename: str) -> str | None:
    """Extract the sigla from a filename via lax matching (A10).

    Lax: the sigla name may appear anywhere in the filename stem, bounded by
    token separators (``^``, ``$``, ``_``, ``-``, ``.``).  Returns the sigla
    whose token-boundary match starts earliest (left-most); ties broken by
    longest (most specific) sigla.  Case-insensitive.

    Handles substring overlaps: ``2026-04_chps_acta_reunion.pdf`` resolves to
    ``chps`` (appears before ``reunion``), not ``reunion``.

    No date-prefix requirement — captures HLL mega-compilation files like
    ``2026-04_andamios.pdf`` (no day component) and arbitrary-casing files
    like ``REUNION_OLD.PDF``.
    """
    fn_lower = filename.lower()
    if not fn_lower.endswith(".pdf"):
        return None
    # Strip the .pdf extension so end-of-string anchors work on the stem.
    stem = fn_lower[: -len(".pdf")]
    candidates: list[tuple[int, str]] = []  # (match_start, sigla)
    for sigla, pattern in _SIGLA_PATTERNS.items():
        m = pattern.search(stem)
        if m is None:
            continue
        candidates.append((m.start(), sigla))
    if not candidates:
        return None
    # Earliest position wins; ties broken by longest sigla (most specific).
    candidates.sort(key=lambda t: (t[0], -len(t[1])))
    return candidates[0][1]


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
