"""
Post-hoc OLS evaluation with normalized scores.

Normalizes both human and LLM scores to [0, 1] before regression,
enabling equivalent comparison across dimensions regardless of scale.

Human score ranges (ICLR native):
  rating:                          1–10  → (x-1)/9
  confidence:                      1–5   → (x-1)/4
  correctness:                     1–4   → (x-1)/3
  technical_novelty_and_significance: 1–4 → (x-1)/3
  empirical_novelty_and_significance: 1–4 → (x-1)/3

LLM score range (new 0–5 prompt):
  all dimensions:                  0–5   → x/5

Two specifications:
  Spec 1: norm_human ~ norm_llm              (no fixed effects)
  Spec 2: norm_human ~ norm_llm + C(model)  (model fixed effects)

Usage:
  # Single results file
  python scripts/ols_normalized.py --results outputs/results_mymodel.jsonl

  # Multiple files (pools across models, enables model FE spec)
  python scripts/ols_normalized.py \\
    --results outputs/results_a.jsonl outputs/results_b.jsonl

  # Override LLM scale if using old-style results on native ICLR scales
  python scripts/ols_normalized.py --results outputs/results_old.jsonl --llm-scale native
"""

import argparse
import json
import os

import pandas as pd
import statsmodels.formula.api as smf

DIMS = [
    "rating",
    "confidence",
    "correctness",
    "technical_novelty_and_significance",
    "empirical_novelty_and_significance",
]

# Human score ranges: (min, max) on native ICLR scale
HUMAN_RANGES = {
    "rating":                              (1, 10),
    "confidence":                          (1, 5),
    "correctness":                         (1, 4),
    "technical_novelty_and_significance":  (1, 4),
    "empirical_novelty_and_significance":  (1, 4),
}

# LLM score ranges for the new 0–5 prompt
LLM_RANGE_NEW = (0, 5)


def normalize(value: float, lo: float, hi: float) -> float:
    return (value - lo) / (hi - lo)


def load_human_scores(subset_path: str) -> dict:
    humans = {}
    with open(subset_path) as f:
        for line in f:
            r = json.loads(line)
            humans[r["paper_id"]] = {
                d: r["reviews"][d]["mean"]
                for d in DIMS
                if d in r.get("reviews", {})
            }
    return humans


def load_results(paths: list[str], humans: dict, llm_scale: str) -> pd.DataFrame:
    rows = []
    for path in paths:
        model_label = os.path.basename(path).replace("results_", "").replace(".jsonl", "")
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                pid = r["paper_id"]
                gr = r.get("generated_review", {})
                h = humans.get(pid, {})

                for dim in DIMS:
                    hval = h.get(dim)
                    mval = gr.get(dim)
                    if hval is None or mval is None:
                        continue
                    try:
                        hval = float(hval)
                        mval = float(mval)
                    except (ValueError, TypeError):
                        continue

                    # Normalize human score from native ICLR scale
                    hlo, hhi = HUMAN_RANGES[dim]
                    norm_human = normalize(hval, hlo, hhi)

                    # Normalize LLM score
                    if llm_scale == "native":
                        # Old-style results: LLM output on same scale as human
                        norm_llm = normalize(mval, hlo, hhi)
                    else:
                        # New-style results: LLM output on 0–5 scale
                        llo, lhi = LLM_RANGE_NEW
                        norm_llm = normalize(mval, llo, lhi)

                    # Clamp to [0, 1] to handle out-of-range model outputs
                    norm_human = max(0.0, min(1.0, norm_human))
                    norm_llm   = max(0.0, min(1.0, norm_llm))

                    rows.append({
                        "model":      model_label,
                        "paper_id":   pid,
                        "field":      dim,
                        "human":      hval,
                        "llm":        mval,
                        "norm_human": norm_human,
                        "norm_llm":   norm_llm,
                    })

    return pd.DataFrame(rows)


def run_regressions(df: pd.DataFrame) -> None:
    n_models = df["model"].nunique()
    print(f"Observations: {len(df)}  |  Models: {n_models}  |  Papers: {df['paper_id'].nunique()}")
    print()

    # ── Spec 1: no fixed effects ──────────────────────────────────────────────
    print("=" * 64)
    print("SPEC 1: norm_human ~ norm_llm  (no fixed effects)")
    print("=" * 64)

    m_pool = smf.ols("norm_human ~ norm_llm", data=df).fit()
    print(f"\nPooled (all fields):  β={m_pool.params['norm_llm']:.3f}  "
          f"intercept={m_pool.params['Intercept']:.3f}  R²={m_pool.rsquared:.3f}")
    print(f"  ⚠  Pooled R² is unreliable — use per-field numbers\n")

    print(f"  {'Field':<42}  {'β':>6}  {'intercept':>9}  {'R²':>6}  {'N':>5}")
    print(f"  {'-'*42}  {'-'*6}  {'-'*9}  {'-'*6}  {'-'*5}")
    s1 = {}
    for dim in DIMS:
        sub = df[df["field"] == dim]
        m = smf.ols("norm_human ~ norm_llm", data=sub).fit()
        s1[dim] = m.rsquared
        print(f"  {dim:<42}  {m.params['norm_llm']:>6.3f}  "
              f"{m.params['Intercept']:>9.3f}  {m.rsquared:>6.3f}  {len(sub):>5}")

    # ── Spec 2: model fixed effects (only meaningful with multiple models) ─────
    if n_models > 1:
        print()
        print("=" * 64)
        print("SPEC 2: norm_human ~ norm_llm + C(model)  (model fixed effects)")
        print("=" * 64)

        m_pool2 = smf.ols("norm_human ~ norm_llm + C(model)", data=df).fit()
        print(f"\nPooled (all fields):  β={m_pool2.params['norm_llm']:.3f}  "
              f"R²={m_pool2.rsquared:.3f}  (vs no-FE R²={m_pool.rsquared:.3f})")
        print()

        print(f"  {'Field':<42}  {'β':>6}  {'R²':>6}  {'ΔR²':>7}")
        print(f"  {'-'*42}  {'-'*6}  {'-'*6}  {'-'*7}")
        for dim in DIMS:
            sub = df[df["field"] == dim]
            m_fe = smf.ols("norm_human ~ norm_llm + C(model)", data=sub).fit()
            delta = m_fe.rsquared - s1[dim]
            print(f"  {dim:<42}  {m_fe.params['norm_llm']:>6.3f}  "
                  f"{m_fe.rsquared:>6.3f}  {delta:>+7.3f}")
    else:
        print(f"\n(Model FE spec skipped — only one model in results)")

    # ── Score distribution summary ────────────────────────────────────────────
    print()
    print("=" * 64)
    print("SCORE DISTRIBUTIONS (normalized 0–1)")
    print("=" * 64)
    print(f"\n  {'Field':<42}  {'human μ':>7}  {'llm μ':>6}  {'human σ':>8}  {'llm σ':>6}")
    print(f"  {'-'*42}  {'-'*7}  {'-'*6}  {'-'*8}  {'-'*6}")
    for dim in DIMS:
        sub = df[df["field"] == dim]
        print(f"  {dim:<42}  {sub['norm_human'].mean():>7.3f}  {sub['norm_llm'].mean():>6.3f}"
              f"  {sub['norm_human'].std():>8.3f}  {sub['norm_llm'].std():>6.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", nargs="+", required=True,
        help="Path(s) to results JSONL file(s)"
    )
    parser.add_argument(
        "--subset", default="outputs/review_subset.jsonl",
        help="Path to human review subset JSONL"
    )
    parser.add_argument(
        "--llm-scale", choices=["0-5", "native"], default="0-5",
        help="Scale of LLM outputs: '0-5' (new prompt, default) or 'native' (old ICLR-scale prompt)"
    )
    args = parser.parse_args()

    humans = load_human_scores(args.subset)
    df = load_results(args.results, humans, args.llm_scale)

    if df.empty:
        print("No matching data found. Check that paper_ids align between results and subset.")
        return

    run_regressions(df)


if __name__ == "__main__":
    main()
