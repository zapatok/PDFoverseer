"""Hand-labeled ground truth for the pagination benchmark (controller-curated 2026-06-20).

Each Sample references a real corpus file under ``INFORME_MENSUAL_ROOT/MAYO`` (resolved
at runtime — NO corpus bytes are committed). GT counted from the most trustworthy source
available, recorded per sample:

  * "DB filename_glob": Daniel's finalized MAYO count for that cell. Trustworthy for a
    *whole* merged file, because he counted the DIVIDED files (1 file = 1 doc) BEFORE
    merging, so the count == the true document count inside the merged PDF.
  * "1-de-1 deterministic": every page is "Página 1 de 1" → docs == pages (not an estimate).
  * "eye": controller counted by looking at the rendered pages (used for slices of the
    degraded merged monsters and for the RCH controls).

Disk folder names (numbered 1..20 on disk) differ from core.domain.CATEGORY_FOLDERS for
cats 13+; the globs below use the on-disk names. ``sigla`` is the canonical key (for the
production-scanner baseline); ``glob`` finds the file; ``page_range`` slices it light.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    sigla: str
    glob: str  # under INFORME_MENSUAL_ROOT/MAYO
    page_range: tuple[int, int] | None  # (start, end) 0-based half-open; None = whole file
    gt: int
    gt_source: str
    cover_code: str | None = None
    note: str = ""


SAMPLES: list[Sample] = [
    # --- Tier A: clean paginated forms (expect MIGRATE) ---
    Sample("odi", "HRB/3.-ODI Visitas/**/*odi*.pdf", None, 21, "DB filename_glob"),
    Sample(
        "art",
        "HPV/7.-ART/**/*aguasan*.pdf",
        None,
        5,
        "eye",
        note="clean 5x4pp ARTs ('Pagina 1 de 4')",
    ),
    Sample(
        "art",
        "HLL/7.-ART/*art*.pdf",
        (0, 120),
        30,
        "eye",
        note="degraded merged slice (+-1) — exercises gap recovery",
    ),
    Sample("altura", "HLU/15.-Trabajos en Altura/**/*altura*.pdf", None, 20, "DB filename_glob"),
    Sample("ext", "HLL/11.-Extintores/**/*ext*.pdf", None, 38, "DB filename_glob"),
    Sample("bodega", "HLL/9.-Inspeccion Bodega/**/*bodega*.pdf", None, 2, "DB filename_glob"),
    Sample(
        "caliente",
        "HLL/16.-Inspeccion Trabajos en Caliente/**/*caliente*.pdf",
        (0, 60),
        60,
        "1-de-1 deterministic",
    ),
    Sample(
        "insgral",
        "HLL/8.-Inspecciones Generales/*insgral*.pdf",
        None,
        1,
        "DB filename_glob",
        note="6pp single checklist — must group to 1 doc",
    ),
    Sample(
        "insgral",
        "HLU/8.-Inspecciones Generales/**/*insgral*arnes*.pdf",
        None,
        48,
        "1-de-1 deterministic",
        note="48 single-page checklists — heterogeneity",
    ),
    Sample(
        "irl",
        "HLU/2.-Induccion IRL/**/*mathias*.pdf",
        None,
        1,
        "eye",
        cover_code="F-CRS-IRL-01",
        note="1 induction packet (31pp IRL form + appendices)",
    ),
    # --- "verificar": likely paginated, migration decided by the benchmark ---
    Sample("exc", "HLL/14.-Excavaciones y Vanos/**/*exc*.pdf", None, 24, "DB filename_glob"),
    Sample("andamios", "HLL/19.-Andamios/**/*andamios*.pdf", None, 39, "DB filename_glob"),
    Sample(
        "herramientas_elec",
        "HLL/18.-Inspeccion Herramientas Electricas/**/*herramientas_elec*.pdf",
        (0, 60),
        60,
        "1-de-1 deterministic",
        note="verificar — assume 1pp; benchmark confirms",
    ),
    # --- RCH controls: pagination is expected to MIS-count (the '1 de 2' bug) → KEEP anchors ---
    Sample(
        "chintegral",
        "HLL/5.-Charla Integral/*chintegral*.pdf",
        None,
        25,
        "eye",
        note="RCH control (~25, +-3); DB says 2 which is WRONG. Expect KEEP.",
    ),
    Sample(
        "charla",
        "HLU/4.-Charlas/**/*charla*rocate*.pdf",
        None,
        36,
        "1-de-1 deterministic",
        note="RCH but all 1pp here → pagination happens to be exact; still KEEP family",
    ),
    Sample(
        "senal",
        "HLL/12.-Senaleticas/**/*senal*.pdf",
        None,
        18,
        "DB filename_glob",
        note="LANDSCAPE — pagination corner expected to FAIL → KEEP anchors",
    ),
]
