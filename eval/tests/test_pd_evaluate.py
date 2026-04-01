"""Tests for eval.pixel_density.evaluate — shared GT loading + metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest  # noqa: E402

# ── load_art674_gt ───────────────────────────────────────────────────────────


def test_load_art674_gt_returns_set_of_ints():
    from eval.pixel_density.evaluate import load_art674_gt

    covers = load_art674_gt()
    assert isinstance(covers, set)
    assert all(isinstance(i, int) for i in covers)


def test_load_art674_gt_count_is_674():
    from eval.pixel_density.evaluate import load_art674_gt

    covers = load_art674_gt()
    assert len(covers) == 674


def test_load_art674_gt_zero_based():
    """Page indices are 0-based (VLM fixture is 1-based, converted on load)."""
    from eval.pixel_density.evaluate import load_art674_gt

    covers = load_art674_gt()
    assert 0 in covers  # first page is always a cover
    assert all(i >= 0 for i in covers)


# ── compute_metrics ──────────────────────────────────────────────────────────


def test_compute_metrics_perfect():
    from eval.pixel_density.evaluate import compute_metrics

    gt = {0, 4, 8}
    result = compute_metrics(matches=[0, 4, 8], gt_covers=gt, target=3)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["error"] == 0
    assert result["tp"] == 3
    assert result["fp"] == 0
    assert result["fn"] == 0


def test_compute_metrics_with_fp_and_fn():
    from eval.pixel_density.evaluate import compute_metrics

    gt = {0, 4, 8}
    result = compute_metrics(matches=[0, 4, 5], gt_covers=gt, target=3)
    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["error"] == 0  # 3 matches, target 3
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)


def test_compute_metrics_empty_matches():
    from eval.pixel_density.evaluate import compute_metrics

    gt = {0, 4, 8}
    result = compute_metrics(matches=[], gt_covers=gt, target=3)
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0
    assert result["fn"] == 3


def test_compute_metrics_tess_only_recovered():
    from eval.pixel_density.evaluate import compute_metrics

    gt = {0, 4, 8}
    tess_only = {4, 8}  # pages only Tesseract finds
    result = compute_metrics(
        matches=[0, 4], gt_covers=gt, target=3, tess_only_pages=tess_only,
    )
    assert result["tess_only_recovered"] == 1  # page 4


def test_compute_metrics_count_only():
    from eval.pixel_density.evaluate import compute_metrics_count_only

    result = compute_metrics_count_only(matches=[0, 1, 2, 3, 4], target=3)
    assert result["matches"] == 5
    assert result["error"] == 2
    assert result["abs_error"] == 2


# ── load_tess_only_pages ─────────────────────────────────────────────────────


def test_load_tess_only_pages_returns_set():
    from eval.pixel_density.evaluate import load_tess_only_pages

    pages = load_tess_only_pages()
    assert isinstance(pages, set)
    assert all(isinstance(i, int) for i in pages)
    # Should be non-empty (we know there are 31 TESS-ONLY pages)
    assert len(pages) > 0


# ── report_table ─────────────────────────────────────────────────────────────


def test_report_table_does_not_crash(capsys):
    from eval.pixel_density.evaluate import report_table

    results = [
        {
            "params": {"bins": 32},
            "f1": 0.93,
            "precision": 0.94,
            "recall": 0.92,
            "matches": 672,
            "error": -2,
            "tp": 620,
            "fp": 52,
            "fn": 54,
            "tess_only_recovered": 3,
        },
    ]
    report_table(results, sort_key="f1", top_n=5)
    captured = capsys.readouterr()
    assert "0.93" in captured.out


# ── save_results ─────────────────────────────────────────────────────────────


def test_save_results_writes_json(tmp_path):
    from eval.pixel_density.evaluate import save_results

    results = {"sweep": "test", "results": [{"f1": 0.9}]}
    path = tmp_path / "out.json"
    save_results(results, path)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["sweep"] == "test"
