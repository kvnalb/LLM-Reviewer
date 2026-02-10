"""
Evaluation metrics for comparing generated reviews to human reviews.

Primary metrics are numerical:
  - Per-dimension absolute error for each of the 5 score columns
  - Mean absolute error (MAE) across scored dimensions
  - Decision agreement (whether rating falls on same side of accept threshold)

Text-based metrics (TF-IDF cosine, keyword Jaccard) are retained behind an
optional flag for reference but are *not* the primary evaluation.
"""

import re
from typing import Dict, Optional

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

SCORE_DIMENSIONS = SCORE_COLUMNS

DEFAULT_ACCEPT_THRESHOLD = 6


def parse_numeric_rating(value: object) -> Optional[float]:
    """Extract the leading number from values like ``'8: Top 50% ...'``."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", value)
        if match:
            return float(match.group(1))
    return None


def _extract_human_score(review: Dict, dim: str) -> Optional[float]:
    """Get parsed numeric value for *dim* from the human review dict.

    Handles both the new schema (``review[dim]["value"]``) and a flat
    fallback (``review[dim]``).
    """
    entry = review.get(dim)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return parse_numeric_rating(entry.get("value"))
    return parse_numeric_rating(entry)


def evaluate(
    example: Dict,
    generated: Dict,
    accept_threshold: int = DEFAULT_ACCEPT_THRESHOLD,
    include_text_metrics: bool = False,
) -> Dict:
    """Compare *generated* review scores against human scores in *example*.

    Parameters
    ----------
    example : dict
        A record from the exported JSONL.  Human scores live under
        ``example["review"][dim]`` (either ``{"raw": ..., "value": ...}``
        or a plain number).
    generated : dict
        Output of a generator.  Scores are top-level keys.
    accept_threshold : int
        Rating >= this is "accept-side".
    include_text_metrics : bool
        If True, also compute tfidf_cosine and keyword_jaccard (slow).

    Returns
    -------
    dict with per-dimension abs errors, mae, decision_agree, and optionally
    text metrics.
    """
    human_review = example.get("review", {}) or {}

    result: Dict = {}
    abs_errors: list[float] = []

    for dim in SCORE_DIMENSIONS:
        human_val = _extract_human_score(human_review, dim)
        gen_val = parse_numeric_rating(generated.get(dim))

        if human_val is not None and gen_val is not None:
            err = abs(human_val - gen_val)
            result[f"{dim}_abs_err"] = err
            abs_errors.append(err)
        else:
            result[f"{dim}_abs_err"] = None

    result["mae"] = sum(abs_errors) / len(abs_errors) if abs_errors else None

    human_rating = _extract_human_score(human_review, "rating")
    gen_rating = parse_numeric_rating(generated.get("rating"))
    if human_rating is not None and gen_rating is not None:
        result["decision_agree"] = (
            (human_rating >= accept_threshold) == (gen_rating >= accept_threshold)
        )
    else:
        result["decision_agree"] = None

    if include_text_metrics:
        human_text = human_review.get("main_review", "") or ""
        gen_text = generated.get("text", "") or ""
        result["tfidf_cosine"] = tfidf_cosine(human_text, gen_text) if human_text and gen_text else 0.0
        result["keyword_jaccard"] = keyword_jaccard(human_text, gen_text) if human_text and gen_text else 0.0

    return result


# ------------------------------------------------------------------
# Legacy text helpers (kept for optional use)
# ------------------------------------------------------------------

def tfidf_cosine(a: str, b: str) -> float:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vect = TfidfVectorizer(stop_words="english")
    X = vect.fit_transform([a, b])
    sim = cosine_similarity(X[0], X[1])[0][0]
    return float(sim)


def keyword_jaccard(a: str, b: str) -> float:
    def toks(s: str) -> set[str]:
        return {t.lower() for t in s.split() if t.isalpha() and len(t) > 3}
    A, B = toks(a), toks(b)
    if not A and not B:
        return 0.0
    return float(len(A & B) / max(1, len(A | B)))
