# NewsPin ABSA API

FastAPI server for NewsPin financial-news ABSA inference.

Current MVP mode uses Gemini API only for the inference step because the local KoELECTRA ABSA models are still being trained. The API shape is designed so the Gemini inference provider can later be replaced with:

```text
KoELECTRA Model A: snippet -> category multi-label
KoELECTRA Model B: snippet -> aspect BIO + evidence BIO + sentiment
```

The rest of the runtime flow should remain stable:

```text
article text
-> span-preserving sentence split
-> snippet candidate generation
-> strong/weak filtering
-> inference provider
   - now: Gemini API
   - later: KoELECTRA Model A -> KoELECTRA Model B
-> exact substring span validation
-> article summary aggregation
-> response to Spring backend
```

## Runtime Target

- AWS Lightsail Ubuntu 22.04
- Docker
- Python 3.11
- Uvicorn workers: `1`

Workers are intentionally fixed to 1 so a future local KoELECTRA model is loaded once in a single process.

## Endpoints

```text
GET  /health
GET  /model-info
POST /analyze
GET  /docs
```

FastAPI Swagger UI is available at `/docs`.

## Environment

Copy `.env.example` to `.env`.

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

`GEMINI_API_KEY` is required for `POST /analyze` in MVP mode. It must be provided as an environment variable or `.env` value. Do not hardcode it in source code.

`API_KEY` is optional. If set, Spring must send it as:

```text
X-API-Key: your-shared-key
```

## Request

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

Validation notes:

- `article.content` has `min_length=1`; empty text returns FastAPI's default 422 validation error.
- Snippet `score` is normalized to `0.0 <= score <= 1.0`.
- Sentiment values are lowercase: `positive`, `neutral`, `negative`.

## Response

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

## Offset Contract

```text
snippet.start/end = article.content character offsets
aspect_term.start/end = snippet.text character offsets
evidence_spans[].start/end = snippet.text character offsets
```

All aspect/evidence spans are recalculated and validated by exact substring matching. Invalid or ambiguous Gemini spans are dropped.

## Error Handling

- Request validation error: FastAPI default `422`
- Missing `GEMINI_API_KEY`: `500` with `GEMINI_CONFIG_ERROR`
- Gemini API call failure or timeout: `502` with `GEMINI_API_ERROR`
- Gemini invalid JSON response: `502` with `GEMINI_PARSE_ERROR`
- Unexpected server error: `500` with `INTERNAL_ERROR`

Gemini JSON parsing accepts both raw JSON and fenced code blocks such as ` ```json {"results":[]} ``` `.

## Local Run

Windows PowerShell:

```powershell
cd C:\Users\s_junkim\Capstone\newspin-absa-api
copy .env.example .env
# edit .env and set GEMINI_API_KEY
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Analyze example:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"request_id":"req-local-001","article":{"article_id":1,"title":"테스트","content":"삼성SDS 목표가를 15% 하향 조정했다.","articleDate":"2020-01-01","source":"test","relatedStocks":["018260"]},"options":{"max_snippets":12,"include_weak_snippets":false,"include_raw_model_output":false}}'
```

## Docker Run

```bash
docker build -t newspin-absa-api .
docker run --env-file .env -p 8000:8000 newspin-absa-api
```

Docker command used by the image:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## AWS Lightsail Ubuntu 22.04

Install Docker, clone or copy this project, create `.env`, then:

```bash
cd ~/newspin-absa-api
docker build -t newspin-absa-api .
docker run -d --name newspin-absa-api --restart unless-stopped --env-file .env -p 8000:8000 newspin-absa-api
```

Open port `8000` in the Lightsail firewall if Spring calls this service directly.

## URL for Spring Backend

Local same-machine test:

```text
http://127.0.0.1:8000/analyze
```

Same LAN test:

```text
http://<your-local-ip>:8000/analyze
```

AWS Lightsail deployment:

```text
http://<lightsail-public-ip>:8000/analyze
```

If FastAPI runs on a local PC while Spring runs on AWS, expose the local server through a tunnel such as ngrok or cloudflared:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
ngrok http 8000
```

Then give Spring:

```text
https://<ngrok-domain>/analyze
```
