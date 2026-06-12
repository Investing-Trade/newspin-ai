# NewsPin ABSA API

NewsPin 금융 뉴스 ABSA 추론용 FastAPI 서버입니다.

현재 서버는 두 가지 추론 모드를 지원합니다.

- `local-koelectra`: 학습 완료된 KoELECTRA Model A/B를 FastAPI lifespan startup에서 1회 로딩해 추론합니다.
- `gemini-api`: Gemini API 기반 임시 fallback 모드입니다.

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
   - local-koelectra: KoELECTRA Model A -> KoELECTRA Model B
   - gemini-api: Gemini API fallback
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
GET  /api/v1/health
GET  /api/v1/model-info
POST /api/v1/analyze
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
MODE=gemini-api
MODEL_PACKAGE_PATH=./models
MODEL_A_PATH=
MODEL_B_PATH=
MODEL_VERSION=koelectra-absa-v3
```

`MODE=local-koelectra`이면 `MODEL_PACKAGE_PATH` 아래에 다음 파일들이 있어야 합니다.

```text
models/
  model_a/
  model_b/
  label_map.json
  thresholds.json
  inference_config.json
```

`MODE=gemini-api`이면 `GEMINI_API_KEY`가 `POST /api/v1/analyze` 실행에 필요합니다. 환경변수 또는 `.env`로 주입해야 하며, 코드에 직접 하드코딩하면 안 됩니다.

`API_KEY`는 선택값입니다. 값을 넣으면 Spring 백엔드는 요청 헤더에 같은 값을 보내야 합니다.

```text
X-API-Key: your-shared-key
```

비워두면 API key 검사를 하지 않습니다.

## 요청 형식

```http
POST /api/v1/analyze
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
    "model_version": "koelectra-absa-v3",
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

로컬 KoELECTRA 모드에서는 tokenizer `offset_mapping`으로 aspect/evidence span을 복원합니다. Gemini fallback 모드에서는 span text만 반환받고 서버가 offset을 다시 계산합니다.

## 에러 처리

- 요청 validation error: FastAPI 기본 `422`
- `GEMINI_API_KEY` 누락: `500 GEMINI_CONFIG_ERROR`
- Gemini API 호출 실패 또는 timeout: `502 GEMINI_API_ERROR`
- Gemini 응답 JSON 파싱 실패: `502 GEMINI_PARSE_ERROR`
- 로컬 모델 파일 누락 또는 ML 의존성 누락: startup 실패 또는 `500 INTERNAL_ERROR`
- 기타 서버 내부 오류: `500 INTERNAL_ERROR`

Gemini 응답 파서는 순수 JSON뿐 아니라 ` ```json {"results":[]} ``` ` 형태의 code block도 처리합니다.

## Docker 실행

CPU 서버 기준 Docker 이미지는 CPU용 PyTorch를 설치합니다. CUDA wheel은 사용하지 않습니다.

```bash
docker build -t newspin-absa-api .
docker run --env-file .env -p 8000:8000 -v /path/to/fastapi_model_handoff:/app/models newspin-absa-api
```

로컬 KoELECTRA 모드 `.env` 예시:

```text
MODE=local-koelectra
MODEL_PACKAGE_PATH=/app/models
MODEL_VERSION=koelectra-absa-v3
```

Gemini fallback 모드 `.env` 예시:

```text
MODE=gemini-api
GEMINI_API_KEY=your-paid-gemini-api-key
```


