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
    """A14: machine-readable signals for the operator (UI in chunk 6)."""

    near_matches: list[NearMatchEntry] = field(default_factory=list)


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
    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult: ...
