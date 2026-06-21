"""PDFoverseer core package.

Intentionally minimal: submodules are imported directly (e.g. ``from core.scanners
import ...``, ``from core.orchestrator import ...``, ``from core.cell_count import ...``).

This ``__init__`` deliberately does NOT eagerly import the deferred V4 cluster
(``core.pipeline`` / ``core.inference`` / ``core.ocr``). Doing so previously made every
``import core.*`` load a dormant, unwired engine (plus cv2/torch probing). The V4 modules
stay importable directly for tests/tools (deferred-fallback decision D10); nothing consumes
a ``from core import ...`` aggregate surface.
"""
