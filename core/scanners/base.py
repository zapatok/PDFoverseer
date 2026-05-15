"""Scanner Protocol + supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ConfidenceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"


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


@runtime_checkable
class Scanner(Protocol):
    sigla: str

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult: ...
