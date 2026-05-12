"""Scanner registry. Scanners auto-register on import."""

from __future__ import annotations

from collections.abc import Iterator

from core.scanners.base import ConfidenceLevel, Scanner, ScanResult

_REGISTRY: dict[str, Scanner] = {}


def register(scanner: Scanner) -> None:
    if scanner.sigla in _REGISTRY:
        raise ValueError(f"duplicate scanner sigla: {scanner.sigla}")
    _REGISTRY[scanner.sigla] = scanner


def get(sigla: str) -> Scanner:
    return _REGISTRY[sigla]


def has(sigla: str) -> bool:
    return sigla in _REGISTRY


def all_siglas() -> list[str]:
    return sorted(_REGISTRY.keys())


def all_scanners() -> Iterator[Scanner]:
    yield from _REGISTRY.values()


def clear() -> None:
    """For tests only."""
    _REGISTRY.clear()


__all__ = [
    "Scanner",
    "ScanResult",
    "ConfidenceLevel",
    "register",
    "get",
    "has",
    "all_siglas",
    "all_scanners",
    "clear",
]
