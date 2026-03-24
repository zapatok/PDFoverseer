# vlm/report.py
"""Print ranked results from VLM sweep.

Usage:
    python -m vlm.report                           # latest summary
    python -m vlm.report vlm/results/sweep_X.json  # specific file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path("vlm/results")


def load_result(path: Path | None = None) -> dict:
    if path is None:
        candidates = sorted(RESULTS_DIR.glob("sweep_*_summary.json"))
        if not candidates:
            print("No sweep results found in vlm/results/")
            sys.exit(1)
        path = candidates[-1]
    print(f"Report for: {path}\n")
    return json.loads(path.read_text())


def print_report(result: dict) -> None:
    total = result["total_configs_tested"]
    sample = result.get("sample_n", "all")

    print(f"Sweep: {result['run_at']}  |  {total} configs  |  sample={sample}\n")
    print(f"{'Rank':>4}  {'exact':>7}  {'curr':>7}  {'parse':>7}  "
          f"{'lat_ms':>7}  {'p95_ms':>7}  {'pre':>10}  {'up':>4}  {'temp':>4}  {'top_p':>5}  prompt")
    print("-" * 110)

    for cfg_entry in result["top_configs"]:
        rank = cfg_entry["rank"]
        m = cfg_entry["metrics"]
        c = cfg_entry["config"]
        prompt_abbrev = c["prompt"][:40] + "..." if len(c["prompt"]) > 40 else c["prompt"]
        print(
            f"{rank:4d}  {m['exact_match']:6.1%}  {m['curr_match']:6.1%}  "
            f"{m['parse_rate']:6.1%}  {m['mean_latency_ms']:7.0f}  "
            f"{m['p95_latency_ms']:7.0f}  {c['preprocess']:>10}  "
            f"{c['upscale']:4.1f}  {c['temperature']:4.1f}  {c['top_p']:5.1f}  "
            f"{prompt_abbrev}"
        )
    print()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = load_result(path)
    print_report(result)


if __name__ == "__main__":
    main()
