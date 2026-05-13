"""Scanner for sigla `odi` — Observación de Incidentes / ODI Visitas."""

from __future__ import annotations

from dataclasses import dataclass

from core.scanners._header_detect_base import HeaderDetectScanner


@dataclass(kw_only=True)
class OdiScanner(HeaderDetectScanner):
    sigla: str = "odi"
    sigla_code: str = "ODI"
