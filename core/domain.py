"""Canonical domain constants — hospitals, siglas, category folder names.

These come from A:\\informe mensual\\.serena\\memories\\ conventions.
Single source of truth: do not duplicate these lists anywhere else.
"""

from __future__ import annotations

HOSPITALS: tuple[str, ...] = ("HPV", "HRB", "HLU", "HLL")

# 18 canonical siglas (order matches the 18 prevention categories)
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
    "exc",
    "altura",
    "caliente",
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
    "exc": "13.-Excavaciones y Vanos",
    "altura": "14.-Trabajos en Altura",
    "caliente": "15.-Inspeccion Trabajos en Caliente",
    "herramientas_elec": "16.-Inspeccion Herramientas Electricas",
    "andamios": "17.-Andamios",
    "chps": "18.-CHPS",
}

_FOLDER_TO_SIGLA: dict[str, str] = {v: k for k, v in CATEGORY_FOLDERS.items()}


def sigla_to_folder(sigla: str) -> str:
    """Return the canonical folder base name for a sigla."""
    return CATEGORY_FOLDERS[sigla]


def folder_to_sigla(folder_name: str) -> str | None:
    """Map a folder name (with or without TOTAL/' 0' suffix) back to its sigla.

    Examples:
        '7.-ART' → 'art'
        '7.-ART 934' → 'art'
        '12.-Senaleticas 0' → 'senal'
        '99.-Unknown' → None
    """
    # strip suffix after the canonical name
    for canonical, sigla in _FOLDER_TO_SIGLA.items():
        if folder_name == canonical or folder_name.startswith(canonical + " "):
            return sigla
    return None
