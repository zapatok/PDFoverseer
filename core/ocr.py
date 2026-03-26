"""OCR pipeline: Tesseract (tiers 1-2) + EasyOCR (tier 3)."""
from __future__ import annotations

import os as _os
import threading  # kept for SR semaphore
from pathlib import Path

import cv2
import numpy as np
import pytesseract
import fitz

from core.utils import TESS_CONFIG, _parse, _PageRead
from core.image import _render_clip, _deskew

# ── Configuración ─────────────────────────────────────────────────────────────

pytesseract.pytesseract.tesseract_cmd = _os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

MODELS_DIR  = Path(__file__).parent.parent / "models"
FSRCNN_PATH = str(MODELS_DIR / "FSRCNN_x4.pb")

# ── Super Resolution (GPU bicubic si disponible, FSRCNN CPU como fallback) ────

_sr_local      = threading.local()        # FSRCNN CPU: un modelo por thread
_gpu_sr_device = None                     # torch.device("cuda") si disponible
_sr_sem        = threading.Semaphore(2)   # max 2 FSRCNN simultáneos (OpenCV DNN ya es multithreaded)

def _init_sr(on_log: callable) -> None:
    """Detect GPU SR capability; fall back to FSRCNN CPU."""
    global _gpu_sr_device
    try:
        import torch
        if torch.cuda.is_available():
            _gpu_sr_device = torch.device("cuda")
            on_log(f"SR Tier-2: PyTorch GPU bicubic 4x ({torch.cuda.get_device_name(0)})", "ok")
            return
    except ImportError:
        pass
    on_log("SR Tier-2: FSRCNN x4 CPU (GPU no disponible)", "info")


def _upsample_4x(bgr: np.ndarray) -> np.ndarray:
    """4x upscale for Tier-2 OCR.  GPU bilinear (~1ms) or FSRCNN CPU (~150ms)."""
    if _gpu_sr_device is not None:
        import torch
        import torch.nn.functional as F
        t = (torch.from_numpy(bgr)
               .permute(2, 0, 1).float().unsqueeze(0)
               .to(_gpu_sr_device) / 255.0)
        t_up = F.interpolate(t, scale_factor=4, mode="bicubic", align_corners=False)
        return (t_up.squeeze(0).permute(1, 2, 0)
                  .clamp(0, 1).mul(255).byte()
                  .cpu().numpy())
    # CPU fallback: FSRCNN (thread-local, max 2 concurrent via semaphore)
    if not getattr(_sr_local, "model", None):
        m = cv2.dnn_superres.DnnSuperResImpl_create()
        m.readModel(FSRCNN_PATH)
        m.setModel("fsrcnn", 4)
        _sr_local.model = m
    with _sr_sem:
        return _sr_local.model.upsample(bgr)


_sr_initialized = False

def _setup_sr(on_log: callable) -> None:
    """One-time SR initialization (called from analyze_pdf on first use)."""
    global _sr_initialized
    _init_sr(on_log)
    if _gpu_sr_device is None:
        on_log("Cargando FSRCNN x4 CPU...", "info")
        _upsample_4x(np.zeros((10, 10, 3), dtype=np.uint8))  # warmup
    _sr_initialized = True

# ── OCR helpers ───────────────────────────────────────────────────────────────

def _tess_ocr(bgr: np.ndarray) -> str:
    """OCR a page-number strip via Tesseract."""
    if len(bgr.shape) == 2 or bgr.shape[2] == 1:
        gray = bgr
    else:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([150, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        bgr_clean = cv2.inpaint(bgr, mask_blue, 3, cv2.INPAINT_NS)
        gray = cv2.cvtColor(bgr_clean, cv2.COLOR_BGR2GRAY)

    # Unsharp mask (sweep-tuned: sigma=1.0, strength=0.3)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
    gray = cv2.addWeighted(gray, 1.3, blurred, -0.3, 0)

    return pytesseract.image_to_string(gray, lang="eng", config=TESS_CONFIG).strip()

# ── Tesseract-only page processor (runs in thread pool) ─────────────────────

def _process_page(doc: fitz.Document, page_idx: int) -> _PageRead:
    """
    Render one page clip and run Tesseract OCR (2 tiers).
    Receives a pre-opened fitz.Document from the caller's doc pool (one per thread).
    pytesseract launches tesseract.exe as subprocess → releases GIL → real parallelism.
    """
    pdf_page = page_idx + 1
    bgr = _render_clip(doc[page_idx])
    bgr = _deskew(bgr)   # correct scan skew; Tier 2 inherits via bgr_sr = _upsample_4x(bgr)

    # Tier 1: Tesseract direct (passing BGR so _tess_ocr can filter colors)
    text = _tess_ocr(bgr)
    c, t = _parse(text)
    if c:
        return _PageRead(pdf_page, c, t, "direct", 1.0)

    # Tier 2: 4x upscale (GPU bicubic ~1ms or FSRCNN CPU ~150ms) + Tesseract
    bgr_sr = _upsample_4x(bgr)
    text_sr = _tess_ocr(bgr_sr)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(pdf_page, c, t, "super_resolution", 1.0)

    return _PageRead(pdf_page, None, None, "failed", 0.0)
