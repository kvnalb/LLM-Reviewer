"""Compare results across multiple model runs.

Reads all outputs/results_*.jsonl files (or specific files passed as args)
and generates comparison reports in multiple formats:
  - Markdown table (human-readable)
  - CSV file (for import to Excel/analysis)
  - HTML report with interactive table
  - PNG/PDF charts (matplotlib visualizations)

Output goes to analysis/comparison_TIMESTAMP/ (gitignored folder)

Usage:
    # Auto-discover all result files:
    PYTHONPATH=src python scripts/compare_models.py

    # Compare specific files:
    PYTHONPATH=src python scripts/compare_models.py \
        outputs/results_mock.jsonl \
        outputs/results_llama3_8b.jsonl

    # Via Make:
    make compare

    # View generated reports:
    ls analysis/comparison_*/
    open analysis/comparison_*/report.html
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
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


def generate_markdown_table(entries: list[tuple[str, dict]]) -> str:
    """Generate a markdown comparison table."""
    # Sort by MAE ascending (lower is better); None goes to bottom
    entries.sort(
        key=lambda e: e[1]["mae_mean"] if e[1]["mae_mean"] is not None else 999
    )

    header_dims = " | ".join(f"{DIM_SHORT[d]}" for d in SCORE_DIMENSIONS)
    header = (
        f"| Rank | Model | MAE | Cov% | DecAgr | {header_dims} | N |\n"
        f"|------|-------|-----|------|--------|{'-|-'.join(['---'] * len(SCORE_DIMENSIONS))}|---|"
    )

    rows = []
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
        dim_cols = " | ".join(dim_strs)

        rows.append(
            f"| {rank} | {label} | {mae_str} | {cov_str} | {agree_str} | {dim_cols} | {summary['n']} |"
        )

    return f"# Model Comparison Report\n\n{header}\n" + "\n".join(rows) + "\n"


def generate_csv(entries: list[tuple[str, dict]]) -> str:
    """Generate CSV format comparison table."""
    # Sort by MAE
    entries.sort(
        key=lambda e: e[1]["mae_mean"] if e[1]["mae_mean"] is not None else 999
    )

    lines = []
    header = ["Rank", "Model", "N", "Coverage%", "MAE", "Decision_Agree%"]
    header.extend(SCORE_DIMENSIONS)
    lines.append(",".join(header))

    for rank, (label, summary) in enumerate(entries, 1):
        row = [
            str(rank),
            label,
            str(summary["n"]),
            f"{summary['coverage_pct']:.1f}",
            f"{summary['mae_mean']:.3f}" if summary["mae_mean"] else "",
            f"{summary['decision_agree_pct']:.1f}" if summary["decision_agree_pct"] else "",
        ]
        for dim in SCORE_DIMENSIONS:
            v = summary["dim_mae"].get(dim)
            row.append(f"{v:.3f}" if v else "")
        lines.append(",".join(row))

    return "\n".join(lines)


def generate_html_report(entries: list[tuple[str, dict]]) -> str:
    """Generate HTML report with sortable table."""
    # Sort by MAE
    entries.sort(
        key=lambda e: e[1]["mae_mean"] if e[1]["mae_mean"] is not None else 999
    )

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Model Comparison Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        h1 { color: #333; }
        table {
            border-collapse: collapse;
            width: 100%;
            background-color: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        th {
            background-color: #2c3e50;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background-color: #f9f9f9;
        }
        .rank-1 { background-color: #fff3cd; font-weight: bold; }
        .rank-2 { background-color: #fff8dc; }
        .metric-good { color: #28a745; }
        .metric-fair { color: #ffc107; }
        .metric-poor { color: #dc3545; }
        .timestamp { color: #666; font-size: 0.9em; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Model Comparison Report</h1>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>N</th>
                <th>Coverage</th>
                <th>MAE</th>
                <th>Decision Agree</th>
"""

    for dim in SCORE_DIMENSIONS:
        html += f"                <th>{DIM_SHORT[dim]}</th>\n"

    html += """            </tr>
        </thead>
        <tbody>
"""

    for rank, (label, summary) in enumerate(entries, 1):
        row_class = "rank-1" if rank == 1 else "rank-2" if rank == 2 else ""
        html += f'            <tr class="{row_class}">\n'
        html += f"                <td>{rank}</td>\n"
        html += f"                <td>{label}</td>\n"
        html += f"                <td>{summary['n']}</td>\n"
        html += f"                <td>{summary['coverage_pct']:.0f}%</td>\n"

        mae = summary["mae_mean"]
        mae_class = ""
        if mae:
            if mae < 0.5:
                mae_class = "metric-good"
            elif mae < 1.0:
                mae_class = "metric-fair"
            else:
                mae_class = "metric-poor"
        html += f'                <td class="{mae_class}">{mae:.3f if mae else ""}</td>\n'

        agree = summary["decision_agree_pct"]
        agree_str = f"{agree:.1f}%" if agree else ""
        html += f"                <td>{agree_str}</td>\n"

        for dim in SCORE_DIMENSIONS:
            v = summary["dim_mae"].get(dim)
            val_str = f"{v:.3f}" if v else ""
            html += f"                <td>{val_str}</td>\n"

        html += "            </tr>\n"

    html += """        </tbody>
    </table>
    <p class="timestamp">Generated: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
</body>
</html>
"""
    return html


def generate_charts(entries: list[tuple[str, dict]], output_dir: Path) -> None:
    """Generate matplotlib charts comparing models."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("⚠️  matplotlib not installed, skipping chart generation")
        return

    # Sort by MAE
    entries.sort(
        key=lambda e: e[1]["mae_mean"] if e[1]["mae_mean"] is not None else 999
    )

    models = [label for label, _ in entries]
    mae_values = [summary["mae_mean"] for _, summary in entries]
    decision_agree = [summary["decision_agree_pct"] for _, summary in entries]

    # Chart 1: MAE Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#28a745" if i == 0 else "#007bff" for i in range(len(models))]
    ax.barh(models, mae_values, color=colors)
    ax.set_xlabel("Mean Absolute Error (lower is better)", fontsize=12)
    ax.set_title("Model Comparison: MAE", fontsize=14, fontweight="bold")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_dir / "mae_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Chart 2: Decision Agreement
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#28a745" if v and v > 50 else "#ffc107" for v in decision_agree]
    ax.barh(models, decision_agree, color=colors)
    ax.set_xlabel("Decision Agreement (%)", fontsize=12)
    ax.set_xlim(0, 100)
    ax.set_title("Model Comparison: Decision Agreement", fontsize=14, fontweight="bold")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_dir / "decision_agreement.png", dpi=150, bbox_inches="tight")
    plt.close()

    print(f"✓ Charts generated:")
    print(f"  - {output_dir / 'mae_comparison.png'}")
    print(f"  - {output_dir / 'decision_agreement.png'}")


def print_comparison_table(entries: list[tuple[str, dict]]) -> None:
    """Print a sorted comparison table to stdout."""
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
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("analysis"),
        help="Directory to save reports (default: analysis/)",
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

    # Create timestamped report directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.report_dir / f"comparison_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Generate reports in multiple formats
    print(f"\nGenerating reports in: {report_dir}/")
    print()

    # Markdown report
    markdown = generate_markdown_table(entries)
    with open(report_dir / "report.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"✓ Markdown report: report.md")

    # CSV report
    csv_content = generate_csv(entries)
    with open(report_dir / "comparison.csv", "w", encoding="utf-8") as f:
        f.write(csv_content)
    print(f"✓ CSV export: comparison.csv")

    # HTML report
    html_content = generate_html_report(entries)
    with open(report_dir / "report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✓ HTML report: report.html")

    # Charts
    generate_charts(entries, report_dir)

    print()
    print(f"All reports saved to: {report_dir}")
    print(f"Open in browser: {report_dir / 'report.html'}")


if __name__ == "__main__":
    main()
