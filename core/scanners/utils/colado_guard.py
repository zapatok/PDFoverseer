"""Anti-colados guard — pure detection + suspect-lifecycle helpers (spec 2026-07-03).

Vertiente 1 (filename, all 20 siglas) ships first; vertiente 2 (form codes,
pagination opt-in) extends this module behind the §7 survey gate. Suspects are
plain dicts in cell state (JSON-persisted); ``ColadoSuspect`` is the typed
construction shape. Counts are NEVER derived here (spec §2.2) — every helper
produces flags/telemetry/suspects only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core.scanners.utils.filename_glob import siglas_suggested_by_filename

KIND_FILENAME = "filename"
KIND_CODE = "code"

# reorg op types that participate in the §5 dedupe table
_OP_MOVE = "move_file"
_OP_EXTRACT = "extract_pages"


def suspect_id(
    kind: str,
    file: str,
    page_range: tuple[int, int] | None,
    suggested_sigla: str | None,
) -> str:
    """Deterministic id over the evidence (spec §5): addressing for dismiss only.

    Not persisted state — recomputed from the evidence every scan, so it is
    stable for the same suspect and changes when the evidence changes.
    """
    raw = f"{kind}|{file}|{page_range}|{suggested_sigla}"
    return "cs_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


@dataclass(frozen=True)
class ColadoSuspect:
    """Typed construction shape for a suspect; ``to_dict`` is the persisted form."""

    kind: str  # KIND_FILENAME | KIND_CODE
    file: str
    evidence: str  # matched foreign sigla(s) (filename) or dominant code (code)
    suggested_sigla: str | None  # None = ambiguous (2+ foreign matches)
    page_range: tuple[int, int] | None = None  # None = whole file
    counted: bool = False

    def to_dict(self) -> dict:
        return {
            "id": suspect_id(self.kind, self.file, self.page_range, self.suggested_sigla),
            "kind": self.kind,
            "file": self.file,
            "evidence": self.evidence,
            "suggested_sigla": self.suggested_sigla,
            "page_range": list(self.page_range) if self.page_range else None,
            "counted": self.counted,
        }


def find_foreign_filename_suspects(filenames: list[str], sigla_host: str) -> list[dict]:
    """Vertiente-1 rule (spec §3) over a folder's basenames.

    Suspect ⟺ the name suggests ≥1 foreign sigla AND does NOT suggest the host.
    Exactly one foreign → that sigla is suggested; 2+ → ``suggested_sigla=None``
    (the operator picks the destination). Host present in the set, or an empty
    set (``crs.pdf`` / ``titan.pdf``), → silence.

    Args:
        filenames: PDF basenames in the cell folder.
        sigla_host: the cell's own sigla.

    Returns:
        Suspect dicts (see :class:`ColadoSuspect`), one per foreign-named file,
        sorted by filename for determinism.
    """
    out: list[dict] = []
    for name in sorted(set(filenames)):
        s = siglas_suggested_by_filename(name)
        if not s or sigla_host in s:
            continue
        suggested = next(iter(s)) if len(s) == 1 else None
        out.append(
            ColadoSuspect(
                kind=KIND_FILENAME,
                file=name,
                evidence=", ".join(sorted(s)),
                suggested_sigla=suggested,
            ).to_dict()
        )
    return out


def merge_suspects(
    existing: list[dict],
    kind: str,
    fresh: list[dict],
    present_files: set[str],
    scanned_files: set[str] | None = None,
) -> list[dict]:
    """Per-kind surgical refresh + evidence-based eviction + precedence (spec §5).

    - Entries of ``kind`` are replaced by ``fresh``: ALL of them when
      ``scanned_files is None`` (pase-1 semantics — the fresh list covers the
      whole folder), else only those whose ``file`` is in ``scanned_files``
      (OCR per-PDF semantics, vertiente 2).
    - Eviction (BOTH kinds, EVERY refresh): any entry whose ``file`` is absent
      from ``present_files`` is dropped — mirrors the Incr-J evidence lifecycle.
      Without it a departed file's suspects (e.g. after paso-1 executed the fix)
      would hold ``all_reliable`` false forever.
    - Precedence: a ``KIND_FILENAME`` suspect for F suppresses ``KIND_CODE``
      entries for F (a whole-file suggestion subsumes page ranges).

    Args:
        existing: the cell's current suspect list.
        kind: the kind being refreshed this call.
        fresh: freshly-detected suspects of ``kind``.
        present_files: names of PDFs currently in the folder (eviction basis).
        scanned_files: for ``KIND_CODE`` OCR refresh, the PDFs actually scanned;
            ``None`` means a whole-folder (pase-1) replace of ``kind``.

    Returns:
        The merged suspect list.
    """
    kept = [
        s
        for s in existing
        if s.get("kind") != kind
        or (scanned_files is not None and s.get("file") not in scanned_files)
    ]
    merged = kept + list(fresh)
    merged = [s for s in merged if s.get("file") in present_files]
    filename_files = {s["file"] for s in merged if s.get("kind") == KIND_FILENAME}
    return [s for s in merged if s.get("kind") != KIND_CODE or s.get("file") not in filename_files]


def annotate_counted_filename(suspects: list[dict], cell: dict) -> list[dict]:
    """Set ``counted`` for KIND_FILENAME suspects from live per-file data (spec §4.5).

    counted = (the file's current contribution to the host count) > 0, read from
    the SAME data ``compute_cell_count`` uses: ``per_file_overrides[f]`` when the
    key exists, else ``per_file.get(f, 0)``. Data-derived — NO cell-type taxonomy
    (the taxonomy lies: OCR cells fall back to 1, anchors F8 read 0 covers, A7
    counts a 1-page file as 1). KIND_CODE entries pass through untouched (their
    ``counted`` is set at scan time from segment data — vertiente 2).

    Args:
        suspects: the merged suspect list.
        cell: the persisted cell state (for per_file / per_file_overrides).

    Returns:
        A new list with KIND_FILENAME suspects' ``counted`` refreshed.
    """
    per_file = cell.get("per_file") or {}
    overrides = cell.get("per_file_overrides") or {}

    def contribution(f: str) -> int:
        if f in overrides:
            return overrides[f] or 0
        return per_file.get(f, 0) or 0

    out: list[dict] = []
    for s in suspects:
        if s.get("kind") == KIND_FILENAME:
            out.append({**s, "counted": contribution(s["file"]) > 0})
        else:
            out.append(s)
    return out


def _ranges_overlap(a: list[int] | tuple[int, int], b: list[int] | tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _op_suppresses(suspect: dict, op: dict) -> bool:
    """Whether ONE pending op on the same (cell, file) suppresses ``suspect`` (§5 table)."""
    op_type = op.get("op_type")
    if op_type == _OP_MOVE:
        return True  # whole file already leaving → suppress everything on it
    if op_type == _OP_EXTRACT:
        if suspect.get("page_range") is None:
            return False  # a partial op never resolves a whole-file suspect
        op_range = (op.get("source") or {}).get("page_range")
        return bool(op_range) and _ranges_overlap(suspect["page_range"], op_range)
    return False  # rotate / split_in_place never suppress


def open_suspects(
    suspects: list[dict], reorg_ops: list[dict], hospital: str, sigla: str
) -> list[dict]:
    """The OPEN suspects = raw minus the op-suppressed ones (spec §5).

    DERIVED, never persisted: deleting the op un-suppresses automatically. Ops
    participate only when ``status == "pending"`` AND their SOURCE CELL matches
    ``(hospital, sigla, file)`` — never basename alone (the corpus reuses
    basenames across cells, F10). ``applied`` ops don't participate: the file is
    then gone from the folder, so eviction already removed its suspect.

    Args:
        suspects: the cell's raw persisted suspect list.
        reorg_ops: the session's reorg ops (``state["reorg_ops"]``).
        hospital: the suspects' cell hospital.
        sigla: the suspects' cell sigla.

    Returns:
        The suspects not covered by a matching pending op.
    """
    relevant: dict[str, list[dict]] = {}
    for op in reorg_ops or []:
        src = op.get("source") or {}
        if (
            op.get("status") == "pending"
            and src.get("hospital") == hospital
            and src.get("sigla") == sigla
            and src.get("file")
        ):
            relevant.setdefault(src["file"], []).append(op)
    return [
        s
        for s in suspects or []
        if not any(_op_suppresses(s, op) for op in relevant.get(s.get("file"), []))
    ]


def has_open_counted_suspects(
    suspects: list[dict], reorg_ops: list[dict], hospital: str, sigla: str
) -> bool:
    """The ``all_reliable`` gate term (spec §4.5): any OPEN suspect with ``counted``."""
    return any(s.get("counted") for s in open_suspects(suspects, reorg_ops, hospital, sigla))
