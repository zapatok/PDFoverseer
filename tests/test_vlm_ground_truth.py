"""Tests for VLM ground truth loader."""
import csv
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from vlm.ground_truth import load_ground_truth, load_corpus, CorpusEntry

OCR_ALL_DIR = "data/ocr_all"
ALL_INDEX = f"{OCR_ALL_DIR}/all_index.csv"
FIXTURES_DIR = "eval/fixtures/real"


def test_load_ground_truth_returns_dict():
    gt = load_ground_truth()
    assert isinstance(gt, dict)
    assert len(gt) > 0
    # Keys are (nickname, page_num) tuples
    key = next(iter(gt))
    assert isinstance(key, tuple)
    assert len(key) == 2


def test_ground_truth_values_are_curr_total():
    gt = load_ground_truth()
    for key, val in list(gt.items())[:20]:
        nickname, page_num = key
        curr, total = val
        assert isinstance(curr, int)
        assert isinstance(total, int)
        assert 1 <= curr <= total


def test_ground_truth_excludes_inferred():
    """Ground truth should only include direct/super_resolution/easyocr methods."""
    gt = load_ground_truth()
    # CH_9 page 1 has tier1_parsed="1/2" → should be in GT
    assert ("CH_9", 1) in gt
    assert gt[("CH_9", 1)] == (1, 2)


def test_load_corpus_failures_only():
    entries = load_corpus(failures_only=True)
    assert len(entries) > 0
    for e in entries:
        assert isinstance(e, CorpusEntry)
        assert e.tier1_parsed == ""
        assert e.tier2_parsed == ""


def test_load_corpus_full():
    entries = load_corpus(failures_only=False)
    assert len(entries) > len(load_corpus(failures_only=True))


def test_load_corpus_sample():
    full = load_corpus(failures_only=True)
    sample = load_corpus(failures_only=True, sample_n=20, seed=42)
    assert len(sample) == 20
    # All sampled entries should be from the failures set
    for e in sample:
        assert e.tier1_parsed == ""
        assert e.tier2_parsed == ""
