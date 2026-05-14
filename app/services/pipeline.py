from __future__ import annotations

from app.config import Settings
from app.schemas import AnalyzeRequest, AnalyzeResponse, ResponseMeta
from app.services.inference import InferenceProvider
from app.services.snippet import build_snippet_candidates
from app.services.summary import build_summary


async def analyze_article(
    request: AnalyzeRequest,
    settings: Settings,
    inference_provider: InferenceProvider,
) -> AnalyzeResponse:
    request_id = request.request_id_or_new()
    max_snippets = min(request.options.max_snippets, settings.max_snippets_limit)
    candidates = build_snippet_candidates(
        article_id=request.article.article_id,
        content=request.article.content,
        include_weak=request.options.include_weak_snippets,
        max_snippets=max_snippets,
    )
    snippets = await inference_provider.analyze(
        article=request.article,
        snippets=candidates,
        include_raw_model_output=request.options.include_raw_model_output,
    )
    summary = build_summary(snippets)
    return AnalyzeResponse(
        request_id=request_id,
        article_id=request.article.article_id,
        status="success",
        summary=summary,
        snippets=snippets,
        meta=ResponseMeta(
            model_version=settings.gemini_model if settings.mode == "gemini-api" else "newspin-absa-local",
            preprocess_version=settings.preprocess_version,
        ),
    )
