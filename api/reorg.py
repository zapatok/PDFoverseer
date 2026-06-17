"""Pure helpers for reorg ops: validation, default resolution, manifest build.

No I/O, no FastAPI — unit-testable in isolation. The endpoints in
``api/routes/sessions.py`` gather the filesystem/state inputs and call these.
"""

from __future__ import annotations

from datetime import datetime

OP_TYPES = {"move_file", "extract_pages", "split_in_place", "rotate"}
ROTATIONS = {0, 90, 180, 270}
MANIFEST_VERSION = 1


def _ranges_overlap(a: list[int], b: list[int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def validate_op(op: dict, *, src_pages: dict[str, int], existing_ops: list[dict]) -> list[str]:
    """Return a list of human-readable error strings ([] = valid).

    Args:
        op: the proposed op (without an id yet).
        src_pages: {filename: page_count} of the *source* cell folder.
        existing_ops: the session's current reorg_ops (for overlap checks).
    """
    errors: list[str] = []
    ot = op.get("op_type")
    if ot not in OP_TYPES:
        errors.append(f"op_type inválido: {ot!r}")
        return errors

    src = op.get("source") or {}
    dst = op.get("dest") or {}
    file = src.get("file")
    pr = op.get("page_range")

    same_cell = (src.get("hospital"), src.get("sigla")) == (dst.get("hospital"), dst.get("sigla"))
    if same_cell and ot in ("move_file", "extract_pages"):
        errors.append("dest no puede ser igual a source para move_file/extract_pages")

    if file not in src_pages:
        errors.append(f"archivo origen no presente: {file!r}")
    pages = src_pages.get(file, 0)

    if ot == "move_file" and pr is not None:
        errors.append("move_file no admite page_range")
    if ot == "extract_pages":
        if pr is None:
            errors.append("extract_pages requiere page_range")
        else:
            x, y = pr
            if not (1 <= x <= y <= pages):
                errors.append(f"page_range fuera de límites: {pr} (páginas={pages})")
            for other in existing_ops:
                if (
                    other.get("op_type") == "extract_pages"
                    and other.get("status", "pending") == "pending"
                    and (other.get("source") or {}).get("file") == file
                    and other.get("page_range")
                    and _ranges_overlap(pr, other["page_range"])
                ):
                    errors.append(
                        f"page_range solapa otra op del mismo archivo: {other['page_range']}"
                    )

    rot = op.get("rotation_deg", 0)
    if rot not in ROTATIONS:
        errors.append(f"rotation_deg inválido: {rot}")

    dc = op.get("doc_count")
    if dc is not None:
        if dc < 0:
            errors.append("doc_count no puede ser negativo")
        elif ot == "extract_pages" and pr is not None and dc > (pr[1] - pr[0] + 1):
            errors.append("doc_count excede las páginas del rango")
        elif ot == "move_file" and dc > pages:
            errors.append("doc_count excede las páginas del archivo")

    return errors


def resolve_op_defaults(op: dict, *, src_cell: dict) -> dict:
    """Return a copy of ``op`` with doc_count/worker_count filled if absent.

    move_file: doc_count = the file's current cell contribution
      (per_file_overrides | per_file | 1); worker_count = sum of the file's marks.
    extract_pages: doc_count = 1; worker_count = sum of marks on the page range.
    split_in_place / rotate: doc_count = worker_count = 0.
    """
    out = dict(op)
    ot = op["op_type"]
    file = (op.get("source") or {}).get("file")
    pr = op.get("page_range")

    def _marks_total(pred) -> int:
        marks = (src_cell.get("worker_marks") or {}).get(file) or []
        return sum((m.get("count") or 0) for m in marks if pred(m))

    def _set_if_none(key: str, value) -> None:
        if out.get(key) is None:
            out[key] = value

    if ot == "move_file":
        per_file = src_cell.get("per_file") or {}
        overrides = src_cell.get("per_file_overrides") or {}
        _set_if_none("doc_count", overrides.get(file, per_file.get(file, 1)))
        _set_if_none("worker_count", _marks_total(lambda m: True))
    elif ot == "extract_pages":
        _set_if_none("doc_count", 1)
        _set_if_none(
            "worker_count",
            _marks_total(lambda m: pr and pr[0] <= (m.get("page") or 0) <= pr[1]),
        )
    else:  # split_in_place, rotate
        _set_if_none("doc_count", 0)
        _set_if_none("worker_count", 0)

    out.setdefault("status", "pending")
    out.setdefault("preserve_date", True)
    out.setdefault("rotation_deg", 0)
    out.setdefault("empresa", None)
    out.setdefault("note", None)
    return out


def build_manifest(state: dict, *, month: str) -> dict:
    """Build the export manifest from a session's pending reorg ops."""
    pending = [o for o in state.get("reorg_ops", []) if o.get("status") == "pending"]
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_project": "PDFoverseer",
        "month": month,
        "operations": pending,
    }
