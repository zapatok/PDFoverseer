"""Tests for VLM sweep utilities."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from vlm.sweep import lhs_sample, adjacent_configs, rank_key
from vlm.params import PARAM_SPACE


def test_lhs_sample_count():
    configs = lhs_sample(10)
    assert len(configs) == 10


def test_lhs_sample_deterministic():
    a = lhs_sample(10, seed=42)
    b = lhs_sample(10, seed=42)
    assert a == b


def test_lhs_sample_different_seeds():
    a = lhs_sample(10, seed=42)
    b = lhs_sample(10, seed=99)
    assert a != b


def test_lhs_sample_valid_values():
    configs = lhs_sample(20)
    for cfg in configs:
        for k, v in cfg.items():
            assert v in PARAM_SPACE[k], f"{k}={v} not in PARAM_SPACE"


def test_adjacent_configs_shifts_one_param():
    base = {k: vals[1] for k, vals in PARAM_SPACE.items()}  # middle values
    adjs = adjacent_configs(base)
    for adj in adjs:
        diffs = [k for k in base if adj[k] != base[k]]
        assert len(diffs) == 1, f"Expected 1 diff, got {diffs}"


def test_adjacent_configs_stays_in_bounds():
    # Use first values — can only shift right
    base = {k: vals[0] for k, vals in PARAM_SPACE.items()}
    adjs = adjacent_configs(base)
    for adj in adjs:
        for k, v in adj.items():
            assert v in PARAM_SPACE[k]


def test_rank_key_ordering():
    better = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 300}
    worse = {"exact_match": 0.5, "curr_match": 0.7, "mean_latency_ms": 200}
    assert rank_key(better) < rank_key(worse)  # better sorts first


def test_rank_key_tiebreak_by_curr():
    a = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 300}
    b = {"exact_match": 0.8, "curr_match": 0.7, "mean_latency_ms": 300}
    assert rank_key(a) < rank_key(b)


def test_rank_key_tiebreak_by_latency():
    a = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 200}
    b = {"exact_match": 0.8, "curr_match": 0.9, "mean_latency_ms": 500}
    assert rank_key(a) < rank_key(b)
