"""PyMuPDF wrapper: render pages or page regions as PIL images, count pages."""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


class PdfRenderError(RuntimeError):
    """Raised when a PDF cannot be opened, parsed, or rendered."""


def get_page_count(pdf_path: Path) -> int:
    """Return the page count of *pdf_path*. Raises PdfRenderError on failure."""
    try:
        with fitz.open(pdf_path) as doc:
            return len(doc)
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot read {pdf_path}: {exc}") from exc


def render_page_image(pdf_path: Path, page_idx: int, *, dpi: int = 150) -> Image.Image:
    """Render a full page at *dpi* and return as PIL.Image (RGB)."""
    try:
        with fitz.open(pdf_path) as doc:
            if not (0 <= page_idx < len(doc)):
                raise PdfRenderError(f"page_idx={page_idx} out of range for {pdf_path}")
            page = doc[page_idx]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            return img
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot render {pdf_path}:{page_idx}: {exc}") from exc


def render_page_region(
    pdf_path: Path,
    page_idx: int,
    *,
    bbox: tuple[float, float, float, float],
    dpi: int = 200,
) -> Image.Image:
    """Render a region of a page.

    Args:
        bbox: ``(x0, y0, x1, y1)`` in *relative* coordinates [0..1].
              ``(0, 0)`` is top-left of the page.
        dpi: target DPI. OCR usually wants 200 or higher.
    """
    x0, y0, x1, y1 = bbox
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(f"invalid bbox {bbox}: expected [0..1] with x0<x1, y0<y1")
    try:
        with fitz.open(pdf_path) as doc:
            if not (0 <= page_idx < len(doc)):
                raise PdfRenderError(f"page_idx={page_idx} out of range for {pdf_path}")
            page = doc[page_idx]
            page_rect = page.rect
            clip = fitz.Rect(
                page_rect.x0 + (page_rect.width * x0),
                page_rect.y0 + (page_rect.height * y0),
                page_rect.x0 + (page_rect.width * x1),
                page_rect.y0 + (page_rect.height * y1),
            )
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
            return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except (fitz.FileDataError, OSError, ValueError, RuntimeError) as exc:
        raise PdfRenderError(f"cannot render {pdf_path}:{page_idx} region {bbox}: {exc}") from exc
