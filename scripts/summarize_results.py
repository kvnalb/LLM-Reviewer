"""Summarise reviewer_sim results JSONL.

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

    dim_norm_errors: dict[str, list[float]] = {d: [] for d in SCORE_DIMENSIONS}
    all_nmae: list[float] = []
    all_rmse: list[float] = []
    agree_count = 0
    agree_total = 0

    for row in rows:
        m = row.get("metrics", {}) or {}

        for dim in SCORE_DIMENSIONS:
            val = m.get(f"{dim}_norm_err")
            if val is not None:
                dim_norm_errors[dim].append(float(val))

        nmae = m.get("nmae")
        if nmae is not None:
            all_nmae.append(float(nmae))

        rmse = m.get("rmse")
        if rmse is not None:
            all_rmse.append(float(rmse))

        da = m.get("decision_agree")
        if da is not None:
            agree_total += 1
            if da:
                agree_count += 1

    print(f"Total:    {total}")
    print(f"Scored:   {len(all_nmae)}")
    if total > 0:
        print(f"Coverage: {len(all_nmae) / total * 100:.1f}%")
    print()

    print("Per-dimension NMAE (normalized by scale range, lower is better):")
    for dim in SCORE_DIMENSIONS:
        vals = dim_norm_errors[dim]
        if vals:
            print(f"  {dim:45s}  mean={mean(vals):.3f}  median={median(vals):.3f}")
        else:
            print(f"  {dim:45s}  n/a")

    print()
    if all_nmae:
        print(f"NMAE (primary):        mean={mean(all_nmae):.3f}  median={median(all_nmae):.3f}")
    if all_rmse:
        print(f"RMSE:                  mean={mean(all_rmse):.3f}  median={median(all_rmse):.3f}")
    if agree_total:
        print(f"Decision agreement:    {agree_count / agree_total * 100:.1f}%  ({agree_count}/{agree_total})")
    else:
        print("Decision agreement:    n/a")


if __name__ == "__main__":
    main()
