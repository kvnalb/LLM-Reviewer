"""
Evaluation metrics for comparing generated reviews to human reviews.

Primary metrics are scale-aware:
  - Normalized MAE (NMAE): error divided by each dimension's range
  - RMSE: root mean square error
  - Spearman correlation: rank correlation (robust to scale differences)
  - Decision agreement: whether rating falls on same side of accept threshold
  - Per-dimension normalized error: shows which dimensions are harder

Text-based metrics (TF-IDF cosine, keyword Jaccard) are retained behind an
optional flag for reference but are *not* the primary evaluation.
"""

import re
from typing import Dict, Optional

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

SCORE_DIMENSIONS = SCORE_COLUMNS

# Scale ranges for each dimension (used for normalization)
SCORE_RANGES = {
    "rating": (1, 10),  # range = 9
    "confidence": (1, 5),  # range = 4
    "correctness": (1, 4),  # range = 3
    "technical_novelty_and_significance": (1, 4),  # range = 3
    "empirical_novelty_and_significance": (1, 4),  # range = 3
}

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


def _normalized_error(abs_error: float, dim: str) -> Optional[float]:
    """Normalize error by the range of the dimension.

    NMAE (Normalized Mean Absolute Error) = error / range
    This makes errors comparable across different scales.

    For example:
    - Error of 1 point on rating (range 9): 1/9 = 0.11
    - Error of 1 point on confidence (range 4): 1/4 = 0.25
    - Error of 1 point on correctness (range 3): 1/3 = 0.33
    """
    if dim not in SCORE_RANGES:
        return None
    min_val, max_val = SCORE_RANGES[dim]
    range_val = max_val - min_val
    return abs_error / range_val if range_val > 0 else None


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
    dict with per-dimension errors, robust metrics (NMAE, RMSE, Spearman),
    decision_agree, and optionally text metrics.
    """
    human_review = example.get("review", {}) or {}

    result: Dict = {}
    abs_errors: list[float] = []
    normalized_errors: list[float] = []
    squared_errors: list[float] = []

    # For correlation calculation
    human_vals: list[float] = []
    gen_vals: list[float] = []

    for dim in SCORE_DIMENSIONS:
        human_val = _extract_human_score(human_review, dim)
        gen_val = parse_numeric_rating(generated.get(dim))

        if human_val is not None and gen_val is not None:
            err = abs(human_val - gen_val)
            result[f"{dim}_abs_err"] = err
            abs_errors.append(err)

            # Normalized error (scale-aware)
            norm_err = _normalized_error(err, dim)
            if norm_err is not None:
                result[f"{dim}_norm_err"] = norm_err
                normalized_errors.append(norm_err)

            # Squared error (for RMSE)
            squared_errors.append(err ** 2)

            # Track for correlation
            human_vals.append(human_val)
            gen_vals.append(gen_val)
        else:
            result[f"{dim}_abs_err"] = None
            result[f"{dim}_norm_err"] = None

    # Primary metric: Normalized MAE (scale-aware)
    result["nmae"] = sum(normalized_errors) / len(normalized_errors) if normalized_errors else None

    # Secondary metric: RMSE (penalizes larger errors)
    result["rmse"] = (sum(squared_errors) / len(squared_errors)) ** 0.5 if squared_errors else None

    # Legacy metric: MAE (kept for backward compatibility, but NMAE is preferred)
    result["mae"] = sum(abs_errors) / len(abs_errors) if abs_errors else None

    # Correlation: Spearman rank correlation (robust to scale)
    if len(human_vals) >= 3:  # Need at least 3 points for correlation
        try:
            from scipy.stats import spearmanr
            import math
            corr, pval = spearmanr(human_vals, gen_vals)
            result["spearman_corr"] = float(corr) if not math.isnan(corr) else None
            result["spearman_pval"] = float(pval) if not math.isnan(pval) else None
        except (ImportError, Exception):
            # Fallback if scipy not available
            result["spearman_corr"] = None
            result["spearman_pval"] = None
    else:
        result["spearman_corr"] = None
        result["spearman_pval"] = None

    # Decision agreement (accept vs reject)
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
