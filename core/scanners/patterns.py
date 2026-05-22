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

# ---------------------------------------------------------------------------
# Chintegral anchor constants (OCR-verified 2026-05-22).
#
# Three flavors observed in the corpus:
#
# f_rch  — Standard RCH template (F-CRS-RCH-01).  The form header reads
#   "REGISTRO DE CHARLA" + "NOMBRE DE LA CHARLA" on cover pages; continuation
#   pages lack "nombre de la charla".  min_match=2 requires both simultaneously.
#   Same anchor pair as _CHARLA_ANCHORS (charla sigla) — shared by design; the
#   two siglas differ in filename_glob and scan context, not in the anchor set.
#
# f_japa — JAPA contractor variant.  The form header reads
#   "REGISTRO CAPACITACIÓN ..." + contractor name "SOCIEDAD DE PROYECTOS DE
#   INGENIERIA".  Plan-proposed anchors ("JAPA", "Nombre del trabajador") were
#   OCR-rejected: they do not appear in the top 25% band.  min_match=2.
#
# f_previene — PREVIENE programme ("PROGRAMA PREVIENE: INFANCIA, JUVENTUD Y
#   BIENESTAR" + "LISTA DE ASISTENCIA").  Odd pages are covers; even pages are
#   signature continuation pages that lack "lista de asistencia" in the top
#   band.  min_match=2.
# ---------------------------------------------------------------------------
_CHINTEGRAL_ANCHORS: list[Flavor] = [
    {
        "name": "f_rch",
        "anchors": [
            "registro de charla",  # Form title — cover and continuations share title
            "nombre de la charla",  # Session title field — cover pages only
        ],
        "min_match": 2,
    },
    {
        "name": "f_japa",
        "anchors": [
            "registro capacitacion",  # JAPA form title prefix (accent-stripped)
            "sociedad de proyectos de ingenieria",  # JAPA contractor name
        ],
        "min_match": 2,
    },
    {
        "name": "f_previene",
        "anchors": [
            "programa previene",  # PREVIENE programme title prefix
            "lista de asistencia",  # Attendance section header — cover pages only
        ],
        "min_match": 2,
    },
]


# ---------------------------------------------------------------------------
# Maquinaria anchor constants (OCR-verified 2026-05-21 against
# maquinaria_accesorios_de_levante.pdf — 7-page HPV compilation with 7
# standalone 1-page checklists; also cross-checked against LCH-08/LCH-15/
# LCH-16 templates from HPV corpus).
#
# The top 25% band reliably captures the form header: "f crs lch" form code
# + "constructora region sur" + "pagina 1 de".  For multi-page forms
# (e.g. LCH-16 grua torres: "Página 1 de 2" / "Página 2 de 2"), only page-1
# carries "pagina 1 de" — continuations read "pagina 2 de" and do NOT fire.
# For 1-page forms (LCH-09 accesorios, LCH-15 montacarga), every page is a
# standalone doc and "pagina 1 de 1" fires on each.
#
# Plan candidates "FECHA ÚLTIMA MANTENCIÓN", "NOMBRE OPERADOR", "RUT", "MARCA"
# were DROPPED: they appear in the body (below 25% band on most templates) and
# are not reliably in the top band across the ≥5 templates observed.
# min_match=2 requires "pagina 1 de" ∩ "constructora region sur".
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Ext anchor constants (OCR-verified 2026-05-21 against ext_chequeos.pdf —
# 15-page HPV compilation; all 15 pages are standalone 1-page extintor
# checklists "Página 1 de 1").
#
# The form header contains "CHEQUEO EXTINTORES" (title), "F-CRS-LCH-18"
# (code, normalized to "f crs lch"), "Constructora Región Sur SpA"
# (normalized to "constructora region sur"), and "Página 1 de 1" (pagination).
# All four are present in the top 25% band on every page.  P1 misses
# "constructora region sur" due to OCR noise on the logo area, but still
# gets 3 hits from the remaining three anchors.  min_match=3 is safe:
# every page reaches ≥3 hits; a hypothetical continuation page that lacked
# "pagina 1 de" would get only 2 hits ("chequeo extintores" + "f crs lch")
# and would not count as a cover.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Caliente anchor constants (OCR-verified 2026-05-21 against
# caliente_chequeos.pdf — 19-page HPV compilation; all 19 pages are standalone
# 1-page trabajos en caliente checklists "Página 1 de 1").
#
# The form header reads "CHEQUEO TRABAJOS EN CALIENTE" and "F-LCH-CRS-32"
# (normalized to "f lch crs" — NOTE: code direction is LCH-CRS, not CRS-LCH).
# "CONSTRUCTORA REGION SUR" and "Página 1 de 1" are also in the top band.
# min_match=3: every standalone cover gets ≥3 hits; a continuation page that
# lacked "pagina 1 de" would drop to ≤2 hits and not count as a cover.
# ---------------------------------------------------------------------------
_CALIENTE_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_crs_32",
        "anchors": [
            "chequeo trabajos en caliente",  # form title — all pages
            "constructora region sur",  # org name — all pages
            "f lch crs",  # form-code family prefix (A12, direction LCH-CRS) — all pages
            "pagina 1 de",  # cover-only discriminator — "Pagina 1 de 1"
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Exc anchor constants (OCR-verified 2026-05-21 against exc_chequeos.pdf —
# 23-page HPV compilation; all 23 pages are standalone 1-page excavacion
# checklists "Página 1 de 1").
#
# The form header reads "EXCAVACIONES" (or "EXCAVACION" depending on template)
# and "F-CRS-LCH-xx" (normalizes to "f crs lch").  "CONSTRUCTORA REGION SUR"
# and "Página 1 de 1" also appear in the top 25% band.  min_match=3: every
# standalone cover gets ≥3 of the four hits; a hypothetical continuation page
# (pagina 2 de N) would miss "pagina 1 de" and drop to ≤2 hits.
# ---------------------------------------------------------------------------
_EXC_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",
        "anchors": [
            "excavaciones",  # form title — all pages
            "constructora region sur",  # org name — all pages
            "f crs lch",  # form-code family prefix (A12) — all pages
            "pagina 1 de",  # cover-only discriminator — "Pagina 1 de 1"
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Senal anchor constants (OCR-verified 2026-05-21 against senal_chequeos.pdf —
# 6-page HPV compilation; all 6 pages are standalone senaletica checklists).
#
# Senal forms use landscape/mixed orientations — the form title "LISTA DE
# CHEQUEO DE SEÑALÉTICA DE SEGURIDAD" and "CONSTRUCTORA REGION SUR" appear
# in different positions depending on form variant.  top_fraction=1.0 is
# required: at 0.25 many pages miss both anchors due to layout variance.
# With full-page scan both anchors appear on every page (each is its own
# standalone cover — no continuation pages).
# Plan candidates ("F-PETS-CRS", "FECHA", "EMPRESA CONTRATISTA") were DROPPED:
# "F-PETS-CRS" yields "f pets crs" which only appeared on 1/6 pages; the
# others were not in the OCR top region consistently.
# min_match=2 requires both anchors simultaneously.
# ---------------------------------------------------------------------------
_SENAL_ANCHORS: list[Flavor] = [
    {
        "name": "f_pets_crs_xx",
        "anchors": [
            "lista de chequeo de senaletica de seguridad",  # form title — all pages
            "constructora region sur",  # org name — all pages
        ],
        "min_match": 2,
    },
]

_EXT_ANCHORS: list[Flavor] = [
    {
        # Intersection of header labels across F-CRS-LCH-18 template (HPV corpus).
        # "chequeo extintores" is the form title — present on all pages.
        # "f crs lch" is the form-code family prefix (A12) — present on all pages.
        # "pagina 1 de" is the cover-only discriminator — "Pagina 1 de 1" on covers.
        # "constructora region sur" is the org name — present on most pages.
        # min_match=3 requires three of these four simultaneously.
        "name": "f_lch_xx",
        "anchors": [
            "chequeo extintores",  # form title — all pages
            "f crs lch",  # form-code family prefix (A12) — all pages
            "pagina 1 de",  # cover-only discriminator — "Pagina 1 de 1"
            "constructora region sur",  # org name — most pages (OCR noise may drop)
        ],
        "min_match": 3,
    },
]


_MAQUINARIA_ANCHORS: list[Flavor] = [
    {
        # Intersection of header labels across ≥5 templates (LCH-08 / -09 / -15 / -16 / -26).
        # "constructora region sur" is in the running header of every page (cover and continuation).
        # "pagina 1 de" is the cover-only discriminator: cover pages read "Pagina 1 de N";
        # continuation pages read "Pagina 2 de N" etc. and do NOT match this anchor.
        # min_match=2 requires both simultaneously.
        "name": "f_lch_xx",
        "anchors": [
            "pagina 1 de",  # cover-only discriminator — "Pagina 1 de N" on P1; absent on P2+
            "constructora region sur",  # running header — all pages; makes pair unique
        ],
        "min_match": 2,
    },
]


# ---------------------------------------------------------------------------
# Herramientas_elec anchor constants (OCR-verified 2026-05-22).
#
# Three flavors found in the corpus:
#
# f_lch_xx  — Standard CRS template (F-CRS-LCH family, multiple variants used
#   by HPV and HRB contractors).  Every page is a standalone cover ("Pagina 1
#   de 1").  'constructora region sur' appears in the running header; 'pagina 1
#   de' is the cover-only discriminator.  min_match=2 of 2 anchors.
#   Anti-anchor: 'chequeo de elementos' fires on the EPP form (F-CRS-LCH-02
#   "Chequeo de Elementos de Protección Personal") that is sometimes misfiled
#   here.  OCR-verified on 2-page EPP shadow fixture: 'chequeo de elementos'
#   fires on 100% of EPP pages in the top-third band; 'elementos de proteccion
#   personal' does NOT appear in the top-third band (title wraps past the crop
#   line), so it is kept as a secondary guard only.  Without anti_anchors, both
#   EPP pages would falsely fire f_lch_xx (both have 'constructora region sur'
#   + 'pagina 1 de' in the header).
#   Known limitation: standalone 1-page EPP PDFs are A7-locked (always 1 doc,
#   no OCR) — anti-anchors only protect multi-page PDFs where OCR is run.
#
# f_hll_17  — HLL proprietary form REG-SSO-HLL-17 "Chequeo de Herramientas".
#   'reg sso hll 17' is the form code; 'chequeo de herramientas' is the form
#   title.  Both appear reliably in the top-third band.  min_match=2 of 2.
#
# f_titan  — TITAN contractor proprietary template (TN-SGSSO-RG-NNN family).
#   OCR-verified 2026-05-22 on 49 TITAN-branded files from the HPV corpus.
#   TITAN uses a proprietary safety-management template distinct from the CRS
#   LCH family (different layout, different form-code family, TITAN branding).
#   63 TITAN files do use the CRS template (covered by f_lch_xx); 49 use this
#   proprietary form.  Anchors (hit rates across 49 proprietary-form files):
#     'titan'                                    → 100%  (brand name, logo area)
#     'sistema de gestion de seguridad y salud'  →  93%  (form title / header)
#     'tn sgsso rg'                              →  71%  (form-code prefix, A12)
#     'inspeccion'                               →  91%  (section label)
#     'herramienta'                              →  85%  (instrument label)
#   min_match=2: 'titan' is always present; one additional anchor always fires
#   even on the weakest pages.  CRS-template TITAN files are excluded because
#   they lack 'titan' in the top-third band.
#
# No f_reali flavor: the only REALI file in the corpus uses F-CRS-LCH-04
# (covered by f_lch_xx).  Plan-proposed anchors ('FORM-PREV-021', REALI
# branding) do not appear in any OCR output from the top-third band.
# ---------------------------------------------------------------------------
_HERRAMIENTAS_ELEC_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",
        "anchors": [
            "constructora region sur",  # running header — all pages
            "pagina 1 de",  # cover-only discriminator ("Pagina 1 de 1")
        ],
        "min_match": 2,
        "anti_anchors": [
            "chequeo de elementos",  # EPP form title — rejects LCH-CRS-02 misfiled pages
            "elementos de proteccion personal",  # EPP form section header (secondary guard)
        ],
    },
    {
        "name": "f_hll_17",
        "anchors": [
            "reg sso hll 17",  # HLL form code — all covers
            "chequeo de herramientas",  # HLL form title — all covers
        ],
        "min_match": 2,
    },
    {
        "name": "f_titan",
        "anchors": [
            "titan",  # TITAN brand name in logo/header area — 100% hit rate
            "sistema de gestion de seguridad y salud",  # form title/header — 93%
            "tn sgsso rg",  # form-code family prefix (A12) — 71%
            "inspeccion",  # section label — 91%
            "herramienta",  # instrument label — 85%
        ],
        "min_match": 2,
    },
]


# ---------------------------------------------------------------------------
# Andamios anchor constants (OCR-verified 2026-05-22).
#
# Two flavors found in the corpus:
#
# f_lch_xx  — Standard CRS template (F-CRS-LCH-05 "Lista de Chequeo de
#   Andamios").  Multiple forms are compiled into a single PDF; each cover page
#   reads "Pagina 1 de N" and carries both 'lista de chequeo de andamios' and
#   'datos del andamio'.  Continuation pages miss at least one of these.
#   min_match=2 of 3 anchors — robust across varying scan quality.
#   Anti-anchor: 'analisis de riesgos en el trabajo' / 'f crs art' reject ART
#   armado_titan forms that are sometimes misfiled in the andamios folder.
#   ART pages naturally fail f_lch_xx anchor matching (0 hits) — the
#   anti_anchors are defense in depth.
#
# f_ribeiro — RIBEIRO SPA proprietary form ("Lista de Verificación Andamios").
#   'linea de negocio' (corporativo selector row) and 'inspeccion de andamios'
#   (section header) appear reliably at default top-25%.  'ribeiro' in the logo
#   area adds a third candidate; min_match=2 of 3 fires on both 0.25 and 0.5.
# ---------------------------------------------------------------------------
_ANDAMIOS_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",
        "anchors": [
            "lista de chequeo de andamios",  # form title — all cover pages
            "datos del andamio",  # structural section header — cover pages
            "pagina 1 de",  # cover-only discriminator
        ],
        "min_match": 2,
        "anti_anchors": [
            "analisis de riesgos en el trabajo",  # ART form title — rejects misfiled ARTs
            "f crs art",  # ART form-code family prefix (A12) — secondary guard
        ],
    },
    {
        "name": "f_ribeiro",
        "anchors": [
            "linea de negocio",  # RIBEIRO corporativo selector — all covers
            "inspeccion de andamios",  # RIBEIRO section header — all covers
            "ribeiro",  # contractor name in logo area
        ],
        "min_match": 2,
    },
]


# ---------------------------------------------------------------------------
# Dif_pts anchor constants (OCR-verified 2026-05-22).
#
# top_fraction=1/3 (instead of default 0.25) — dif_pts forms carry the
# key discriminating fields in the upper-third of the page; 25% was too
# tight for some templates.
#
# Three flavors observed in the corpus:
#
# f_rch  — Standard RCH standalone charla sheets (F-CRS-RCH-01 family).
#   Each page is an independent 1-page form ("Página 1 de 1").  The form
#   code "f crs rch 01" and pagination "pagina 1 de 1" appear reliably in
#   the top-third band.  "nombre de la charla" is present on covers.
#   min_match=2 is sufficient; a 3-anchor match fires on every standalone page.
#   Note: A7 lock fires for 1-page PDFs — OCR not needed; the fixture is 1 page.
#
# f_ch_crs_01 — HLL compilation format (F-CH-CRS-01).  Alternates real
#   charla covers with "TEST DE COMPRENSIÓN" shadow pages every other page.
#   Cover anchors: "registro de charla" + "f ch crs 01" + "nombre de la
#   capacitacion" (min_match=2 of 3).
#   Shadow pages are rejected by anti_anchors: "alternativa correcta" fires
#   reliably on shadow pages (OCR-verified on p2 of HLL fixture); "test de
#   comprension" is a secondary guard that fires on most shadow pages.
#   Rejection is robust: shadow p1 also fails anchor matching (score=1 < 2).
#
# f_aguasan — AGUASAN contractor variant ("registro de charla y capacitacion"
#   + "charla operacional" + other structural fields).  min_match=2 of 4
#   possible anchors; "tema tratado" + "seleccione" appear on all observed
#   covers.  A7 lock fires for 1-page PDFs.
# ---------------------------------------------------------------------------
_DIF_PTS_ANCHORS: list[Flavor] = [
    {
        "name": "f_rch",
        "anchors": [
            "f crs rch 01",  # form code — all standalone dif_pts sheets
            "pagina 1 de 1",  # every standalone page is "Pagina 1 de 1"
            "nombre de la charla",  # session title field — covers
        ],
        "min_match": 2,
    },
    {
        "name": "f_ch_crs_01",
        "anchors": [
            "registro de charla",  # form title — cover pages (HLL compilation)
            "f ch crs 01",  # form code — cover pages
            "nombre de la capacitacion",  # training-session title field
        ],
        "min_match": 2,
        "anti_anchors": [
            "alternativa correcta",  # answer-key field — shadow test-de-comprension pages ONLY
            "test de comprension",  # shadow page section header (secondary guard)
        ],
    },
    {
        "name": "f_aguasan",
        "anchors": [
            "tema tratado",  # AGUASAN topic field — all covers
            "seleccione",  # AGUASAN checkbox instruction — all covers
            "registro de charla y capacitacion",  # AGUASAN form title
            "charla operacional",  # AGUASAN charla type label
        ],
        "min_match": 2,
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
    "caliente": {
        "filename_glob": r"^.*caliente.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _CALIENTE_ANCHORS,
    },
    "exc": {
        "filename_glob": r"^.*exc.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _EXC_ANCHORS,
    },
    "senal": {
        "filename_glob": r"^.*senal.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _SENAL_ANCHORS,
        "top_fraction": 1.0,
    },
    "ext": {
        "filename_glob": r"^.*ext.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _EXT_ANCHORS,
    },
    "maquinaria": {
        "filename_glob": r"^.*maquinaria.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _MAQUINARIA_ANCHORS,
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
    "chintegral": {
        "filename_glob": r"^.*chintegral.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _CHINTEGRAL_ANCHORS,
    },
    "dif_pts": {
        "filename_glob": r"^.*dif_pts.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "top_fraction": 1 / 3,
        "cover_flavors": _DIF_PTS_ANCHORS,
    },
    "herramientas_elec": {
        "filename_glob": r"^.*herramientas_elec.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        # top_fraction 1/3 (not the 0.25 default): the HLL REG-SSO-HLL-17
        # form-code sits lower than the 0.25 band. All three flavors' anchor
        # hit-rates (see comment above) were OCR-verified in this top-third band.
        "top_fraction": 1 / 3,
        "cover_flavors": _HERRAMIENTAS_ELEC_ANCHORS,
    },
    "andamios": {
        "filename_glob": r"^.*andamios.*\.pdf$",
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "cover_flavors": _ANDAMIOS_ANCHORS,
    },
}


def get_pattern(sigla: str) -> SiglaPattern:
    """Return the SiglaPattern for `sigla`. Raises KeyError if unknown."""
    if sigla not in PATTERNS:
        raise KeyError(f"unknown_sigla: {sigla}")
    return PATTERNS[sigla]
