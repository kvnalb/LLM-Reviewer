#!/usr/bin/env python3
"""
Exploratory analysis of review data in gen_review.db.

Slice: 2023 papers only, excluding Withdrawn / Desk Reject /
       Invite to Workshop decisions, limited to the top 200 papers
       by summary_of_the_review length.

(a) Summary stats & histograms of text lengths for:
    - summary_of_the_review  (REVIEW table)
    - generated              (GENAI_REVIEW table, type='neutral')

(b) Extract leading numbers from 5 numerical review columns
    (rating, confidence, correctness,
     technical_novelty_and_significance, empirical_novelty_and_significance)
    and present summary stats + histograms.

Outputs:
    - Console: summary statistics tables
    - scripts/plots/  : histogram PNGs

Usage:
    python scripts/explore_review_distributions.py
    python scripts/explore_review_distributions.py --db-path /other/path.db
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "gen_review.db"
PLOT_DIR = Path(__file__).resolve().parent / "plots"

NUMERIC_COLUMNS = [
    "rating",
    "confidence",
    "correctness",
    "technical_novelty_and_significance",
    "empirical_novelty_and_significance",
]

EXCLUDED_DECISIONS = ("Withdrawn", "Desk Reject", "Invite to Workshop")
TOP_N_BY_SOTR_LENGTH = 200

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_leading_number(value: object) -> Optional[float]:
    """Extract the leading number from strings like '8: Top 50% ...'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", value)
        if m:
            return float(m.group(1))
    return None


def summary_stats(values: list[float], label: str) -> dict:
    """Compute summary statistics for a list of numeric values."""
    arr = np.array(values, dtype=float)
    return {
        "column": label,
        "count": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(np.min(arr)),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)),
        "max": float(np.max(arr)),
        "non_null": len(arr),
    }


def print_stats_table(rows: list[dict]) -> None:
    """Pretty-print a table of summary statistics."""
    cols = ["column", "count", "mean", "std", "min", "p25", "median", "p75", "max"]
    widths = {c: max(len(c), *(len(fmt_val(r[c])) for r in rows)) for c in cols}
    header = " | ".join(c.rjust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(fmt_val(r[c]).rjust(widths[c]) for c in cols))


def fmt_val(v) -> str:
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def save_histogram(
    values: list[float],
    title: str,
    xlabel: str,
    filename: str,
    bins: int | str = "auto",
    color: str = "#4C72B0",
) -> Path:
    """Save a histogram as a PNG."""
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(values, bins=bins, color=color, edgecolor="white", alpha=0.85)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    ax.spines[["top", "right"]].set_visible(False)

    # Add summary annotation
    arr = np.array(values)
    stats_text = (
        f"n={len(arr):,}\n"
        f"mean={np.mean(arr):.1f}\n"
        f"median={np.median(arr):.1f}\n"
        f"std={np.std(arr, ddof=1):.1f}" if len(arr) > 1 else f"n={len(arr):,}"
    )
    ax.text(
        0.97, 0.95, stats_text,
        transform=ax.transAxes, fontsize=9, verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="wheat", alpha=0.5),
    )

    path = PLOT_DIR / filename
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def detect_genai_columns(cursor: sqlite3.Cursor) -> tuple[Optional[str], Optional[str]]:
    """Auto-detect paper_id and generated text columns in GENAI_REVIEW."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='GENAI_REVIEW'")
    if not cursor.fetchone():
        return None, None
    cursor.execute("PRAGMA table_info(GENAI_REVIEW)")
    cols = {row[1] for row in cursor.fetchall()}
    paper_col = "paper_id" if "paper_id" in cols else next(
        (c for c in cols if "paper" in c.lower()), None
    )
    gen_col = "generated" if "generated" in cols else next(
        (c for c in cols if "generated" in c.lower() or c == "text"), None
    )
    return paper_col, gen_col


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def get_year_col(cursor: sqlite3.Cursor) -> Optional[str]:
    """Detect year column in SUBMISSION."""
    cursor.execute("PRAGMA table_info(SUBMISSION)")
    cols = {row[1].lower() for row in cursor.fetchall()}
    for c in ("year", "submission_year", "when_submitted"):
        if c in cols:
            return c
    return None


def build_paper_slice(
    cursor: sqlite3.Cursor,
    year_col: str,
) -> list[str]:
    """
    Return paper IDs for the analysis slice:
      - 2023 only
      - Exclude Withdrawn, Desk Reject, Invite to Workshop
      - Top 200 by longest summary_of_the_review
    """
    excluded_placeholders = ",".join("?" for _ in EXCLUDED_DECISIONS)
    query = f"""
        SELECT s.id AS paper_id,
               MAX(LENGTH(COALESCE(r.summary_of_the_review, ''))) AS max_sotr_len
        FROM SUBMISSION s
        JOIN REVIEW r ON r.paper_id = s.id
        WHERE s.{year_col} = 2023
          AND TRIM(COALESCE(s.decision, '')) NOT IN ({excluded_placeholders})
          AND TRIM(COALESCE(s.decision, '')) != ''
        GROUP BY s.id
        ORDER BY max_sotr_len DESC
        LIMIT ?
    """
    cursor.execute(query, (*EXCLUDED_DECISIONS, TOP_N_BY_SOTR_LENGTH))
    return [row["paper_id"] for row in cursor.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore review distributions")
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB,
        help="Path to gen_review.db",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Build the paper slice
    # ------------------------------------------------------------------
    year_col = get_year_col(cur)
    if not year_col:
        print("No year column found in SUBMISSION.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    paper_ids = build_paper_slice(cur, year_col)
    if not paper_ids:
        print("No papers matched the slice criteria.")
        conn.close()
        return

    print("=" * 70)
    print("Data slice")
    print("=" * 70)
    print(f"  Year:               2023")
    print(f"  Excluded decisions: {', '.join(EXCLUDED_DECISIONS)}")
    print(f"  Top N by sotr len:  {TOP_N_BY_SOTR_LENGTH}")
    print(f"  Papers selected:    {len(paper_ids)}")

    # Helper: SQL IN-clause for the slice
    id_placeholders = ",".join("?" for _ in paper_ids)

    # ==================================================================
    # (a) Text length distributions
    # ==================================================================
    print("\n" + "=" * 70)
    print("(a) Text length distributions")
    print("=" * 70)

    # --- summary_of_the_review ---
    cur.execute(
        f"SELECT summary_of_the_review FROM REVIEW "
        f"WHERE paper_id IN ({id_placeholders}) "
        f"AND summary_of_the_review IS NOT NULL AND TRIM(summary_of_the_review) != ''",
        paper_ids,
    )
    sotr_lengths = [len(row["summary_of_the_review"]) for row in cur.fetchall()]

    # --- GENAI_REVIEW generated (type='neutral') ---
    genai_paper_col, genai_gen_col = detect_genai_columns(cur)
    genai_lengths: list[int] = []
    if genai_paper_col and genai_gen_col:
        cur.execute(
            f"SELECT {genai_gen_col} FROM GENAI_REVIEW "
            f"WHERE {genai_paper_col} IN ({id_placeholders}) "
            f"AND TRIM(COALESCE(type, '')) = 'neutral' "
            f"AND {genai_gen_col} IS NOT NULL AND TRIM({genai_gen_col}) != ''",
            paper_ids,
        )
        genai_lengths = [len(row[genai_gen_col]) for row in cur.fetchall()]
    else:
        print("  [!] GENAI_REVIEW table not found or columns unrecognized.\n")

    # Summary stats
    length_stats: list[dict] = []
    if sotr_lengths:
        length_stats.append(summary_stats([float(x) for x in sotr_lengths], "summary_of_the_review"))
    else:
        print("  [!] No non-empty summary_of_the_review rows found.\n")
    if genai_lengths:
        length_stats.append(summary_stats([float(x) for x in genai_lengths], "genai_review_neutral"))

    if length_stats:
        print("\nText length summary (character count):\n")
        print_stats_table(length_stats)

    # Histograms
    slice_label = "2023 top-200 sotr"
    plots_saved: list[Path] = []
    if sotr_lengths:
        p = save_histogram(
            [float(x) for x in sotr_lengths],
            f"Length of summary_of_the_review ({slice_label})",
            "Characters",
            "length_summary_of_the_review.png",
            bins=50,
        )
        plots_saved.append(p)
    if genai_lengths:
        p = save_histogram(
            [float(x) for x in genai_lengths],
            f"Length of generated review, neutral ({slice_label})",
            "Characters",
            "length_genai_review_neutral.png",
            bins=50,
        )
        plots_saved.append(p)

    # Side-by-side comparison if both exist
    if sotr_lengths and genai_lengths:
        PLOT_DIR.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), sharey=False)

        axes[0].hist(sotr_lengths, bins=50, color="#4C72B0", edgecolor="white", alpha=0.85)
        axes[0].set_title("summary_of_the_review", fontsize=12, fontweight="bold")
        axes[0].set_xlabel("Characters")
        axes[0].set_ylabel("Count")
        axes[0].spines[["top", "right"]].set_visible(False)

        axes[1].hist(genai_lengths, bins=50, color="#DD8452", edgecolor="white", alpha=0.85)
        axes[1].set_title("GENAI_REVIEW (neutral)", fontsize=12, fontweight="bold")
        axes[1].set_xlabel("Characters")
        axes[1].set_ylabel("Count")
        axes[1].spines[["top", "right"]].set_visible(False)

        fig.suptitle(f"Text Length Comparison ({slice_label})", fontsize=14, fontweight="bold", y=1.02)
        fig.tight_layout()
        p = PLOT_DIR / "length_comparison.png"
        fig.savefig(p, dpi=120, bbox_inches="tight")
        plt.close(fig)
        plots_saved.append(p)

    # ==================================================================
    # (b) Numerical column distributions
    # ==================================================================
    print("\n" + "=" * 70)
    print(f"(b) Numerical columns: {', '.join(NUMERIC_COLUMNS)}")
    print("=" * 70)

    # Check which columns actually exist
    cur.execute("PRAGMA table_info(REVIEW)")
    review_cols = {row[1] for row in cur.fetchall()}
    available = [c for c in NUMERIC_COLUMNS if c in review_cols]
    missing = [c for c in NUMERIC_COLUMNS if c not in review_cols]
    if missing:
        print(f"  [!] Columns not found in REVIEW: {missing}")

    numeric_data: dict[str, list[float]] = {}
    raw_samples: dict[str, list[str]] = {}
    null_counts: dict[str, int] = {}

    for col in available:
        cur.execute(
            f"SELECT {col} FROM REVIEW "
            f"WHERE paper_id IN ({id_placeholders}) AND {col} IS NOT NULL",
            paper_ids,
        )
        raw_vals = [row[col] for row in cur.fetchall()]
        parsed = [parse_leading_number(v) for v in raw_vals]
        non_null = [v for v in parsed if v is not None]
        numeric_data[col] = non_null
        null_counts[col] = len(raw_vals) - len(non_null)
        # Keep a few raw samples for display
        raw_samples[col] = [str(v) for v in raw_vals[:5]]

    # Print raw samples
    print("\nRaw value samples (first 5 non-null per column):\n")
    for col in available:
        print(f"  {col}:")
        for s in raw_samples[col]:
            print(f"    {s!r}")
        print()

    # Summary stats table
    num_stats = []
    for col in available:
        vals = numeric_data[col]
        if vals:
            st = summary_stats(vals, col)
            st["unparseable"] = null_counts[col]
            num_stats.append(st)

    if num_stats:
        print("Numeric summary (leading number extracted):\n")
        # Extended table with unparseable count
        cols_hdr = ["column", "count", "unparseable", "mean", "std", "min", "p25", "median", "p75", "max"]
        widths = {}
        for c in cols_hdr:
            w = len(c)
            for r in num_stats:
                v = r.get(c, "")
                w = max(w, len(fmt_val(v)))
            widths[c] = w

        header = " | ".join(c.rjust(widths[c]) for c in cols_hdr)
        sep = "-+-".join("-" * widths[c] for c in cols_hdr)
        print(header)
        print(sep)
        for r in num_stats:
            print(" | ".join(fmt_val(r.get(c, "")).rjust(widths[c]) for c in cols_hdr))
        print()

    # Individual histograms
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]
    for i, col in enumerate(available):
        vals = numeric_data[col]
        if not vals:
            continue
        # Use integer bins for discrete ratings
        unique = sorted(set(vals))
        if len(unique) <= 20:
            bins = [u - 0.5 for u in unique] + [unique[-1] + 0.5]
        else:
            bins = 30
        # Shorten long column names for filenames
        short_name = col.replace("_and_", "_").replace("_", "_")
        p = save_histogram(
            vals,
            f"{col} ({slice_label})",
            col,
            f"numeric_{short_name}.png",
            bins=bins,
            color=colors[i % len(colors)],
        )
        plots_saved.append(p)

    # Combined figure: all columns on one page
    if len(available) >= 2:
        PLOT_DIR.mkdir(parents=True, exist_ok=True)
        ncols = min(3, len(available))
        nrows = (len(available) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4 * nrows))
        axes_flat = np.array(axes).flatten() if len(available) > 1 else [axes]

        for i, col in enumerate(available):
            ax = axes_flat[i]
            vals = numeric_data[col]
            if not vals:
                ax.set_visible(False)
                continue
            unique = sorted(set(vals))
            if len(unique) <= 20:
                bins = [u - 0.5 for u in unique] + [unique[-1] + 0.5]
            else:
                bins = 30
            ax.hist(vals, bins=bins, color=colors[i % len(colors)], edgecolor="white", alpha=0.85)
            # Wrap long titles
            display_name = col.replace("_", " ")
            ax.set_title(display_name, fontsize=10, fontweight="bold")
            ax.set_xlabel("Value")
            ax.set_ylabel("Count")
            ax.spines[["top", "right"]].set_visible(False)

        # Hide unused subplots
        for j in range(len(available), len(axes_flat)):
            axes_flat[j].set_visible(False)

        fig.suptitle(
            f"Numerical Review Column Distributions ({slice_label})",
            fontsize=14, fontweight="bold", y=1.02,
        )
        fig.tight_layout()
        p = PLOT_DIR / "numeric_all_columns.png"
        fig.savefig(p, dpi=120, bbox_inches="tight")
        plt.close(fig)
        plots_saved.append(p)

    # ==================================================================
    # Summary
    # ==================================================================
    conn.close()

    print("=" * 70)
    print("Plots saved:")
    print("=" * 70)
    for p in plots_saved:
        print(f"  {p}")
    print(f"\nDone. {len(plots_saved)} plots written to {PLOT_DIR}/")


if __name__ == "__main__":
    main()
