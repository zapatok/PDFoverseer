"""Tests for VLM benchmark runner."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import pytest

from vlm.benchmark import compute_metrics, run


def test_compute_metrics_perfect():
    results = [
        {"parsed": (1, 3), "ground_truth": (1, 3), "latency_ms": 200.0},
        {"parsed": (2, 3), "ground_truth": (2, 3), "latency_ms": 300.0},
        {"parsed": (3, 3), "ground_truth": (3, 3), "latency_ms": 250.0},
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == 1.0
    assert m["curr_match"] == 1.0
    assert m["parse_rate"] == 1.0
    assert m["mean_latency_ms"] == pytest.approx(250.0)


def test_compute_metrics_partial():
    results = [
        {"parsed": (1, 3), "ground_truth": (1, 3), "latency_ms": 200.0},
        {"parsed": (2, 5), "ground_truth": (2, 3), "latency_ms": 300.0},  # curr OK, total wrong
        {"parsed": None, "ground_truth": (3, 3), "latency_ms": 250.0},     # parse failed
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == pytest.approx(1 / 3)
    assert m["curr_match"] == pytest.approx(2 / 3)
    assert m["parse_rate"] == pytest.approx(2 / 3)


def test_compute_metrics_no_ground_truth():
    """Pages without ground truth count for parse_rate but not accuracy."""
    results = [
        {"parsed": (1, 3), "ground_truth": None, "latency_ms": 200.0},
        {"parsed": (2, 3), "ground_truth": (2, 3), "latency_ms": 300.0},
    ]
    m = compute_metrics(results)
    assert m["exact_match"] == 1.0  # 1/1 with GT
    assert m["parse_rate"] == 1.0   # 2/2 parsed


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["exact_match"] == 0.0
    assert m["parse_rate"] == 0.0
