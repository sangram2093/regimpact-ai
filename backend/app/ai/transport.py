from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_version: str | None = None
    model_calls: int | None = None


class StructuredTransport(Protocol):
    model: str

    async def complete(
        self,
        *,
        system_instruction: str,
        context: dict[str, Any],
        response_schema: dict[str, Any],
        repair_errors: tuple[str, ...],
    ) -> ModelResponse: ...
