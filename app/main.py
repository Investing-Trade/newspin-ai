from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

app = FastAPI(title="NewsPin AI")

class Article(BaseModel):
    articleId: Optional[str] = None
    title: Optional[str] = None
    content: str
    press: Optional[str] = None
    publishedAt: Optional[str] = None
    url: Optional[str] = None

class AnalyzeOptions(BaseModel):
    maxSnippets: int = 6
    maxOpinions: int = 12
    returnSnippets: bool = True
    timeoutMs: int = 9000

class ArticleAnalyzeRequest(BaseModel):
    requestId: str
    article: Article
    options: Optional[AnalyzeOptions] = None

class EvidenceSpan(BaseModel):
    start: int
    end: int
    text: str

class Opinion(BaseModel):
    category: str
    aspectTerm: str
    polarity: str
    confidence: float
    evidenceSpans: List[EvidenceSpan] = []

class Snippet(BaseModel):
    snippetId: str
    text: str
    startChar: int
    endChar: int

class Aggregate(BaseModel):
    positiveScore: float
    negativeScore: float
    neutralScore: float
    topCategories: List[str]
    topKeywords: List[str]
    summary: Optional[str] = None
    confidence: float

class ModelInfo(BaseModel):
    provider: str
    name: str
    version: str

class Meta(BaseModel):
    latencyMs: int
    analyzedAt: str

class ArticleAnalyzeResponse(BaseModel):
    requestId: str
    model: ModelInfo
    articleId: Optional[str] = None
    snippets: List[Snippet] = []
    opinions: List[Opinion] = []
    aggregate: Aggregate
    meta: Meta

class ApiResponse(BaseModel):
    status: str
    code: str
    message: str
    data: Optional[ArticleAnalyzeResponse] = None

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@app.post("/absa/analyze", response_model=ApiResponse)
def analyze(payload: ArticleAnalyzeRequest):
    # TODO: integrate Gemini client + ABSA logic
    model = ModelInfo(provider="gemini", name="gemini-2.5-flash", version="demo-0.1")
    aggregate = Aggregate(
        positiveScore=0.0,
        negativeScore=0.0,
        neutralScore=1.0,
        topCategories=["other"],
        topKeywords=[],
        summary=None,
        confidence=0.0,
    )
    meta = Meta(latencyMs=0, analyzedAt=datetime.now(timezone.utc).isoformat())
    data = ArticleAnalyzeResponse(
        requestId=payload.requestId,
        model=model,
        articleId=payload.article.articleId,
        snippets=[],
        opinions=[],
        aggregate=aggregate,
        meta=meta,
    )
    return ApiResponse(status="success", code="OK", message="OK", data=data)
