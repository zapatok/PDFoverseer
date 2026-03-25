"""OCR pipeline: Tesseract (tiers 1-2) + EasyOCR (tier 3)."""
from __future__ import annotations

import os as _os
import threading
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

EASYOCR_DPI = 300  # EasyOCR needs higher DPI for small text accuracy

# ── EasyOCR GPU (Tier 1.5) ───────────────────────────────────────────────────

_easyocr_reader = None        # singleton, lazy-loaded (not thread-safe — use via queue)
_easyocr_lock   = threading.Lock()

def _init_easyocr(on_log: callable) -> None:
    """Lazy-init EasyOCR Reader with GPU support."""
    global _easyocr_reader
    if _easyocr_reader is not None:
        return
    with _easyocr_lock:
        if _easyocr_reader is not None:
            return  # double-check after lock
        try:
            import easyocr
            gpu = False
            try:
                import torch
                gpu = torch.cuda.is_available()
            except ImportError:
                pass
            on_log(f"EasyOCR: inicializando ({'GPU' if gpu else 'CPU'})...", "info")
            _easyocr_reader = easyocr.Reader(
                ["es", "en"], gpu=gpu, verbose=False
            )
            on_log(f"EasyOCR: listo ({'GPU' if gpu else 'CPU'})", "ok")
        except Exception as e:
            on_log(f"EasyOCR: no disponible ({e})", "warn")

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

def _process_page(doc: fitz.Document, page_idx: int) -> tuple[_PageRead, np.ndarray | None]:
    """
    Render one page clip and run Tesseract OCR (3 tiers: T1→T2-SR→T2b-DPI300).
    Returns (PageRead, bgr_300_or_None).
    bgr_300 is the deskewed DPI-300 image, returned when T2b runs (success or fail)
    so the GPU consumer can reuse it for EasyOCR without re-rendering.
    """
    pdf_page = page_idx + 1
    bgr = _render_clip(doc[page_idx])
    bgr = _deskew(bgr)

    # Tier 1: Tesseract @ DPI 150
    text = _tess_ocr(bgr)
    c, t = _parse(text)
    if c:
        return _PageRead(pdf_page, c, t, "direct", 1.0), None

    # Tier 2: 4x upscale of DPI-150 image + Tesseract
    bgr_sr = _upsample_4x(bgr)
    text_sr = _tess_ocr(bgr_sr)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(pdf_page, c, t, "super_resolution", 1.0), None

    # Tier 2b: Tesseract @ DPI 300 — SR fallback (sweep: +14 pages only-DPI300 recovers)
    bgr_300 = _render_clip(doc[page_idx], dpi=EASYOCR_DPI)
    bgr_300 = _deskew(bgr_300)
    text_300 = _tess_ocr(bgr_300)
    c, t = _parse(text_300)
    if c:
        return _PageRead(pdf_page, c, t, "dpi300", 1.0), bgr_300

    return _PageRead(pdf_page, None, None, "failed", 0.0), bgr_300
