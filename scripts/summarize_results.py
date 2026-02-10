"""Summarise reviewer_sim results JSONL (numerical eval metrics).

Usage:
    python scripts/summarize_results.py outputs/results.jsonl
"""

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import List

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

SCORE_DIMENSIONS = SCORE_COLUMNS


def _read_jsonl(path: Path) -> List[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise reviewer_sim results JSONL.")
    parser.add_argument("path", type=Path, help="Path to results JSONL")
    args = parser.parse_args()

    rows = _read_jsonl(args.path)
    total = len(rows)

    # Collect per-dimension errors
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

        mae = m.get("mae")
        if mae is not None:
            all_mae.append(float(mae))

        da = m.get("decision_agree")
        if da is not None:
            agree_total += 1
            if da:
                agree_count += 1

    print(f"Total rows: {total}")
    print(f"Processed:  {len(all_mae)}")
    if total > 0:
        coverage = len(all_mae) / total * 100
        print(f"Coverage:   {coverage:.1f}%")
    print()

    print("Per-dimension MAE:")
    for dim in SCORE_DIMENSIONS:
        vals = dim_errors[dim]
        if vals:
            print(f"  {dim:45s}  mean={mean(vals):.3f}  median={median(vals):.3f}  n={len(vals)}")
        else:
            print(f"  {dim:45s}  n/a")

    if all_mae:
        print(f"\nOverall MAE:  mean={mean(all_mae):.3f}  median={median(all_mae):.3f}  n={len(all_mae)}")
    else:
        print("\nOverall MAE:  n/a")

    if agree_total:
        pct = agree_count / agree_total * 100
        print(f"Decision agreement: {pct:.1f}%  ({agree_count}/{agree_total})")
    else:
        print("Decision agreement: n/a")


if __name__ == "__main__":
    main()
