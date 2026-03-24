# eval/ocr_report.py
"""
Print ranked results from an OCR preprocessing sweep JSON file.

Usage:
    python eval/ocr_report.py                          # latest result
    python eval/ocr_report.py eval/results/ocr_sweep_*.json  # specific file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.ocr_params import OCR_PRODUCTION_PARAMS

RESULTS_DIR = Path(__file__).parent / "results"


def find_latest() -> Path | None:
    files = sorted(RESULTS_DIR.glob("ocr_sweep_*.json"))
    return files[-1] if files else None


def print_report(data: dict) -> None:
    print("=" * 72)
    print("OCR Preprocessing Sweep Report")
    print(f"  Run: {data['run_at']}")
    print(f"  Failed pages: {data['total_failed_pages']}")
    print(f"  Success sample: {data['success_sample_size']}")
    print(f"  Configs tested: {data['configs_tested']}")
    print()

    bl_f = data["baseline_failed"]
    bl_s = data["baseline_success"]
    print(f"  Baseline (production): rescued={bl_f['rescued']}, "
          f"regression={bl_s['regressed']}/{data['success_sample_size']}")
    print("=" * 72)

    print(f"\n{'Rank':>4} {'Rescued':>8} {'Regressed':>10} {'NetGain':>8}  "
          f"{'Diff from production'}")
    print("-" * 72)

    for i, entry in enumerate(data["top_configs"], 1):
        pa = entry["phase_a"]
        pb = entry["phase_b"]
        diff = {k: v for k, v in entry["params"].items()
                if v != OCR_PRODUCTION_PARAMS.get(k)}
        diff_str = ", ".join(f"{k}={v}" for k, v in sorted(diff.items()))
        print(f"{i:>4} {pa['rescued']:>8} {pb['regressed']:>10} "
              f"{entry['net_gain']:>8}  {diff_str}")

    if data["top_configs"]:
        print(f"\nBest config rescued pages:")
        best = data["top_configs"][0]
        for p in best.get("rescued_pages", [])[:20]:
            print(f"  {p}")
        remaining = len(best.get("rescued_pages", [])) - 20
        if remaining > 0:
            print(f"  ... and {remaining} more")


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = find_latest()
        if not path:
            print("No sweep results found in eval/results/")
            sys.exit(1)

    data = json.loads(path.read_text())
    print_report(data)


if __name__ == "__main__":
    main()
