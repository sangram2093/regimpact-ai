import asyncio
import math
import re
from time import perf_counter

from app.ai.contracts import Candidate, CandidateResult, RunStep, WorkflowRun
from app.domain.errors import DomainError
from app.domain.models import NodeType
from app.repositories.ports import EmbeddingClient, RegulatoryRepository, SearchRepository
from app.services.retrieval import reciprocal_rank_fusion


class CandidateService:
    """Deterministic preparation; absent cloud embeddings are never simulated."""

    def __init__(
        self,
        repository: RegulatoryRepository,
        embedding_client: EmbeddingClient | None = None,
        search_repository: SearchRepository | None = None,
        embedding_model: str | None = None,
    ) -> None:
        if (embedding_client is None) != (search_repository is None):
            raise ValueError("Hybrid retrieval requires both embedding and search adapters")
        self.bundle = repository.snapshot()
        self.embedding_client = embedding_client
        self.search_repository = search_repository
        self.embedding_model = embedding_model

    async def retrieve(self, mandate_id: str) -> CandidateResult:
        started = perf_counter()
        run = WorkflowRun(
            workflow="policy-candidates",
            kind="LOCAL_DETERMINISTIC",
            status="SUCCEEDED",
            label="Deterministic candidate retrieval — no generative AI judgment",
            validation_status="PASSED",
        )
        mandate = next((item for item in self.bundle.mandates if item.id == mandate_id), None)
        if mandate is None:
            raise DomainError("MANDATE_NOT_FOUND", "The requested mandate was not found.", 404)
        policies = {n.id: n for n in self.bundle.catalog if n.type == NodeType.POLICY_REQUIREMENT}
        evidence = {e.id: e for e in self.bundle.evidence}
        query = mandate.title + " " + " ".join(evidence[i].text for i in mandate.evidence_ids)
        change = next((c for c in self.bundle.changes if c.mandate_id == mandate_id), None)
        if change:
            proposal_ids = set(change.proposal_evidence_ids)
            for statement in self.bundle.proposed_change_statements:
                if statement.global_scope or mandate_id in statement.target_mandate_ids:
                    proposal_ids.update(statement.evidence_ids)
            query += (
                " "
                + change.summary
                + " "
                + " ".join(evidence[i].text for i in sorted(proposal_ids))
            )
        if self.embedding_client and self.search_repository:
            embeddings = await self.embedding_client.embed((query,))
            if (
                len(embeddings) != 1
                or not embeddings[0]
                or not all(math.isfinite(value) for value in embeddings[0])
            ):
                raise DomainError(
                    "EMBEDDING_INVALID", "Embedding provider returned invalid data.", 502
                )
            vector_raw, lexical_raw = await asyncio.gather(
                self.search_repository.vector_search(embeddings[0], limit=15),
                self.search_repository.lexical_search(query, limit=15),
            )
            # Candidates from the repository must still belong to the allowed catalog.
            if any(item not in policies for item in (*vector_raw, *lexical_raw)):
                raise DomainError("RETRIEVAL_INVALID", "Search returned an unknown policy ID.", 502)
            vector_ids = tuple(vector_raw[:15])
            lexical_ids = tuple(lexical_raw[:15])
            mode = "HYBRID"
            detail = "Top 15 vector + top 15 lexical; RRF k=60; top 8 retained."
        else:
            query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
            scores = {
                key: len(
                    query_tokens
                    & set(re.findall(r"[a-z0-9]+", (node.title + " " + node.text).lower()))
                )
                for key, node in policies.items()
            }
            lexical_ids = tuple(
                key
                for key in sorted(scores, key=lambda key: (-scores[key], key))
                if scores[key] > 0
            )[:15]
            vector_ids = ()
            mode = "LEXICAL_LOCAL"
            detail = "Local token-overlap lexical retrieval; no vectors or model ranks are claimed."
        fused = reciprocal_rank_fusion(vector_ids, lexical_ids, k=60, limit=8)
        candidates = list(
            Candidate(
                id=item.id,
                title=policies[item.id].title,
                text=policies[item.id].text,
                type=policies[item.id].type,
                vector_rank=item.vector_rank,
                lexical_rank=item.lexical_rank,
                rrf_rank=item.rrf_rank,
                rrf_score=item.score,
                reason="Retrieved for specialist review; "
                "contextual suitability has not been approved.",
            )
            for item in fused
        )
        prior_ids = {
            edge.target_id
            for edge in self.bundle.edges
            if edge.source_id == mandate_id
            and edge.relationship == "ADDRESSED_BY"
            and edge.status == "APPROVED"
        }
        if len(prior_ids) > 8:
            raise DomainError(
                "CANDIDATE_LIMIT",
                "Review the baseline policy set manually; it exceeds the bounded context.",
                422,
            )
        for prior_id in sorted(prior_ids):
            prior = next((c for c in candidates if c.id == prior_id), None)
            if prior:
                candidates[candidates.index(prior)] = prior.model_copy(
                    update={
                        "origin": "APPROVED_BASELINE",
                        "reason": "Existing approved baseline policy; assess its suitability "
                        "against the proposed change.",
                    }
                )
            else:
                if len(candidates) == 8:
                    remove = next(
                        i
                        for i in reversed(range(len(candidates)))
                        if candidates[i].id not in prior_ids
                    )
                    candidates.pop(remove)
                candidates.append(
                    Candidate(
                        id=prior_id,
                        title=policies[prior_id].title,
                        text=policies[prior_id].text,
                        type=policies[prior_id].type,
                        vector_rank=None,
                        lexical_rank=None,
                        rrf_rank=None,
                        rrf_score=None,
                        origin="APPROVED_BASELINE",
                        reason="Existing approved baseline policy retained for comparison; "
                        "outside the retrieved top eight, so no retrieval rank is claimed.",
                    )
                )
        return CandidateResult(
            mandate_id=mandate_id,
            candidates=tuple(candidates),
            retrieval_mode=mode,
            embedding_model=self.embedding_model if mode == "HYBRID" else None,
            review_status="HUMAN_REVIEW_REQUIRED" if candidates else "NO_SUITABLE_CANDIDATE",
            run=run.model_copy(
                update={
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "kind": "LIVE_AI" if mode == "HYBRID" else "LOCAL_DETERMINISTIC",
                    "model": self.embedding_model if mode == "HYBRID" else None,
                    "candidate_ids": tuple(candidate.id for candidate in candidates),
                    "candidate_details": tuple(candidate.model_dump() for candidate in candidates),
                    "steps": (
                        RunStep(name="retrieve-and-fuse", status="SUCCEEDED", detail=detail),
                    ),
                }
            ),
        )
