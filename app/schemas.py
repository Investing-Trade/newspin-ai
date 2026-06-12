from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Category = Literal[
    "price",
    "earnings",
    "growth_outlook",
    "investment_financing",
    "management_governance",
    "regulation_macro",
]
Sentiment = Literal["positive", "neutral", "negative"]


class ArticleInput(BaseModel):
    article_id: int
    title: str = ""
    content: str = Field(min_length=1)
    articleDate: str | None = None
    source: str | None = None
    relatedStocks: list[str] = Field(default_factory=list)


class AnalyzeOptions(BaseModel):
    max_snippets: int = Field(default=12, ge=1, le=50)
    include_weak_snippets: bool = False
    include_raw_model_output: bool = False


class AnalyzeRequest(BaseModel):
    request_id: str | None = None
    article: ArticleInput
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)

    def request_id_or_new(self) -> str:
        return self.request_id or f"req-{uuid4()}"


class SpanResponse(BaseModel):
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class OpinionResponse(BaseModel):
    category: Category
    aspect_term: SpanResponse
    evidence_spans: list[SpanResponse] = Field(min_length=1)
    polarity: Sentiment
    confidence: float = Field(ge=0.0, le=1.0)


class SummaryResponse(BaseModel):
    positive_score: float = Field(ge=0.0, le=1.0)
    negative_score: float = Field(ge=0.0, le=1.0)
    neutral_score: float = Field(ge=0.0, le=1.0)
    overall_sentiment: Sentiment
    positive_keywords: list[str]
    negative_keywords: list[str]
    dominant_categories: list[Category]
    opinion_count: dict[Sentiment, int]


class SnippetResponse(BaseModel):
    snippet_id: str
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quality: Literal["strong", "weak"]
    score: float = Field(ge=0.0, le=1.0)
    category_hits: list[Category]
    model_status: Literal["success", "failed", "skipped"]
    categories: list[Category]
    opinions: list[OpinionResponse]
    raw_model_output: dict[str, Any] | None = None


class ResponseMeta(BaseModel):
    model_version: str
    preprocess_version: str
    processed_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class AnalyzeResponse(BaseModel):
    request_id: str
    article_id: int
    status: Literal["success", "failed"]
    summary: SummaryResponse
    snippets: list[SnippetResponse]
    meta: ResponseMeta


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ModelInfoResponse(BaseModel):
    mode: str
    model_loaded: bool
    local_model: bool
    model_version: str
    preprocess_version: str
