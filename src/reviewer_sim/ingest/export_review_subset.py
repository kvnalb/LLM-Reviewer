"""
Export a clean subset of papers with reviews from the Gen-Review SQLite database.

Example usage:
    python -m reviewer_sim.ingest.export_review_subset \\
        --db-path data/gen_review.db \\
        --out-path outputs/review_subset.jsonl \\
        --n 200 \\
        --seed 42 \\
        --min-year 2021 \\
        --min-review-chars 50 \\
        --year 2023 \\
        --exclude-decisions "Withdrawn,Desk Reject,Invite to Workshop"

Filters applied:
    - Only papers with non-empty review text (main_review, falling back to
      summary_of_the_review for 2023+ where main_review is empty)
    - Only papers from >= min-year (based on when_submitted or detected year column)
    - Optionally only papers from exact --year
    - Optionally exclude specific decision values
    - Only reviews with >= min-review-chars after whitespace normalization
    - Drops rows with missing paper_id

Column semantics (ICLR OpenReview):
    - main_review:             full review text (populated for <=2022)
    - summary:                 reviewer's summary OF the paper (not a review)
    - summary_of_the_review:   short review by the human reviewer (populated for 2023+)

Output schema per line:
    {
        "paper_id": "<str>",
        "title": "<str>",
        "abstract": "<str>",
        "pdf_url": "<str or null>",
        "primary_area": "<str>",
        "year": <int or null>,
        "decision": "<str or null>",
        "reviews": {
            "count": <int>,  # Number of human reviewers
            "rating": {
                "values": [<float>, ...],  # Individual reviewer scores
                "mean": <float>,           # Average across reviewers
                "median": <float>,
                "std": <float>
            },
            "confidence": {...},  # Same structure for each dimension
            "correctness": {...},
            "technical_novelty_and_significance": {...},
            "empirical_novelty_and_significance": {...},
            "all_reviews": [  # Full individual reviews for inspection
                {
                    "reviewer_id": "<str>",
                    "main_review": "<str>",
                    "rating": <float>,
                    "confidence": <float>,
                    ...
                },
                ...
            ]
        },
        "meta": {
            "source": "gen_review_sqlite",
            "filters": {...},
            "exported_at": "<ISO8601>"
        }
    }
"""

import argparse
import json
import random
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Optional


# Priority order for year/date columns
YEAR_COLUMN_PRIORITY = [
    ("year", "int"),
    ("submission_year", "int"),
    ("when_submitted", "int"),  # In this DB, it's actually a year int
    ("created_at", "timestamp"),
    ("submitted_at", "timestamp"),
    ("decision_date", "timestamp"),
]

# Numerical review columns to export alongside review text.
# Canonical list — metrics.py and providers.py import from here.
SCORE_COLUMNS = [
    "rating",
    "confidence",
    "correctness",
    "technical_novelty_and_significance",
    "empirical_novelty_and_significance",
]


@dataclass
class DropStats:
    null_or_empty_review: int = 0
    pre_min_year: int = 0
    excluded_decision: int = 0
    missing_paper_id: int = 0
    too_short: int = 0
    bad_date: int = 0
    total_candidates: int = 0
    kept: int = 0
    review_lengths: list = field(default_factory=list)
    years: list = field(default_factory=list)


def detect_year_column(cursor: sqlite3.Cursor) -> Optional[tuple[str, str]]:
    """Detect which year/date column exists in SUBMISSION table."""
    cursor.execute("PRAGMA table_info(SUBMISSION)")
    columns = {row[1].lower() for row in cursor.fetchall()}

    for col_name, col_type in YEAR_COLUMN_PRIORITY:
        if col_name.lower() in columns:
            return (col_name, col_type)
    return None


def parse_year_from_value(value, col_type: str) -> Optional[int]:
    """Parse year from column value based on column type."""
    if value is None:
        return None

    if col_type == "int":
        try:
            year = int(value)
            if 1900 <= year <= 2100:
                return year
        except (ValueError, TypeError):
            pass
        return None

    # Timestamp/string parsing
    if col_type == "timestamp":
        val_str = str(value)
        match = re.match(r"(\d{4})", val_str)
        if match:
            year = int(match.group(1))
            if 1900 <= year <= 2100:
                return year
    return None


def parse_leading_number(value: object) -> Optional[float]:
    """Extract leading number from strings like '8: Top 50% ...'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", value)
        if m:
            return float(m.group(1))
    return None


def normalize_text(text: Optional[str]) -> str:
    """Strip and collapse multiple whitespace/newlines."""
    if text is None:
        return ""
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _detect_score_columns(cursor: sqlite3.Cursor) -> list[str]:
    """Return the subset of SCORE_COLUMNS that exist in the REVIEW table."""
    cursor.execute("PRAGMA table_info(REVIEW)")
    existing = {row[1].lower() for row in cursor.fetchall()}
    return [c for c in SCORE_COLUMNS if c.lower() in existing]


def export_review_subset(
    db_path: Path,
    out_path: Path,
    n: int = 200,
    seed: int = 42,
    min_year: Optional[int] = None,
    year: Optional[int] = None,
    exclude_decisions: Optional[list[str]] = None,
    min_review_chars: int = 50,
    allow_missing_year_filter: bool = False,
    keep_bad_dates: bool = False,
) -> DropStats:
    """Export a clean subset of papers with reviews.

    Parameters
    ----------
    year : optional int
        If set, only export papers from this exact year.
    exclude_decisions : optional list[str]
        Decision values to exclude (e.g. ["Withdrawn", "Desk Reject"]).
    """
    stats = DropStats()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Detect year column
    year_col_info = detect_year_column(cursor)
    year_col = None
    year_col_type = None

    if year_col_info:
        year_col, year_col_type = year_col_info
        print(f"Using year column: {year_col} (type: {year_col_type})")
    else:
        if (min_year is not None or year is not None) and not allow_missing_year_filter:
            raise ValueError(
                "No year/date column found in SUBMISSION table. "
                "Pass --allow-missing-year-filter to export without year filtering."
            )
        print("Warning: No year column found. Year filtering disabled.")

    # Detect available score columns
    available_scores = _detect_score_columns(cursor)
    if available_scores:
        print(f"Score columns found: {available_scores}")
    else:
        print("Warning: No score columns found in REVIEW table.")

    # Build query to fetch ALL reviews for each paper
    # (We'll aggregate them later, not cherry-pick one reviewer)
    year_select = f", s.{year_col}" if year_col else ""
    score_select = "".join(f", r.{c}" for c in available_scores)
    review_expr = (
        "COALESCE(NULLIF(TRIM(r.main_review), ''), "
        "NULLIF(TRIM(r.summary_of_the_review), ''))"
    )
    query = f"""
        SELECT
            s.id as paper_id,
            s.title,
            s.abstract,
            s.primary_area,
            s.decision,
            s.pdf as pdf_url,
            r.reviewer_id,
            {review_expr} as review_text,
            r.summary as paper_summary
            {score_select}
            {year_select}
        FROM REVIEW r
        JOIN SUBMISSION s ON r.paper_id = s.id
        WHERE {review_expr} IS NOT NULL
        ORDER BY s.id, r.reviewer_id
    """

    # Count total joined rows (including empty reviews) for accurate stats
    count_query = """
        SELECT COUNT(DISTINCT r.paper_id) FROM REVIEW r
        JOIN SUBMISSION s ON r.paper_id = s.id
    """
    cursor.execute(count_query)
    total_papers = cursor.fetchone()[0]

    cursor.execute(query)
    all_reviews = cursor.fetchall()
    conn.close()

    stats.total_candidates = total_papers

    # Group reviews by paper_id
    papers_dict: dict = {}
    for row in all_reviews:
        idx = 0
        paper_id = row[idx]; idx += 1
        title = row[idx]; idx += 1
        abstract = row[idx]; idx += 1
        primary_area = row[idx]; idx += 1
        decision = row[idx]; idx += 1
        pdf_url = row[idx]; idx += 1
        reviewer_id = row[idx]; idx += 1
        review_text = row[idx]; idx += 1
        paper_summary = row[idx]; idx += 1

        score_raw: dict[str, object] = {}
        for col in available_scores:
            score_raw[col] = row[idx]; idx += 1

        year_val = None
        if year_col:
            year_val = row[idx]; idx += 1

        if paper_id not in papers_dict:
            papers_dict[paper_id] = {
                "paper_id": paper_id,
                "title": title,
                "abstract": abstract,
                "primary_area": primary_area,
                "decision": decision,
                "pdf_url": pdf_url,
                "year": year_val,
                "reviews": []
            }

        papers_dict[paper_id]["reviews"].append({
            "reviewer_id": reviewer_id,
            "review_text": review_text,
            "paper_summary": paper_summary,
            "scores": score_raw
        })

    print(f"Total papers with reviews: {len(papers_dict)}")

    null_or_empty_count = 0

    # Normalise exclude_decisions for case-insensitive matching
    excluded_set: set[str] = set()
    if exclude_decisions:
        excluded_set = {d.strip().lower() for d in exclude_decisions}

    # Process and filter — now aggregate reviews per paper
    from statistics import mean, stdev

    candidates = []
    for paper_id, paper_data in papers_dict.items():
        # Check paper_id
        if not paper_id or not str(paper_id).strip():
            stats.missing_paper_id += 1
            continue

        decision = paper_data["decision"]

        # Decision filter
        if excluded_set:
            dec_str = (decision or "").strip().lower()
            if dec_str and dec_str in excluded_set:
                stats.excluded_decision += 1
                continue

        # Parse year
        year_int = None
        year_val = paper_data["year"]
        if year_col:
            year_int = parse_year_from_value(year_val, year_col_type)
            if year_int is None and year_val is not None:
                if not keep_bad_dates:
                    stats.bad_date += 1
                    continue

        # Exact year filter
        if year is not None and year_int is not None:
            if year_int != year:
                stats.pre_min_year += 1
                continue

        # Min year filter
        if min_year is not None and year_int is not None:
            if year_int < min_year:
                stats.pre_min_year += 1
                continue

        # Aggregate reviews: check that we have at least one non-empty review
        reviews = paper_data["reviews"]
        has_valid_review = False
        for review in reviews:
            clean_review = normalize_text(review["review_text"])
            if len(clean_review) >= min_review_chars:
                has_valid_review = True
                break

        if not has_valid_review:
            stats.too_short += 1
            continue

        # Clean other fields
        clean_title = normalize_text(paper_data["title"])
        clean_abstract = normalize_text(paper_data["abstract"])
        clean_primary_area = normalize_text(paper_data["primary_area"]) or "general"
        clean_decision = normalize_text(decision) or None

        # Aggregate scores across all reviewers
        aggregated_scores: dict[str, dict] = {}
        all_individual_reviews = []

        for score_col in available_scores:
            values = []
            for review in reviews:
                val = parse_leading_number(review["scores"].get(score_col))
                if val is not None:
                    values.append(val)

            if values:
                aggregated_scores[score_col] = {
                    "values": values,
                    "mean": mean(values),
                    "median": median(values),
                    "std": stdev(values) if len(values) > 1 else 0.0,
                    "count": len(values)
                }
            else:
                aggregated_scores[score_col] = {
                    "values": [],
                    "mean": None,
                    "median": None,
                    "std": None,
                    "count": 0
                }

        # Build individual reviews for inspection
        for review in reviews:
            parsed_scores: dict[str, dict] = {}
            for col in available_scores:
                raw_val = review["scores"].get(col)
                raw_str = str(raw_val) if raw_val is not None else ""
                parsed_scores[col] = {
                    "raw": raw_str,
                    "value": parse_leading_number(raw_val),
                }

            all_individual_reviews.append({
                "reviewer_id": review["reviewer_id"],
                "main_review": normalize_text(review["review_text"]),
                "paper_summary": normalize_text(review["paper_summary"]) or None,
                "scores": parsed_scores,
            })

        candidates.append({
            "paper_id": str(paper_id).strip(),
            "title": clean_title,
            "abstract": clean_abstract,
            "pdf_url": normalize_text(paper_data["pdf_url"]) or None,
            "primary_area": clean_primary_area,
            "decision": clean_decision,
            "year": year_int,
            "reviews": {
                "count": len(all_individual_reviews),
                "aggregated_scores": aggregated_scores,
                "all_individual_reviews": all_individual_reviews,
            }
        })

    print(f"Candidates after filtering: {len(candidates)}")

    # Deterministic shuffle and sample
    rng = random.Random(seed)
    rng.shuffle(candidates)
    selected = candidates[:n]

    stats.kept = len(selected)

    # Build output
    exported_at = datetime.now(timezone.utc).isoformat()
    meta_filters: dict = {
        "min_year": min_year,
        "year": year,
        "exclude_decisions": list(excluded_set) if excluded_set else None,
        "min_review_chars": min_review_chars,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in selected:
            # Track first review length for stats
            if rec["reviews"]["all_individual_reviews"]:
                first_review_len = len(rec["reviews"]["all_individual_reviews"][0]["main_review"])
                stats.review_lengths.append(first_review_len)

            if rec["year"] is not None:
                stats.years.append(rec["year"])

            # Build output record with aggregated reviews
            reviews_obj: dict = {
                "count": rec["reviews"]["count"],
            }

            # Add aggregated scores
            for score_col, agg_data in rec["reviews"]["aggregated_scores"].items():
                reviews_obj[score_col] = agg_data

            # Add all individual reviews for inspection
            reviews_obj["all_reviews"] = rec["reviews"]["all_individual_reviews"]

            output_record = {
                "paper_id": rec["paper_id"],
                "title": rec["title"],
                "abstract": rec["abstract"],
                "pdf_url": rec.get("pdf_url"),
                "primary_area": rec["primary_area"],
                "decision": rec["decision"],
                "year": rec["year"],
                "reviews": reviews_obj,
                "meta": {
                    "source": "gen_review_sqlite",
                    "filters": meta_filters,
                    "exported_at": exported_at,
                },
            }
            f.write(json.dumps(output_record, ensure_ascii=False) + "\n")

    return stats


def print_summary(stats: DropStats) -> None:
    """Print export summary statistics."""
    print("\n" + "=" * 50)
    print("EXPORT SUMMARY")
    print("=" * 50)
    print(f"Total joined rows (pre-filters): {stats.total_candidates}")
    print(f"Kept: {stats.kept}")
    print("\nDropped by reason:")
    print(f"  - null_or_empty_review: {stats.null_or_empty_review}")
    print(f"  - pre_min_year: {stats.pre_min_year}")
    print(f"  - excluded_decision: {stats.excluded_decision}")
    print(f"  - missing_paper_id: {stats.missing_paper_id}")
    print(f"  - too_short: {stats.too_short}")
    print(f"  - bad_date: {stats.bad_date}")

    if stats.review_lengths:
        sorted_lens = sorted(stats.review_lengths)
        p95_idx = int(len(sorted_lens) * 0.95)
        print(f"\nReview length stats (kept):")
        print(f"  - min: {min(sorted_lens)}")
        print(f"  - median: {median(sorted_lens):.0f}")
        print(f"  - p95: {sorted_lens[p95_idx]}")

    if stats.years:
        from collections import Counter
        year_counts = Counter(stats.years)
        print(f"\nYear distribution (kept):")
        print(f"  - min: {min(stats.years)}, max: {max(stats.years)}")
        print("  - top counts:")
        for y, count in year_counts.most_common(5):
            print(f"      {y}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a clean subset of papers with reviews from Gen-Review SQLite."
    )
    parser.add_argument("--db-path", type=Path, default=Path("data/gen_review.db"), help="Path to SQLite database")
    parser.add_argument("--out-path", type=Path, default=Path("outputs/review_subset.jsonl"), help="Output JSONL path")
    parser.add_argument("--n", type=int, default=120, help="Number of samples to export")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic sampling")
    parser.add_argument("--min-year", type=int, default=None, help="Minimum year filter (e.g., 2021)")
    parser.add_argument("--year", type=int, default=None, help="Exact year filter (e.g., 2023)")
    parser.add_argument("--exclude-decisions", type=str, default=None,
                        help='Comma-separated decisions to exclude (e.g., "Withdrawn,Desk Reject,Invite to Workshop")')
    parser.add_argument("--min-review-chars", type=int, default=50, help="Min review length in characters after normalization")
    parser.add_argument("--allow-missing-year-filter", action="store_true", help="Allow export without year filtering")
    parser.add_argument("--keep-bad-dates", action="store_true", help="Keep rows with unparseable dates (year will be null)")

    args = parser.parse_args()

    if not args.db_path.exists():
        raise FileNotFoundError(f"Database not found: {args.db_path}")

    exclude_decisions = None
    if args.exclude_decisions:
        exclude_decisions = [d.strip() for d in args.exclude_decisions.split(",")]

    print(f"Exporting from: {args.db_path}")
    print(f"Output to: {args.out_path}")
    print(f"Samples: {args.n}, Seed: {args.seed}")
    if args.min_year:
        print(f"Min year: {args.min_year}")
    if args.year:
        print(f"Exact year: {args.year}")
    if exclude_decisions:
        print(f"Excluding decisions: {exclude_decisions}")
    print(f"Min review chars: {args.min_review_chars}")

    stats = export_review_subset(
        db_path=args.db_path, out_path=args.out_path, n=args.n, seed=args.seed,
        min_year=args.min_year, year=args.year, exclude_decisions=exclude_decisions,
        min_review_chars=args.min_review_chars,
        allow_missing_year_filter=args.allow_missing_year_filter,
        keep_bad_dates=args.keep_bad_dates,
    )

    print_summary(stats)
    print(f"\nExported {stats.kept} records to: {args.out_path}")


if __name__ == "__main__":
    main()
