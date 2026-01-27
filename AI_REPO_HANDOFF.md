# NewsPin AI (FastAPI + Gemini) — Handoff (Single MD)

> 목적: **Gemini API가 연결된 FastAPI “프레임(껍데기)”**를 빠르게 만들어 `ai` 레포에 올리고, 백엔드(Spring)가 **JSON으로 호출**해 데모를 붙일 수 있도록 **계약(Contract) + 실행/배포 디테일**을 한 파일에 정리한다.  
> 필수 조건:
> 1) Organization 기반(레포 4개: main/fe/be/ai)  
> 2) Backend(Spring)는 **8080** 사용 중 → FastAPI(AI)는 **8000** 사용  
> 3) BE와는 **구조화 JSON**으로 통신

---

## 0) 프로젝트 컨텍스트 (Org/Repo)
- GitHub Organization 내 레포 4개:
  - `main` : 통합/문서/리소스(아직 아무것도 없음)
  - `FrontEnd` : 프론트엔드 (이미 개발 진행 중)
  - `newspin-be` : 백엔드 Spring (이미 개발 진행 중, **8080 사용**)
  - `newspin-ai` : FastAPI + Gemini ABSA 데모 서버 (이번 작업 대상)
- 목표는 “AI 파트(ABSA)”를 서비스 형태로 분리해, BE가 HTTP로 호출하는 구조를 확정하는 것.

### 0.1) 백엔드 컨벤션 요약
- API prefix: 글로벌 prefix 없음 (`/user/...` 형태; 즉 `/api` 같은 공통 prefix 강제 없음)
- JSON naming: Jackson 기본 → **lower camelCase**
- DTO 스타일: Lombok 클래스 + Jakarta Validation
- 에러/응답 envelope: `ApiResponse(status, code, message, data)`
- 보안: Spring Security 적용  
  - `/user/**` 일부만 공개  
  - 그 외는 `Authorization: Bearer <token>` 필요
- 외부 호출 패턴: HTTP 클라이언트(Feign/WebClient/RestTemplate) 사용 흔적 거의 없음(메일은 JavaMailSender)

---

## 1) 이번 스프린트 범위
### 반드시 되는 것
- FastAPI 서버가 **8000 포트**에서 실행된다.
- `/health`와 `/absa/analyze` 엔드포인트가 있다.
- `/absa/analyze`는 Gemini API를 호출해 **스키마 고정된 JSON**으로 응답한다.
- 로컬 실행 + Docker 실행이 가능하다.
- `.gitignore`, `.env.example` 포함하여 키 유출/배포 이슈를 예방한다.

### 이번 범위 아님(나중에)
- 실제 파인튜닝 ABSA 모델(Model A/B) 서빙
- DB 적재/로그 적재/모니터링(간단 로그는 가능)
- FE/BE 내부 구조 변경(계약만 맞추면 됨)

---

## 2) 권장 통신 구조(데모 안정성)
- FE는 **BE만 호출**
- BE가 서버-서버로 AI(FastAPI)를 호출하고 결과를 FE에 전달
- 브라우저가 AI를 직접 호출하지 않게 하면 CORS 이슈가 크게 줄어든다.
- 데모 편의를 위해 AI 서버에 CORS 설정을 두되, 운영 전에는 도메인 제한 필수.

---

## 3) API 계약(Contract) — v0 (Demo)

### Base URL
- Local: `http://localhost:8000`
- Deployed: `http://<ai-host>:8000`

---

### 3.1 Health Check
**GET** `/health`

Response `200`:
```json
{
  "status": "ok",
  "time": "2026-01-27T00:00:00Z"
}
```

### 3.2 ABSA Analyze (Article-level)

**POST** /absa/analyze
Content-Type: application/json

**Request** — ArticleAnalyzeRequest(camelCase)
```json
{
  "requestId": "uuid-or-any-string",
  "article": {
    "articleId": "string-optional",
    "title": "string-optional",
    "content": "string-required",
    "press": "string-optional",
    "publishedAt": "YYYY-MM-DD or ISO8601 optional",
    "url": "string-optional"
  },
  "options": {
    "maxSnippets": 6,
    "maxOpinions": 12,
    "returnSnippets": true,
    "timeoutMs": 9000
  }
}
```
**Validation 권장(문서 기준)**

article.content 필수, 빈 문자열 금지
options.timeoutMs: 1000~20000 권장 (기본 9000)
options.maxSnippets: 0~10 권장 (기본 6)
options.maxOpinions: 0~30 권장 (기본 12)
요청 본문이 너무 길면(예: 20,000자 초과) 413/422로 거절 권장


**Response** — ArticleAnalyzeResponse
```json
{
  "requestId": "same-as-request",
  "model": {
    "provider": "gemini",
    "name": "gemini-2.5-flash",
    "version": "demo-0.1"
  },
  "articleId": "string-or-null",
  "snippets": [
    {
      "snippetId": "s1",
      "text": "1~3문장 스니펫",
      "startChar": 0,
      "endChar": 120
    }
  ],
  "opinions": [
    {
      "category": "earnings",
      "aspectTerm": "실적",
      "polarity": "positive",
      "confidence": 0.73,
      "evidenceSpans": [
        { "start": 10, "end": 40, "text": "근거 구간(원문 substring)" }
      ]
    }
  ],
  "aggregate": {
    "positiveScore": 0.55,
    "negativeScore": 0.25,
    "neutralScore": 0.20,
    "topCategories": ["earnings", "price"],
    "topKeywords": ["실적", "전망", "급락"],
    "summary": "한 줄 요약(선택)",
    "confidence": 0.68
  },
  "meta": {
    "latencyMs": 1234,
    "analyzedAt": "2026-01-27T00:00:00Z"
  }
}
```
**Offset 규칙(명확히 고정)**

evidenceSpans[].start/end는 article.content 기준 0-based character offset (end는 exclusive 권장)

evidenceSpans[].text는 반드시 article.content[start:end]와 일치(또는 완전 포함)하도록 생성

**Success Response** — 성공 응답
```json
{
  "status": "success",
  "code": "OK",
  "message": "OK",
  "data": { ...기존 ArticleAnalyzeResponse... }
}

```

**Error Response** — ApiResponse<null> (BE 표준에 맞춤)
```json
{
  "status": "error",
  "code": "GEMINI_TIMEOUT",
  "message": "Gemini request timed out",
  "data": null
}

```

## 4) Category 목록(ABSA 분류 축)

v0에서는 아래 8개(+other)로 고정:
price
earnings
growthOutlook
investmentFinancing
technologyProduct
managementGovernance
regulationMacro
competition
other

## 5) Gemini 연동 원칙

### 5.1 환경변수(Secrets)

GEMINI_API_KEY (required) — 절대 Git 커밋 금지

GEMINI_MODEL (default: gemini-2.5-flash)

REQUEST_TIMEOUT_MS (default: 9000)

CORS_ORIGINS (default: * for demo; prod에서는 FE/BE 도메인만)

LOG_LEVEL (default: INFO)

APP_ENV (default: local)

### 5.2 Structured Output 강제

Gemini 호출 시 “응답을 반드시 JSON으로, 스키마에 맞게” 강제

목표: BE가 파싱 실패 없이 DTO로 안정적으로 매핑

temperature 낮게(예: 0.2)

### 5.3 안정성

timeout 적용

retry는 0~1회(데모 단계 과도 retry 금지)

실패 시 안정적인 error envelope 반환

## 6) Repository Layout (권장)

```txt
newspin-ai/
  app/
    __init__.py
    main.py              # FastAPI entry (라우팅)
    schemas.py           # Pydantic models (request/response/error)
    gemini_client.py     # Gemini 호출 래퍼 (timeout/retry/structured output)
    absa_service.py      # snippet 추출 + prompt 구성 + aggregate 계산
    utils.py
  Dockerfile
  docker-compose.yml    # optional
  requirements.txt
  .env.example
  .gitignore
  AI_REPO_HANDOFF.md
```

## 7) Local Run(Conda 기준 + pip 설치)

```txt
conda create -n newspin-ai python=3.11 -y
conda activate newspin-ai

pip install -r requirements.txt

cp .env.example .env
# .env에 GEMINI_API_KEY 입력

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Swagger UI: http://localhost:8000/docs
