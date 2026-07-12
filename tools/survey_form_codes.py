"""Deep form-code survey for the anti-colados vertiente-2 gate (spec §7).

READ-ONLY over the corpus (never writes there). Walks ABRIL+MAYO × 4 hospitals,
resolves each folder to its sigla, and for every MULTI-PAGE PDF of a pagination
sigla OCRs the top-right corner with the PRODUCTION extractor
(``pagination_count._corner_text`` + ``extract_code``). Aggregates the normalized
form codes per sigla so we can propose ``expected_codes`` and flag cross-sigla
collisions before wiring vertiente 2.

Why multi-page only: A7 files (1 page) never reach vertiente 2, so their codes
are irrelevant. HRB is over-sampled (Daniel: it is the misfile hotspot).

Maintenance tool (A13-adjacent). Usage:

    python -X utf8 tools/survey_form_codes.py [--months ABRIL MAYO] [--out map.md]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # noqa: E402

from core.domain import folder_to_sigla  # noqa: E402
from core.scanners.patterns import PATTERNS  # noqa: E402
from core.scanners.utils.pagination_count import (  # noqa: E402
    _DIGIT,
    _corner_text,
    extract_code,
)

CORPUS = Path("A:/informe mensual")
HOSPITALS = ["HPV", "HRB", "HLU", "HLL"]
PAGES_PER_PDF = 8
PDFS_PER_CELL = 8
PDFS_PER_CELL_HRB = 16  # HRB is the hotspot — over-sample it

PAGINATION_SIGLAS = [s for s, p in PATTERNS.items() if p.get("scan_strategy") == "pagination"]


def normalize_code(raw: str) -> str:
    """Form-code normalization (uppercase → strip non-alnum → OCR fold).

    This survey's own copy — kept as-is permanently, not a TEMP stand-in: the
    anti-colados vertiente-2 gate this fed (spec §7, "Task 12") was ABORTED
    2026-07-04 (see ``docs/research/2026-07-04-anti-colados-v2-survey-abort.md``),
    so there is no ``colado_guard.normalize_code`` to import. The survey script
    itself stays as a standalone maintenance/research tool.
    """
    folded = raw.upper().translate(_DIGIT)
    return re.sub(r"[^A-Z0-9]", "", folded)


def _pdf_codes(pdf: Path) -> Counter[str]:
    codes: Counter[str] = Counter()
    try:
        with fitz.open(pdf) as doc:
            if doc.page_count <= 1:
                return codes  # A7 — never seen by vertiente 2
            for pi in range(min(doc.page_count, PAGES_PER_PDF)):
                code = extract_code(_corner_text(doc[pi]))
                if code:
                    codes[normalize_code(code)] += 1
    except Exception as exc:  # noqa: BLE001 — survey tool, keep going on a bad PDF
        print(f"  !! {pdf.name}: {exc}", flush=True)
    return codes


def survey(months: list[str]) -> dict[str, Counter[str]]:
    """Return ``{sigla: Counter[normalized_code]}`` across the sampled corpus."""
    per_sigla: dict[str, Counter[str]] = defaultdict(Counter)
    sampled: Counter[str] = Counter()
    for month in months:
        for hosp in HOSPITALS:
            hdir = CORPUS / month / hosp
            if not hdir.is_dir():
                continue
            cap = PDFS_PER_CELL_HRB if hosp == "HRB" else PDFS_PER_CELL
            for folder in sorted(p for p in hdir.iterdir() if p.is_dir()):
                sigla = folder_to_sigla(folder.name)
                if sigla not in PAGINATION_SIGLAS:
                    continue
                key = f"{sigla}|{hosp}"
                for pdf in sorted(folder.rglob("*.pdf")):
                    if sampled[key] >= cap:
                        break
                    codes = _pdf_codes(pdf)
                    if codes:
                        per_sigla[sigla] += codes
                        sampled[key] += 1
    return per_sigla


def propose(per_sigla: dict[str, Counter[str]]) -> dict[str, list[str]]:
    """Propose ``expected_codes`` per sigla: codes seen ≥2× (drop OCR-noise singletons)."""
    return {
        sigla: sorted(c for c, n in codes.most_common() if n >= 2)
        for sigla, codes in per_sigla.items()
        if any(n >= 2 for n in codes.values())
    }


def collisions(proposed: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Pairwise cross-sigla equality on normalized codes (a code shared by two siglas)."""
    out: list[tuple[str, str, str]] = []
    siglas = list(proposed)
    for i, a in enumerate(siglas):
        for b in siglas[i + 1 :]:
            shared = set(proposed[a]) & set(proposed[b])
            for code in sorted(shared):
                out.append((a, b, code))
    return out


def render(per_sigla: dict[str, Counter[str]], proposed: dict[str, list[str]]) -> str:
    lines = ["# Anti-colados vertiente-2 code survey\n"]
    for sigla in PAGINATION_SIGLAS:
        codes = per_sigla.get(sigla)
        if not codes:
            lines.append(f"## {sigla}\n\n(no multi-page codes read) → OUT of vertiente 2\n")
            continue
        freq = ", ".join(f"`{c}`×{n}" for c, n in codes.most_common())
        prop = proposed.get(sigla)
        lines.append(f"## {sigla}\n\n- codes: {freq}")
        lines.append(
            f"- proposed expected_codes: {prop if prop else 'NONE (all singletons) → OUT'}\n"
        )
    cols = collisions(proposed)
    lines.append("## Cross-sigla collisions\n")
    lines.append("\n".join(f"- ⚠ {a} vs {b}: `{c}`" for a, b, c in cols) if cols else "- none\n")
    viable = len(proposed)
    lines.append(f"\n## Verdict\n\n- viable siglas: {viable} (abort criterion: <4)\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", default=["ABRIL", "MAYO"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    per_sigla = survey(args.months)
    proposed = propose(per_sigla)
    report = render(per_sigla, proposed)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"\n[written to {args.out}]")


if __name__ == "__main__":
    main()
