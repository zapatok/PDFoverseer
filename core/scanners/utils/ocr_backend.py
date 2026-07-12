"""Pluggable OCR text-extraction backend: pytesseract (default) or tesserocr (opt-in).

pytesseract spawns a fresh ``tesseract.exe`` process on every call — on Windows
that spawn alone measured ~195 ms/page (2026-07-11 threading spike), on top of
the OCR itself. ``tesserocr`` (the C-API binding) keeps one Tesseract engine
loaded per thread and skips the spawn entirely; a same-image micro-benchmark
against the 3 call-sites below measured 367 -> 164 ms/crop (2.23x,
``docs/research/2026-07-12-tesserocr-spike.md``).

Select the backend with the ``OVERSEER_OCR_BACKEND`` env var:

- unset, or ``"pytesseract"`` (the default): spawns ``tesseract.exe`` per call,
  exactly today's behavior. Works with zero extra install — this is the
  CI-safe / no-tesserocr-package path.
- ``"tesserocr"``: one ``tesserocr.PyTessBaseAPI`` per OCR **thread**
  (``threading.local()`` — tesserocr is not safe to share across concurrently
  running threads; mirrors the thread-local ``fitz.Document`` idiom already
  used in ``pagination_count.py``/``header_band_anchors.py``). If the
  ``tesserocr`` package is not importable, this falls back to pytesseract
  automatically (with a log warning) — the flag is always safe to set.

Windows install: PyPI has no prebuilt wheel for ``tesserocr`` and building
from source fails (no local Tesseract/Leptonica dev headers). Use the
community wheel from
https://github.com/simonflueckiger/tesserocr-windows_build/releases — pick
the release matching the venv's Python (``python --version``); the wheel
embeds its own Tesseract + Leptonica build, so it does not need to match the
system Tesseract version exactly (verified here:
``tesserocr-2.10.0-cp310-cp310-win_amd64.whl`` from the
``tesserocr-v2.10.0-tesseract-5.5.2`` release, against a system Tesseract
5.5.0 install). ``TESSDATA_PREFIX`` must still point at the *system*
``tessdata`` dir (``C:\\Program Files\\Tesseract-OCR\\tessdata``) for
``lang="spa+eng"`` to resolve — this module sets that via
``os.environ.setdefault`` so callers never have to.

Public entry point: ``ocr_image``. It parses the pytesseract-style ``config``
string (e.g. ``"--psm 6 --oem 1"``) into tesserocr's ``psm``/``oem`` ints, so
the 3 existing call-sites (``pagination_count._corner_text``;
``header_band_anchors.count_covers_by_anchors``'s raw + E6-preprocessed
passes) migrate without changing their config literals or behavior on the
default backend.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# Tesseract binary path for the pytesseract backend — single source of truth
# for the 3 call-sites that used to set this individually (mirror core/ocr.py
# convention). Centralized here since this module is now their only pytesseract
# entry point.
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

try:
    import tesserocr
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    tesserocr = None

_TESSDATA_PREFIX_DEFAULT = r"C:\Program Files\Tesseract-OCR\tessdata"
if tesserocr is not None:
    os.environ.setdefault("TESSDATA_PREFIX", _TESSDATA_PREFIX_DEFAULT)


def _tessdata_path() -> str:
    """The tessdata dir tesserocr's ``PyTessBaseAPI(path=...)`` needs (trailing slash).

    Gotcha found during Task 3 (2026-07-12): unlike the Tesseract *binary*,
    this tesserocr Windows build does NOT fall back to reading
    ``TESSDATA_PREFIX`` on its own — its ``path`` kwarg defaults to ``"./"``,
    which fails with ``RuntimeError: Failed to init API, possibly an invalid
    tessdata path: ./`` outside a tessdata-rooted cwd. So ``path`` must always
    be passed explicitly; this helper is that single source of truth (reads
    the same ``TESSDATA_PREFIX`` env var set above, for one configuration
    knob).
    """
    prefix = os.environ.get("TESSDATA_PREFIX", _TESSDATA_PREFIX_DEFAULT)
    return prefix if prefix.endswith(("/", "\\")) else prefix + "/"


_PSM_RX = re.compile(r"--psm\s+(\d+)")
_OEM_RX = re.compile(r"--oem\s+(\d+)")
# Tesseract's own defaults when a flag is absent from the config string.
_DEFAULT_PSM = 3
_DEFAULT_OEM = 3

_tl = threading.local()


def _parse_config(config: str) -> tuple[int, int]:
    """Extract ``--psm``/``--oem`` ints from a pytesseract-style config string."""
    psm_m = _PSM_RX.search(config)
    oem_m = _OEM_RX.search(config)
    psm = int(psm_m.group(1)) if psm_m else _DEFAULT_PSM
    oem = int(oem_m.group(1)) if oem_m else _DEFAULT_OEM
    return psm, oem


def _to_pil(img: Any) -> Image.Image:
    """tesserocr's ``SetImage`` needs a PIL.Image; callers may pass a numpy array."""
    if isinstance(img, Image.Image):
        return img
    return Image.fromarray(img)


def _tesserocr_api(*, lang: str, psm: int, oem: int) -> Any:
    """Return this thread's ``PyTessBaseAPI``, (re)built only if its config changed."""
    key = (lang, psm, oem)
    if getattr(_tl, "key", None) != key:
        _tl.api = tesserocr.PyTessBaseAPI(path=_tessdata_path(), lang=lang, psm=psm, oem=oem)
        _tl.key = key
    return _tl.api


def _ocr_tesserocr(img: Any, *, config: str, lang: str) -> str:
    psm, oem = _parse_config(config)
    api = _tesserocr_api(lang=lang, psm=psm, oem=oem)
    api.SetImage(_to_pil(img))
    return api.GetUTF8Text()


def _ocr_pytesseract(img: Any, *, config: str, lang: str) -> str:
    return pytesseract.image_to_string(img, config=config, lang=lang)


def ocr_image(img: Any, *, config: str, lang: str) -> str:
    """Run OCR on *img* through the backend selected by ``OVERSEER_OCR_BACKEND``.

    Args:
        img: a PIL.Image or numpy array — whatever the caller already renders.
        config: pytesseract-style flags, e.g. ``"--psm 6 --oem 1"``.
        lang: Tesseract language string, e.g. ``"spa+eng"``.

    Returns:
        Raw OCR text, unstripped (callers strip if they need to). The backend
        choice never changes the counting derivation: with the default
        (pytesseract) backend this call is byte-identical to calling
        ``pytesseract.image_to_string`` directly. Whitespace may differ
        between backends; document/page counts derived from it must not
        (verified by the equivalence gate, Task 3).
    """
    backend = os.environ.get("OVERSEER_OCR_BACKEND", "pytesseract")
    if backend == "tesserocr":
        if tesserocr is None:
            logger.warning(
                "OVERSEER_OCR_BACKEND=tesserocr but the tesserocr package is not "
                "installed; falling back to pytesseract. See this module's "
                "docstring for the Windows wheel URL."
            )
        else:
            return _ocr_tesserocr(img, config=config, lang=lang)
    return _ocr_pytesseract(img, config=config, lang=lang)
