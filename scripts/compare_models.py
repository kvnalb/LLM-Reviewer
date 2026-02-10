"""Compare results across multiple model runs.

Reads all outputs/results_*.jsonl files (or specific files passed as args)
and prints a sorted comparison table.

Usage:
    # Auto-discover all result files:
    PYTHONPATH=src python scripts/compare_models.py

    # Compare specific files:
    PYTHONPATH=src python scripts/compare_models.py \
        outputs/results_mock.jsonl \
        outputs/results_llama3_8b.jsonl

    # Via Make:
    make compare
"""

import argparse
import json
import re
from pathlib import Path
from statistics import mean
from typing import List

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

SCORE_DIMENSIONS = SCORE_COLUMNS

DIM_SHORT = {
    "rating": "Rating",
    "confidence": "Conf",
    "correctness": "Corr",
    "technical_novelty_and_significance": "TechNov",
    "empirical_novelty_and_significance": "EmpNov",
}


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _label_from_path(path: Path) -> str:
    """Derive a human-readable label from a results filename."""
    stem = path.stem  # e.g. "results_meta_llama_llama_3_8b_chat_hf"
    label = stem.removeprefix("results_").removeprefix("results")
    label = re.sub(r"_+", " ", label).strip()
    return label or stem


def compute_summary(path: Path) -> dict:
    """Compute aggregate metrics for one results file."""
    rows = _read_jsonl(path)

    dim_errors: dict[str, list[float]] = {d: [] for d in SCORE_DIMENSIONS}
    all_mae: list[float] = []
    agree_count = 0
    agree_total = 0

    for row in rows:
        m = row.get("metrics", {}) or {}
        for dim in SCORE_DIMENSIONS:
            val = m.get(f"{dim}_abs_err")
            if val is not None:
                dim_errors[dim].append(float(val))
        mae_val = m.get("mae")
        if mae_val is not None:
            all_mae.append(float(mae_val))
        da = m.get("decision_agree")
        if da is not None:
            agree_total += 1
            if da:
                agree_count += 1

    return {
        "n": len(rows),
        "n_processed": len(all_mae),
        "coverage_pct": (len(all_mae) / len(rows) * 100) if rows else 0.0,
        "mae_mean": mean(all_mae) if all_mae else None,
        "mae_median": sorted(all_mae)[len(all_mae) // 2] if all_mae else None,
        "decision_agree_pct": (
            agree_count / agree_total * 100 if agree_total else None
        ),
        "agree_count": agree_count,
        "agree_total": agree_total,
        "dim_mae": {
            dim: mean(vals) if vals else None
            for dim, vals in dim_errors.items()
        },
    }


def print_comparison_table(entries: list[tuple[str, dict]]) -> None:
    """Print a sorted comparison table.

    entries: list of (label, summary_dict)
    """
    # Sort by MAE ascending (lower is better); None goes to bottom
    entries.sort(
        key=lambda e: e[1]["mae_mean"] if e[1]["mae_mean"] is not None else 999
    )

    header_dims = "  ".join(f"{DIM_SHORT[d]:>7s}" for d in SCORE_DIMENSIONS)
    header = (
        f"{'Rank':>4s}  {'Model':<28s}  {'MAE':>6s}  {'Cov%':>5s}  {'DecAgr':>7s}  "
        f"{header_dims}  {'N':>4s}"
    )
    sep = "-" * len(header)

    print(f"\n{sep}")
    print("  MODEL COMPARISON  (sorted by overall MAE, lower is better)")
    print(sep)
    print(header)
    print(sep)

    for rank, (label, summary) in enumerate(entries, 1):
        mae_str = (
            f"{summary['mae_mean']:.3f}"
            if summary["mae_mean"] is not None
            else "n/a"
        )
        cov_str = f"{summary['coverage_pct']:.0f}%"
        if summary["decision_agree_pct"] is not None:
            agree_str = f"{summary['decision_agree_pct']:.1f}%"
        else:
            agree_str = "n/a"

        dim_strs = []
        for dim in SCORE_DIMENSIONS:
            v = summary["dim_mae"].get(dim)
            dim_strs.append(f"{v:.2f}" if v is not None else "n/a")
        dim_cols = "  ".join(f"{s:>7s}" for s in dim_strs)

        print(
            f"{rank:>4d}  {label:<28s}  {mae_str:>6s}  {cov_str:>5s}  {agree_str:>7s}  "
            f"{dim_cols}  {summary['n']:>4d}"
        )

    print(sep)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare evaluation results across multiple models."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "Paths to results JSONL files. If none given, auto-discovers "
            "all outputs/results_*.jsonl files."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory to search for results files (default: outputs/)",
    )
    args = parser.parse_args()

    if args.paths:
        paths = args.paths
    else:
        # Auto-discover
        paths = sorted(args.output_dir.glob("results_*.jsonl"))
        if not paths:
            print(f"No results_*.jsonl files found in {args.output_dir}/")
            print("Run the pipeline first, or pass file paths explicitly.")
            return

    print(f"Found {len(paths)} result file(s):")
    for p in paths:
        print(f"  - {p}")

    entries: list[tuple[str, dict]] = []
    for path in paths:
        label = _label_from_path(path)
        summary = compute_summary(path)
        entries.append((label, summary))

    print_comparison_table(entries)


if __name__ == "__main__":
    main()
