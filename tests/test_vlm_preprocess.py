"""Tests for VLM image preprocessing."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import numpy as np
import pytest
from vlm.preprocess import apply_preprocess


@pytest.fixture
def color_image():
    """A 100x100 color image with some variation."""
    img = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    return img


def test_preprocess_none(color_image):
    result = apply_preprocess(color_image, mode="none", upscale=1.0)
    assert result.shape == color_image.shape
    assert np.array_equal(result, color_image)


def test_preprocess_grayscale(color_image):
    result = apply_preprocess(color_image, mode="grayscale", upscale=1.0)
    # Grayscale converted back to 3-channel for Ollama
    assert result.shape[0] == 100
    assert result.shape[1] == 100


def test_preprocess_otsu(color_image):
    result = apply_preprocess(color_image, mode="otsu", upscale=1.0)
    assert result.shape[0] == 100
    assert result.shape[1] == 100
    # Otsu produces binary image — only 0 and 255
    unique = np.unique(result)
    assert len(unique) <= 2


def test_preprocess_contrast(color_image):
    result = apply_preprocess(color_image, mode="contrast", upscale=1.0)
    assert result.shape[0] == 100
    assert result.shape[1] == 100


def test_preprocess_upscale(color_image):
    result = apply_preprocess(color_image, mode="none", upscale=2.0)
    assert result.shape[0] == 200
    assert result.shape[1] == 200


def test_preprocess_upscale_with_mode(color_image):
    result = apply_preprocess(color_image, mode="grayscale", upscale=1.5)
    assert result.shape[0] == 150
    assert result.shape[1] == 150


def test_preprocess_invalid_mode(color_image):
    with pytest.raises(ValueError, match="Unknown preprocess mode"):
        apply_preprocess(color_image, mode="invalid", upscale=1.0)
