"""
distance.py — OCR-weighted string distance.

Uses weighted-levenshtein with the confusion matrix from confusion.py.
Substitutions of visually similar characters (g↔q, i↔1, etc.) cost less
than generic substitutions, producing a score that reflects OCR plausibility.
"""

import numpy as np
from weighted_levenshtein import levenshtein

from ocr_matcher.confusion import build_matrix

# Insertion and deletion costs: uniform 1.0 per character
_INSERT = np.ones(128, dtype=np.float64)
_DELETE = np.ones(128, dtype=np.float64)
_SUBSTITUTE = build_matrix()


def ocr_distance(a: str, b: str, ignore_case: bool = False) -> float:
    """
    Compute the OCR-weighted edit distance between strings `a` and `b`.

    Lower = more likely to be an OCR variant of the same word.
    Returns 0.0 for identical strings.

    Only handles ASCII (ord < 128). Unicode chars outside the confusion
    table incur standard cost 1.0 per operation.
    """
    if ignore_case:
        a, b = a.lower(), b.lower()
    if a == b:
        return 0.0
    a_safe = "".join(c if ord(c) < 128 else "?" for c in a)
    b_safe = "".join(c if ord(c) < 128 else "?" for c in b)
    return float(levenshtein(a_safe, b_safe,
                             insert_costs=_INSERT,
                             delete_costs=_DELETE,
                             substitute_costs=_SUBSTITUTE))


def is_likely_ocr_of(candidate: str, target: str,
                     threshold: float = 0.5,
                     ignore_case: bool = True) -> bool:
    """
    Return True if `candidate` is likely an OCR corruption of `target`.

    `threshold` is the maximum allowed weighted edit distance per character.
    Normalizing by word length makes the threshold word-length agnostic.
    """
    if not target:
        return False
    dist = ocr_distance(candidate, target, ignore_case=ignore_case)
    normalized = dist / max(len(target), len(candidate))
    return normalized <= threshold
