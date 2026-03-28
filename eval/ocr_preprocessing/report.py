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

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.ocr_preprocessing.params import OCR_PRODUCTION_PARAMS, OCR_TIER1_PARAMS  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"


def find_latest(tier1: bool = False, mini: bool = False) -> Path | None:
    if mini:
        pattern = "ocr_mini_sweep_*.json"
    elif tier1:
        pattern = "ocr_tier1_sweep_*.json"
    else:
        pattern = "ocr_sweep_*.json"
    files = sorted(RESULTS_DIR.glob(pattern))
    return files[-1] if files else None


def print_report(data: dict) -> None:
    mode = data.get("mode", "")
    is_tier1 = mode.startswith("tier1") or mode == "mini"
    baseline_params = OCR_TIER1_PARAMS if is_tier1 else OCR_PRODUCTION_PARAMS
    label = "tier1" if is_tier1 else "production"

    print("=" * 72)
    print("OCR Sweep Report" + (" [tier1 mode]" if is_tier1 else ""))
    print(f"  Run: {data['run_at']}")
    print(f"  Mode: {data.get('mode', 'full')}")
    print(f"  Failed pages: {data['total_failed_pages']}")
    print(f"  Success sample: {data['success_sample_size']}")
    print(f"  Configs tested: {data['configs_tested']}")
    print()

    bl_f = data["baseline_failed"]
    bl_s = data["baseline_success"]
    print(f"  Baseline ({label}): rescued={bl_f['rescued']}, "
          f"regression={bl_s['regressed']}/{data['success_sample_size']}")
    print("=" * 72)

    print(f"\n{'Rank':>4} {'Rescued':>8} {'Regressed':>10} {'NetGain':>8}  "
          f"{'Diff from ' + label}")
    print("-" * 72)

    for i, entry in enumerate(data["top_configs"], 1):
        pa = entry["phase_a"]
        pb = entry["phase_b"]
        label = entry.get("label", "")
        diff = {k: v for k, v in entry["params"].items()
                if v != baseline_params.get(k)}
        diff_str = ", ".join(f"{k}={v}" for k, v in sorted(diff.items()))
        name = f"{label}: {diff_str}" if label else diff_str
        print(f"{i:>4} {pa['rescued']:>8} {pb['regressed']:>10} "
              f"{entry['net_gain']:>8}  {name}")

    if data["top_configs"]:
        print("\nBest config rescued pages:")
        best = data["top_configs"][0]
        for p in best.get("rescued_pages", [])[:20]:
            print(f"  {p}")
        remaining = len(best.get("rescued_pages", [])) - 20
        if remaining > 0:
            print(f"  ... and {remaining} more")


def main():
    tier1 = "--tier1" in sys.argv
    mini  = "--mini"  in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        path = Path(args[0])
    else:
        path = find_latest(tier1=tier1, mini=mini)
        if not path:
            label = "mini" if mini else ("tier1" if tier1 else "ocr")
            print(f"No {label} sweep results found in eval/results/")
            sys.exit(1)

    data = json.loads(path.read_text())
    print_report(data)


if __name__ == "__main__":
    main()
