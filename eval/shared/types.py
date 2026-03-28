"""Shared data types for all eval engines."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageRead:
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float
    # Internal flag set during inference (not in fixture JSON — has default):
    _ph1_orphan_candidate: bool = field(default=False, repr=False, compare=False)


@dataclass
class Document:
    index:          int
    start_pdf_page: int
    declared_total: int
    pages:          list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok:    bool      = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total
