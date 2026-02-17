"""Run a multi-model experiment using Together AI and produce a comparison table.

Sequentially runs the reviewer_sim pipeline for each model listed in MODELS,
writing per-model results to outputs/results_<slug>.jsonl, then prints a
sorted comparison table at the end.

Usage:
    PYTHONPATH=src TOGETHER_API_KEY=your-key python scripts/run_experiment.py

    Or via Make:
    TOGETHER_API_KEY=your-key make experiment

To customise which models are evaluated, edit the MODELS list below.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from statistics import mean
from typing import List

# ---------------------------------------------------------------------------
# Configure your experiment here.
# Each entry: (together_model_id, short_label_for_display)
# NOTE: Prefer serverless models (no dedicated endpoint required)
# ---------------------------------------------------------------------------
MODELS: List[tuple[str, str]] = [
    # Dense — scale progression
    ("meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "Llama-3.1-8B"),        # cheapest baseline
    ("openai/gpt-oss-20b",                           "GPT-OSS-20B"),          # current default, anchor
    ("mistralai/Mistral-Small-24B-Instruct-2501",    "Mistral-Small-24B"),    # different training lineage
    ("meta-llama/Llama-3.3-70B-Instruct-Turbo",      "Llama-3.3-70B"),        # well-benchmarked mid-tier
    # MoE — active-param efficiency at scale
    ("meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "Llama4-Maverick"), # 17B active, 128 experts
    ("Qwen/Qwen3-235B-A22B-Instruct-2507-tput",      "Qwen3-235B"),           # 22B active, Alibaba flagship
    ("deepseek-ai/DeepSeek-V3.1",                    "DeepSeek-V3.1"),        # 37B active, frontier non-thinking
    # Reasoning — CoT vs standard on same base
    ("deepseek-ai/DeepSeek-R1",                      "DeepSeek-R1"),          # 37B active, thinking model
]

INPUT_JSONL = "outputs/review_subset.jsonl"
OUTPUT_DIR = Path("outputs")

SCORE_DIMENSIONS = [
    "rating",
    "confidence",
    "correctness",
    "technical_novelty_and_significance",
    "empirical_novelty_and_significance",
]


def _slugify(model_id: str) -> str:
    """Turn a model ID into a safe filename fragment."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", model_id).strip("_").lower()


def _run_pipeline(model_id: str, output_path: Path) -> bool:
    """Run reviewer_sim.run for one model. Returns True on success."""
    env = {
        **os.environ,
        "MODEL_PROVIDER": "together",
        "MODEL_PATH": model_id,
        "INPUT_JSONL": INPUT_JSONL,
        "OUTPUT_JSONL": str(output_path),
        "PYTHONPATH": os.environ.get("PYTHONPATH", "src"),
    }
    print(f"\n{'='*60}")
    print(f"  Running: {model_id}")
    print(f"  Output:  {output_path}")
    print(f"{'='*60}\n")

    result = subprocess.run(
        [sys.executable, "-m", "reviewer_sim.run"],
        env=env,
    )
    if result.returncode != 0:
        print(f"\n  [FAILED] {model_id} (exit code {result.returncode})")
        return False
    return True


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _compute_summary(path: Path) -> dict:
    """Compute aggregate metrics for one results file."""
    rows = _read_jsonl(path)

    dim_norm_errors: dict[str, list[float]] = {d: [] for d in SCORE_DIMENSIONS}
    all_nmae: list[float] = []
    all_spearman: list[float] = []
    agree_count = 0
    agree_total = 0

    for row in rows:
        m = row.get("metrics", {}) or {}
        for dim in SCORE_DIMENSIONS:
            val = m.get(f"{dim}_norm_err")
            if val is not None:
                dim_norm_errors[dim].append(float(val))
        nmae_val = m.get("nmae")
        if nmae_val is not None:
            all_nmae.append(float(nmae_val))
        sc = m.get("spearman_corr")
        if sc is not None:
            all_spearman.append(float(sc))
        da = m.get("decision_agree")
        if da is not None:
            agree_total += 1
            if da:
                agree_count += 1

    return {
        "n": len(rows),
        "nmae_mean": mean(all_nmae) if all_nmae else None,
        "spearman_mean": mean(all_spearman) if all_spearman else None,
        "decision_agree_pct": (
            agree_count / agree_total * 100 if agree_total else None
        ),
        "agree_count": agree_count,
        "agree_total": agree_total,
        "dim_nmae": {
            dim: mean(vals) if vals else None
            for dim, vals in dim_norm_errors.items()
        },
    }


def _print_comparison_table(results: list[tuple[str, str, dict]]) -> None:
    """Print a sorted comparison table.

    results: list of (model_id, label, summary_dict)
    """
    # Sort by NMAE ascending (lower is better); None goes to bottom
    results.sort(key=lambda r: r[2]["nmae_mean"] if r[2]["nmae_mean"] is not None else 999)

    dim_short = {
        "rating": "Rating",
        "confidence": "Conf",
        "correctness": "Corr",
        "technical_novelty_and_significance": "TechNov",
        "empirical_novelty_and_significance": "EmpNov",
    }

    header_dims = "  ".join(f"{dim_short[d]:>7s}" for d in SCORE_DIMENSIONS)
    header = f"{'Rank':>4s}  {'Model':<22s}  {'NMAE':>6s}  {'Spear':>6s}  {'DecAgr':>7s}  {header_dims}  {'N':>4s}"
    sep = "-" * len(header)

    print(f"\n{sep}")
    print("  EXPERIMENT RESULTS  (sorted by NMAE, lower is better)")
    print(sep)
    print(header)
    print(sep)

    for rank, (model_id, label, summary) in enumerate(results, 1):
        nmae_str = f"{summary['nmae_mean']:.3f}" if summary["nmae_mean"] is not None else "n/a"
        spear_str = f"{summary['spearman_mean']:.3f}" if summary["spearman_mean"] is not None else "n/a"
        agree_str = f"{summary['decision_agree_pct']:.1f}%" if summary["decision_agree_pct"] is not None else "n/a"

        dim_strs = []
        for dim in SCORE_DIMENSIONS:
            v = summary["dim_nmae"].get(dim)
            dim_strs.append(f"{v:.3f}" if v is not None else "n/a")
        dim_cols = "  ".join(f"{s:>7s}" for s in dim_strs)

        print(f"{rank:>4d}  {label:<22s}  {nmae_str:>6s}  {spear_str:>6s}  {agree_str:>7s}  {dim_cols}  {summary['n']:>4d}")

    print(sep)
    print()


def main() -> None:
    api_key = os.environ.get("TOGETHER_API_KEY", "")
    if not api_key:
        print("ERROR: TOGETHER_API_KEY environment variable is required.")
        sys.exit(1)

    input_path = Path(INPUT_JSONL)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("Run 'make export' first to generate the input JSONL.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Run each model
    completed: list[tuple[str, str, Path]] = []
    failed: list[tuple[str, str]] = []

    for model_id, label in MODELS:
        slug = _slugify(model_id)
        output_path = OUTPUT_DIR / f"results_{slug}.jsonl"
        ok = _run_pipeline(model_id, output_path)
        if ok and output_path.exists():
            completed.append((model_id, label, output_path))
        else:
            failed.append((model_id, label))

    # Compute summaries and print table
    if completed:
        results = []
        for model_id, label, path in completed:
            summary = _compute_summary(path)
            results.append((model_id, label, summary))
        _print_comparison_table(results)
    else:
        print("\nNo models completed successfully.")

    if failed:
        print("Failed models:")
        for model_id, label in failed:
            print(f"  - {label} ({model_id})")

    # Also write machine-readable summary
    summary_path = OUTPUT_DIR / "experiment_summary.json"
    summary_data = []
    for model_id, label, path in completed:
        s = _compute_summary(path)
        summary_data.append({
            "model_id": model_id,
            "label": label,
            "results_file": str(path),
            **s,
        })
    summary_data.sort(key=lambda r: r["nmae_mean"] if r["nmae_mean"] is not None else 999)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    print(f"Machine-readable summary written to: {summary_path}")


if __name__ == "__main__":
    main()
