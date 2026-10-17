import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from functools import wraps
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from app.ai.prompts import load_prompt
from app.ai.read_tools import ReadOnlyTools
from app.ai.transport import ModelResponse


class AskTransport(Protocol):
    model: str

    async def select_facts(self, question: str, tools: ReadOnlyTools) -> ModelResponse: ...


class AdkModelError(RuntimeError):
    def __init__(self, provider_code: str) -> None:
        self.code = (
            provider_code
            if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", provider_code)
            else "PROVIDER_ERROR"
        )
        super().__init__("ADK model invocation failed")


class AdkAskTransport:
    """A genuine tool-using ADK agent, with no write tools and a short-lived run session."""

    def __init__(
        self, *, client: Any, model: str, max_llm_calls: int = 4, timeout_seconds: float = 40
    ) -> None:
        if not 1 <= max_llm_calls <= 6:
            raise ValueError("Ask model-call budget must be between one and six")
        self.client = client
        self.model = model
        self.max_llm_calls = max_llm_calls
        self.timeout_seconds = timeout_seconds
        self.thinking_level = "LOW"
        self.final_selection_thinking_level = "MINIMAL"

    def build_agent(self, tools: ReadOnlyTools) -> Any:
        from google.adk.agents import LlmAgent
        from google.adk.agents.callback_context import CallbackContext
        from google.adk.models.google_llm import Gemini
        from google.adk.models.llm_request import LlmRequest
        from google.genai import types

        tool_lock = RLock()
        model_calls = 0

        def finish_within_budget(
            callback_context: CallbackContext, llm_request: LlmRequest
        ) -> None:
            nonlocal model_calls
            model_calls += 1
            if model_calls >= min(self.max_llm_calls, 3) or len(tools.calls) >= min(
                tools.max_calls, 2
            ):
                # Reserve the last allowed generation for the answer, not another tool cycle.
                # This remains a real model selection from this run's bounded fact allowlist.
                llm_request.tools_dict.clear()
                llm_request.config.tools = None
                llm_request.config.tool_config = None
                llm_request.config.response_mime_type = "application/json"
                # Selecting already verified IDs needs no further investigative reasoning.
                llm_request.config.thinking_config = types.ThinkingConfig(
                    thinking_level=self.final_selection_thinking_level
                )
                fact_ids: dict[str, Any] = {
                    "type": "array",
                    "items": {"type": "string", "enum": list(tools.facts)},
                    "maxItems": 12,
                }
                if not tools.facts:
                    fact_ids = {"type": "array", "items": {"type": "string"}, "maxItems": 0}
                llm_request.config.response_json_schema = {
                    "type": "object",
                    "properties": {"fact_ids": fact_ids},
                    "required": ["fact_ids"],
                    "additionalProperties": False,
                }
                llm_request.append_instructions(
                    [
                        "Tool research is complete for this bounded run. Return only JSON "
                        "selecting relevant fact_ids already returned by tools. "
                        "Return an empty list if those facts cannot answer the question."
                    ]
                )

        def threaded[**P, T](function: Callable[P, T]) -> Callable[P, Awaitable[T]]:
            @wraps(function)
            async def invoke(*args: P.args, **kwargs: P.kwargs) -> T:
                def run() -> T:
                    # Serialize the exact-run ledger while SDK graph reads run off the event loop.
                    with tool_lock:
                        return function(*args, **kwargs)

                return await asyncio.to_thread(run)

            return invoke

        discovery = [
            {"id": change.id, "title": change.title, "mandate_id": change.mandate_id}
            for change in tools.bundle.changes
        ]
        return LlmAgent(
            name="ask_regimpact",
            model=Gemini(model=self.model, client=self.client),
            instruction=load_prompt("ask-regimpact-v1")
            + "\nKnown scenario identifiers for discovery only (not answer facts):\n"
            + json.dumps(discovery),
            tools=[threaded(getattr(tools, name)) for name in ReadOnlyTools.TOOL_NAMES],
            before_model_callback=finish_within_budget,
            generate_content_config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
                max_output_tokens=4096,
                automatic_continuation=False,
            ),
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )

    async def select_facts(self, question: str, tools: ReadOnlyTools) -> ModelResponse:
        from google.adk.agents.run_config import RunConfig
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        session_service = InMemorySessionService()
        app_name = "regimpact_readonly"
        run_id = str(uuid4())
        await session_service.create_session(app_name=app_name, user_id=run_id, session_id=run_id)
        runner = Runner(
            agent=self.build_agent(tools), app_name=app_name, session_service=session_service
        )
        answer = ""
        input_tokens = output_tokens = 0
        saw_usage = False
        model_calls = 0
        model_version = None
        async with asyncio.timeout(self.timeout_seconds):
            async for event in runner.run_async(
                user_id=run_id,
                session_id=run_id,
                new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
                run_config=RunConfig(max_llm_calls=self.max_llm_calls),
            ):
                if event.error_code:
                    raise AdkModelError(event.error_code)
                if event.usage_metadata:
                    model_calls += 1
                    saw_usage = True
                    input_tokens += event.usage_metadata.prompt_token_count or 0
                    output_tokens += event.usage_metadata.candidates_token_count or 0
                if event.model_version:
                    model_version = event.model_version
                if event.is_final_response() and event.content:
                    answer = "".join(part.text or "" for part in event.content.parts or [])
        return ModelResponse(
            answer,
            input_tokens if saw_usage else None,
            output_tokens if saw_usage else None,
            model_version,
            model_calls if saw_usage else None,
        )
