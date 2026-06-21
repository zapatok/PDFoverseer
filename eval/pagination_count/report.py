"""Render a Markdown comparison table from benchmark results.

Usage (from project root, with venv active)::

    python eval/pagination_count/report.py

Reads ``eval/pagination_count/results/benchmark.json`` and prints a Markdown
table to stdout.  Run ``benchmark.py`` first to generate the JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

_RESULTS_FILE = Path(__file__).parent / "results" / "benchmark.json"


def render_report(rows: list[dict]) -> str:
    """Render *rows* as a Markdown comparison table with per-sigla verdicts.

    The table columns are:
      sigla | pages | GT | current (Δ) | pagination (Δ) | recovered | source

    Below the per-sample table a per-sigla roll-up section shows a **verdict**:

    * ``MIGRATE`` — sum of ``|pag_delta|`` across that sigla's rows is **≤**
      sum of ``|current_delta|``: the new engine is at least as accurate as the
      production scanner.
    * ``KEEP`` — the production scanner wins or ties only because the new engine
      is strictly worse.

    Args:
        rows: List of result dicts as returned by ``run_benchmark``.

    Returns:
        A Markdown string (table + roll-up).
    """
    lines: list[str] = []

    # --- Per-sample table ---
    lines.append("## Per-sample results\n")
    header = "| sigla | pages | GT | current (Δ) | pagination (Δ) | recovered | source |"
    sep = "|-------|------:|---:|------------:|---------------:|----------:|--------|"
    lines.append(header)
    lines.append(sep)

    for r in rows:
        cur_d = r["current_delta"]
        pag_d = r["pag_delta"]
        cur_str = f"{r['current_count']} ({_fmt_delta(cur_d)})"
        pag_str = f"{r['pag_count']} ({_fmt_delta(pag_d)})"
        lines.append(
            f"| {r['sigla']} "
            f"| {r['pages']} "
            f"| {r['gt']} "
            f"| {cur_str} "
            f"| {pag_str} "
            f"| {r['recovered']} "
            f"| {r['gt_source']} |"
        )

    lines.append("")

    # --- Per-sigla roll-up ---
    lines.append("## Per-sigla verdict\n")
    roll_header = "| sigla | Σ|current Δ| | Σ|pag Δ| | verdict |"
    roll_sep = "|-------|----------------:|------------:|---------|"
    lines.append(roll_header)
    lines.append(roll_sep)

    # Aggregate by sigla preserving first-seen order.
    seen: dict[str, dict] = {}
    for r in rows:
        sig = r["sigla"]
        if sig not in seen:
            seen[sig] = {"cur_abs": 0, "pag_abs": 0}
        seen[sig]["cur_abs"] += abs(r["current_delta"])
        seen[sig]["pag_abs"] += abs(r["pag_delta"])

    for sig, agg in seen.items():
        cur_abs = agg["cur_abs"]
        pag_abs = agg["pag_abs"]
        verdict = "MIGRATE" if pag_abs <= cur_abs else "KEEP"
        lines.append(f"| {sig} | {cur_abs} | {pag_abs} | **{verdict}** |")

    lines.append("")
    return "\n".join(lines)


def _fmt_delta(d: int) -> str:
    return f"+{d}" if d > 0 else str(d)


def main() -> None:
    if not _RESULTS_FILE.exists():
        print(f"Results file not found: {_RESULTS_FILE}\nRun benchmark.py first.")
        return
    rows = json.loads(_RESULTS_FILE.read_text(encoding="utf-8"))
    print(render_report(rows))


if __name__ == "__main__":
    main()
