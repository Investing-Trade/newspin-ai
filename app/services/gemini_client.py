from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from google import genai
from google.genai import types


class GeminiConfigError(RuntimeError):
    pass


class GeminiAPIError(RuntimeError):
    pass


class GeminiParseError(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, api_key: str, model_name: str, timeout_seconds: int) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise GeminiConfigError("GEMINI_API_KEY is not configured.")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._generate_json_sync, prompt),
                timeout=self.timeout_seconds,
            )
        except GeminiParseError:
            raise
        except GeminiConfigError:
            raise
        except Exception as exc:
            raise GeminiAPIError(str(exc)) from exc

    def _generate_json_sync(self, prompt: str) -> dict[str, Any]:
        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise GeminiAPIError("Gemini response did not include text.")
        return parse_json_object(text)


def parse_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as first_error:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise GeminiParseError(f"Invalid JSON response: {first_error}") from first_error
        try:
            parsed = json.loads(value[start : end + 1])
        except json.JSONDecodeError as second_error:
            raise GeminiParseError(f"Invalid JSON response: {second_error}") from second_error
    if not isinstance(parsed, dict):
        raise GeminiParseError("Gemini JSON root must be an object.")
    return parsed
