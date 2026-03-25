"""3-pass parameter sweep for VLM OCR.

Pass 1: Latin Hypercube Sample — 80 configs
Pass 2: Fine grid around top-10 — adjacent index +/-1 per param
Pass 3: Beam search from top-3

Usage:
    python -m vlm.sweep
    python -m vlm.sweep --sample 50    # use 50-image subset per config
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

from vlm.benchmark import run, compute_metrics
from vlm.params import PARAM_SPACE

log = logging.getLogger(__name__)
RESULTS_DIR = Path("vlm/results")

LHS_SAMPLES = 30
PASS2_TOP_N = 10
BEAM_TOP_N = 3
RANDOM_SEED = 42


def lhs_sample(n: int, seed: int = RANDOM_SEED,
               param_space: dict | None = None) -> list[dict]:
    """Latin Hypercube Sample from parameter space."""
    space = param_space or PARAM_SPACE
    rng = random.Random(seed)
    keys = list(space.keys())
    indices_per_param: dict[str, list[int]] = {}
    for k, vals in space.items():
        m = len(vals)
        slots = [rng.randint(0, m - 1) for _ in range(n)]
        rng.shuffle(slots)
        indices_per_param[k] = slots

    configs = []
    for i in range(n):
        cfg = {k: space[k][indices_per_param[k][i]] for k in keys}
        configs.append(cfg)
    return configs


def adjacent_configs(base: dict, param_space: dict | None = None) -> list[dict]:
    """Generate configs with one parameter shifted +/-1 index."""
    space = param_space or PARAM_SPACE
    configs = []
    for k, vals in space.items():
        try:
            idx = vals.index(base[k])
        except ValueError:
            continue
        for new_idx in [idx - 1, idx + 1]:
            if 0 <= new_idx < len(vals):
                cfg = dict(base)
                cfg[k] = vals[new_idx]
                configs.append(cfg)
    return configs


def rank_key(metrics: dict) -> tuple:
    """Sort key: exact_match desc, curr_match desc, latency asc."""
    return (-metrics["exact_match"], -metrics["curr_match"], metrics["mean_latency_ms"])


def run_sweep(sample_n: int | None = None) -> dict:
    """Execute 3-pass sweep, saving results per config for crash resilience."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results: list[tuple[dict, dict]] = []  # (config, metrics)

    def run_configs(configs: list[dict], label: str) -> list[tuple[dict, dict]]:
        results = []
        for i, cfg in enumerate(configs):
            t0 = datetime.now()
            result = run(config=cfg, failures_only=True, sample_n=sample_n)
            metrics = result["metrics"]
            results.append((cfg, metrics))

            # Save per-config for crash resilience
            cfg_path = RESULTS_DIR / f"sweep_{ts}_config_{len(all_results) + len(results):04d}.json"
            cfg_path.write_text(json.dumps({
                "config": cfg, "metrics": metrics,
                "n_images": result["n_images"], "n_with_gt": result["n_with_gt"],
            }, indent=2))

            elapsed = (datetime.now() - t0).total_seconds()
            remaining = (len(configs) - i - 1) * elapsed
            log.info(
                "  %s %d/%d | exact=%.1f%% curr=%.1f%% parse=%.1f%% | %.0fs/cfg ETA %.0fm",
                label, i + 1, len(configs),
                metrics["exact_match"] * 100, metrics["curr_match"] * 100,
                metrics["parse_rate"] * 100, elapsed, remaining / 60,
            )
        return results

    def top_k(results: list[tuple[dict, dict]], k: int) -> list[tuple[dict, dict]]:
        return sorted(results, key=lambda x: rank_key(x[1]))[:k]

    # Pre-check: seed stability at temp=0
    # If 3 seeds give identical results, drop seed from sweep space
    log.info("Seed stability check (3 seeds x 20 images)...")
    seed_results = []
    for s in PARAM_SPACE["seed"]:
        cfg = {k: PARAM_SPACE[k][0] for k in PARAM_SPACE}
        cfg["seed"] = s
        cfg["temperature"] = 0.0
        r = run(config=cfg, failures_only=True, sample_n=20)
        seed_results.append(r["metrics"]["exact_match"])
    if len(set(seed_results)) == 1:
        log.info("  Seeds are stable at temp=0 — dropping seed from sweep space.")
        active_space = {k: v for k, v in PARAM_SPACE.items() if k != "seed"}
    else:
        log.info("  Seeds vary (results: %s) — keeping seed in sweep.", seed_results)
        active_space = PARAM_SPACE

    # Pass 1: LHS
    log.info("Pass 1: Latin Hypercube Sample (%d configs)...", LHS_SAMPLES)
    p1 = run_configs(lhs_sample(LHS_SAMPLES, param_space=active_space), "P1")
    all_results.extend(p1)
    top10 = top_k(all_results, PASS2_TOP_N)

    # Pass 2: Fine grid
    log.info("Pass 2: Fine grid around top-%d...", PASS2_TOP_N)
    p2_configs: list[dict] = []
    seen = set()
    for cfg, _ in top10:
        for adj in adjacent_configs(cfg, param_space=active_space):
            key = tuple(sorted(adj.items()))
            if key not in seen:
                seen.add(key)
                p2_configs.append(adj)
    p2 = run_configs(p2_configs, "P2")
    all_results.extend(p2)
    top3 = top_k(all_results, BEAM_TOP_N)

    # Pass 3: Beam search
    log.info("Pass 3: Beam search from top-%d...", BEAM_TOP_N)
    p3_configs: list[dict] = []
    seen3 = set()
    for cfg, _ in top3:
        for adj in adjacent_configs(cfg, param_space=active_space):
            key = tuple(sorted(adj.items()))
            if key not in seen3:
                seen3.add(key)
                p3_configs.append(adj)
    p3 = run_configs(p3_configs, "P3")
    all_results.extend(p3)

    # Final ranking
    ranked = top_k(all_results, 20)
    top_configs = []
    for rank, (cfg, metrics) in enumerate(ranked, 1):
        top_configs.append({"rank": rank, "config": cfg, "metrics": metrics})

    summary = {
        "run_at": datetime.now().isoformat(),
        "total_configs_tested": len(all_results),
        "sample_n": sample_n,
        "top_configs": top_configs,
    }
    summary_path = RESULTS_DIR / f"sweep_{ts}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Sweep complete. Summary: %s", summary_path)
    return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="VLM OCR Parameter Sweep")
    parser.add_argument("--sample", type=int, default=None,
                        help="Use N-image subset per config (faster iteration)")
    args = parser.parse_args()
    run_sweep(sample_n=args.sample)


if __name__ == "__main__":
    main()
