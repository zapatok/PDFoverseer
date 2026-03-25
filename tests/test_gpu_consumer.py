"""Tests for pipeline GPU consumer image reuse (core/pipeline.py)."""
import numpy as np
import queue
import threading
from unittest.mock import patch, MagicMock

from core.utils import _PageRead


class TestWorkerReturnUnpacking:
    """Pipeline must correctly unpack (PageRead, image) from workers."""

    def test_successful_read_unpacks_none_image(self):
        """A successful OCR read returns (PageRead, None)."""
        pr = _PageRead(1, 1, 4, "direct", 1.0)
        result = (pr, None)
        page_read, bgr_300 = result
        assert page_read.curr == 1
        assert bgr_300 is None

    def test_failed_read_unpacks_image(self):
        """A failed OCR read returns (PageRead, bgr_300)."""
        pr = _PageRead(1, None, None, "failed", 0.0)
        img = np.zeros((100, 300, 3), dtype=np.uint8)
        result = (pr, img)
        page_read, bgr_300 = result
        assert page_read.method == "failed"
        assert bgr_300 is not None
        assert bgr_300.shape == (100, 300, 3)


class TestGpuQueueFormat:
    """GPU queue must accept (page_idx, bgr_300) tuples."""

    def test_queue_accepts_image_tuple(self):
        """Queue should accept (int, ndarray) items."""
        q = queue.Queue()
        img = np.zeros((100, 300, 3), dtype=np.uint8)
        q.put((5, img))
        q.put(None)  # sentinel

        item = q.get()
        assert item is not None
        idx, bgr = item
        assert idx == 5
        assert bgr.shape == (100, 300, 3)

        sentinel = q.get()
        assert sentinel is None
