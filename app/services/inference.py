from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from app.config import Settings
from app.schemas import ArticleInput, SnippetResponse
from app.services.gemini_client import GeminiClient
from app.services.snippet import SnippetCandidate
from app.services.validator import validate_opinions


class InferenceProvider(ABC):
    @abstractmethod
    async def analyze(
        self,
        article: ArticleInput,
        snippets: list[SnippetCandidate],
        include_raw_model_output: bool,
    ) -> list[SnippetResponse]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class GeminiInferenceProvider(InferenceProvider):
    mode = "gemini-api"
    local_model = False
    model_loaded = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_version = settings.gemini_model
        self.client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )

    async def analyze(
        self,
        article: ArticleInput,
        snippets: list[SnippetCandidate],
        include_raw_model_output: bool,
    ) -> list[SnippetResponse]:
        if not snippets:
            return []
        payload = await self.client.generate_json(build_prompt(article, snippets))
        return build_snippet_responses(snippets, payload, include_raw_model_output)

def build_prompt(article: ArticleInput, snippets: list[SnippetCandidate]) -> str:
    items = [
        {
            "snippet_id": snippet.snippet_id,
            "snippet_text": snippet.text,
            "category_hints": snippet.category_hits,
        }
        for snippet in snippets
    ]
    metadata = {
        "article_id": article.article_id,
        "title": article.title,
        "source": article.source,
        "articleDate": article.articleDate,
        "relatedStocks": article.relatedStocks,
    }
    return (
        "You are a strict Korean financial-news ABSA engine.\n"
        "In this MVP, you temporarily replace KoELECTRA Model A and Model B.\n"
        "Model A task: detect allowed categories for each snippet.\n"
        "Model B task: extract aspect/evidence spans and polarity for each detected opinion.\n\n"
        "Return JSON only. No prose. No markdown.\n"
        "Allowed categories: price, earnings, growth_outlook, investment_financing, management_governance, regulation_macro.\n"
        "Allowed sentiment/polarity: positive, neutral, negative.\n\n"
        "Hard constraints:\n"
        "- aspect_term.text must be an exact substring copied from snippet_text.\n"
        "- every evidence_spans[].text must be an exact substring copied from snippet_text.\n"
        "- never paraphrase, summarize, or invent text.\n"
        "- if no clear opinion exists, return categories=[] and opinions=[].\n"
        "- confidence must be between 0.0 and 1.0.\n\n"
        "Output schema:\n"
        '{"results":[{"snippet_id":"...","categories":["price"],"opinions":[{"category":"price","aspect_term":{"text":"..."},"evidence_spans":[{"text":"..."}],"polarity":"negative","confidence":0.88}]}]}\n\n'
        f"Article metadata:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
        f"Snippets:\n{json.dumps(items, ensure_ascii=False, indent=2)}"
    )


def build_snippet_responses(
    snippets: list[SnippetCandidate],
    payload: dict[str, Any],
    include_raw_model_output: bool,
) -> list[SnippetResponse]:
    raw_results = payload.get("results", [])
    by_id = {
        str(item.get("snippet_id", "")): item
        for item in raw_results
        if isinstance(item, dict)
    } if isinstance(raw_results, list) else {}

    output: list[SnippetResponse] = []
    for snippet in snippets:
        raw_item = by_id.get(snippet.snippet_id, {})
        raw_opinions = raw_item.get("opinions", []) if isinstance(raw_item, dict) else []
        if not isinstance(raw_opinions, list):
            raw_opinions = []
        opinions = validate_opinions(snippet.text, raw_opinions)
        categories = sorted({opinion.category for opinion in opinions})
        output.append(
            SnippetResponse(
                snippet_id=snippet.snippet_id,
                text=snippet.text,
                start=snippet.start,
                end=snippet.end,
                quality=snippet.quality,  # type: ignore[arg-type]
                score=snippet.score,
                category_hits=snippet.category_hits,  # type: ignore[arg-type]
                model_status="success",
                categories=categories,  # type: ignore[arg-type]
                opinions=opinions,
                raw_model_output=raw_item if include_raw_model_output else None,
            )
        )
    return output
