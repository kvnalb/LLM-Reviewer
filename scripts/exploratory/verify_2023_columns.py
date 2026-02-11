"""
Verify 2023 columns in data/gen_review.db:
- summary vs summary_of_the_review from REVIEW
- Sample rating, confidence, correctness (raw)
- generated from GENAI_REVIEW (type='neutral')
- Counts for summary_of_the_review and GENAI_REVIEW neutral.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gen_review.db"


def get_year_col(cursor) -> str | None:
    cursor.execute("PRAGMA table_info(SUBMISSION)")
    cols = {row[1].lower() for row in cursor.fetchall()}
    for c in ("year", "submission_year", "when_submitted"):
        if c in cols:
            return c
    return None


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    year_col = get_year_col(cur)
    if not year_col:
        print("No year column found in SUBMISSION (year, submission_year, when_submitted).", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # 2023 papers with Accept/Reject
    cur.execute(
        f"""
        SELECT id FROM SUBMISSION
        WHERE {year_col} = 2023
          AND TRIM(COALESCE(decision, '')) IN ('Accept', 'Reject')
        """
    )
    paper_ids = [row["id"] for row in cur.fetchall()]
    if not paper_ids:
        print("No 2023 Accept/Reject papers found.")
        conn.close()
        return

    # 3 random papers
    import random
    random.seed(42)
    sample_ids = random.sample(paper_ids, min(3, len(paper_ids)))

    print("=" * 60)
    print("1. First 200 chars: summary_of_the_review vs summary (REVIEW)")
    print("=" * 60)
    for pid in sample_ids:
        cur.execute(
            """
            SELECT paper_id, summary_of_the_review, summary
            FROM REVIEW WHERE paper_id = ?
            LIMIT 1
            """,
            (pid,),
        )
        row = cur.fetchone()
        if not row:
            print(f"\nPaper {pid}: no REVIEW row")
            continue
        sotr = (row["summary_of_the_review"] or "")[:200]
        summ = (row["summary"] or "")[:200]
        print(f"\nPaper: {pid}")
        print(f"  summary_of_the_review (200): {sotr!r}")
        print(f"  summary (200):               {summ!r}")

    print("\n" + "=" * 60)
    print("2. Sample rating, confidence, correctness (raw strings)")
    print("=" * 60)
    cur.execute(
        f"""
        SELECT rating, confidence, correctness
        FROM REVIEW r
        JOIN SUBMISSION s ON r.paper_id = s.id
        WHERE s.{year_col} = 2023 AND TRIM(COALESCE(s.decision, '')) IN ('Accept', 'Reject')
          AND (r.rating IS NOT NULL OR r.confidence IS NOT NULL OR r.correctness IS NOT NULL)
        LIMIT 5
        """
    )
    for row in cur.fetchall():
        print(f"  rating: {row['rating']!r}")
        print(f"  confidence: {row['confidence']!r}")
        print(f"  correctness: {row['correctness']!r}")
        print()

    print("=" * 60)
    print("3. First 200 chars of generated from GENAI_REVIEW (type='neutral') for same 3 papers")
    print("=" * 60)
    # Check if GENAI_REVIEW exists and has expected columns
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='GENAI_REVIEW'")
    if not cur.fetchone():
        print("GENAI_REVIEW table not found.")
    else:
        cur.execute("PRAGMA table_info(GENAI_REVIEW)")
        gen_cols = {row[1] for row in cur.fetchall()}
        paper_col = "paper_id" if "paper_id" in gen_cols else next((c for c in gen_cols if "paper" in c.lower() or c == "id"), None)
        gen_col = "generated" if "generated" in gen_cols else next((c for c in gen_cols if "generated" in c.lower() or c == "text"), None)
        if not paper_col or not gen_col:
            print(f"GENAI_REVIEW columns: {gen_cols}; could not find paper id or generated column.")
        else:
            for pid in sample_ids:
                cur.execute(
                    f"SELECT {gen_col} FROM GENAI_REVIEW WHERE {paper_col} = ? AND TRIM(COALESCE(type, '')) = 'neutral' LIMIT 1",
                    (pid,),
                )
                row = cur.fetchone()
                if not row:
                    print(f"\nPaper {pid}: no GENAI_REVIEW neutral row")
                else:
                    gen = (row[gen_col] or "")[:200]
                    print(f"\nPaper {pid}: {gen!r}")

    print("\n" + "=" * 60)
    print("4. Counts (2023 Accept/Reject papers)")
    print("=" * 60)
    # Papers with at least one non-empty summary_of_the_review
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT s.id) AS n
        FROM SUBMISSION s
        JOIN REVIEW r ON r.paper_id = s.id
        WHERE s.{year_col} = 2023
          AND TRIM(COALESCE(s.decision, '')) IN ('Accept', 'Reject')
          AND r.summary_of_the_review IS NOT NULL AND TRIM(r.summary_of_the_review) != ''
        """
    )
    with_sotr = cur.fetchone()["n"]
    print(f"  With at least one non-empty summary_of_the_review: {with_sotr}")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='GENAI_REVIEW'")
    if not cur.fetchone():
        print("  With GENAI_REVIEW neutral row: (table missing)")
    else:
        cur.execute("PRAGMA table_info(GENAI_REVIEW)")
        gen_cols = {row[1] for row in cur.fetchall()}
        paper_col = "paper_id" if "paper_id" in gen_cols else next((c for c in gen_cols if "paper" in c.lower() or c == "id"), None)
        if not paper_col:
            print("  With GENAI_REVIEW neutral row: (no paper column)")
        else:
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT g.{paper_col}) AS n
                FROM GENAI_REVIEW g
                JOIN SUBMISSION s ON s.id = g.{paper_col}
                WHERE s.{year_col} = 2023
                  AND TRIM(COALESCE(s.decision, '')) IN ('Accept', 'Reject')
                  AND TRIM(COALESCE(g.type, '')) = 'neutral'
                """
            )
            with_neutral = cur.fetchone()["n"]
            print(f"  With at least one GENAI_REVIEW neutral row: {with_neutral}")

    conn.close()


if __name__ == "__main__":
    main()
