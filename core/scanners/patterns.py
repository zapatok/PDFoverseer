"""Central registry of patterns per sigla — see A1, A9, A10, A11 in the spec.

Each entry declares how a sigla counts when pase-1 filename matching is not
enough (pase-1 itself lives in core.scanners.utils.filename_glob — this
registry does not drive its matching; see D8).
The 20 SIGLAS from core.domain MUST each have an entry here (enforced by the
completeness gate, tests/unit/scanners/test_patterns_registry.py).

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

    `scan_strategy`: "anchors" | "pagination" | "none".
    `cover_flavors`: required if strategy="anchors".
    `top_fraction`: optional — default 0.25 (A2).
    `recursive_glob`: optional — INFORMATIONAL ONLY (count_pdfs_by_sigla
        already uses rglob unconditionally; this field documents intent).
    `cover_code`: pagination only — count only covers whose form code contains
        this substring (e.g. ``"F-CRS-ODI-01"`` for IRL). When absent, every
        ``curr==1`` page counts as a document start.
    `count_scope`: optional — default ``"token"`` (pase-1 counts only PDFs
        whose filename resolves to this sigla via ``extract_sigla``).
        ``"folder"`` (F14) counts every PDF in the resolved category folder,
        no token required — for siglas whose real files carry no reliable
        filename token at all (chps: real files like ``crs.pdf``/``titan.pdf``
        are unnamed by convention; the folder itself is the classifier).
        Honored by ``count_pdfs_by_sigla`` and ``SimpleFilenameScanner``'s
        per-file path resolution — both delegate to
        ``filename_glob._matches`` so the two stay in lock-step.
    """

    scan_strategy: ScanStrategy
    cover_flavors: NotRequired[list[Flavor]]
    top_fraction: NotRequired[float]
    recursive_glob: NotRequired[bool]
    cover_code: NotRequired[str]
    count_scope: NotRequired[Literal["token", "folder"]]


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
# Bodega anchor constants (verbatim from spec §9 · bodega).
#
# Mono-flavor f_pets_07_03 (no-CRS-prefixed code preserved per A9).
# 6 anclas / min_match=3 (regla universal). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba a 5 anclas con un literal truncado
# "f pets crs" en vez del código completo "f pets crs 07 03" y omitía
# "bodega respel" basándose en una verificación empírica del implementer).
# ---------------------------------------------------------------------------
_BODEGA_ANCHORS: list[Flavor] = [
    {
        "name": "f_pets_07_03",
        "anchors": [
            "chequeo bodega suspel respel",  # form title (slash→space)
            "f pets crs 07 03",  # full form code (A12 family prefix + suffix)
            "obra",  # site field
            "realizado por",  # signatory field
            "bodega suspel",  # section label
            "bodega respel",  # section label
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# CHPS anchor constants (verbatim from spec §18 · chps).
#
# Mono-flavor f_ar_01 (Acta de Reunión CHPS, F-CRS-AR-01). 7 anclas /
# min_match=3 (regla universal). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba a 5 anclas — faltaba "desarrollo de
# la reunion" + "pagina 1 de", y el código estaba truncado a "f crs ar"
# en vez del código completo "f crs ar 01").
# ---------------------------------------------------------------------------
_CHPS_ANCHORS: list[Flavor] = [
    {
        "name": "f_ar_01",
        "anchors": [
            "acta de reunion",  # form title — running header
            "f crs ar 01",  # full form code (A12 family prefix + suffix)
            "lista de convocados",  # attendee table header — cover only
            "desarrollo de la reunion",  # section header — cover only
            "hospital de",  # site field — cover only
            "lugar de la reunion",  # meeting location field — cover only
            "pagina 1 de",  # cover marker
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
# Caliente anchor constants (verbatim from spec §15 · caliente).
#
# Mono-flavor f_lch_3x (cubre F-LCH-CRS-32 + -36 por intersección). 8 anclas
# / min_match=3 (regla universal). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba a 4 anclas con flavor name
# "f_lch_crs_32" — código demasiado específico, no captura el variante -36).
# ---------------------------------------------------------------------------
_CALIENTE_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_3x",  # A9 — cubre F-LCH-CRS-32 + -36
        "anchors": [
            "chequeo trabajos en caliente",  # form title
            "constructora region sur spa",  # org name (with SpA suffix per spec)
            "f lch crs",  # form-code family prefix (A12, LCH-CRS direction)
            "item",  # column header
            "actividad",  # column header
            "cumple",  # column header
            "esmeril angular",  # checklist item (template-specific, distinctive)
            "pagina 1 de",  # cover marker
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Exc anchor constants (verbatim from spec §13 · exc).
#
# Mono-flavor por intersección (cubre LCH-31 + LCH-034). 8 anclas /
# min_match=3 (regla universal). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba a 4 anclas, una de ellas inventada
# por el implementer — "f crs lch" — que NO está en el spec; el spec usa
# field-labels específicos de la excavación).
# ---------------------------------------------------------------------------
_EXC_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",  # A9 — cubre LCH-31 + LCH-034 por intersección
        "anchors": [
            "excavaciones",  # form title
            "sector inspeccionado",  # field label
            "obra",  # field label
            "fecha",  # field label
            "cargo",  # field label
            "constructora region sur spa",  # org name (with SpA suffix per spec)
            "descripcion",  # field label
            "pagina 1 de",  # cover marker
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Senal anchor constants (verbatim from spec §12 · senal).
#
# Mono-flavor f_lch_22. 8 anclas / min_match=3 (regla universal). Restaurada
# 2026-05-22 tras anchor-truncation postmortem (flavor estaba renombrado a
# "f_pets_crs_xx" — no coincide con el código del formulario; estaba a
# 2 anclas con min_match=2, y la entrada PATTERNS forzaba top_fraction=1.0
# para compensar; el spec usa el default 0.25 con field-labels específicos
# que tolerarán variaciones de layout vía la redundancia min_match=3).
# ---------------------------------------------------------------------------
_SENAL_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_22",  # A9 — código del formulario
        "anchors": [
            "lista de chequeo de senaletica",  # form title
            "zona area",  # field label (slash→space)
            "persona(s) que realiza la inspeccion",  # field label
            "codigo de registro pgs",  # field label
            "cumple",  # column header
            "fotografia",  # column header
            "inspeccion realizada por",  # field label
            "pagina 1 de",  # cover marker
        ],
        "min_match": 3,
    },
]

# ---------------------------------------------------------------------------
# Ext anchor constants (verbatim from spec §11 · ext).
#
# Mono-flavor por intersección de field-labels (cubre LCH-18 + LCH-37).
# 6 anclas / min_match=3 (regla universal). Restaurada 2026-05-22 tras
# anchor-truncation postmortem (estaba a 4 anclas, dos de ellas inventadas
# por el implementer — "f crs lch" + "constructora region sur" — que NO
# están en el spec; el spec usa field-labels específicos del extintor).
# ---------------------------------------------------------------------------
_EXT_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",  # A9 — cubre LCH-18 + LCH-37 por intersección
        "anchors": [
            "chequeo extintores",  # form title
            "ubicacion del extintor",  # field label
            "numero de serie del extintor",  # field label (distinctive)
            "fecha de vencimiento del extintor",  # field label
            "tipo de extintor",  # field label
            "pagina 1 de",  # cover marker
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
# Herramientas_elec anchor constants (verbatim from spec §16 ·
# herramientas_elec).
#
# Multi-flavor (4 sabores) por spec:
#
# f_lch_xx  — Intersección de field-labels del checklist CRS (cubre
#   F-CRS-LCH-* + F-LCH-CRS-* + F-CRS-CRS-* por intersección). 12 anclas /
#   min_match=4 (la única excepción a la regla universal min_match=3 en el
#   spec — el spec eleva a 4 por la corta-substring "SI" / "NO" / "NA" que
#   pueden match falso). Anti-anchors rechazan la familia EPP (LCH-CRS-02).
#
# f_titan   — TITAN contractor template (TN-SGSSO-RG-NNN). 5 anclas /
#   min_match=3.
#
# f_reali   — REALI propietario (FORM-PREV-021). 4 anclas / min_match=3.
#
# f_hll_17  — HLL propietario REG-SSO-HLL-17 "Chequeo de Herramientas".
#   5 anclas / min_match=3.
#
# Restaurada 2026-05-22 tras anchor-truncation postmortem (f_lch_xx estaba
# a 2 anclas / min_match=2; f_hll_17 a 2/2; f_titan a 5/2 con anclas
# parcialmente distintas del spec; falta f_reali). PATTERNS["herramientas_elec"]
# top_fraction=1/3 también removido — el spec usa default 0.25 (línea 2204).
# ---------------------------------------------------------------------------
_HERRAMIENTAS_ELEC_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_xx",  # A9 — cubre F-CRS-LCH-* + F-LCH-CRS-* + F-CRS-CRS-*
        "anchors": [
            "constructora region sur",  # running header
            "f crs lch",  # form-code variant 1
            "f lch crs",  # form-code variant 2
            "f crs crs",  # form-code variant 3
            "item",  # column header
            "actividad",  # column header
            "cumple",  # column header
            "si",  # column value header (short — defended by min_match=4)
            "no",  # column value header
            "na",  # column value header
            "pagina 1 de",  # cover marker
            "inspeccion realizada",  # section header
        ],
        "min_match": 4,  # spec excepción — eleva a 4 por short-substring risk
        "anti_anchors": [
            "elementos de proteccion personal",  # EPP form title — rejects LCH-CRS-02
            "lch crs 02",  # EPP form code
        ],
    },
    {
        "name": "f_titan",  # A9
        "anchors": [
            "titan",  # brand
            "check list",  # title fragment
            "herramientas electricas",  # title fragment
            "tn sgsso rg",  # form-code family prefix (A12)
            "sistema de gestion de seguridad y salud ocupacional",  # title/header
        ],
        "min_match": 3,
    },
    {
        "name": "f_reali",  # A9
        "anchors": [
            "reali",  # brand
            "form prev 021",  # form code (separators normalized)
            "lista de chequeo de herramientas",  # form title
            "programa de gestion en seguridad",  # subtitle/banner
        ],
        "min_match": 3,
    },
    {
        "name": "f_hll_17",  # A9 — REG-SSO-HLL-17
        "anchors": [
            "reg sso hll 17",  # full form code
            "chequeo de herramientas",  # form title
            "mantencion de obra",  # section/site label
            "codificacion",  # field label
            "estado enchufe macho",  # checklist item (distinctive)
        ],
        "min_match": 3,
    },
]


# ---------------------------------------------------------------------------
# Andamios anchor constants (verbatim from spec §17 · andamios).
#
# Multi-flavor (2 sabores):
#
# f_lch_05  — Familia CRS estándar F-CRS-LCH-05 "LISTA DE CHEQUEO DE
#   ANDAMIOS", ~95% del corpus (incluye HPV/HRB/HLL — HLL aquí viene en
#   portrait, no landscape). 9 anclas, min_match=4 (redundancia útil con
#   varios section headers). Anti-anchors rechazan ARTs cross-categoría
#   (HPV/TITAN `*_armado_*.pdf` son F-CRS-ART-01, no chequeos de andamio).
#
# f_ribeiro  — Sabor minoritario HRB "RIBEIRO SPA / 1cl-1890". 6 anclas,
#   min_match=3.
#
# Restaurada 2026-05-22 tras anchor-truncation postmortem (f_lch_05 estaba
# truncada a 3 anclas/min_match=2; f_ribeiro a 3 anclas/min_match=2).
# El flavor f_lch_05 también fue renombrado desde "f_lch_xx" — el spec da
# el código exacto F-CRS-LCH-05 (no hay variantes numéricas observadas en
# esta sigla, a diferencia de herramientas_elec).
# ---------------------------------------------------------------------------
_ANDAMIOS_ANCHORS: list[Flavor] = [
    {
        "name": "f_lch_05",  # A9 — exact form code F-CRS-LCH-05
        "anchors": [
            "lista de chequeo de andamios",  # form title — universal
            "constructora region sur",  # header subtitle
            "f crs lch 05",  # form code (no observed variants)
            "tipo andamio",  # field label (FACHADA / MULTIDIRECCIONAL)
            "datos del andamio",  # section header
            "superficie de apoyo",  # section header
            "estructura del andamio",  # section header
            "plataformas de trabajo",  # section header
            "pagina 1 de",  # cover marker
        ],
        # Spec §17 set min_match=4 with "redundancia útil" but no OCR data.
        # Fase A 2026-05-22 OCR diagnostic (.tmp_calibration/ocr_band_diagnostic.py):
        # EVERY casi-match on the real ABRIL HRB fixture matched exactly 3 of 9
        # anchors (lista de chequeo de andamios + datos del andamio OR tipo
        # andamio + pagina 1 de). The remaining 6 anchors (running header,
        # form code, section headers) are NOT picked up by Tesseract at
        # top_fraction=0.25 — verified across all 4 casi-match pages.
        # Conformed to universal rule (≥3 matches ⇒ portada). Anti-anchors
        # already protect against ART cross-categoría.
        "min_match": 3,
        "anti_anchors": [
            "analisis de riesgos en el trabajo",  # ART form title — rejects misfiled ARTs
            "f crs art 01",  # ART form code (full A12 family prefix)
        ],
    },
    {
        "name": "f_ribeiro",  # A9 — RIBEIRO SPA propietario
        "anchors": [
            "ribeiro spa",  # contractor name
            "lista de verificacion andamios",  # form title
            "1cl 1890",  # form code (hyphen→space)
            "inspeccion de andamios",  # section header
            "centro de trabajo",  # field label
            "linea de negocio",  # corporativo selector row
        ],
        "min_match": 3,
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
        "scan_strategy": "none",
    },
    "art": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        # top_fraction defaults to 0.25 per spec §7 ("top_fraction=1/4 default,
        # no override"). recursive_glob=True per spec §7 ("Nota de enumeración"):
        # HRB has 7.-ART/<EMPRESA>/*.pdf subfolders that must be enumerated.
        "recursive_glob": True,
        "cover_flavors": _ART_ANCHORS,
    },
    "irl": {
        "scan_strategy": "pagination",  # v4: migrated — packet covers via cover_code
        "cover_code": "F-CRS-ODI-01",  # count only IRL form covers, not appendix page-1s
        "cover_flavors": _IRL_ANCHORS,
    },
    "odi": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "cover_flavors": _ODI_ANCHORS,
    },
    "charla": {
        "scan_strategy": "anchors",
        # recursive_glob: True per Fase B audit 2026-05-22. Spec §4 didn't
        # mandate recursive enumeration but the real corpus shows both HPV
        # (338 PDFs) and HRB (46 PDFs) organize charlas by contractor
        # subfolders (AGUASAN, ALUMINIO 2000, ARAYA, …) — the same pattern
        # ART § 7 documents. Without recursive_glob the scanner finds 0
        # files at top level for HPV/HRB charla. HLU and HLL keep charlas
        # flat; recursive_glob doesn'"'"'t hurt them. Same gap-fill as the
        # art recursive_glob=True I added in Group 2.
        "recursive_glob": True,
        # Spec §4 didn't override top_fraction. Fase A 2026-05-22 OCR
        # diagnostic showed that on a HRB chintegral compilation page (same
        # F-CRS-RCH-01 template), top_fraction=0.25 captures only the title
        # field ("nombre de la charla", 1/12 anchors) — the typology
        # checkboxes (charla de induccion, charla re instruccion, reunion
        # de coordinacion, difusion de documentos) sit between 0.25 and 0.33
        # vertically. Raising to 1/3 recovers 4 additional anchors per
        # cover page → reaches min_match=3 reliably. Matches the band
        # already used by dif_pts (shares the same form template family).
        "top_fraction": 1 / 3,
        "cover_flavors": _CHARLA_ANCHORS,
    },
    "insgral": {
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
    "bodega": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "cover_flavors": _BODEGA_ANCHORS,
    },
    "caliente": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "recursive_glob": True,
        "cover_flavors": _CALIENTE_ANCHORS,
    },
    "exc": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "recursive_glob": True,
        "cover_flavors": _EXC_ANCHORS,
    },
    "senal": {
        "scan_strategy": "anchors",
        "recursive_glob": True,
        # top_fraction defaults to 0.25 per spec §12 (no override). Earlier
        # implementation set 1.0 as a workaround for 2-anchor truncation;
        # restoring 8 anchors removes the need for the workaround.
        "cover_flavors": _SENAL_ANCHORS,
    },
    "ext": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "recursive_glob": True,
        "cover_flavors": _EXT_ANCHORS,
    },
    "maquinaria": {
        "scan_strategy": "anchors",  # KEEP: count_type=checks (not documents) — not migrated
        "recursive_glob": True,
        "cover_flavors": _MAQUINARIA_ANCHORS,
    },
    "altura": {
        "scan_strategy": "pagination",
        "recursive_glob": True,
    },
    "chps": {
        "scan_strategy": "anchors",
        "cover_flavors": _CHPS_ANCHORS,
        # F14: real chps files carry no reliable token (ABRIL: the real
        # Comité Paritario spelling "cphs"; MAYO: unnamed crs.pdf/titan.pdf).
        # The folder is the only reliable classifier — count every PDF in it.
        "count_scope": "folder",
    },
    "chintegral": {
        "scan_strategy": "anchors",
        "recursive_glob": True,
        # Same OCR-band rationale as charla above — chintegral shares the
        # F-CRS-RCH-01 form template (f_rch flavor) and needs the wider
        # band to pick up the typology checkbox anchors. The other two
        # flavors (f_japa, f_previene) are independent templates whose
        # anchors are concentrated higher; widening doesn't hurt them.
        "top_fraction": 1 / 3,
        "cover_flavors": _CHINTEGRAL_ANCHORS,
    },
    "dif_pts": {
        "scan_strategy": "anchors",
        "recursive_glob": True,
        "top_fraction": 1 / 3,
        "cover_flavors": _DIF_PTS_ANCHORS,
    },
    "herramientas_elec": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "recursive_glob": True,
        # top_fraction defaults to 0.25 per spec §16 line 2204 (explicit
        # "top_fraction": 0.25 in the spec'"'"'s Python block). Earlier
        # implementation set 1/3 as a workaround for 2-anchor truncation
        # in f_hll_17; restoring 5 anchors removes the need for the workaround.
        "cover_flavors": _HERRAMIENTAS_ELEC_ANCHORS,
    },
    "andamios": {
        "scan_strategy": "pagination",  # v4: migrated from anchors (benchmark 2026-06-21)
        "recursive_glob": True,
        "cover_flavors": _ANDAMIOS_ANCHORS,
    },
    "revdocmaq": {
        # Incr B: "Revisión de Documentación de Maquinaria" (folder 13). Provisional
        # (1 PDF = 1 doc). Fase 5 (F6): the deep audit found real corpus files that
        # carry no "revdocmaq" token at all (e.g. REVISION_DOCUMENTACION_MAQUINARIA_
        # AGUASAN.pdf) — matching happens via a "revision"+"documentacion" phrase
        # alias in core.scanners.utils.filename_glob (_SIGLA_TOKEN_ALIASES).
        "scan_strategy": "none",
        "recursive_glob": True,
    },
    "espacios": {
        # Incr B: "Espacios Confinados" (folder 17). The lone sample is a
        # compilation of 2-page "Página N de 2" inspection forms (F-PETS-CRS-08-01)
        # → pagination counts the inspections; cover_code restricts doc-starts to
        # that form's covers. count_type=documents.
        "scan_strategy": "pagination",
        "cover_code": "F-PETS-CRS-08-01",
        "recursive_glob": True,
    },
}


def get_pattern(sigla: str) -> SiglaPattern:
    """Return the SiglaPattern for `sigla`. Raises KeyError if unknown."""
    if sigla not in PATTERNS:
        raise KeyError(f"unknown_sigla: {sigla}")
    return PATTERNS[sigla]


CountType = Literal["documents", "documents_workers", "checks"]

# Per-sigla count type — Decisión 4 / grupo F del triage 2026-06-09. Qué cuenta
# el número de la celda, ortogonal a CÓMO se escanea (scan_strategy):
#   documents          — la mayoría: el número son documentos.
#   documents_workers  — charla/chintegral/dif_pts: documentos a una columna del
#                        Excel + trabajadores (contador por teclado) a otra (HH).
#   checks             — maquinaria: chequeos = columnas de fecha marcadas (no
#                        documentos; puede superar las páginas por diseño).
# El gate de completitud (tests/unit/scanners/test_count_type.py) exige las 20.
COUNT_TYPE_BY_SIGLA: dict[str, CountType] = {
    "reunion": "documents",
    "art": "documents",
    "irl": "documents",
    "odi": "documents",
    "charla": "documents_workers",
    "insgral": "documents",
    "bodega": "documents",
    "caliente": "documents",
    "exc": "documents",
    "senal": "documents",
    "ext": "documents",
    "maquinaria": "checks",
    "altura": "documents",
    "chps": "documents",
    "chintegral": "documents_workers",
    "dif_pts": "documents_workers",
    "herramientas_elec": "documents",
    "andamios": "documents",
    "revdocmaq": "documents",
    "espacios": "documents",
}


def count_type_for(sigla: str) -> CountType:
    """Tipo de conteo de la sigla (documents/documents_workers/checks).

    Default ``"documents"`` para una sigla desconocida (no debería ocurrir: el
    gate de completitud exige las 20 en ``COUNT_TYPE_BY_SIGLA``).
    """
    return COUNT_TYPE_BY_SIGLA.get(sigla, "documents")
