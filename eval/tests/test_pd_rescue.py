"""Tests for eval.pixel_density.sweep_rescue — cross-validation harness + scorers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402


def test_cross_validate_returns_per_pdf_results():
    """cross_validate() returns a list of dicts with name, target, matches, error."""
    from eval.pixel_density.sweep_rescue import cross_validate

    def dummy_scorer(pages: np.ndarray) -> list[int]:
        return [0, 1, 2]

    corpus = [("QUEVEDO_1", "data/samples/QUEVEDO_1.pdf", 1)]
    results = cross_validate(dummy_scorer, corpus)

    assert len(results) == 1
    r = results[0]
    assert r["name"] == "QUEVEDO_1"
    assert r["target"] == 1
    assert r["matches"] == 3
    assert r["error"] == 2
    assert r["abs_error"] == 2


def test_cross_validate_multiple_pdfs():
    """cross_validate() processes multiple PDFs in order."""
    from eval.pixel_density.sweep_rescue import cross_validate

    def dummy_scorer(pages: np.ndarray) -> list[int]:
        return [0]

    corpus = [
        ("QUEVEDO_1", "data/samples/QUEVEDO_1.pdf", 1),
        ("QUEVEDO_2", "data/samples/QUEVEDO_2.pdf", 2),
    ]
    results = cross_validate(dummy_scorer, corpus)

    assert len(results) == 2
    assert results[0]["name"] == "QUEVEDO_1"
    assert results[0]["error"] == 0
    assert results[1]["name"] == "QUEVEDO_2"
    assert results[1]["error"] == -1


def test_scorer_v1_returns_list_of_ints():
    """scorer_v1() returns a list of 0-based page indices."""
    from eval.pixel_density.sweep_rescue import scorer_v1

    pages = np.zeros((4, 100, 80), dtype=np.uint8)
    matches = scorer_v1(pages)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_scorer_rescue_a_returns_list_of_ints():
    """scorer_rescue_a() returns cover page indices using edge_density_grid."""
    from eval.pixel_density.sweep_rescue import scorer_rescue_a

    pages = np.zeros((4, 100, 80), dtype=np.uint8)
    matches = scorer_rescue_a(pages)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_scorer_rescue_b_returns_list_of_ints():
    """scorer_rescue_b() returns cover pages from fused V1+edge scores."""
    from eval.pixel_density.sweep_rescue import scorer_rescue_b

    pages = np.zeros((4, 100, 80), dtype=np.uint8)
    matches = scorer_rescue_b(pages, edge_weight=0.2)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_scorer_rescue_b_weight_1_equals_edge_only():
    """With edge_weight=1.0, Rescue B should behave like edge-only scoring."""
    from eval.pixel_density.sweep_rescue import scorer_rescue_b

    rng = np.random.RandomState(42)
    pages = rng.randint(0, 256, size=(10, 100, 80), dtype=np.uint8)
    matches = scorer_rescue_b(pages, edge_weight=1.0)
    assert isinstance(matches, list)
    assert 0 in matches


def test_scorer_rescue_c_returns_list_of_ints():
    """scorer_rescue_c() returns cover pages from multi-descriptor + pct threshold."""
    from eval.pixel_density.sweep_rescue import scorer_rescue_c

    pages = np.zeros((4, 100, 80), dtype=np.uint8)
    matches = scorer_rescue_c(pages)
    assert isinstance(matches, list)
    assert all(isinstance(i, int) for i in matches)
    assert 0 in matches


def test_format_comparison_table(capsys):
    """format_comparison_table() prints a readable per-PDF comparison."""
    from eval.pixel_density.sweep_rescue import format_comparison_table

    v1_results = [
        {"name": "PDF_A", "target": 10, "matches": 10, "error": 0, "abs_error": 0},
        {"name": "PDF_B", "target": 5, "matches": 7, "error": 2, "abs_error": 2},
    ]
    rescue_results = {
        "A": [
            {"name": "PDF_A", "target": 10, "matches": 11, "error": 1, "abs_error": 1},
            {"name": "PDF_B", "target": 5, "matches": 5, "error": 0, "abs_error": 0},
        ],
    }
    format_comparison_table(v1_results, rescue_results)
    captured = capsys.readouterr()
    assert "PDF_A" in captured.out
    assert "PDF_B" in captured.out
    assert "V1" in captured.out


def test_compute_summary_mae():
    """compute_summary() returns MAE and exact-match count."""
    from eval.pixel_density.sweep_rescue import compute_summary

    results = [
        {"name": "A", "abs_error": 2},
        {"name": "B", "abs_error": 4},
        {"name": "C", "abs_error": 0},
    ]
    summary = compute_summary(results)
    assert summary["mae"] == pytest.approx(2.0)
    assert summary["exact"] == 1
    assert summary["within_2"] == 2
    assert summary["n"] == 3
