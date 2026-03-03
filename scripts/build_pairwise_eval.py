"""
Build pairwise evaluation dataset for ranking analysis.

Groups papers into three buckets by mean human rating:
  - low  (≤4)   : clear rejects
  - mid  (5–7)  : borderline / accepted
  - high (≥8)   : strong accepts

Creates cross-bucket pairs only — within-bucket comparisons are excluded
because ground truth is unreliable when papers have similar mean ratings.
Papers in the grey zone (4.01–4.99, 7.01–7.99) are excluded entirely.

Each pair includes:
  - comparison_type, score_gap, ground_truth ("b" = higher bucket)
  - For each paper: id, bucket, mean/std rating, n_reviewers,
    title, abstract, tldr, primary_area, decision

NOTE: ground_truth is always "b" (higher bucket paper is always paper_b).
Randomize which paper is presented first when prompting the model to
avoid position bias.

Usage:
    python scripts/build_pairwise_eval.py [--out data/processed/pairwise_eval.jsonl]
"""

import argparse
import json
import sqlite3
from itertools import product

BUCKET_LABEL = {1: "low (≤4)", 2: "mid (5–7)", 3: "high (≥8)"}


def assign_bucket(mean: float) -> int | None:
    if mean <= 4:
        return 1
    elif 5 <= mean <= 7:
        return 2
    elif mean >= 8:
        return 3
    return None  # grey zone — excluded


def load_papers(subset_path: str) -> dict:
    papers = {}
    with open(subset_path) as f:
        for line in f:
            r = json.loads(line)
            papers[r["paper_id"]] = {
                "mean_rating": r["reviews"]["rating"]["mean"],
                "std_rating":  r["reviews"]["rating"].get("std"),
                "n_reviewers": r["reviews"]["rating"].get("count"),
                "decision":    r.get("decision"),
            }
    return papers


def load_metadata(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    meta = {
        row["id"]: dict(row)
        for row in con.execute(
            "SELECT id, title, abstract, tldr, primary_area, decision FROM SUBMISSION"
        )
    }
    con.close()
    return meta


def build_pairs(papers: dict, meta: dict) -> list[dict]:
    buckets: dict[int, list[str]] = {1: [], 2: [], 3: []}
    grey = []
    for pid, info in papers.items():
        b = assign_bucket(info["mean_rating"])
        if b is not None:
            buckets[b].append(pid)
        else:
            grey.append(pid)

    print(f"Bucket 1 (≤4):  {len(buckets[1])} papers")
    print(f"Bucket 2 (5–7): {len(buckets[2])} papers")
    print(f"Bucket 3 (≥8):  {len(buckets[3])} papers")
    print(f"Grey zone excluded: {len(grey)} papers")

    def entry(pid: str, bucket: int) -> dict:
        p = papers[pid]
        m = meta.get(pid, {})
        return {
            "paper_id":     pid,
            "bucket":       bucket,
            "bucket_label": BUCKET_LABEL[bucket],
            "mean_rating":  p["mean_rating"],
            "std_rating":   p["std_rating"],
            "n_reviewers":  p["n_reviewers"],
            "title":        m.get("title", ""),
            "abstract":     m.get("abstract", ""),
            "tldr":         m.get("tldr", ""),
            "primary_area": m.get("primary_area", ""),
            "decision":     p.get("decision") or m.get("decision", ""),
        }

    pairs = []
    for b_lo, b_hi in [(1, 2), (1, 3), (2, 3)]:
        for pid_a, pid_b in product(buckets[b_lo], buckets[b_hi]):
            m_a = papers[pid_a]["mean_rating"]
            m_b = papers[pid_b]["mean_rating"]
            pairs.append({
                "comparison_type": f"bucket{b_lo}_vs_bucket{b_hi}",
                "score_gap":       round(m_b - m_a, 3),
                "ground_truth":    "b",  # b is always the higher-bucket paper
                "paper_a":         entry(pid_a, b_lo),
                "paper_b":         entry(pid_b, b_hi),
            })

    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", default="outputs/review_subset.jsonl")
    parser.add_argument("--db",     default="data/gen_review.db")
    parser.add_argument("--out",    default="data/processed/pairwise_eval.jsonl")
    args = parser.parse_args()

    papers = load_papers(args.subset)
    meta   = load_metadata(args.db)
    pairs  = build_pairs(papers, meta)

    with open(args.out, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")

    print(f"\nWritten {len(pairs)} pairs to {args.out}")
    for ct in [f"bucket{a}_vs_bucket{b}" for a, b in [(1,2),(1,3),(2,3)]]:
        sub = [p for p in pairs if p["comparison_type"] == ct]
        gaps = [p["score_gap"] for p in sub]
        print(f"  {ct}: {len(sub)} pairs  "
              f"gap min={min(gaps):.2f}  mean={sum(gaps)/len(gaps):.2f}  max={max(gaps):.2f}")


if __name__ == "__main__":
    main()
