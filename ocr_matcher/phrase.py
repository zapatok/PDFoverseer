"""
phrase.py — OCR-aware phrase pattern generator.

Template syntax:
    {num}   — digit sequence with OCR alternatives (captured group)
    {word}  — any non-space sequence (generic placeholder)
    literal — any other text is treated as a literal word, OCR-expanded

Example:
    generate_phrase_pattern("Pagina {num} de {num}")
    -> matches "Pagina 3 de 8", "Paqina l de z", "Pagina3de8", ...
    -> m.group(1) == "3", m.group(2) == "8"

Capture groups correspond to {num} tokens left-to-right.
Use re.compile(..., re.IGNORECASE) on the returned pattern string.
"""

import re as _re

from ocr_matcher.pattern import generate_charclass_pattern

# Characters that OCR commonly confuses with digits:
#   0 ↔ O, o     (round shape)
#   1 ↔ l, i, I, |  (thin verticals)
#   2 ↔ z, Z     (angular)
_NUM_CLASS = r"([0-9OoIl|zZ]{1,4})"

# Generic word placeholder — used when the caller doesn't know the literal word
_WORD_CLASS = r"(\S+)"

# Tokenizer: {placeholder} or whitespace-delimited literal
_TOKEN_RE = _re.compile(r"\{(\w+)\}|(\S+)")


def generate_phrase_pattern(template: str) -> str:
    """
    Generate an OCR-aware regex pattern from a phrase template.

    Template syntax:
        {num}   — digit sequence with OCR alternatives (captured group)
        {word}  — any non-space sequence (generic anchor placeholder)
        literal — OCR-expanded word via generate_charclass_pattern

    Returns a raw pattern string for re.compile(..., re.IGNORECASE).
    Flexible spacing (\\s*) is inserted between tokens to handle
    'pegado' OCR output where spaces are dropped.

    Capture groups correspond to {num} tokens in left-to-right order.
    """
    parts = []
    for m in _TOKEN_RE.finditer(template.strip()):
        placeholder, literal = m.group(1), m.group(2)
        if placeholder == "num":
            parts.append(_NUM_CLASS)
        elif placeholder == "word":
            parts.append(_WORD_CLASS)
        elif literal:
            # Only the first literal word gets \b — intermediate words must not
            # have \b because in pegado OCR output (no spaces) there is no word
            # boundary between adjacent \w characters (e.g. "3de").
            boundary = len(parts) == 0
            parts.append(generate_charclass_pattern(literal, boundary=boundary))

    return r"\s*".join(parts)
