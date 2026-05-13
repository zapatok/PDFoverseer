"""Scanner for sigla `irl` — Inspecciones de Riesgo Laboral."""

from __future__ import annotations

from dataclasses import dataclass

from core.scanners._header_detect_base import HeaderDetectScanner


@dataclass(kw_only=True)
class IrlScanner(HeaderDetectScanner):
    sigla: str = "irl"
    sigla_code: str = "IRL"
