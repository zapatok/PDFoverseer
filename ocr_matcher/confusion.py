"""
confusion.py — OCR character substitution cost table.

Costs are in range [0.0, 1.0]:
  0.0  = same character (free)
  0.05–0.15 = very common OCR confusion
  0.2–0.4   = plausible OCR confusion
  1.0  = default (unrelated characters)

Sources: Schulz & Mihov 2002, arxiv:1604.06225, arxiv:2602.14524,
         Tesseract unicharambigs, community OCR error catalogs.
"""

import numpy as np

# fmt: off
# (char_a, char_b, cost)  — table is made bidirectional automatically
_RAW: list[tuple[str, str, float]] = [
    # --- Very common single-char substitutions (Tesseract + EasyOCR) ---
    ('0', 'O', 0.05), ('0', 'o', 0.05), ('O', 'o', 0.05),
    ('1', 'l', 0.05), ('1', 'i', 0.05), ('1', 'I', 0.05), ('1', '|', 0.05),
    ('l', 'i', 0.08), ('l', 'I', 0.08), ('l', '|', 0.08),
    ('i', 'I', 0.08),
    ('g', 'q', 0.05), ('g', '9', 0.10),
    ('q', '9', 0.10),
    ('s', '5', 0.08), ('s', 'S', 0.05), ('s', '$', 0.10),
    ('5', 'S', 0.08), ('5', '$', 0.10),
    ('z', '2', 0.08), ('z', 'Z', 0.05),
    ('2', 'Z', 0.08),
    ('a', '@', 0.10), ('a', 'á', 0.05), ('a', 'à', 0.05),
    ('e', '3', 0.10), ('e', 'é', 0.05), ('e', 'è', 0.05),
    ('n', 'ñ', 0.05),
    ('u', 'ü', 0.05), ('u', 'ú', 0.05),
    ('o', 'ó', 0.05), ('o', 'ò', 0.05),
    ('c', '(', 0.10), ('c', 'C', 0.05),
    ('b', '6', 0.10), ('b', 'B', 0.05),
    ('h', '#', 0.15),
    ('t', '+', 0.15),
    # --- Less frequent but documented ---
    ('d', '0', 0.20),
    # ('d', 'a') cost 0.25 is intentionally excluded from charclass generation
    # (threshold uses strict < 0.25) — weak visual claim, drives false positives
    ('f', 't', 0.20),
    ('P', 'p', 0.05), ('F', 'f', 0.05),
    ('B', '8', 0.10), ('B', '3', 0.12),
    ('D', '0', 0.15),
]
# fmt: on


def build_matrix() -> np.ndarray:
    """Return a 128×128 float64 cost matrix (ASCII only)."""
    m = np.ones((128, 128), dtype=np.float64)
    np.fill_diagonal(m, 0.0)
    for a, b, cost in _RAW:
        if ord(a) < 128 and ord(b) < 128:
            m[ord(a), ord(b)] = cost
            m[ord(b), ord(a)] = cost  # bidirectional
    return m


# Module-level singleton — build once
_MATRIX: np.ndarray = build_matrix()


def substitution_cost(a: str, b: str) -> float:
    """
    Return the OCR substitution cost for replacing character `a` with `b`.

    Returns 0.0 for identical chars, 1.0 for unrelated chars, and
    a value in (0, 1) for known OCR confusion pairs.
    """
    if a == b:
        return 0.0
    ia, ib = ord(a), ord(b)
    if ia >= 128 or ib >= 128:
        return 0.0 if a == b else 1.0
    return float(_MATRIX[ia, ib])
