from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.schemas import SnippetResponse, SummaryResponse


def _round(value: float) -> float:
    return round(value, 4)


def _keywords_for_polarity(snippets: list[SnippetResponse], polarity: str, limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    for snippet in snippets:
        for opinion in snippet.opinions:
            if opinion.polarity != polarity:
                continue
            aspect = opinion.aspect_term.text.strip()
            if aspect:
                counts[aspect] += 2
            for evidence in opinion.evidence_spans:
                for token in re.findall(r"[가-힣A-Za-z0-9%]+", evidence.text):
                    if len(token) >= 2:
                        counts[token] += 1
    return [keyword for keyword, _ in counts.most_common(limit)]


def build_summary(snippets: list[SnippetResponse]) -> SummaryResponse:
    polarity_counts: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    polarity_confidence: dict[str, float] = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    category_confidence: defaultdict[str, float] = defaultdict(float)

    for snippet in snippets:
        for opinion in snippet.opinions:
            polarity_counts[opinion.polarity] += 1
            polarity_confidence[opinion.polarity] += opinion.confidence
            category_confidence[opinion.category] += opinion.confidence

    total = sum(polarity_confidence.values())
    if total <= 0:
        positive_score = 0.0
        negative_score = 0.0
        neutral_score = 1.0
    else:
        positive_score = polarity_confidence["positive"] / total
        negative_score = polarity_confidence["negative"] / total
        neutral_score = polarity_confidence["neutral"] / total

    ordered_scores = {
        "positive": positive_score,
        "negative": negative_score,
        "neutral": neutral_score,
    }
    overall = max(ordered_scores.items(), key=lambda item: item[1])[0]

    dominant_categories = [
        category
        for category, _ in sorted(category_confidence.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]

    return SummaryResponse(
        positive_score=_round(positive_score),
        negative_score=_round(negative_score),
        neutral_score=_round(neutral_score),
        overall_sentiment=overall,  # type: ignore[arg-type]
        positive_keywords=_keywords_for_polarity(snippets, "positive"),
        negative_keywords=_keywords_for_polarity(snippets, "negative"),
        dominant_categories=dominant_categories,  # type: ignore[arg-type]
        opinion_count={
            "positive": polarity_counts["positive"],
            "negative": polarity_counts["negative"],
            "neutral": polarity_counts["neutral"],
        },
    )
