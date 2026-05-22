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
# ---------------------------------------------------------------------------
# ART anchor constants (verbatim from spec §7 · art).
#
# ART = "Análisis de Riesgos en el Trabajo" (F-CRS-ART-01 / Rev. 02). Es un
# documento de 4 páginas; el header del formulario (título, logo, cuadro de
# código) repite en las 4 páginas → NO sirve como ancla. Solo los CAMPOS
# DEL FORMULARIO COVER son cover-only. Sin shadow cover (A5 no necesario).
#
# Lista completa del spec — 6 anclas — con min_match=3 (regla universal).
# Si OCR pierde 2-3 anclas (sello sobre el header, manchas), las restantes
# pasan. Restaurada 2026-05-22 tras anchor-truncation postmortem (estaba
# truncada a 2 anclas con min_match=2).
# ---------------------------------------------------------------------------
_ART_ANCHORS: list[Flavor] = [
    {
        "name": "f_art_01",
        "anchors": [
            "nombre del supervisor",  # top ~10% — cover-only
            "area de trabajo",  # top ~15% — cover-only
            "descripcion del trabajo a realizar",  # top ~18% — muy distintiva
            "hora de inicio de los trabajos",  # top ~22% — cover-only
            "n de trabajadores involucrados",  # top ~22% (° dropped — OCR-fragile)
            "pagina 1 de",  # top ~5% — cover-only ("Página 1 de 4")
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# IRL anchor constants (verbatim from spec §2 · irl).
#
# IRL = "Información de Riesgos Laborales" (F-CRS-ODI-01 — el código real es
# ODI-01, no IRL). El header del formulario y los encabezados de tabla
# (ACTIVIDAD / PELIGRO / RIESGOS ASOCIADOS / MEDIDAS DE CONTROL) repiten en
# TODAS las páginas — por eso NO sirven como anclas. Las anclas son
# campos del formulario que solo aparecen en la portada (cover-only).
#
# Lista completa del spec — 14 anclas — con min_match=3 (regla universal).
# Redundancia alta → tolera OCR sucio mucho mejor que un único código.
# Restaurada 2026-05-22 tras anchor-truncation postmortem (estaba truncada a
# 2 anclas con min_match=2).
# ---------------------------------------------------------------------------
_IRL_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_odi_01",
        "anchors": [
            "antecedentes generales",  # cover section header
            "fecha de realizacion",  # cover field
            "tiempo de duracion",  # cover field
            "horario de inicio",  # cover field
            "horario de termino",  # cover field
            "obra",  # cover field
            "tipo de induccion",  # cover field
            "identificacion del trabajador",  # cover section header
            "identificacion del relator",  # cover section header
            "persona trabajadora nueva",  # tipo de induccion checkbox
            "con ausencia prolongada",  # tipo de induccion checkbox
            "reubicada con nuevo cargo",  # tipo de induccion checkbox (slash→space)
            "por nuevo proceso productivo",  # tipo de induccion checkbox
            "pagina 1 de",  # P1 only — V4 pagination pattern reused as anchor
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# ODI anchor constants (verbatim from spec §3 · odi).
#
# ODI Visitas = "Obligación de Informar Visita" (F-CRS-ODI-03). El título y
# el cuadro de código repiten en página 2; por eso NO son anclas. Las anclas
# son campos cover-only del visitante (nombre, teléfono, identidad, etc.) y
# los encabezados de columna que en este formulario NO se repiten en la
# continuación.
#
# Lista completa del spec — 8 anclas — con min_match=3 (regla universal).
# Constelación más distintiva (nombre completo + n° telefónico + c. identidad)
# es casi única de la portada de ODI Visita. Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba truncada a 2 anclas con min_match=2).
# ---------------------------------------------------------------------------
_ODI_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_odi_03",
        "anchors": [
            "nombre completo",  # visitante field — cover only
            "n telefonico",  # visitante field (° dropped — OCR-fragile)
            "c identidad",  # visitante field (period dropped — OCR-fragile)
            "empresa",  # visitante field
            "actividad",  # column header — cover only (does NOT repeat on p2)
            "peligro incidente potencial",  # column header (slash→space)
            "medidas de control",  # column header — cover only in ODI
            "pagina 1 de",  # P1 only — V4 pagination pattern reused as anchor
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# CRS_RCH_ANCHORS — shared form-field anchors for the F-CRS-RCH-01 template
# (charla, chintegral, dif_pts all reuse this list per the spec sections
# 4 · charla, 5 · chintegral, 6 · dif_pts).
#
# The form has variants (Rev 01 2024 with "Tiempo duración charla" +
# "Tipología de Charla/Reunión"; Rev 03 2025 with "Hora de inicio" + "Hora
# de Término" without typology). The list covers both variants — with the
# rule ≥ 3 matches, any variant passes.
#
# **Repeat on every page (NOT useful as anchor)** per spec: form title
# "REGISTRO DE FORMACIÓN E INFORMACIÓN", "CONSTRUCTORA REGIÓN SUR SPA",
# code box "F-CRS-RCH-01". Crucially, "Página 1 de N" is **NOT** included
# in this anchor set — continuation pages (signature grids) of charla also
# read "Página 1 de 2" (template bug — verified with sample from Daniel).
#
# All cover-only field labels normalized to the form _normalize_text emits
# (lowercase, accent-stripped, separator /-_→space).
# ---------------------------------------------------------------------------
CRS_RCH_ANCHORS: list[str] = [
    "nombre de la charla",  # session title field — cover only
    "obra",  # site field — cover only
    "relator",  # speaker field — cover only
    "cargo relator",  # speaker role field — cover only
    "hora de inicio",  # start time — Rev 03+
    "hora de termino",  # end time — Rev 03+
    "tiempo duracion charla",  # duration field — Rev 01
    "tipologia de charla",  # typology section header — Rev 01 (slash→space)
    "charla de induccion",  # typology checkbox — Rev 01
    "charla re instruccion",  # typology checkbox — Rev 01 (hyphen→space)
    "reunion de coordinacion",  # typology checkbox — Rev 01
    "difusion de documentos",  # typology checkbox — Rev 01
]

_CHARLA_ANCHORS: list[Flavor] = [
    {
        "name": "f_crs_rch_01",
        "anchors": CRS_RCH_ANCHORS,
        "min_match": 3,
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
# ("chequeo bodega" ∩ "f pets crs" ∩ "bodega suspel") fires on every
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
            "f pets crs",  # Form-code family prefix (A12) — all bodega covers
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
# "f crs ar" (form-code family prefix) also appears in the running header.
# "lista de convocados" is ONLY on the cover (page 1 attendee table).
# "hospital de" and "lugar de la reunion" are also cover-only fields.
# min_match=3: cover (p1) gets ≥5 matches; continuations (p2/p3) get 2
# ("acta de reunion" + "f crs ar") → not counted as covers.
# ---------------------------------------------------------------------------
_CHPS_ANCHORS: list[Flavor] = [
    {
        "name": "f_ar_01",
        "anchors": [
            "acta de reunion",  # Form title — all pages (running header)
            "f crs ar",  # Form-code family prefix (A12) — all pages (running header)
            "lista de convocados",  # Attendee table header — cover only (p1)
            "hospital de",  # Site field — cover only (p1)
            "lugar de la reunion",  # Meeting location field — cover only (p1)
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Chintegral anchor constants (verbatim from spec §5 · chintegral).
#
# Three flavors per the spec:
#
# f_rch — Standard RCH template (F-CRS-RCH-01). Reuses CRS_RCH_ANCHORS
#   (shared with charla and dif_pts). The "Tipología" checkbox with
#   "Charla Integral" marked is what distinguishes a chintegral from a
#   regular charla; the filename_glob already separates them by folder.
#
# f_japa — JAPA contractor variant (Sociedad de Proyectos de Ingeniería).
#   Form title "REGISTRO CAPACITACIÓN" + multiple structural fields. Anchors
#   transcribed verbatim from the spec §5 prose list.
#
# f_previene — PREVIENE programme (Plan de Acción Nacional de Drogas).
#   Documented anchors include the programme title, subtitle, the
#   "LISTA DE ASISTENCIA" section, the campaign banner, and the standard
#   programme fields (Región, Comuna, etc.). Anchors per spec §5.
# ---------------------------------------------------------------------------
_CHINTEGRAL_ANCHORS: list[Flavor] = [
    {
        "name": "f_rch",
        "anchors": CRS_RCH_ANCHORS,
        "min_match": 3,
    },
    {
        "name": "f_japa",
        "anchors": [
            "registro capacitacion",  # JAPA form title (accent-stripped)
            "lugar",  # field label
            "temas tratados",  # section
            "tipo charla",  # caja
            "capacitacion interna",  # checkbox
            "capacitacion externa",  # checkbox
            "charla integral",  # checkbox (literal)
            "reinstruccion",  # checkbox
            "procedimiento",  # checkbox (high false-positive risk; min_match=3 protects)
            "charla 5 minutos",  # checkbox
            "protocolo",  # checkbox (high false-positive risk)
            "personal japa",  # caja al final
            "subcontrato",  # caja al final
            "sociedad de proyectos de ingenieria",  # JAPA full contractor name (logo footer)
        ],
        "min_match": 3,
    },
    {
        "name": "f_previene",
        "anchors": [
            "programa previene",  # title — distinctive
            "infancia juventud y bienestar",  # subtitle (comma dropped)
            "lista de asistencia",  # section
            "estrategia nacional de drogas",  # banner
            "region",  # field
            "comuna",  # field
            "espacio de intervencion",  # field
            "numero de asistentes",  # field
            "componente",  # field
            "tematica",  # field
        ],
        "min_match": 3,
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


# ---------------------------------------------------------------------------
# Maquinaria anchor constants (verbatim from spec §10 · maquinaria).
#
# "Universo de templates abierto" — observamos ≥5 templates (F-CRS-LCH-08,
# -16, -26, -40, LCH-CRS-07 con prefijo distinto). El spec usa la
# **intersección estable de field-labels de identificación** del formulario
# (cover-only en todos los templates), NO el running header. Verificado
# leyendo p2 de F-CRS-LCH-16 grúa: la continuación tiene el header del form
# y el ITEM/ACTIVIDAD del checklist pero NO los field-labels de
# identificación.
#
# 5 anchors / min_match=3 (regla universal). Cualquier template observado
# matchea ≥4; un template nuevo debería matchear ≥3 si mantiene los básicos
# (fecha mantención + operador + paginación). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba truncada a 2 anclas con min_match=2
# usando "constructora region sur" + "pagina 1 de", que NO es el set del
# spec — el running header no es cover-only en este universo de templates).
# ---------------------------------------------------------------------------
_MAQUINARIA_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",  # A9 — cubre F-CRS-LCH-* y F-LCH-CRS-* por intersección
        "anchors": [
            "fecha ultima mantencion",  # long distinctive label — cover-only
            "nombre operador",  # distinctive field — cover-only
            "rut",  # classic field label
            "marca",  # also substring-matches "MARCA/MODELO"
            "pagina 1 de",  # cover-only universal — P2+ says "pagina 2 de N"
        ],
        "min_match": 3,
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
# Dif_pts anchor constants (verbatim from spec §6 · dif_pts).
#
# top_fraction=1/3 (set in PATTERNS entry below): the HLL flavor B and the
# AGUASAN flavor C extend the cover form below the default 0.25 band.
#
# Three flavors per spec:
#
# f_rch — Standard RCH (F-CRS-RCH-01) — reuses CRS_RCH_ANCHORS shared with
#   charla and chintegral. The chintegral "Nombre de la Charla" field on
#   dif_pts forms usually says "DIFUSIÓN DE …" or "PROCEDIMIENTO TRABAJO
#   SEGURO …"; the filename_glob distinguishes dif_pts from charla.
#
# f_ch_crs_01 — HLL compilation format (F-CH-CRS-01) alternating cover +
#   shadow "TEST DE COMPRENSIÓN" pages. Anti-anchors reject the test pages
#   so they don't double-count. Anchors and anti-anchors are copy-pasted
#   from the spec §6 Python literal verbatim (line 1007-1024 of the spec).
#
# f_aguasan — AGUASAN contractor template (code SGT-06-F2). Self-contained
#   (no shadow pages observed). Anchors from spec §6 Python literal
#   (line 1041-1055 of the spec).
# ---------------------------------------------------------------------------
_DIF_PTS_ANCHORS: list[Flavor] = [
    {
        "name": "f_rch",
        "anchors": CRS_RCH_ANCHORS,
        "min_match": 3,
    },
    {
        "name": "f_ch_crs_01",
        "anchors": [
            "registro de charla",  # form title — cover (compilation HLL)
            "nombre de la capacitacion",  # training-session title field
            "cargo relator",  # speaker role field
            "tiempo duracion charla",  # duration field
        ],
        "min_match": 3,
        "anti_anchors": [
            "test de comprension",  # shadow page title
            "test trabajo en",  # covers "...EN ALTURA", "...EN CALIENTE", etc.
            "alternativa correcta",  # answer-key field — shadow pages only
            "f pets crs",  # test form-code prefix (cover uses f ch crs 01)
        ],
    },
    {
        "name": "f_aguasan",
        "anchors": [
            "aguasan",  # contractor brand
            "registro de charla y capacitacion",  # AGUASAN form title
            "categoria",  # field
            "charla especifica diaria",  # category checkbox
            "charla operacional",  # category checkbox
            "total personal entrenado",  # field
            "tema tratado",  # topic field — all covers
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
        # top_fraction defaults to 0.25 per spec §7 ("top_fraction=1/4 default,
        # no override"). recursive_glob=True per spec §7 ("Nota de enumeración"):
        # HRB has 7.-ART/<EMPRESA>/*.pdf subfolders that must be enumerated.
        "recursive_glob": True,
        "cover_flavors": _ART_ANCHORS,
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
