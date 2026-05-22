"""Central registry of patterns per sigla — see A1, A9, A10, A11 in the spec.

Each entry declares how a sigla counts when filename_glob is not enough.
The 18 SIGLAS from core.domain MUST each have an entry here.

See:
    docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md
"""

from __future__ import annotations

from typing import Literal, TypedDict

from typing_extensions import NotRequired

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

    `filename_glob`: lax full-match regex (A10) — the ^.* prefix allows arbitrary prefixes; matched via re.match.
    `scan_strategy`: "anchors" | "pagination" | "none".
    `cover_flavors`: required if strategy="anchors".
    `top_fraction`: optional — default 0.25 (A2).
    `recursive_glob`: optional — INFORMATIONAL ONLY (count_pdfs_by_sigla
        already uses rglob unconditionally; this field documents intent).
    """

    filename_glob: str
    scan_strategy: ScanStrategy
    cover_flavors: NotRequired[list[Flavor]]
    top_fraction: NotRequired[float]
    recursive_glob: NotRequired[bool]


# Defaults documented as source of truth.
DEFAULT_TOP_FRACTION: float = 0.25
DEFAULT_MIN_MATCH: int = 3
DEFAULT_ANTI_MIN_MATCH: int = 1


# ---------------------------------------------------------------------------
# ART anchor constants (OCR-verified 2026-05-21 against f_art_01_p1.pdf)
#
# top_fraction=0.40 chosen empirically — at 0.25 the cover band did not
# reliably yield the anchor pair under OCR. "analisis de riesgos" is the form
# title and appears on every page; "pagina 1" is the cover-only discriminator
# (the header pagination reads "Página 1 de 4" on the cover, "Página 2 de 4"
# etc. on continuations). The anchor is "pagina 1" — not "pagina 1 de" — so it
# tolerates OCR rendering the digit with or without a space ("1 de" / "1de").
# Both anchors must match (min_match=2).
# ---------------------------------------------------------------------------
_ART_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_art_01",
        "anchors": [
            "pagina 1",  # cover-only — header pagination start; space-tolerant
            "analisis de riesgos",  # ART form title, present on all pages (makes pair unique)
        ],
        "min_match": 2,
    },
]

# ---------------------------------------------------------------------------
# IRL anchor constants (OCR-verified 2026-05-21 against f_irl_01_p1.pdf)
#
# IRL booklets are 50+ page compilations (pages 1-32 are the core booklet;
# pages 33+ are embedded sub-forms: test de comprension, declarations, etc.).
# The booklet running header ("f crs odi 01" + title) repeats on EVERY page
# of the 32-page section — it cannot discriminate P1 from P2-P32.
# The body intro "forma oportuna" also repeats verbatim (DS-44 article text).
#
# The IRL *cover* (P1) is uniquely identified by attendance-section fields:
#   "pagina 1 de"           — page-1 marker; absent on pages 2-32 (pagina 2 de
#                             32 etc.); sub-form covers at pages 33+ also have
#                             pagina-1-de but lack the second anchor.
#   "fecha de realizacion"  — attendance header field present only on the IRL
#                             cover; absent from all sub-form covers (test
#                             forms, declarations, cartillas at pages 33+).
# min_match=2 requires both simultaneously.
# ---------------------------------------------------------------------------
_IRL_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_odi_01",
        "anchors": [
            "pagina 1 de",  # page-1 marker — P1 only among the 32-page booklet
            "fecha de realizacion",  # attendance field — IRL cover only, absent from sub-forms
        ],
        "min_match": 2,
    },
]

# ---------------------------------------------------------------------------
# ODI anchor constants (OCR-verified 2026-05-21 against f_odi_01_p1.pdf)
#
# ODI is a 2-page form. Both pages share the title "obligacion de informar
# visita" in the header. Only the cover (P1) has "nombre completo" (the
# signature field section). P2 has "induccion inicial" in its body. Using
# title + signature-field anchor discriminates P1 uniquely. min_match=2.
# ---------------------------------------------------------------------------
_ODI_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_odi_03",
        "anchors": [
            "obligacion de informar visita",  # ODI title — both pages
            "nombre completo",  # Signature table header — cover only
        ],
        "min_match": 2,
    },
]

# ---------------------------------------------------------------------------
# Charla anchor constants (OCR-verified 2026-05-21 against f_rch_p1.pdf)
#
# Charla PDFs are multi-document compilations: P1 and P3 are both covers
# (separate charla sessions), P2 is the continuation of the first session.
# "registro de charla" appears in all pages' headers; "nombre de la charla"
# appears only on cover pages (P1 and P3). min_match=2 pairs the title
# (universal) with the cover-specific field label.
# ---------------------------------------------------------------------------
_CHARLA_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_rch_01",
        "anchors": [
            "registro de charla",  # Charla form title — all pages
            "nombre de la charla",  # Session title field — cover pages only
        ],
        "min_match": 2,
    },
]

# ---------------------------------------------------------------------------
# Bodega anchor constants (OCR-verified 2026-05-21 against
# f_pets_07_03_p1_chequeo.pdf — 4-page HPV compilation with 4 separate
# bodega cover pages, each "Pagina 1 de 1").
#
# The form header reads "CHEQUEO BODEGA SUSPEL/RESPEL  F-PETS-CRS-07-03"
# followed by "CONSTRUCTORA REGION SUR S.A." — all present in the top 25%
# band on every page.  With min_match=3 the triple
# ("chequeo bodega" ∩ "f-pets-crs-07-03" ∩ "bodega suspel") fires on every
# page — which is CORRECT: each page of this PDF is a separate 1-page
# document (distinct dates/RESPEL sections); all 4 are covers.
# "bodega respel" was NOT verified in the top 25% band (OCR sees it as part
# of "suspel/respel" without a leading "bodega " prefix); dropped from the
# working anchor set.  "realizado por" and "obra" appear sporadically; kept
# as optional extras that do not affect min_match=3 firing.
# ---------------------------------------------------------------------------
_BODEGA_ANCHORS: list[Flavor] = [
    {
        "name": "f_pets_07_03",
        "anchors": [
            "chequeo bodega",  # Form title — all bodega covers
            "f-pets-crs-07-03",  # Form code — all bodega covers
            "bodega suspel",  # Section label — present on cover band
            "realizado por",  # Signatory field — optional extra
            "obra",  # Site field — optional extra
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# CHPS anchor constants (OCR-verified 2026-05-21 against
# f_ar_01_p1_acta_reunion.pdf — 3-page HPV CHPS meeting minutes).
#
# "acta de reunion" appears in the running header of all 3 pages.
# "f-crs-ar-01" also appears in the running header of all pages.
# "lista de convocados" is ONLY on the cover (page 1 attendee table).
# "hospital de" and "lugar de la reunion" are also cover-only fields.
# min_match=3: cover (p1) gets ≥5 matches; continuations (p2/p3) get 2
# ("acta de reunion" + "f-crs-ar-01") → not counted as covers.
# ---------------------------------------------------------------------------
_CHPS_ANCHORS: list[Flavor] = [
    {
        "name": "f_ar_01",
        "anchors": [
            "acta de reunion",  # Form title — all pages (running header)
            "f-crs-ar-01",  # Form code — all pages (running header)
            "lista de convocados",  # Attendee table header — cover only (p1)
            "hospital de",  # Site field — cover only (p1)
            "lugar de la reunion",  # Meeting location field — cover only (p1)
        ],
        "min_match": 3,
    },
]


PATTERNS: dict[str, SiglaPattern] = {
    "reunion": {
        "filename_glob": r"^.*reunion.*\.pdf$",
        "scan_strategy": "none",
    },
    "art": {
        "filename_glob": r"^.*art.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _ART_ANCHORS,
        "top_fraction": 0.40,
    },
    "irl": {
        "filename_glob": r"^.*irl.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _IRL_ANCHORS,
    },
    "odi": {
        "filename_glob": r"^.*odi.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _ODI_ANCHORS,
    },
    "charla": {
        "filename_glob": r"^.*charla.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _CHARLA_ANCHORS,
    },
    "insgral": {
        "filename_glob": r"^.*insgral.*\.pdf$",
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
    "bodega": {
        "filename_glob": r"^.*bodega.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _BODEGA_ANCHORS,
    },
    "altura": {
        "filename_glob": r"^.*altura.*\.pdf$",
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
    "chps": {
        "filename_glob": r"^.*chps.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": _CHPS_ANCHORS,
    },
    # ... remaining entries llenadas en chunks posteriores
}


def get_pattern(sigla: str) -> SiglaPattern:
    """Return the SiglaPattern for `sigla`. Raises KeyError if unknown."""
    if sigla not in PATTERNS:
        raise KeyError(f"unknown_sigla: {sigla}")
    return PATTERNS[sigla]
