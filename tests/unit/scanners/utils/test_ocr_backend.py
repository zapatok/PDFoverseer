"""Tests for the pluggable OCR backend seam (Track D §2)."""

from __future__ import annotations

import logging

import pytest
from PIL import Image

from core.scanners.utils import ocr_backend


@pytest.fixture(autouse=True)
def _clean_backend_env(monkeypatch):
    """No test should inherit a real env override or a cached thread-local API."""
    monkeypatch.delenv("OVERSEER_OCR_BACKEND", raising=False)
    monkeypatch.delattr(ocr_backend._tl, "api", raising=False)
    monkeypatch.delattr(ocr_backend._tl, "key", raising=False)


class _FakeAPI:
    """Records SetImage/GetUTF8Text calls; mirrors tesserocr.PyTessBaseAPI's surface."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.set_image_calls: list[object] = []

    def SetImage(self, img):  # noqa: N802 - matches tesserocr's real method name
        self.set_image_calls.append(img)

    def GetUTF8Text(self):  # noqa: N802 - matches tesserocr's real method name
        return "fake tesserocr text"


class _FakeTesserocrModule:
    """Spies on PyTessBaseAPI construction (one call per new thread expected)."""

    def __init__(self):
        self.built_apis: list[_FakeAPI] = []

    def PyTessBaseAPI(self, **kwargs):  # noqa: N802 - matches tesserocr's real class name
        api = _FakeAPI(**kwargs)
        self.built_apis.append(api)
        return api


# ---------------------------------------------------------------------------
# (a) default (OVERSEER_OCR_BACKEND absent) -> tesserocr if the package is
# importable, else pytesseract (Track D §2, Task 4 — tesserocr became the
# default once the equivalence gate passed: docs/research/2026-07-12-tesserocr-spike.md)
# ---------------------------------------------------------------------------


def test_default_backend_is_tesserocr_when_package_present(monkeypatch):
    """Package importable + env unset -> the default routes through tesserocr."""
    fake_mod = _FakeTesserocrModule()
    monkeypatch.setattr(ocr_backend, "tesserocr", fake_mod)
    pytesseract_calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: pytesseract_calls.append((img, kw)) or "SHOULD NOT BE CALLED",
    )

    img = Image.new("L", (4, 4))
    result = ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")

    assert result == "fake tesserocr text"
    assert not pytesseract_calls
    assert len(fake_mod.built_apis) == 1


def test_default_backend_is_pytesseract_when_package_absent(monkeypatch):
    """Package NOT importable (simulated absence) + env unset -> pytesseract, no error.

    tesserocr IS installed in this venv (Task 1), so absence is simulated the
    same way test_tesserocr_flag_without_package_falls_back_with_warning does:
    monkeypatch ocr_backend's already-resolved ``tesserocr`` name to None —
    exactly what a real ImportError at module-import time would have left it
    as, per the try/except at the top of ocr_backend.py.
    """
    monkeypatch.setattr(ocr_backend, "tesserocr", None)
    calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: calls.append((img, kw)) or "raw pytesseract text",
    )

    img = object()
    result = ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")

    assert result == "raw pytesseract text"
    assert calls == [(img, {"config": "--psm 6 --oem 1", "lang": "spa+eng"})]


def test_explicit_pytesseract_backend_overrides_the_tesserocr_default(monkeypatch):
    """An explicit env value always wins over whatever the default would be."""
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "pytesseract")
    calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: calls.append((img, kw)) or "text",
    )
    img = object()
    assert ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng") == "text"
    assert calls == [(img, {"config": "--psm 6 --oem 1", "lang": "spa+eng"})]


# ---------------------------------------------------------------------------
# (b) OVERSEER_OCR_BACKEND=tesserocr but the package is absent -> pytesseract + warning
# ---------------------------------------------------------------------------


def test_tesserocr_flag_without_package_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "tesserocr")
    monkeypatch.setattr(ocr_backend, "tesserocr", None)

    calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: calls.append((img, kw)) or "fallback text",
    )

    with caplog.at_level(logging.WARNING, logger="core.scanners.utils.ocr_backend"):
        img = object()
        result = ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")

    assert result == "fallback text"
    assert calls == [(img, {"config": "--psm 6 --oem 1", "lang": "spa+eng"})]
    assert any(
        "tesserocr" in rec.message and "not installed" in rec.message for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# (c) flag set + package present -> one API per thread, tesserocr does the OCR
# ---------------------------------------------------------------------------


def test_tesserocr_backend_calls_tesserocr_not_pytesseract(monkeypatch):
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "tesserocr")
    fake_mod = _FakeTesserocrModule()
    monkeypatch.setattr(ocr_backend, "tesserocr", fake_mod)

    pytesseract_calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: pytesseract_calls.append((img, kw)) or "SHOULD NOT BE CALLED",
    )

    img = Image.new("L", (4, 4))
    result = ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")

    assert result == "fake tesserocr text"
    assert not pytesseract_calls
    assert len(fake_mod.built_apis) == 1
    assert fake_mod.built_apis[0].set_image_calls == [img]


def test_tesserocr_backend_one_api_per_thread(monkeypatch):
    """A single thread reuses its PyTessBaseAPI across repeated calls; each new
    thread builds its own (tesserocr is not safe to share across threads)."""
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "tesserocr")
    fake_mod = _FakeTesserocrModule()
    monkeypatch.setattr(ocr_backend, "tesserocr", fake_mod)

    img = Image.new("L", (4, 4))
    ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")
    ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")
    ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")

    assert len(fake_mod.built_apis) == 1  # same thread, same config -> reused

    import threading

    other_thread_apis = []

    def _run_in_other_thread():
        ocr_backend.ocr_image(img, config="--psm 6 --oem 1", lang="spa+eng")
        other_thread_apis.append(len(fake_mod.built_apis))

    t = threading.Thread(target=_run_in_other_thread)
    t.start()
    t.join()

    assert len(fake_mod.built_apis) == 2  # a second thread built its own API


# ---------------------------------------------------------------------------
# (d) config (psm/oem) + lang are preserved end to end
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config,expected_psm,expected_oem",
    [
        ("--psm 6 --oem 1", 6, 1),
        ("--psm 11 --oem 0", 11, 0),
        ("", 3, 3),  # tesseract's own defaults when flags are absent
    ],
)
def test_tesserocr_backend_preserves_psm_oem_config(
    monkeypatch, config, expected_psm, expected_oem
):
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "tesserocr")
    fake_mod = _FakeTesserocrModule()
    monkeypatch.setattr(ocr_backend, "tesserocr", fake_mod)

    img = Image.new("L", (4, 4))
    ocr_backend.ocr_image(img, config=config, lang="spa+eng")

    kwargs = fake_mod.built_apis[0].kwargs
    assert kwargs["lang"] == "spa+eng"
    assert kwargs["psm"] == expected_psm
    assert kwargs["oem"] == expected_oem
    assert kwargs["path"].endswith(("/", "\\"))  # tesserocr requires a trailing separator


def test_pytesseract_backend_preserves_config_and_lang_literally(monkeypatch):
    """The default backend must pass config/lang through unchanged (AC-a: byte-identical)."""
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "pytesseract")
    calls = []
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: calls.append(kw) or "x",
    )
    ocr_backend.ocr_image(object(), config="--psm 11 --oem 0", lang="eng")
    assert calls == [{"config": "--psm 11 --oem 0", "lang": "eng"}]


def test_to_pil_converts_numpy_array(monkeypatch):
    """header_band_anchors' E6 preprocessed pass hands a numpy array, not a PIL.Image."""
    import numpy as np

    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "tesserocr")
    fake_mod = _FakeTesserocrModule()
    monkeypatch.setattr(ocr_backend, "tesserocr", fake_mod)

    arr = np.zeros((4, 4), dtype="uint8")
    ocr_backend.ocr_image(arr, config="--psm 6 --oem 1", lang="spa+eng")

    seen = fake_mod.built_apis[0].set_image_calls[0]
    assert isinstance(seen, Image.Image)
