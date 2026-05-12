"""Filename-based counting: walk a folder, count PDFs by sigla in the filename."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.domain import SIGLAS

# Capture the dash-free remainder between the date prefix and the .pdf suffix.
# Sigla resolution (which token of the remainder is the sigla) happens against
# the closed SIGLAS list — the previous regex-only approach broke on multi-word
# siglas like `dif_pts` because non-greedy `[a-z_]+?` stopped at the first `_`.
_FILENAME_REMAINDER_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}_(?P<rest>.+?)\.pdf$",
    re.IGNORECASE,
)

# Match longest siglas first so `dif_pts` wins over a hypothetical `dif`,
# `herramientas_elec` over `herramientas`, etc.
_SIGLAS_BY_LEN_DESC = sorted(SIGLAS, key=len, reverse=True)


@dataclass(frozen=True)
class GlobCountResult:
    count: int
    method: str
    files_scanned: int
    flags: list[str] = field(default_factory=list)


def extract_sigla(filename: str) -> str | None:
    """Extract the sigla from a canonical filename like
    `2026-04-01_art_crs_andamios.pdf`. Returns None if format doesn't match
    or no known sigla is present at the start of the remainder.
    """
    m = _FILENAME_REMAINDER_RE.match(filename)
    if not m:
        return None
    rest = m.group("rest").lower()
    for sigla in _SIGLAS_BY_LEN_DESC:
        if rest == sigla or rest.startswith(sigla + "_"):
            return sigla
    return None


def count_pdfs_by_sigla(folder: Path, *, sigla: str) -> GlobCountResult:
    """Count PDFs (recursively) where filename starts with the given sigla.

    Args:
        folder: Directory to search (may or may not exist).
        sigla: Canonical sigla string to match (e.g. ``"art"``).

    Returns:
        GlobCountResult with count, method, files_scanned, and flags.
        Returns count=0 with flag 'folder_missing' if folder doesn't exist.
    """
    if not folder.exists():
        return GlobCountResult(
            count=0,
            method="filename_glob",
            files_scanned=0,
            flags=["folder_missing"],
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
