"""Scanner Protocol + supporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"


@dataclass(frozen=True)
class NearMatchEntry:
    """A14: per-PDF, per-page near-match record exposed in ScanResult."""

    pdf_name: str
    page_index: int  # 0-based
    flavor_name: str
    matched_anchors: list[str]
    missing_anchors: list[str]


@dataclass(frozen=True)
class ScanTelemetry:
    """A14: machine-readable signals for the operator (UI in chunk 6).

    ``colado_suspects``/``present_files`` (anti-colados V1): misfiled-document
    suspects detected this scan + every PDF present in the folder (the eviction
    basis persistence needs). Both default-empty so existing constructions
    (AnchorsScanner) stay valid.
    """

    near_matches: list[NearMatchEntry] = field(default_factory=list)
    colado_suspects: list[dict] = field(default_factory=list)
    present_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScanResult:
    count: int
    confidence: ConfidenceLevel
    method: str
    breakdown: dict[str, int] | None
    flags: list[str]
    errors: list[str]
    duration_ms: int
    files_scanned: int
    per_file: dict[str, int] | None = None
    telemetry: ScanTelemetry | None = None  # A14


@runtime_checkable
class Scanner(Protocol):
    """Pase-1 scanner contract: every sigla exposes ``count`` (filename glob).

    Pase-2 OCR is an *optional* capability, deliberately NOT declared here: the OCR
    scanners (``AnchorsScanner``, ``PaginationScanner``) also implement
    ``count_ocr(...)``, but ``SimpleFilenameScanner`` (``scan_strategy="none"``) does
    not. The orchestrator dispatches OCR via ``getattr(scanner, "count_ocr", None)``
    so a non-OCR sigla isn't forced to implement an unused method.
    """

    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult: ...
