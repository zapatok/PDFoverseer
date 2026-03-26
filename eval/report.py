# eval/report.py
"""
Read the latest sweep result and print a human-readable ranked table.

Usage:
    python eval/report.py                              # latest result
    python eval/report.py eval/results/sweep_X.json   # specific file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path("eval/results")


def load_result(path: Path | None = None) -> dict:
    if path is None:
        candidates = sorted(RESULTS_DIR.glob("sweep_*.json"))
        if not candidates:
            print("No sweep results found in eval/results/")
            sys.exit(1)
        path = candidates[-1]
    print(f"Report for: {path}\n")
    return json.loads(path.read_text())


def fmt_scores(s: dict) -> str:
    return (f"score={s['composite_score']:+4d}  "
            f"doc_exact={s['doc_count_exact']:2d}  "
            f"doc_delta={s['doc_count_delta']:2d}  "
            f"com_exact={s['complete_count_exact']:2d}  "
            f"inf_delta={s['inferred_delta']:2d}  "
            f"reg={s['regression_count']}")


def print_report(result: dict) -> None:
    baseline = result["baseline"]
    top = result["top_configs"]
    total = result["total_configs_tested"]
    fixtures_n = result["fixtures_count"]

    print(f"Sweep: {result['run_at']}  |  {total} configs  |  {fixtures_n} fixtures\n")
    print(f"{'BASELINE':8s}  {fmt_scores(baseline)}")
    print("-" * 90)

    for cfg in top:
        rank = cfg["rank"]
        scores = cfg["scores"]
        params = cfg["params"]
        flag = "  *** REGRESSION ***" if scores["regression_count"] > 0 else ""
        print(f"Rank {rank:2d}  {fmt_scores(scores)}{flag}")

        from eval.params import PRODUCTION_PARAMS
        diffs = {k: v for k, v in params.items() if v != PRODUCTION_PARAMS.get(k)}
        if diffs:
            diff_str = "  ".join(f"{k}={v}" for k, v in diffs.items())
            print(f"         Dparams: {diff_str}")
        else:
            print("         Dparams: (same as production)")

        fails = [k for k, v in cfg.get("fixture_breakdown", {}).items() if v == "fail"]
        if fails:
            print(f"         fails:   {', '.join(fails)}")
        print()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = load_result(path)
    print_report(result)


if __name__ == "__main__":
    main()
