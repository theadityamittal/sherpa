"""4-factor confidence scoring for RAG search results.

Weights intentionally rebalanced from legacy codebase (was 40/25/20/15).
Onboarding questions are more specific, so non-similarity factors get
equal 20% weight each.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Spec weights: similarity 40%, count 20%, keyword 20%, length 20%
_SIMILARITY_WEIGHT = 0.4
_COUNT_WEIGHT = 0.2
_KEYWORD_WEIGHT = 0.2
_LENGTH_WEIGHT = 0.2

# Content length thresholds for scoring
_MIN_CONTENT_LENGTH = 50
_MAX_CONTENT_LENGTH = 2000


@dataclass(frozen=True)
class ConfidenceResult:
    """Immutable confidence scoring result with factor breakdown."""

    score: float
    breakdown: dict[str, Any] = field(default_factory=dict)


def calculate_confidence(
    *,
    similarity_scores: list[float],
    query_keywords: set[str],
    result_texts: list[str],
    max_expected_results: int = 10,
) -> ConfidenceResult:
    """Calculate 4-factor confidence for RAG search results.

    Args:
        similarity_scores: Cosine similarity scores from vector search.
        query_keywords: Keywords extracted from the user query.
        result_texts: Text content of each search result.
        max_expected_results: Upper bound for count factor normalization.

    Returns:
        ConfidenceResult with score in [0, 1] and factor breakdown.
    """
    if not similarity_scores:
        return ConfidenceResult(
            score=0.0,
            breakdown={
                "similarity": 0.0,
                "count": 0.0,
                "keyword_overlap": 0.0,
                "content_length": 0.0,
                "similarity_weight": _SIMILARITY_WEIGHT,
                "count_weight": _COUNT_WEIGHT,
                "keyword_weight": _KEYWORD_WEIGHT,
                "length_weight": _LENGTH_WEIGHT,
            },
        )

    similarity_factor = sum(similarity_scores) / len(similarity_scores)
    count_factor = min(len(similarity_scores) / max(max_expected_results, 1), 1.0)
    keyword_factor = _keyword_overlap_factor(query_keywords, result_texts)
    length_factor = _content_length_factor(result_texts)

    score = (
        _SIMILARITY_WEIGHT * similarity_factor
        + _COUNT_WEIGHT * count_factor
        + _KEYWORD_WEIGHT * keyword_factor
        + _LENGTH_WEIGHT * length_factor
    )

    clamped = max(0.0, min(score, 1.0))

    return ConfidenceResult(
        score=round(clamped, 4),
        breakdown={
            "similarity": round(similarity_factor, 4),
            "count": round(count_factor, 4),
            "keyword_overlap": round(keyword_factor, 4),
            "content_length": round(length_factor, 4),
            "similarity_weight": _SIMILARITY_WEIGHT,
            "count_weight": _COUNT_WEIGHT,
            "keyword_weight": _KEYWORD_WEIGHT,
            "length_weight": _LENGTH_WEIGHT,
        },
    )


def _keyword_overlap_factor(query_keywords: set[str], result_texts: list[str]) -> float:
    """Fraction of query keywords found in any result text."""
    if not query_keywords:
        return 0.0

    combined = " ".join(result_texts).lower()
    found = sum(1 for kw in query_keywords if kw.lower() in combined)
    return found / len(query_keywords)


def _content_length_factor(result_texts: list[str]) -> float:
    """Score based on average content length (longer = more informative)."""
    if not result_texts:
        return 0.0

    avg_length = sum(len(t) for t in result_texts) / len(result_texts)
    normalized = (avg_length - _MIN_CONTENT_LENGTH) / (
        _MAX_CONTENT_LENGTH - _MIN_CONTENT_LENGTH
    )
    return max(0.0, min(normalized, 1.0))
