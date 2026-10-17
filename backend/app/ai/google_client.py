"""Optional real Vertex AI SDK adapters. Construction never substitutes fixture output."""

import asyncio
import json
import math
from typing import Any, Literal

from app.ai.transport import ModelResponse


def provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Keep the decoding grammar small; application validation retains every bound."""
    annotations = {"minLength", "maxLength", "minItems", "maxItems", "title", "default"}

    def compact(value: Any) -> Any:
        if isinstance(value, list):
            return [compact(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: {name: compact(child) for name, child in item.items()}
            if key in {"properties", "$defs"}
            else compact(item)
            for key, item in value.items()
            if key not in annotations
        }

    return compact(schema)


def create_vertex_client(project: str, location: str, *, timeout_seconds: float = 40) -> Any:
    if not project or not location:
        raise ValueError("Google Cloud project and Vertex location are required")
    from google import genai
    from google.genai import types

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            api_version="v1",
            timeout=int(timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


class GoogleGenAITransport:
    def __init__(self, *, client: Any, model: str, timeout_seconds: float = 40) -> None:
        if not model:
            raise ValueError("An explicitly configured Gemini model is required")
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.thinking_level = "LOW"

    async def complete(
        self,
        *,
        system_instruction: str,
        context: dict[str, Any],
        response_schema: dict[str, Any],
        repair_errors: tuple[str, ...],
    ) -> ModelResponse:
        from google.genai import types

        contents = json.dumps(
            {
                "data": context,
                "output_validation_schema": response_schema,
                "validation_errors_to_repair": repair_errors,
            }
        )
        async with asyncio.timeout(self.timeout_seconds):
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_json_schema=provider_schema(response_schema),
                    thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
                    max_output_tokens=8192,
                    automatic_continuation=False,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        usage = response.usage_metadata
        return ModelResponse(
            text=response.text or "",
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            model_version=getattr(response, "model_version", None),
        )


class VertexEmbeddingClient:
    """One input per Gemini embedding request; fixed dimensions align with the database."""

    def __init__(
        self,
        *,
        client: Any,
        model: str = "gemini-embedding-001",
        dimensions: int = 768,
        task_type: Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"] = "RETRIEVAL_QUERY",
        timeout_seconds: float = 40,
    ) -> None:
        if dimensions != 768:
            raise ValueError(
                "The current operational vector schema requires exactly 768 dimensions"
            )
        self.client = client
        self.model = model
        self.dimensions = dimensions
        self.task_type = task_type
        self.timeout_seconds = timeout_seconds

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        from google.genai import types

        if len(texts) > 30 or any(not text.strip() or len(text) > 20000 for text in texts):
            raise ValueError("Embedding input must contain at most 30 bounded non-empty texts")
        vectors = []
        for text in texts:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.client.aio.models.embed_content(
                    model=self.model,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=self.task_type,
                        output_dimensionality=self.dimensions,
                        auto_truncate=False,
                    ),
                )
            if not response.embeddings or len(response.embeddings) != 1:
                raise ValueError("Embedding provider did not return one vector per input")
            values = tuple(response.embeddings[0].values or ())
            if len(values) != self.dimensions or not all(math.isfinite(value) for value in values):
                raise ValueError("Embedding provider returned invalid dimensions or values")
            if not any(value != 0 for value in values):
                raise ValueError("Embedding provider returned a zero vector")
            vectors.append(values)
        return tuple(vectors)
