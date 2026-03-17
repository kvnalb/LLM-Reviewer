"""Summarise reviewer_sim results JSONL.

Reports per-dimension NMAE, RMSE, decision agreement, and per-dimension
OLS regression (norm_human ~ norm_llm) with R² — all on the [0,1] scale.

Usage:
    python scripts/summarize_results.py outputs/results.jsonl
"""

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import List

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS
from reviewer_sim.evaluate.metrics import SCORE_RANGES, LLM_SCORE_RANGE, _to_unit, _extract_human_score, parse_numeric_rating

SCORE_DIMENSIONS = SCORE_COLUMNS


def _read_jsonl(path: Path) -> List[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _ols_r2(x: list[float], y: list[float]):
    """R² for simple OLS of y ~ x. Returns None if fewer than 3 points."""
    n = len(x)
    if n < 3:
        return None
    xm = sum(x) / n
    ym = sum(y) / n
    ss_res = sum((yi - (ym + (sum((xi - xm) * (yi - ym) for xi, yi in zip(x, y)) /
                              (sum((xi - xm) ** 2 for xi in x) or 1e-12)) * (xi - xm))
                 ** 2) for xi, yi in zip(x, y))
    ss_tot = sum((yi - ym) ** 2 for yi in y)
    return 1 - ss_res / ss_tot if ss_tot > 1e-12 else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise reviewer_sim results JSONL.")
    parser.add_argument("path", type=Path, help="Path to results JSONL")
    parser.add_argument("--subset", type=Path, default=Path("outputs/review_subset.jsonl"),
                        help="Human review subset JSONL for OLS R² (default: outputs/review_subset.jsonl)")
    args = parser.parse_args()

    rows = _read_jsonl(args.path)
    total = len(rows)

    # Load human scores keyed by paper_id for OLS
    human_lookup: dict = {}
    if args.subset.exists():
        for r in _read_jsonl(args.subset):
            human_lookup[r["paper_id"]] = r.get("reviews", {})

    dim_norm_errors: dict[str, list[float]] = {d: [] for d in SCORE_DIMENSIONS}
    # For OLS: collect (norm_human, norm_llm) pairs per dimension
    dim_ols: dict[str, tuple[list[float], list[float]]] = {d: ([], []) for d in SCORE_DIMENSIONS}
    all_nmae: list[float] = []
    all_rmse: list[float] = []
    agree_count = 0
    agree_total = 0

    l_lo, l_hi = LLM_SCORE_RANGE

    for row in rows:
        m = row.get("metrics", {}) or {}
        gr = row.get("generated_review", {}) or {}
        human_review = human_lookup.get(row.get("paper_id"), {})

        for dim in SCORE_DIMENSIONS:
            val = m.get(f"{dim}_norm_err")
            if val is not None:
                dim_norm_errors[dim].append(float(val))

            # Collect normalized pairs for OLS
            hval = _extract_human_score(human_review, dim)
            lval = parse_numeric_rating(gr.get(dim))
            if hval is not None and lval is not None:
                h_lo, h_hi = SCORE_RANGES[dim]
                dim_ols[dim][0].append(_to_unit(hval, h_lo, h_hi))
                dim_ols[dim][1].append(_to_unit(lval, l_lo, l_hi))

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

    print("Per-dimension NMAE (lower is better) and OLS R² (norm_human ~ norm_llm):")
    print("  NOTE: R² is only meaningful for results generated with the 0–5 LLM prompt.")
    print("        Negative R² indicates old-scale results were passed (scores mismatched).")
    print(f"  {'Dimension':<45}  {'NMAE mean':>9}  {'NMAE med':>8}  {'R²':>6}")
    print(f"  {'-'*45}  {'-'*9}  {'-'*8}  {'-'*6}")
    for dim in SCORE_DIMENSIONS:
        vals = dim_norm_errors[dim]
        nh, nl = dim_ols[dim]
        r2 = _ols_r2(nh, nl)
        nmae_str  = f"{mean(vals):.3f}" if vals else "n/a"
        nmaem_str = f"{median(vals):.3f}" if vals else "n/a"
        r2_str    = f"{r2:.3f}" if r2 is not None else "n/a"
        print(f"  {dim:<45}  {nmae_str:>9}  {nmaem_str:>8}  {r2_str:>6}")

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
