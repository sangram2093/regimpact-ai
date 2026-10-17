import asyncio

import pytest

from app.domain.errors import DomainError
from app.services.candidates import CandidateService


class Repository:
    def __init__(self, bundle):
        self.bundle = bundle

    def snapshot(self):
        return self.bundle


def test_local_search_is_deterministic_and_never_invents_vector_provenance(bundle) -> None:
    service = CandidateService(Repository(bundle))
    first = asyncio.run(service.retrieve("M-GIFT"))
    second = asyncio.run(service.retrieve("M-GIFT"))
    assert first.candidates == second.candidates
    assert first.retrieval_mode == "LEXICAL_LOCAL"
    assert all(c.vector_rank is None for c in first.candidates)
    assert first.run.model is None
    assert first.candidates[0].id == "PR-GIFT-01"
    assert len(first.candidates) <= 8


def test_hybrid_search_requests_both_top15_then_rrf60(bundle) -> None:
    class Embeddings:
        async def embed(self, texts):
            return ((0.1,) * 768,)

    class Search:
        def __init__(self):
            self.limits = []

        async def vector_search(self, embedding, limit):
            self.limits.append(limit)
            return ("PR-GIFT-01", "PR-IDENTITY-01")

        async def lexical_search(self, query, limit):
            self.limits.append(limit)
            return ("PR-GIFT-01", "PR-CONSENT-01")

    search = Search()
    service = CandidateService(Repository(bundle), Embeddings(), search, "injected-embedding-model")
    result = asyncio.run(service.retrieve("M-GIFT"))
    assert search.limits == [15, 15]
    assert result.retrieval_mode == "HYBRID"
    assert result.candidates[0].rrf_score == pytest.approx(2 / 61)
    assert result.embedding_model == "injected-embedding-model"


def test_unknown_search_ids_fail_closed_instead_of_entering_model_context(bundle) -> None:
    class Embeddings:
        async def embed(self, texts):
            return ((0.1,) * 768,)

    class Search:
        async def vector_search(self, embedding, limit):
            return ("INVENTED",)

        async def lexical_search(self, query, limit):
            return ()

    with pytest.raises(DomainError, match="unknown policy"):
        asyncio.run(CandidateService(Repository(bundle), Embeddings(), Search()).retrieve("M-GIFT"))


def test_partially_configured_hybrid_does_not_fall_back(bundle) -> None:
    with pytest.raises(ValueError, match="requires both"):
        CandidateService(Repository(bundle), embedding_client=object())


def test_query_includes_proposal_and_retains_prior_policy_without_fake_rank(bundle) -> None:
    captured = []

    class Embeddings:
        async def embed(self, texts):
            captured.extend(texts)
            return ((0.1,) * 768,)

    class Search:
        async def vector_search(self, embedding, limit):
            return ("PR-CONSENT-01",)

        async def lexical_search(self, query, limit):
            return ("PR-IDENTITY-01",)

    result = asyncio.run(
        CandidateService(Repository(bundle), Embeddings(), Search()).retrieve("M-GIFT")
    )
    change = next(c for c in bundle.changes if c.mandate_id == "M-GIFT")
    assert change.summary in captured[0]
    assert all(
        next(e.text for e in bundle.evidence if e.id == ref) in captured[0]
        for ref in change.proposal_evidence_ids
    )
    prior = next(c for c in result.candidates if c.id == "PR-GIFT-01")
    assert prior.origin == "APPROVED_BASELINE"
    assert prior.rrf_rank is None and prior.rrf_score is None
    assert prior.vector_rank is None and prior.lexical_rank is None
    assert len(result.candidates) <= 8
