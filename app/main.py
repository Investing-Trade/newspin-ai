from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, status

from app.config import get_settings
from app.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse, ModelInfoResponse
from app.services.gemini_client import GeminiAPIError, GeminiConfigError, GeminiParseError
from app.services.inference import GeminiInferenceProvider
from app.services.pipeline import analyze_article


def create_inference_provider(settings):
    if settings.mode == "gemini-api":
        return GeminiInferenceProvider(settings)
    if settings.mode == "local-koelectra":
        from app.services.local_koelectra import LocalKoELECTRAInferenceProvider

        return LocalKoELECTRAInferenceProvider(settings)
    raise RuntimeError(f"Unsupported MODE: {settings.mode}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Local KoELECTRA mode loads Model A/B and tokenizers once here.
    # Keep Docker workers=1 so model memory is not duplicated across processes.
    app.state.inference_provider = create_inference_provider(settings)
    yield
    await app.state.inference_provider.close()


def create_app() -> FastAPI:
    settings = get_settings()
    return FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


app = create_app()
API_PREFIX = "/api/v1"


def check_api_key(x_api_key: str | None) -> None:
    settings = get_settings()
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")


@app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(f"{API_PREFIX}/model-info", response_model=ModelInfoResponse)
async def model_info() -> ModelInfoResponse:
    settings = get_settings()
    provider = getattr(app.state, "inference_provider", None)
    return ModelInfoResponse(
        mode=getattr(provider, "mode", settings.mode),
        model_loaded=getattr(provider, "model_loaded", settings.model_loaded),
        local_model=getattr(provider, "local_model", settings.local_model),
        model_version=getattr(
            provider,
            "model_version",
            settings.gemini_model if settings.mode == "gemini-api" else settings.model_version,
        ),
        preprocess_version=settings.preprocess_version,
    )


@app.post(f"{API_PREFIX}/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> AnalyzeResponse:
    check_api_key(x_api_key)
    settings = get_settings()
    provider = request.app.state.inference_provider
    try:
        return await analyze_article(payload, settings, provider)
    except GeminiConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "GEMINI_CONFIG_ERROR", "message": str(exc)},
        ) from exc
    except GeminiParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GEMINI_PARSE_ERROR", "message": str(exc)},
        ) from exc
    except GeminiAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GEMINI_API_ERROR", "message": str(exc)},
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "message": str(exc)},
        ) from exc
