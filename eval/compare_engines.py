"""
Compare three inference engines on all active fixtures.

Engines:
    existing  — eval/inference.py      (multi-phase + D-S)
    graph     — eval/graph_inference.py (pure HMM+Viterbi)
    hybrid    — eval/hybrid_inference.py (phases 0-6 → Viterbi)

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/compare_engines.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.graph_inference import run_pipeline as run_graph
from eval.hybrid_inference import run_pipeline as run_hybrid
from eval.inference import PageRead
from eval.inference import run_pipeline as run_existing

FIXTURES_DIR      = Path("eval/fixtures")
GROUND_TRUTH_PATH = Path("eval/ground_truth.json")

SYNTHETIC_NAMES = {
    "ins31_gap", "undercount_chain", "ambiguous_start",
    "noisy_period", "seq_break", "ds_conflict",
}

# ── Best known params ─────────────────────────────────────────────────────────

# Best existing engine params (composite=139, sweep_20260323_195204.json rank-1)
BEST_EXISTING = {
    "fwd_conf": 1.0, "new_doc_base": 0.6, "new_doc_hom_mul": 0.25,
    "back_conf": 0.85, "xval_cap": 0.5,
    "ds_period_weight": 0.1, "ds_neighbor_weight": 0.08,
    "ds_prior_weight": 0.09, "ds_boost_max": 0.2,
    "ph5b_conf_min": 0.65, "ph5b_ratio_min": 0.93,
    "min_conf_for_new_doc": 0.7, "anomaly_dropout": 0.0,
    "clash_w_local": 1.5, "clash_w_period": 3.0,
    "phase4_conf": 0.1, "clash_boundary_pen": 2.0,
    "window": 9, "hom_threshold": 0.8,
}

# Best graph (HMM-only) params (composite=85, graph_sweep_20260323_211859.json rank-1)
BEST_GRAPH = {
    "trans_continue": 0.95, "trans_new_doc": 0.05, "trans_skip": 0.01,
    "emit_match": 0.9, "emit_conf_scale": 1.0, "emit_partial": 0.1,
    "emit_null": 0.5, "max_total": 20, "boundary_bonus": 2.0, "period_prior": 0.5,
}

# Hybrid: merged (key sets are disjoint)
BEST_HYBRID = {**BEST_EXISTING, **BEST_GRAPH}


# ── Fixture loading ───────────────────────────────────────────────────────────

def load_fixtures():
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if "archived" in path.parts:
            continue
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures


def load_ground_truth():
    return json.loads(GROUND_TRUTH_PATH.read_text())


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_all(run_fn, params, fixtures, gt):
    """Returns {fixture_name: "pass"/"fail"} and aggregate scores."""
    doc_exact = complete_exact = inf_delta = 0
    real_doc_delta = syn_doc_delta = 0
    results = {}

    for fx in fixtures:
        name = fx["name"]
        if name not in gt:
            continue
        truth = gt[name]
        is_real = fx.get("source", "synthetic") == "real"
        docs = run_fn(fx["reads"], params)

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
            if got_complete >= truth["complete_count"]:
                complete_exact += 2
        else:
            d_comp = (got_docs == truth["doc_count"]
                      and got_complete == truth["complete_count"])
            d_inf  = abs(got_inferred - truth["inferred_count"])
            passed = (d_doc == 0 and d_comp)
            if d_doc == 0:
                doc_exact += 3
            if d_comp:
                complete_exact += 2
            syn_doc_delta += d_doc
            inf_delta += d_inf

        results[name] = "pass" if passed else "fail"

    composite = (doc_exact + complete_exact
                 - real_doc_delta * 3
                 - syn_doc_delta
                 - inf_delta)
    passes = sum(1 for v in results.values() if v == "pass")
    return results, composite, passes


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    fixtures = load_fixtures()
    gt = load_ground_truth()
    active_gt = {k: v for k, v in gt.items()
                 if k in SYNTHETIC_NAMES or v["doc_count"] > 0}
    active_fixtures = [fx for fx in fixtures if fx["name"] in active_gt]
    n = len(active_fixtures)
    print(f"Loaded {len(fixtures)} fixtures, {n} active\n")

    print("Scoring existing engine...")
    ex_bd, ex_comp, ex_p = score_all(run_existing, BEST_EXISTING, active_fixtures, active_gt)

    print("Scoring graph (HMM-only) engine...")
    gr_bd, gr_comp, gr_p = score_all(run_graph, BEST_GRAPH, active_fixtures, active_gt)

    print("Scoring hybrid engine (phases 0-6 + Viterbi)...")
    hy_bd, hy_comp, hy_p = score_all(run_hybrid, BEST_HYBRID, active_fixtures, active_gt)

    all_fx = sorted(set(ex_bd) | set(gr_bd) | set(hy_bd))

    print(f"\n{'Fixture':<30} {'Existing':>8} {'Graph':>7} {'Hybrid':>7}  Notes")
    print("-" * 72)
    for fx in all_fx:
        e = ex_bd.get(fx, "?")
        g = gr_bd.get(fx, "?")
        h = hy_bd.get(fx, "?")
        note = ""
        if h == "pass" and e == "fail":
            note = "<< HY gains"
        elif h == "fail" and e == "pass":
            note = ">> HY loses"
        print(f"{fx:<30} {e:>8} {g:>7} {h:>7}  {note}")

    print("-" * 72)
    print(f"{'PASSES':<30} {ex_p:>8} {gr_p:>7} {hy_p:>7}")
    print()
    print(f"Composite — existing: {ex_comp:>5}   graph: {gr_comp:>5}   hybrid: {hy_comp:>5}")
    print()

    gains = [fx for fx in all_fx if hy_bd.get(fx) == "pass" and ex_bd.get(fx) == "fail"]
    losses = [fx for fx in all_fx if hy_bd.get(fx) == "fail" and ex_bd.get(fx) == "pass"]
    if gains:
        print(f"Hybrid GAINS vs existing: {gains}")
    if losses:
        print(f"Hybrid LOSES vs existing: {losses}")
    if not gains and not losses:
        print("Hybrid result identical to existing.")


if __name__ == "__main__":
    main()
