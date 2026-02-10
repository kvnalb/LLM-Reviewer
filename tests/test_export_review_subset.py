"""
Tests for the export_review_subset module.

Run with: pytest tests/test_export_review_subset.py -v
"""

import json
import sqlite3
from pathlib import Path

import pytest

from reviewer_sim.ingest.export_review_subset import (
    export_review_subset,
    parse_leading_number,
    DropStats,
)


def create_test_db(db_path: Path) -> None:
    """Create a test database with SUBMISSION and REVIEW tables.

    Includes score columns and decision values for filter testing.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE SUBMISSION (
            id TEXT PRIMARY KEY, paper_number INTEGER, title TEXT,
            abstract TEXT, tldr TEXT, primary_area TEXT, code_of_ethics TEXT,
            pdf TEXT, keywords TEXT, decision TEXT, when_submitted INTEGER,
            source_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE REVIEW (
            paper_id TEXT, reviewer_id TEXT, summary TEXT,
            soundness TEXT, presentation TEXT, contribution TEXT,
            strength TEXT, weaknesses TEXT, questions TEXT,
            flag_for_ethics_review TEXT, rating TEXT, confidence TEXT,
            correctness TEXT, technical_novelty_and_significance TEXT,
            empirical_novelty_and_significance TEXT, main_review TEXT,
            summary_of_the_review TEXT, binocular_score REAL,
            PRIMARY KEY (paper_id, reviewer_id)
        )
    """)

    submissions = [
        ("paper_2020_a", 1, "Old Paper", "Abstract A", 2020, "ML", "Accept"),
        ("paper_2021_b", 2, "Paper 2021 B", "Abstract B", 2021, "NLP", "Accept"),
        ("paper_2022_c", 3, "Paper 2022 C", "Abstract C", 2022, "CV", "Reject"),
        ("paper_empty_review", 4, "Paper Empty", "Abstract Empty", 2021, "ML", "Accept"),
        ("paper_2023_d", 5, "Paper 2023 D", "Abstract D", 2023, "ML", "Accept"),
        ("paper_2023_withdrawn", 6, "Withdrawn Paper", "Abstract W", 2023, "ML", "Withdrawn"),
    ]
    for pid, num, title, abstract, year, area, decision in submissions:
        cursor.execute(
            "INSERT INTO SUBMISSION (id, paper_number, title, abstract, when_submitted, primary_area, decision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, num, title, abstract, year, area, decision),
        )

    #                    (paper_id, reviewer_id,
    #                     main_review, summary_of_the_review, summary,
    #                     rating, confidence, correctness, tech_novelty, emp_novelty)
    reviews = [
        ("paper_2020_a", "r1",
         "This is a valid main_review for the old paper with enough characters to pass.",
         "Short review of old paper.", "Reviewer summary of the paper.",
         "6: Marginally above", "3: Fairly confident",
         "3: Some claims minor issues", "3: Significant somewhat new", "2: Only marginally significant"),
        ("paper_2021_b", "r2",
         "This is a valid main_review for paper B from 2021 with sufficient length.",
         "Short review of B.", "Reviewer summary of paper B.",
         "8: Top 50%", "4: Confident",
         "4: All claims well-supported", "4: Creative contributions", "3: Significant somewhat new"),
        ("paper_2022_c", "r3",
         "This is a valid main_review for paper C from 2022 with enough content.",
         "Short review of C.", "Reviewer summary of paper C.",
         "3: Clear rejection", "2: Willing to defend",
         "2: Several claims incorrect", "2: Only marginally significant", "Not applicable"),
        ("paper_empty_review", "r4",
         "", "", None,
         None, None, None, None, None),
        # 2023 paper: main_review is EMPTY, summary_of_the_review has the review
        ("paper_2023_d", "r5",
         "", "This is the short review for paper D from 2023 with enough chars for tests.",
         "Reviewer summary of paper D topic.",
         "5: Marginally below", "3: Fairly confident",
         "3: Some claims minor issues", "3: Significant somewhat new", "3: Significant somewhat new"),
        ("paper_2023_withdrawn", "r6",
         "", "Review for withdrawn paper, should be filtered by decision exclusion.",
         "Reviewer summary of withdrawn paper.",
         "5: Marginally below", "3: Fairly confident",
         "3: Minor issues", "2: Marginally significant", "2: Marginally significant"),
    ]
    for (pid, rid, main_review, sotr, summary,
         rating, confidence, correctness, tech_nov, emp_nov) in reviews:
        cursor.execute(
            "INSERT INTO REVIEW (paper_id, reviewer_id, main_review, summary_of_the_review, "
            "summary, rating, confidence, correctness, "
            "technical_novelty_and_significance, empirical_novelty_and_significance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, rid, main_review, sotr, summary,
             rating, confidence, correctness, tech_nov, emp_nov),
        )

    conn.commit()
    conn.close()


class TestParseLeadingNumber:
    def test_int_string(self) -> None:
        assert parse_leading_number("6: Marginally above") == 6.0

    def test_float_string(self) -> None:
        assert parse_leading_number("3.5: something") == 3.5

    def test_int(self) -> None:
        assert parse_leading_number(8) == 8.0

    def test_none(self) -> None:
        assert parse_leading_number(None) is None

    def test_non_numeric(self) -> None:
        assert parse_leading_number("Not applicable") is None

    def test_empty(self) -> None:
        assert parse_leading_number("") is None


class TestExportReviewSubset:
    def test_filters_old_papers_by_min_year(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        stats = export_review_subset(
            db_path=db_path, out_path=out_path, n=10, seed=42,
            min_year=2021, min_review_chars=10,
        )

        assert stats.pre_min_year == 1  # paper_2020_a

        with open(out_path) as f:
            records = [json.loads(line) for line in f]
        paper_ids = {r["paper_id"] for r in records}
        assert "paper_2020_a" not in paper_ids

    def test_deterministic_sampling(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out1 = tmp_path / "o1.jsonl"
        out2 = tmp_path / "o2.jsonl"
        create_test_db(db_path)

        export_review_subset(db_path=db_path, out_path=out1, n=1, seed=42, min_year=2021, min_review_chars=10)
        export_review_subset(db_path=db_path, out_path=out2, n=1, seed=42, min_year=2021, min_review_chars=10)

        with open(out1) as f:
            r1 = json.loads(f.readline())
        with open(out2) as f:
            r2 = json.loads(f.readline())
        assert r1["paper_id"] == r2["paper_id"]
        assert r1["review"] == r2["review"]

    def test_drops_empty_reviews(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(db_path=db_path, out_path=out_path, n=10, seed=42, min_review_chars=10)

        with open(out_path) as f:
            paper_ids = {json.loads(line)["paper_id"] for line in f}
        assert "paper_empty_review" not in paper_ids

    def test_filters_short_reviews(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        stats = export_review_subset(db_path=db_path, out_path=out_path, n=10, seed=42, min_review_chars=1000)
        assert stats.too_short >= 3
        assert stats.kept == 0

    def test_output_schema_includes_scores_and_paper_summary(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(db_path=db_path, out_path=out_path, n=1, seed=42, min_year=2021, min_review_chars=10)

        with open(out_path) as f:
            record = json.loads(f.readline())

        assert "paper_id" in record
        assert "decision" in record
        assert "review" in record
        review = record["review"]
        assert "main_review" in review
        assert "paper_summary" in review
        for col in ["rating", "confidence", "correctness",
                     "technical_novelty_and_significance",
                     "empirical_novelty_and_significance"]:
            assert col in review, f"Missing {col}"
            assert "raw" in review[col]
            assert "value" in review[col]

    def test_score_values_parsed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(db_path=db_path, out_path=out_path, n=10, seed=42, min_year=2021, min_review_chars=10)

        with open(out_path) as f:
            records = [json.loads(line) for line in f]

        rec_b = next((r for r in records if r["paper_id"] == "paper_2021_b"), None)
        if rec_b:
            assert rec_b["review"]["rating"]["value"] == 8.0
            assert rec_b["review"]["confidence"]["value"] == 4.0

        rec_c = next((r for r in records if r["paper_id"] == "paper_2022_c"), None)
        if rec_c:
            assert rec_c["review"]["empirical_novelty_and_significance"]["value"] is None

    def test_exclude_decisions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        stats = export_review_subset(
            db_path=db_path, out_path=out_path, n=10, seed=42,
            min_review_chars=10, exclude_decisions=["Withdrawn"],
        )

        with open(out_path) as f:
            paper_ids = {json.loads(line)["paper_id"] for line in f}
        assert "paper_2023_withdrawn" not in paper_ids
        assert stats.excluded_decision >= 1

    def test_exact_year_filter(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(db_path=db_path, out_path=out_path, n=10, seed=42, year=2023, min_review_chars=10)

        with open(out_path) as f:
            records = [json.loads(line) for line in f]
        for rec in records:
            assert rec["year"] == 2023

    def test_combined_year_and_decision_filter(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(
            db_path=db_path, out_path=out_path, n=10, seed=42,
            year=2023, exclude_decisions=["Withdrawn"], min_review_chars=10,
        )

        with open(out_path) as f:
            records = [json.loads(line) for line in f]
        assert len(records) == 1
        assert records[0]["paper_id"] == "paper_2023_d"

    def test_falls_back_to_summary_of_the_review(self, tmp_path: Path) -> None:
        """When main_review is empty, summary_of_the_review should be used."""
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(
            db_path=db_path, out_path=out_path, n=10, seed=42,
            year=2023, exclude_decisions=["Withdrawn"], min_review_chars=10,
        )

        with open(out_path) as f:
            rec = json.loads(f.readline())
        # paper_2023_d has empty main_review; review text should come from summary_of_the_review
        assert "short review for paper D" in rec["review"]["main_review"]

    def test_paper_summary_is_reviewer_summary_of_paper(self, tmp_path: Path) -> None:
        """The paper_summary field should contain the reviewer's summary OF the paper
        (from the 'summary' column), NOT the review text."""
        db_path = tmp_path / "test.db"
        out_path = tmp_path / "output.jsonl"
        create_test_db(db_path)

        export_review_subset(
            db_path=db_path, out_path=out_path, n=10, seed=42,
            year=2023, exclude_decisions=["Withdrawn"], min_review_chars=10,
        )

        with open(out_path) as f:
            rec = json.loads(f.readline())
        # paper_summary should be from the 'summary' column (reviewer's summary OF paper)
        assert rec["review"]["paper_summary"] is not None
        assert "paper D topic" in rec["review"]["paper_summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
