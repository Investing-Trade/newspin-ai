from __future__ import annotations

from typing import Any

from app.schemas import OpinionResponse, SpanResponse


ALLOWED_CATEGORIES = {
    "price",
    "earnings",
    "growth_outlook",
    "investment_financing",
    "management_governance",
    "regulation_macro",
}
ALLOWED_POLARITIES = {"positive", "negative", "neutral"}


def _unique_span(snippet_text: str, text: str) -> SpanResponse | None:
    value = str(text or "")
    if not value:
        return None
    matches: list[int] = []
    cursor = 0
    while True:
        idx = snippet_text.find(value, cursor)
        if idx < 0:
            break
        matches.append(idx)
        cursor = idx + 1
        if len(matches) > 1:
            break
    if len(matches) != 1:
        return None
    start = matches[0]
    end = start + len(value)
    return SpanResponse(text=value, start=start, end=end)


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, number))


def validate_opinions(snippet_text: str, raw_opinions: list[Any]) -> list[OpinionResponse]:
    valid: list[OpinionResponse] = []
    for item in raw_opinions:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", ""))
        polarity = str(item.get("polarity", "")).lower()
        if category not in ALLOWED_CATEGORIES or polarity not in ALLOWED_POLARITIES:
            continue

        aspect_obj = item.get("aspect_term", {})
        aspect_text = aspect_obj.get("text", "") if isinstance(aspect_obj, dict) else str(aspect_obj or "")
        aspect = _unique_span(snippet_text, str(aspect_text))
        if aspect is None:
            continue

        evidence_items = item.get("evidence_spans", [])
        if not isinstance(evidence_items, list):
            evidence_items = [evidence_items]
        evidence_spans: list[SpanResponse] = []
        for evidence_obj in evidence_items:
            evidence_text = evidence_obj.get("text", "") if isinstance(evidence_obj, dict) else str(evidence_obj or "")
            evidence = _unique_span(snippet_text, str(evidence_text))
            if evidence is not None:
                evidence_spans.append(evidence)
        if not evidence_spans:
            continue

        valid.append(
            OpinionResponse(
                category=category,  # type: ignore[arg-type]
                aspect_term=aspect,
                evidence_spans=evidence_spans,
                polarity=polarity,  # type: ignore[arg-type]
                confidence=_confidence(item.get("confidence", 0.0)),
            )
        )
    return valid
