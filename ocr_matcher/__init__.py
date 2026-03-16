"""ocr_matcher — OCR-aware fuzzy word matching. Standalone, off-pipeline."""

from ocr_matcher.pattern import generate_charclass_pattern, generate_fuzzy_pattern
from ocr_matcher.distance import ocr_distance, is_likely_ocr_of
from ocr_matcher.phrase import generate_phrase_pattern

__all__ = [
    "generate_charclass_pattern",
    "generate_fuzzy_pattern",
    "generate_phrase_pattern",
    "ocr_distance",
    "is_likely_ocr_of",
]
