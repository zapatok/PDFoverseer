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
from pathlib import Path

import fitz

from core.scanners.patterns import CRS_RCH_ANCHORS


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


# ---------------------------------------------------------------------------
# Synthetic RCH fixtures (Track D / D2, Task 6). Reproduce the pattern Fase 0
# actually MEASURED (docs/research/2026-07-12-rch-corner-survey.md) — clean,
# correctly-alternating pagination is the norm on the 7 real charla samples,
# not the originally-imagined uniform "1 de N" repeat. One adversarial case
# (``rch_case_bug_repeated_pagination``) is kept as a regression guard for the
# hybrid-fallback approach even though Fase 0 did not observe it on the real
# samples — an untested safety net proves nothing.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RchPageSpec:
    """One page of a synthetic RCH-template PDF (see ``make_rch_pdf``).

    ``printed_curr``/``printed_total`` are the pagination text actually
    rendered in the corner (``None`` → no pagination text at all, e.g. an
    illegible cover or an appendix page). ``cover_anchors`` renders a handful
    of real ``CRS_RCH_ANCHORS`` phrases in the top-left band — the region
    Fase 0 found actually holds the cover-only fields (Result 2 of the
    corner-survey doc), used by the region-discriminator approach's tests.
    """

    printed_curr: int | None
    printed_total: int | None
    cover_anchors: bool = False
    code: str = "F-CRS-RCH-01"


def make_rch_pdf(path: Path, pages: list[RchPageSpec]) -> Path:
    """Render a synthetic RCH-template compilation PDF from *pages*.

    Mirrors ``conftest.make_pagination_pdf``'s corner placement (top-right,
    "Codigo: …" / "Pagina C de M") and adds an optional top-left cover-anchor
    block per page (real ``CRS_RCH_ANCHORS`` phrases, y < 200pt — inside both
    the default 0.25 AND charla's 1/3 top-band fraction of an A4 page, so
    either anchor-strategy band reads it consistently).

    Args:
        path: destination PDF path.
        pages: one ``RchPageSpec`` per page, in order.

    Returns:
        *path* (for chaining, matching ``conftest.make_pagination_pdf``).
    """
    doc = fitz.open()
    rect = fitz.paper_rect("a4")
    for spec in pages:
        page = doc.new_page(width=rect.width, height=rect.height)
        if spec.printed_curr is not None:
            x = page.rect.width - 230
            page.insert_text((x, 36), f"Codigo: {spec.code}", fontsize=10)
            if spec.printed_total is not None:
                page.insert_text(
                    (x, 52),
                    f"Pagina {spec.printed_curr} de {spec.printed_total}",
                    fontsize=10,
                )
        if spec.cover_anchors:
            y = 40
            for anchor in CRS_RCH_ANCHORS[:5]:
                page.insert_text((40, y), anchor, fontsize=9)
                y += 20
        page.insert_text((72, 260), "contenido de prueba", fontsize=12)
    doc.save(path)
    doc.close()
    return path


def rch_case_uniform_2pp(n_docs: int = 6) -> list[RchPageSpec]:
    """Uniform 2pp/doc — the pattern CH_39/CH_51/CH_BSM_18 actually measured
    (Fase 0): every document reads "1 de 2" then "2 de 2", correctly."""
    pages: list[RchPageSpec] = []
    for _ in range(n_docs):
        pages.append(RchPageSpec(1, 2, cover_anchors=True))
        pages.append(RchPageSpec(2, 2))
    return pages


def rch_case_mixed_2_3pp() -> list[RchPageSpec]:
    """Mixed 2pp + 3pp docs — the pattern CHAR_25 measured (Fase 0): document
    lengths vary but each page reads its own pagination correctly."""
    return [
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
        RchPageSpec(1, 3, cover_anchors=True),
        RchPageSpec(2, 3),
        RchPageSpec(3, 3),
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
    ]


def rch_case_illegible_cover() -> list[RchPageSpec]:
    """A cover whose corner OCR fails entirely (no pagination text rendered) —
    the CH_39 page-14 case Fase 0 actually measured (one isolated OCR miss,
    not a systematic bug). Production recovery fills the gap; the
    undercount-safe tests assert an unconfirmed page never fabricates an
    extra count."""
    return [
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
        RchPageSpec(None, None),  # illegible cover — no pagination text at all
        RchPageSpec(2, 2),
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
    ]


def rch_case_appendix_no_pagination() -> list[RchPageSpec]:
    """A compilation followed by trailing appendix pages that carry no
    pagination marker at all (attachments, photos) — not observed in the 7
    Fase-0 samples but a realistic corpus shape worth guarding against."""
    return [
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
        RchPageSpec(None, None),  # appendix p1 — no pagination
        RchPageSpec(None, None),  # appendix p2 — no pagination
    ]


def rch_case_bug_repeated_pagination() -> list[RchPageSpec]:
    """ADVERSARIAL regression case — NOT measured in Fase 0 (see
    docs/research/2026-07-12-rch-corner-survey.md, Resultado 1: zero
    confirmed occurrences across 136 real pages). Reproduces the originally
    PINNED bug literally: a continuation page repeats "Pagina 1 de 2" instead
    of "Pagina 2 de 2". Kept to prove the hybrid fallback (approach 3)
    actually engages when the pattern DOES appear — an untested safety net
    proves nothing."""
    return [
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(1, 2),  # BUG: continuation repeats "1 de 2"
        RchPageSpec(1, 2, cover_anchors=True),
        RchPageSpec(2, 2),
    ]


def rch_case_bug_all_pages_read_1(n_docs: int = 3, doc_len: int = 2) -> list[RchPageSpec]:
    """ADVERSARIAL regression case for ``count_by_arithmetic_dedup``'s ONE
    documented trigger path (spec §3, candidate 1: "TODAS las páginas leen
    1 de M"). NOT measured in Fase 0 — no real sample ever had every page
    (covers AND continuations) read "1 de N"; this is the extreme,
    unobserved worst case the approach was originally designed for."""
    return [
        RchPageSpec(1, doc_len, cover_anchors=(i % doc_len == 0)) for i in range(n_docs * doc_len)
    ]
