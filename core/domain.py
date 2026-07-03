"""Canonical domain constants — hospitals, siglas, category folder names.

These come from A:\\informe mensual\\.serena\\memories\\ conventions.
Single source of truth: do not duplicate these lists anywhere else.
"""

from __future__ import annotations

import re

HOSPITALS: tuple[str, ...] = ("HPV", "HRB", "HLU", "HLL")

# 20 canonical siglas (order matches the 20 prevention categories)
SIGLAS: tuple[str, ...] = (
    "reunion",
    "irl",
    "odi",
    "charla",
    "chintegral",
    "dif_pts",
    "art",
    "insgral",
    "bodega",
    "maquinaria",
    "ext",
    "senal",
    "revdocmaq",
    "exc",
    "altura",
    "caliente",
    "espacios",
    "herramientas_elec",
    "andamios",
    "chps",
)

# Sigla → canonical folder name (without TOTAL/" 0" suffix)
CATEGORY_FOLDERS: dict[str, str] = {
    "reunion": "1.-Reunion Prevencion",
    "irl": "2.-Induccion IRL",
    "odi": "3.-ODI Visitas",
    "charla": "4.-Charlas",
    "chintegral": "5.-Charla Integral",
    "dif_pts": "6.-Difusion PTS",
    "art": "7.-ART",
    "insgral": "8.-Inspecciones Generales",
    "bodega": "9.-Inspeccion Bodega",
    "maquinaria": "10.-Inspeccion de Maquinaria",
    "ext": "11.-Extintores",
    "senal": "12.-Senaleticas",
    "revdocmaq": "13.-Revision Documentacion Maquinaria",
    "exc": "13.-Excavaciones y Vanos",
    "altura": "14.-Trabajos en Altura",
    "caliente": "15.-Inspeccion Trabajos en Caliente",
    "espacios": "17.-Espacios Confinados",
    "herramientas_elec": "16.-Inspeccion Herramientas Electricas",
    "andamios": "17.-Andamios",
    "chps": "18.-CHPS",
}

# Strip a leading "NN.-" numeric index from a category folder name so matching
# survives corpus renumbering (the live corpus inserts categories mid-list).
_INDEX_RE = re.compile(r"^\s*\d+\s*\.\s*-?\s*")


def _folder_text(name: str) -> str:
    """Return a folder name without its leading ``NN.-`` numeric index.

    Examples:
        '14.-Excavaciones y Vanos' -> 'Excavaciones y Vanos'
        '7.-ART 934' -> 'ART 934'
    """
    return _INDEX_RE.sub("", name).strip()


# Extra folder-text spellings a sigla also matches, beyond its canonical text.
# 'CPHS' is the real spelling on disk (Comité Paritario); the canonical 'CHPS'
# is a transposition typo kept only as the nominal fallback path.
_SIGLA_FOLDER_ALIASES: dict[str, tuple[str, ...]] = {
    "chps": ("CPHS",),
}


def _match_texts(sigla: str) -> tuple[str, ...]:
    """All folder texts (canonical + aliases) that resolve to ``sigla``."""
    return (_folder_text(CATEGORY_FOLDERS[sigla]), *_SIGLA_FOLDER_ALIASES.get(sigla, ()))


def sigla_to_folder(sigla: str) -> str:
    """Return the canonical folder base name for a sigla."""
    return CATEGORY_FOLDERS[sigla]


def folder_to_sigla(folder_name: str) -> str | None:
    """Map a folder name back to its sigla, tolerant of the leading ``NN.-``
    numeric index (so corpus renumbering doesn't break it) and of TOTAL/' 0'/
    contractor-count suffixes.

    Examples:
        '7.-ART' -> 'art'
        '14.-Excavaciones y Vanos' -> 'exc'   (renumbered)
        '20.-CPHS' -> 'chps'                  (alias spelling)
        '7.-ART 934' -> 'art'
        '99.-Categoria Inventada' -> None     (unmodeled)
    """
    text = _folder_text(folder_name)
    for sigla in CATEGORY_FOLDERS:
        for canon in _match_texts(sigla):
            if text == canon or text.startswith(canon + " "):
                return sigla
    return None
