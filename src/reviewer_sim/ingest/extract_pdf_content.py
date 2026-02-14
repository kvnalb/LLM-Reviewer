#!/usr/bin/env python3
"""
Standalone script to extract PDF content from OpenReview papers.

This is a SEPARATE step from review generation. Run this ONCE to enrich the dataset,
then use the enriched JSONL for all subsequent experiments.

Usage:
    python -m reviewer_sim.ingest.extract_pdf_content \\
        --input outputs/review_subset.jsonl \\
        --output outputs/review_subset_with_pdf.jsonl \\
        --mode sections \\
        --cache data/pdf_cache

Environment variables:
    (none required)
"""

import argparse
import json
from pathlib import Path
from tqdm import tqdm

from .pdf_extractor import PDFExtractor
from .load_jsonl import load_jsonl


def main():
    parser = argparse.ArgumentParser(
        description="Extract PDF content from papers enriches a review subset JSONL"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSONL (e.g., review_subset.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL with PDF content enriched",
    )
    parser.add_argument(
        "--mode",
        choices=["sections", "fulltext"],
        default="sections",
        help="Extraction mode: 'sections' (smart) or 'fulltext' (complete)",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/pdf_cache"),
        help="Directory for PDF cache",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=6000,
        help="Target token budget",
    )
    args = parser.parse_args()

    # Load input data
    papers = load_jsonl(args.input)
    print(f"Loaded {len(papers)} papers from {args.input}")

    # Initialize extractor
    extractor = PDFExtractor(
        cache_dir=args.cache,
        extraction_mode=args.mode,
        max_tokens=args.max_tokens,
    )

    # Process each paper
    results = []
    failures = []

    for paper in tqdm(papers, desc="Extracting PDFs"):
        paper_id = paper["paper_id"]
        pdf_url = paper.get("pdf_url")

        if not pdf_url:
            print(f"WARNING: No pdf_url for {paper_id}, skipping")
            failures.append({"paper_id": paper_id, "error": "No pdf_url in data"})
            continue

        # Extract PDF content
        pdf_data = extractor.extract_paper(
            paper_id=paper_id,
            pdf_url=pdf_url,
            title=paper.get("title", ""),
            abstract=paper.get("abstract", ""),
        )

        # Add to paper record
        paper["pdf_content"] = pdf_data
        results.append(paper)

        # Track failures for manual review
        if not pdf_data["extraction_metadata"]["success"]:
            failures.append(
                {
                    "paper_id": paper_id,
                    "pdf_url": pdf_url,
                    "error": pdf_data["extraction_metadata"]["error"],
                }
            )

    # Write enriched output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for paper in results:
            f.write(json.dumps(paper, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(results)} papers to {args.output}")

    # Report extraction stats
    success_count = sum(
        1 for r in results if r["pdf_content"]["extraction_metadata"]["success"]
    )
    print(f"\nExtraction Summary:")
    print(f"  Success: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    print(f"  Failures: {len(failures)}")

    if failures:
        failure_log = args.output.parent / "pdf_extraction_failures.jsonl"
        with open(failure_log, "w", encoding="utf-8") as f:
            for fail in failures:
                f.write(json.dumps(fail, ensure_ascii=False) + "\n")
        print(f"\nFailed extractions logged to: {failure_log}")
        print("MANUAL ACTION REQUIRED: Review and fix failed PDFs before proceeding")


if __name__ == "__main__":
    main()
