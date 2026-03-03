"""
Evaluation metrics for comparing generated reviews to human reviews.

Primary metrics are scale-aware (both human and LLM scores normalized to [0,1]):
  - Normalized MAE (NMAE): mean absolute error on [0,1] scale across dimensions
  - RMSE: root mean square error on [0,1] scale
  - Decision agreement: whether rating falls on same side of accept threshold
  - Per-dimension normalized error: shows which dimensions are harder

Human scores are on native ICLR scales (rating 1–10, others 1–4 or 1–5).
LLM scores are on the new 0–5 prompt scale.
Both are normalized to [0,1] before any error computation.

Text-based metrics (TF-IDF cosine, keyword Jaccard) are retained behind an
optional flag for reference but are *not* the primary evaluation.
"""

import re
from typing import Dict, Optional

from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

SCORE_DIMENSIONS = SCORE_COLUMNS

# Human score ranges on native ICLR scales
SCORE_RANGES = {
    "rating": (1, 10),
    "confidence": (1, 5),
    "correctness": (1, 4),
    "technical_novelty_and_significance": (1, 4),
    "empirical_novelty_and_significance": (1, 4),
}

# LLM output range (new 0–5 prompt)
LLM_SCORE_RANGE = (0.0, 5.0)

# Accept thresholds on their respective scales
HUMAN_ACCEPT_THRESHOLD = 6      # on 1–10 human scale
DEFAULT_ACCEPT_THRESHOLD = 3.0  # on 0–5 LLM scale (≈ 6/10)


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

    Handles multiple schemas:
    1. New aggregated schema: review[dim]["mean"] (average across reviewers)
    2. Old single-reviewer schema: review[dim]["value"]
    3. Flat fallback: review[dim]
    """
    entry = review.get(dim)
    if entry is None:
        return None

    # New aggregated schema: use mean score across all reviewers
    if isinstance(entry, dict):
        if "mean" in entry:  # New aggregated schema
            return parse_numeric_rating(entry.get("mean"))
        elif "value" in entry:  # Old single-reviewer schema
            return parse_numeric_rating(entry.get("value"))

    # Fallback
    return parse_numeric_rating(entry)


def _to_unit(value: float, lo: float, hi: float) -> float:
    """Clamp and normalize *value* from [lo, hi] to [0, 1]."""
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def evaluate(
    example: Dict,
    generated: Dict,
    accept_threshold: float = DEFAULT_ACCEPT_THRESHOLD,
    include_text_metrics: bool = False,
) -> Dict:
    """Compare *generated* review scores against human scores in *example*.

    Both human and LLM scores are normalized to [0, 1] before error
    computation, so NMAE and RMSE are directly comparable across dimensions
    regardless of their native scales.

    Parameters
    ----------
    example : dict
        A record from the exported JSONL.  Human scores live under:
        - New schema: ``example["reviews"][dim]`` with {"mean": ..., "values": [...], ...}
        - Old schema: ``example["review"][dim]`` with {"raw": ..., "value": ...}
    generated : dict
        Output of a generator. Scores are top-level keys on the 0–5 LLM scale.
    accept_threshold : float
        LLM rating >= this is "accept-side" (default 3.0 on 0–5 scale).
    include_text_metrics : bool
        If True, also compute tfidf_cosine and keyword_jaccard (slow).

    Returns
    -------
    dict with per-dimension normalized errors, NMAE, RMSE, decision_agree,
    and optionally text metrics.
    """
    # Handle both old ("review") and new ("reviews") schemas
    if "reviews" in example:
        human_review = example.get("reviews", {}) or {}
    else:
        human_review = example.get("review", {}) or {}

    result: Dict = {}
    normalized_errors: list[float] = []
    squared_errors: list[float] = []

    l_lo, l_hi = LLM_SCORE_RANGE

    for dim in SCORE_DIMENSIONS:
        human_val = _extract_human_score(human_review, dim)
        gen_val = parse_numeric_rating(generated.get(dim))

        if human_val is not None and gen_val is not None:
            h_lo, h_hi = SCORE_RANGES[dim]
            norm_human = _to_unit(human_val, h_lo, h_hi)
            norm_llm = _to_unit(gen_val, l_lo, l_hi)
            norm_err = abs(norm_human - norm_llm)

            result[f"{dim}_norm_err"] = norm_err
            normalized_errors.append(norm_err)
            squared_errors.append(norm_err ** 2)
        else:
            result[f"{dim}_norm_err"] = None

    # Primary metric: NMAE on [0,1] scale
    result["nmae"] = sum(normalized_errors) / len(normalized_errors) if normalized_errors else None

    # Secondary metric: RMSE on [0,1] scale
    result["rmse"] = (sum(squared_errors) / len(squared_errors)) ** 0.5 if squared_errors else None

    # Decision agreement: human threshold on 1–10 scale, LLM threshold on 0–5 scale
    human_rating = _extract_human_score(human_review, "rating")
    gen_rating = parse_numeric_rating(generated.get("rating"))
    if human_rating is not None and gen_rating is not None:
        result["decision_agree"] = (
            (human_rating >= HUMAN_ACCEPT_THRESHOLD) == (gen_rating >= accept_threshold)
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
