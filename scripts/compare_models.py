"""Compare results across multiple model runs.

Reads all outputs/results_*.jsonl files (or specific files passed as args)
and generates comparison reports in multiple formats:
  - Markdown table (human-readable)
  - CSV file (for import to Excel/analysis)
  - HTML report with interactive table
  - PNG charts (matplotlib visualizations)

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
        "n_processed": len(all_nmae),
        "coverage_pct": (len(all_nmae) / len(rows) * 100) if rows else 0.0,
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


def generate_markdown_table(entries: list[tuple[str, dict]]) -> str:
    """Generate a markdown comparison table."""
    entries.sort(
        key=lambda e: e[1]["nmae_mean"] if e[1]["nmae_mean"] is not None else 999
    )

    header_dims = " | ".join(f"{DIM_SHORT[d]}" for d in SCORE_DIMENSIONS)
    header = (
        f"| Rank | Model | NMAE | Spearman | Cov% | DecAgr | {header_dims} | N |\n"
        f"|------|-------|------|----------|------|--------|{'-|-'.join(['---'] * len(SCORE_DIMENSIONS))}|---|"
    )

    rows = []
    for rank, (label, summary) in enumerate(entries, 1):
        nmae_str = f"{summary['nmae_mean']:.3f}" if summary["nmae_mean"] is not None else "n/a"
        spear_str = f"{summary['spearman_mean']:.3f}" if summary["spearman_mean"] is not None else "n/a"
        cov_str = f"{summary['coverage_pct']:.0f}%"
        agree_str = f"{summary['decision_agree_pct']:.1f}%" if summary["decision_agree_pct"] is not None else "n/a"

        dim_strs = [
            f"{summary['dim_nmae'].get(dim):.3f}" if summary["dim_nmae"].get(dim) is not None else "n/a"
            for dim in SCORE_DIMENSIONS
        ]
        dim_cols = " | ".join(dim_strs)

        rows.append(
            f"| {rank} | {label} | {nmae_str} | {spear_str} | {cov_str} | {agree_str} | {dim_cols} | {summary['n']} |"
        )

    return f"# Model Comparison Report\n\n{header}\n" + "\n".join(rows) + "\n"


def generate_csv(entries: list[tuple[str, dict]]) -> str:
    """Generate CSV format comparison table."""
    entries.sort(
        key=lambda e: e[1]["nmae_mean"] if e[1]["nmae_mean"] is not None else 999
    )

    lines = []
    header = ["Rank", "Model", "N", "Coverage%", "NMAE", "Spearman", "Decision_Agree%"]
    header.extend(SCORE_DIMENSIONS)
    lines.append(",".join(header))

    for rank, (label, summary) in enumerate(entries, 1):
        row = [
            str(rank),
            label,
            str(summary["n"]),
            f"{summary['coverage_pct']:.1f}",
            f"{summary['nmae_mean']:.3f}" if summary["nmae_mean"] else "",
            f"{summary['spearman_mean']:.3f}" if summary["spearman_mean"] else "",
            f"{summary['decision_agree_pct']:.1f}" if summary["decision_agree_pct"] else "",
        ]
        for dim in SCORE_DIMENSIONS:
            v = summary["dim_nmae"].get(dim)
            row.append(f"{v:.3f}" if v else "")
        lines.append(",".join(row))

    return "\n".join(lines)


def generate_html_report(entries: list[tuple[str, dict]]) -> str:
    """Generate HTML report with sortable table."""
    entries.sort(
        key=lambda e: e[1]["nmae_mean"] if e[1]["nmae_mean"] is not None else 999
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
        tr:hover { background-color: #f9f9f9; }
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
    <p>Primary metric: NMAE (Normalized MAE, lower is better). Good &lt;0.15, Fair &lt;0.25, Poor &ge;0.25</p>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>N</th>
                <th>Coverage</th>
                <th>NMAE</th>
                <th>Spearman</th>
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

        nmae = summary["nmae_mean"]
        if nmae is not None:
            nmae_class = "metric-good" if nmae < 0.15 else "metric-fair" if nmae < 0.25 else "metric-poor"
            html += f'                <td class="{nmae_class}">{nmae:.3f}</td>\n'
        else:
            html += "                <td>n/a</td>\n"

        spear = summary["spearman_mean"]
        html += f"                <td>{f'{spear:.3f}' if spear is not None else 'n/a'}</td>\n"

        agree = summary["decision_agree_pct"]
        html += f"                <td>{f'{agree:.1f}%' if agree is not None else 'n/a'}</td>\n"

        for dim in SCORE_DIMENSIONS:
            v = summary["dim_nmae"].get(dim)
            html += f"                <td>{f'{v:.3f}' if v is not None else ''}</td>\n"

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
    except ImportError:
        print("matplotlib not installed, skipping chart generation")
        return

    entries.sort(
        key=lambda e: e[1]["nmae_mean"] if e[1]["nmae_mean"] is not None else 999
    )

    # Filter out entries with no NMAE data for charts
    valid_entries = [(label, summary) for label, summary in entries if summary["nmae_mean"] is not None]
    models = [label for label, _ in valid_entries]
    nmae_values = [summary["nmae_mean"] for _, summary in valid_entries]
    decision_agree = [summary["decision_agree_pct"] for _, summary in valid_entries]

    # Chart 1: NMAE Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#28a745" if i == 0 else "#007bff" for i in range(len(models))]
    ax.barh(models, nmae_values, color=colors)
    ax.set_xlabel("NMAE — Normalized MAE (lower is better)", fontsize=12)
    ax.set_title("Model Comparison: NMAE", fontsize=14, fontweight="bold")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_dir / "nmae_comparison.png", dpi=150, bbox_inches="tight")
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

    print(f"Charts generated:")
    print(f"  - {output_dir / 'nmae_comparison.png'}")
    print(f"  - {output_dir / 'decision_agreement.png'}")


def print_comparison_table(entries: list[tuple[str, dict]]) -> None:
    """Print a sorted comparison table to stdout."""
    entries.sort(
        key=lambda e: e[1]["nmae_mean"] if e[1]["nmae_mean"] is not None else 999
    )

    header_dims = "  ".join(f"{DIM_SHORT[d]:>7s}" for d in SCORE_DIMENSIONS)
    header = (
        f"{'Rank':>4s}  {'Model':<28s}  {'NMAE':>6s}  {'Spear':>6s}  {'Cov%':>5s}  {'DecAgr':>7s}  "
        f"{header_dims}  {'N':>4s}"
    )
    sep = "-" * len(header)

    print(f"\n{sep}")
    print("  MODEL COMPARISON  (sorted by NMAE, lower is better)")
    print(sep)
    print(header)
    print(sep)

    for rank, (label, summary) in enumerate(entries, 1):
        nmae_str = f"{summary['nmae_mean']:.3f}" if summary["nmae_mean"] is not None else "n/a"
        spear_str = f"{summary['spearman_mean']:.3f}" if summary["spearman_mean"] is not None else "n/a"
        cov_str = f"{summary['coverage_pct']:.0f}%"
        agree_str = f"{summary['decision_agree_pct']:.1f}%" if summary["decision_agree_pct"] is not None else "n/a"

        dim_strs = [
            f"{summary['dim_nmae'].get(dim):.3f}" if summary["dim_nmae"].get(dim) is not None else "n/a"
            for dim in SCORE_DIMENSIONS
        ]
        dim_cols = "  ".join(f"{s:>7s}" for s in dim_strs)

        print(
            f"{rank:>4d}  {label:<28s}  {nmae_str:>6s}  {spear_str:>6s}  {cov_str:>5s}  {agree_str:>7s}  "
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.report_dir / f"comparison_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating reports in: {report_dir}/")
    print()

    markdown = generate_markdown_table(entries)
    with open(report_dir / "report.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"Markdown report: report.md")

    csv_content = generate_csv(entries)
    with open(report_dir / "comparison.csv", "w", encoding="utf-8") as f:
        f.write(csv_content)
    print(f"CSV export: comparison.csv")

    html_content = generate_html_report(entries)
    with open(report_dir / "report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML report: report.html")

    generate_charts(entries, report_dir)

    print()
    print(f"All reports saved to: {report_dir}")
    print(f"Open in browser: {report_dir / 'report.html'}")


if __name__ == "__main__":
    main()
