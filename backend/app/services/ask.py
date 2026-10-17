"""Read-only Ask with exact-run fact selection and deterministic answer construction."""

import asyncio
import hashlib
import re
from time import perf_counter

from pydantic import ValidationError

from app.ai.adk_ask import AdkModelError, AskTransport
from app.ai.armor import ContentScreen
from app.ai.contracts import AskConfig, AskResponse, AskSelection, RunStep, WorkflowRun
from app.ai.read_tools import ReadOnlyTools
from app.domain.errors import DomainError
from app.domain.models import SeedBundle
from app.services.impact import ImpactService

UNGROUNDED_MESSAGE = "I couldn't ground a complete answer in approved graph data."


class AskService:
    def __init__(
        self,
        bundle: SeedBundle,
        impact: ImpactService,
        transport: AskTransport | None = None,
        screen: ContentScreen | None = None,
        *,
        max_tool_calls: int = 8,
    ) -> None:
        self.bundle = bundle
        self.impact = impact
        self.transport = transport
        self.screen = screen
        self.max_tool_calls = max_tool_calls

    def config(self) -> AskConfig:
        return AskConfig(
            mode="LIVE_AI" if self.transport else "LOCAL_DETERMINISTIC",
            label="Gemini + ADK — approved baseline graph only"
            if self.transport
            else "Approved baseline graph — deterministic, no live AI",
            available=True,
            reason="Answers use immutable approved baseline mappings and source-backed "
            "proposal scenarios. Session mapping decisions are not included; "
            "coverage gaps refer to baseline coverage. "
            + (
                "Gemini selects facts from bounded read-only tools."
                if self.transport
                else "Local mode supports deterministic graph questions."
            ),
            suggested_questions=(
                "What changes in the gift safeguard, and which controls should we review?",
                "Why does the gift safeguard map to the gifts policy?",
                "Where are the coverage gaps for the new intent and consent obligation?",
            ),
        )

    def _local_selection(self, question: str, tools: ReadOnlyTools) -> list[str]:
        lowered = question.lower()
        if re.search(
            r"\b(approve|reject|delete|modify|execute|ignore previous|system prompt)\b", lowered
        ):
            return []
        changes = []
        for change in self.bundle.changes:
            mandate = next(m for m in self.bundle.mandates if m.id == change.mandate_id)
            label_terms = set(re.findall(r"[a-z]+", f"{change.title} {mandate.title}".lower()))
            # Deliberately narrow local intent matching; unknown questions fail closed.
            discriminative = label_terms & {"gift", "gifts", "consent", "intent", "identity"}
            if any(re.search(rf"\b{re.escape(term)}s?\b", lowered) for term in discriminative):
                changes.append(change)
        if "gap" in lowered and not changes:
            tools.list_coverage_gaps(self.bundle.scenario.id)
        else:
            for change in changes[:2]:
                if "gap" in lowered:
                    tools.list_coverage_gaps(change.id)
                elif any(term in lowered for term in ("why", "rationale", "explain", "map")):
                    policy_edges = [
                        edge
                        for edge in self.bundle.edges
                        if edge.source_id == change.mandate_id
                        and edge.relationship == "ADDRESSED_BY"
                        and edge.status == "APPROVED"
                    ]
                    if policy_edges:
                        tools.explain_edge(policy_edges[0].id)
                        tools.get_source_evidence(policy_edges[0].id)
                    else:
                        tools.list_coverage_gaps(change.id)
                else:
                    tools.get_change_impact(change.id)
                    tools.get_lineage(change.mandate_id)
        return list(tools.facts)[:12]

    async def ask(self, question: str, scenario_id: str) -> AskResponse:
        question = question.strip()
        if not 3 <= len(question) <= 1000:
            raise DomainError(
                "INVALID_QUESTION", "Ask a question between 3 and 1,000 characters.", 422
            )
        if scenario_id != self.bundle.scenario.id:
            raise DomainError("SCENARIO_NOT_FOUND", "The requested scenario was not found.", 404)
        started = perf_counter()
        tools = ReadOnlyTools(self.bundle, self.impact, max_calls=self.max_tool_calls)
        steps = []
        if getattr(self.transport, "final_selection_thinking_level", None):
            steps.append(
                RunStep(
                    name="bounded-agent-configuration",
                    status="CONFIGURED",
                    detail="LOW thinking during research; MINIMAL for constrained final "
                    "fact selection. At most two research rounds, then final selection.",
                )
            )
        run = WorkflowRun(
            workflow="ask-regimpact",
            kind="LIVE_AI" if self.transport else "LOCAL_DETERMINISTIC",
            status="BLOCKED",
            model=self.transport.model if self.transport else None,
            prompt_version="ask-regimpact-v1" if self.transport else None,
            validation_status="NOT_RUN",
            label=self.config().label,
            input_sha256=hashlib.sha256(question.encode()).hexdigest(),
            thinking_level=getattr(self.transport, "thinking_level", None),
        )

        def failed(detail: str, *, blocked: bool = False) -> AskResponse:
            return AskResponse(
                answer=UNGROUNDED_MESSAGE,
                grounded=False,
                verified_references=0,
                total_references=0,
                citations=(),
                tool_calls=tuple(tools.calls),
                run=run.model_copy(
                    update={
                        "status": "BLOCKED" if blocked else "MANUAL_REVIEW_REQUIRED",
                        "validation_status": "FAILED",
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                        "steps": tuple(
                            steps
                            + [RunStep(name="answer-validation", status="FAILED", detail=detail)]
                        ),
                    }
                ),
            )

        if self.screen:
            if not await self.screen.allow(question):
                return failed("Configured Model Armor input screening did not pass.", blocked=True)
            steps.append(
                RunStep(
                    name="model-armor-input",
                    status="SUCCEEDED",
                    detail="Input passed configured screening.",
                )
            )
        else:
            steps.append(
                RunStep(
                    name="model-armor",
                    status="NOT_CONFIGURED",
                    detail="No external screening is configured for this run.",
                )
            )
        try:
            if self.transport:
                run = run.model_copy(update={"attempts": 1})
                response = await self.transport.select_facts(question, tools)
                run = run.model_copy(
                    update={
                        "attempts": 1,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "provider_model_version": response.model_version,
                        "model_calls": response.model_calls,
                    }
                )
                selection = AskSelection.model_validate_json(response.text)
                selected = selection.fact_ids
            else:
                selected = await asyncio.to_thread(self._local_selection, question, tools)
        except (ValidationError, ValueError, DomainError):
            return failed("Read-only tool selection or structured answer selection failed.")
        except AdkModelError as exc:
            return failed(
                f"The live agent stopped ({exc.code}); no fixture answer was substituted."
            )
        except Exception:
            return failed("The live agent was unavailable; no fixture answer was substituted.")
        if not selected or any(fact_id not in tools.facts for fact_id in selected):
            return failed("No complete set of facts from this exact run supports the answer.")
        selected = list(dict.fromkeys(selected))
        facts = [tools.facts[fact_id] for fact_id in selected]
        references = tuple(
            dict.fromkeys(reference for fact in facts for reference in fact.references)
        )
        if not references or not set(references) <= tools.returned_ids:
            return failed("Answer references were not returned by this run's tools.")
        answer = "\n\n".join(
            fact.text + " " + " ".join(f"[{reference}]" for reference in fact.references)
            for fact in facts
        )
        # The answer contains only exact tool facts, not model-written claims carrying valid IDs.
        bracketed = re.findall(r"\[([^\[\]\n]+)\]", answer)
        if not set(bracketed) <= tools.returned_ids:
            return failed("A source fact contained an unsupported reference.")
        if self.screen and not await self.screen.allow(answer, is_response=True):
            return failed("Configured Model Armor output screening did not pass.", blocked=True)
        steps.append(
            RunStep(
                name="exact-run-grounding",
                status="SUCCEEDED",
                detail="Every displayed claim is an exact tool fact; "
                "all references came from this run.",
            )
        )
        return AskResponse(
            answer=answer,
            grounded=True,
            verified_references=len(references),
            total_references=len(references),
            citations=tuple(tools.citations[i] for i in references),
            tool_calls=tuple(tools.calls),
            run=run.model_copy(
                update={
                    "status": "SUCCEEDED",
                    "output_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                    "validation_status": "PASSED",
                    "steps": tuple(steps),
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            ),
        )
