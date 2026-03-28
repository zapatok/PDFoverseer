# eval/graph_sweep.py
"""
Parameter sweep for the graph inference engine (HMM + Viterbi).

Reuses the 3-pass sweep structure and scoring from eval/sweep.py,
but runs eval/graph_inference.run_pipeline instead.

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/graph_sweep.py
    # -> writes eval/results/graph_sweep_YYYYMMDD_HHMMSS.json
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.graph_inference import PageRead, run_pipeline
from eval.graph_params import GRAPH_DEFAULT_PARAMS, GRAPH_PARAM_SPACE

FIXTURES_DIR = Path("eval/fixtures")
GROUND_TRUTH_PATH = Path("eval/ground_truth.json")
RESULTS_DIR = Path("eval/results")
TOP_N = 10
LHS_SAMPLES = 500
PASS2_TOP_N = 20
BEAM_TOP_N = 5
RANDOM_SEED = 42


# -- Fixture loading ----------------------------------------------------------

def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if "archived" in path.parts:
            continue
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures


def load_ground_truth() -> dict[str, dict]:
    return json.loads(GROUND_TRUTH_PATH.read_text())


# -- Scoring (mirrored from sweep.py, uses graph run_pipeline) ----------------

def score_config(params: dict, fixtures: list[dict], gt: dict[str, dict],
                 baseline_passes: set[str]) -> dict:
    doc_exact = complete_exact = inf_delta = regressions = 0
    real_doc_delta = syn_doc_delta = 0
    fixture_results = {}

    for fx in fixtures:
        name = fx["name"]
        if name not in gt:
            continue
        truth = gt[name]
        is_real = fx.get("source", "synthetic") == "real"
        docs = run_pipeline(fx["reads"], params)

        got_docs     = len(docs)
        got_complete = sum(1 for d in docs if d.is_complete)
        got_inferred = sum(len(d.inferred_pages) for d in docs)

        d_doc = abs(got_docs - truth["doc_count"])

        if is_real:
            passed = (d_doc == 0)
            if d_doc == 0:
                doc_exact += 5
            else:
                real_doc_delta += d_doc
        else:
            d_comp = (got_docs == truth["doc_count"]
                      and got_complete == truth["complete_count"])
            d_inf = abs(got_inferred - truth["inferred_count"])
            passed = (d_doc == 0 and d_comp)
            if d_doc == 0:
                doc_exact += 3
            if d_comp:
                complete_exact += 2
            syn_doc_delta += d_doc
            inf_delta += d_inf

        if name in baseline_passes and not passed:
            regressions += 1

        fixture_results[name] = "pass" if passed else "fail"

    composite = (doc_exact + complete_exact
                 - real_doc_delta * 3
                 - syn_doc_delta
                 - inf_delta
                 - regressions * 5)
    return {
        "doc_count_exact":      doc_exact,
        "doc_count_delta":      real_doc_delta + syn_doc_delta,
        "complete_count_exact": complete_exact,
        "inferred_delta":       inf_delta,
        "regression_count":     regressions,
        "composite_score":      composite,
        "_fixture_results":     fixture_results,
    }


# -- Latin Hypercube Sample ---------------------------------------------------

def lhs_sample(n: int, seed: int = RANDOM_SEED) -> list[dict]:
    rng = random.Random(seed)
    keys = list(GRAPH_PARAM_SPACE.keys())
    indices_per_param: dict[str, list[int]] = {}
    for k, vals in GRAPH_PARAM_SPACE.items():
        m = len(vals)
        slots = [rng.randint(0, m - 1) for _ in range(n)]
        rng.shuffle(slots)
        indices_per_param[k] = slots
    configs = []
    for i in range(n):
        cfg = {k: GRAPH_PARAM_SPACE[k][indices_per_param[k][i]] for k in keys}
        configs.append(cfg)
    return configs


# -- Fine grid (adjacent step) ------------------------------------------------

def adjacent_configs(base: dict) -> list[dict]:
    configs = []
    for k, vals in GRAPH_PARAM_SPACE.items():
        idx = vals.index(base[k])
        for new_idx in [idx - 1, idx + 1]:
            if 0 <= new_idx < len(vals):
                cfg = dict(base)
                cfg[k] = vals[new_idx]
                configs.append(cfg)
    return configs


# -- Sweep runner -------------------------------------------------------------

def run_sweep(fixtures: list[dict], gt: dict) -> dict:
    SYNTHETIC_NAMES = {"ins31_gap", "undercount_chain", "ambiguous_start",
                       "noisy_period", "seq_break", "ds_conflict"}
    active_gt = {k: v for k, v in gt.items()
                 if k in SYNTHETIC_NAMES or v["doc_count"] > 0}
    active_fixtures = [fx for fx in fixtures if fx["name"] in active_gt]

    print("Scoring baseline (graph default params)...")
    baseline_result = score_config(GRAPH_DEFAULT_PARAMS, active_fixtures, active_gt, set())
    baseline_passes = {
        name for name, res in baseline_result["_fixture_results"].items()
        if res == "pass"
    }
    print(f"  baseline composite={baseline_result['composite_score']} "
          f"doc_exact={baseline_result['doc_count_exact']} "
          f"passes={len(baseline_passes)}/{len(active_fixtures)}")

    def run_configs(configs: list[dict], label: str) -> list[tuple[dict, dict]]:
        results = []
        for i, cfg in enumerate(configs):
            s = score_config(cfg, active_fixtures, active_gt, baseline_passes)
            results.append((cfg, s))
            if (i + 1) % 50 == 0:
                print(f"  {label}: {i+1}/{len(configs)}", end="\r")
        print(f"  {label}: {len(configs)}/{len(configs)} done")
        return results

    def top_k(results: list[tuple[dict, dict]], k: int) -> list[tuple[dict, dict]]:
        return sorted(results, key=lambda x: (
            -x[1]["composite_score"], x[1]["doc_count_delta"]
        ))[:k]

    # Pass 1: LHS
    print(f"\nPass 1: Latin Hypercube Sample ({LHS_SAMPLES} configs)...")
    p1_configs = lhs_sample(LHS_SAMPLES)
    p1_results = run_configs(p1_configs, "Pass1")
    top20 = top_k(p1_results, PASS2_TOP_N)

    # Pass 2: Fine grid
    print(f"\nPass 2: Fine grid around top-{PASS2_TOP_N}...")
    p2_configs_set: list[dict] = []
    seen = set()
    for cfg, _ in top20:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen:
                seen.add(key)
                p2_configs_set.append(adj)
    p2_results = run_configs(p2_configs_set, "Pass2")
    top5 = top_k(p1_results + p2_results, BEAM_TOP_N)

    # Pass 3: Beam search
    print(f"\nPass 3: Beam search from top-{BEAM_TOP_N}...")
    p3_configs: list[dict] = []
    seen3 = set()
    for cfg, _ in top5:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen3:
                seen3.add(key)
                p3_configs.append(adj)
    p3_results = run_configs(p3_configs, "Pass3")

    # Final ranking
    all_results = p1_results + p2_results + p3_results
    ranked = top_k(all_results, TOP_N)

    top_configs = []
    for rank, (cfg, scores) in enumerate(ranked, 1):
        top_configs.append({
            "rank": rank,
            "params": cfg,
            "scores": {k: v for k, v in scores.items() if not k.startswith("_")},
            "fixture_breakdown": scores["_fixture_results"],
        })

    baseline_summary = {k: v for k, v in baseline_result.items() if not k.startswith("_")}
    baseline_summary["fixture_breakdown"] = baseline_result["_fixture_results"]

    return {
        "engine": "graph-hmm-viterbi",
        "run_at": datetime.now().isoformat(),
        "fixtures_count": len(active_fixtures),
        "total_configs_tested": len(all_results),
        "baseline": baseline_summary,
        "top_configs": top_configs,
    }


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = load_fixtures()
    gt = load_ground_truth()
    print(f"Loaded {len(fixtures)} fixtures, {len(gt)} ground truth entries")

    result = run_sweep(fixtures, gt)

    out_path = RESULTS_DIR / f"graph_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResults saved to {out_path}")
    if result["top_configs"]:
        print(f"Top config: composite={result['top_configs'][0]['scores']['composite_score']}"
              f" regressions={result['top_configs'][0]['scores']['regression_count']}")


if __name__ == "__main__":
    main()
