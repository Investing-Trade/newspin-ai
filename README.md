# NewsPin ABSA API

NewsPin 금융 뉴스 ABSA 추론용 FastAPI 서버입니다.

현재 MVP 버전에서는 자체 KoELECTRA ABSA 모델이 아직 학습 중이므로, **추론 단계만 임시로 Gemini API가 대체**합니다. API 구조는 나중에 Gemini 부분만 아래 로컬 모델 흐름으로 바꾸기 쉽게 분리되어 있습니다.

```text
KoELECTRA Model A: snippet -> category multi-label
KoELECTRA Model B: snippet -> aspect BIO + evidence BIO + sentiment
```

전체 실행 흐름은 다음과 같습니다.

```text
article text
-> span-preserving 문장 분리
-> snippet 후보 생성
-> strong/weak 필터링
-> inference provider
   - 현재: Gemini API
   - 추후: KoELECTRA Model A -> KoELECTRA Model B
-> exact substring span 검증
-> 기사 단위 summary 집계
-> Spring 백엔드로 응답
```

## 실행 대상 환경

- AWS Lightsail Ubuntu 22.04
- Docker
- Python 3.11
- Uvicorn workers: `1`

`workers=1`로 고정하는 이유는 추후 KoELECTRA 로컬 모델을 붙였을 때 프로세스마다 모델이 중복 로딩되는 것을 막기 위해서입니다.

## 엔드포인트

```text
GET  /health
GET  /model-info
POST /analyze
GET  /docs
```

FastAPI Swagger UI는 `/docs`에서 확인할 수 있습니다.

## 환경변수

`.env.example`을 복사해서 `.env`를 만듭니다.

```text
APP_NAME=NewsPin ABSA API
APP_ENV=local
API_KEY=
GEMINI_API_KEY=your-paid-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=60
MAX_SNIPPETS_DEFAULT=12
MAX_SNIPPETS_LIMIT=30
```

`GEMINI_API_KEY`는 MVP 모드의 `POST /analyze` 실행에 필요합니다. 환경변수 또는 `.env`로 주입해야 하며, 코드에 직접 하드코딩하면 안 됩니다.

`API_KEY`는 선택값입니다. 값을 넣으면 Spring 백엔드는 요청 헤더에 같은 값을 보내야 합니다.

```text
X-API-Key: your-shared-key
```

비워두면 API key 검사를 하지 않습니다.

## 요청 형식

```http
POST /analyze
Content-Type: application/json
```

```json
{
  "request_id": "req-001",
  "article": {
    "article_id": 123,
    "title": "삼성전자 실적 개선 기대",
    "content": "전처리된 뉴스 본문...",
    "articleDate": "2020-01-01",
    "source": "한국경제",
    "relatedStocks": ["005930"]
  },
  "options": {
    "max_snippets": 12,
    "include_weak_snippets": false,
    "include_raw_model_output": false
  }
}
```

검증 규칙:

- `article.content`는 `min_length=1`입니다. 빈 문자열이면 FastAPI 기본 `422` validation error가 발생합니다.
- snippet `score`는 `0.0 <= score <= 1.0` 범위로 정규화됩니다.
- sentiment/polarity 값은 `positive`, `neutral`, `negative` 중 하나만 허용합니다.

## 응답 형식

```json
{
  "request_id": "req-001",
  "article_id": 123,
  "status": "success",
  "summary": {
    "positive_score": 0.26,
    "negative_score": 0.74,
    "neutral_score": 0.0,
    "overall_sentiment": "negative",
    "positive_keywords": ["기회", "성장동력"],
    "negative_keywords": ["하향", "관건"],
    "dominant_categories": ["price", "growth_outlook"],
    "opinion_count": {
      "positive": 1,
      "negative": 3,
      "neutral": 0
    }
  },
  "snippets": [
    {
      "snippet_id": "123_snp_0001",
      "text": "삼성SDS 목표가를 15% 하향 조정했다",
      "start": 120,
      "end": 141,
      "quality": "strong",
      "score": 0.84,
      "category_hits": ["price"],
      "model_status": "success",
      "categories": ["price"],
      "opinions": [
        {
          "category": "price",
          "aspect_term": {
            "text": "목표가",
            "start": 5,
            "end": 8
          },
          "evidence_spans": [
            {
              "text": "목표가를 15% 하향 조정했다",
              "start": 5,
              "end": 21
            }
          ],
          "polarity": "negative",
          "confidence": 0.88
        }
      ]
    }
  ],
  "meta": {
    "model_version": "gemini-2.5-flash",
    "preprocess_version": "news_v2_snippet_rules_v1",
    "processed_at": "2026-05-14T20:00:00"
  }
}
```

## Offset 기준

```text
snippet.start/end = article.content 기준 문자 offset
aspect_term.start/end = snippet.text 기준 문자 offset
evidence_spans[].start/end = snippet.text 기준 문자 offset
```

Gemini는 span text만 반환하고, 서버가 offset을 다시 계산합니다. aspect/evidence는 exact substring으로 검증되며, 불일치하거나 중복 출현으로 모호한 span은 제외됩니다.

## 에러 처리

- 요청 validation error: FastAPI 기본 `422`
- `GEMINI_API_KEY` 누락: `500 GEMINI_CONFIG_ERROR`
- Gemini API 호출 실패 또는 timeout: `502 GEMINI_API_ERROR`
- Gemini 응답 JSON 파싱 실패: `502 GEMINI_PARSE_ERROR`
- 기타 서버 내부 오류: `500 INTERNAL_ERROR`

Gemini 응답 파서는 순수 JSON뿐 아니라 ` ```json {"results":[]} ``` ` 형태의 code block도 처리합니다.


