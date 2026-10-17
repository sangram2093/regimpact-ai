"""Exact cosine KNN and indexed full-text retrieval; fusion is deterministic Python."""

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Any

from app.adapters.gcp.common import sql_types
from app.adapters.gcp.timeouts import TRANSACTION_RETRY_SECONDS, bounded_operation, rpc_options
from app.domain.errors import DomainError
from app.services.retrieval import FusedCandidate, reciprocal_rank_fusion

ALLOWED_KINDS = frozenset({"POLICY_REQUIREMENT", "CONTROL_OBJECTIVE", "RISK_TYPE", "RISK_DRIVER"})
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "to",
        "with",
    }
)


@dataclass(frozen=True)
class SearchEntity:
    id: str
    kind: str
    text: str
    embedding: tuple[float, ...] | None = None


class SpannerSearchRepository:
    def __init__(
        self,
        database: Any,
        scenario_id: str,
        *,
        entity_types: tuple[str, ...] = ("POLICY_REQUIREMENT",),
        embedding_model: str = "gemini-embedding-001",
        dimensions: int = 768,
    ) -> None:
        if not scenario_id or not embedding_model or dimensions != 768:
            raise ValueError(
                "Search requires a scenario, embedding model and the 768-dimension schema"
            )
        if not entity_types or not set(entity_types) <= ALLOWED_KINDS:
            raise ValueError("Search entity types must belong to the allowed catalog")
        self.database, self.scenario_id = database, scenario_id
        self.entity_types, self.embedding_model, self.dimensions = (
            entity_types,
            embedding_model,
            dimensions,
        )

    def _vector(self, embedding: tuple[float, ...]) -> None:
        if (
            len(embedding) != self.dimensions
            or not all(math.isfinite(value) for value in embedding)
            or not any(value != 0 for value in embedding)
        ):
            raise DomainError(
                "EMBEDDING_INVALID",
                "Search requires a finite, nonzero 768-dimensional embedding.",
                422,
            )

    def _arguments(self, limit: int) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("Search limit must be between 1 and 100")
        types = sql_types()
        return {
            "params": {
                "bundle": self.scenario_id,
                "kinds": list(self.entity_types),
                "limit": limit,
            },
            "param_types": {
                "bundle": types.STRING,
                "kinds": types.Array(types.STRING),
                "limit": types.INT64,
            },
        }

    @bounded_operation
    def _query(self, sql: str, arguments: dict[str, Any]) -> tuple[str, ...]:
        try:
            with self.database.snapshot() as snapshot:
                return tuple(
                    row[0] for row in snapshot.execute_sql(sql, **arguments, **rpc_options())
                )
        except Exception as exc:
            raise DomainError(
                "SPANNER_SEARCH_FAILED",
                "Spanner search is unavailable; no substitute rankings were generated.",
                503,
            ) from exc

    async def vector_search(self, embedding: tuple[float, ...], limit: int = 15) -> tuple[str, ...]:
        self._vector(embedding)
        types = sql_types()
        arguments = self._arguments(limit)
        arguments["params"].update(vector=list(embedding), model=self.embedding_model)
        arguments["param_types"].update(vector=types.Array(types.FLOAT32), model=types.STRING)
        return await asyncio.to_thread(
            self._query,
            """
            SELECT EntityId FROM SearchEntity
            WHERE BundleId = @bundle AND Kind IN UNNEST(@kinds) AND Status = 'ACTIVE'
              AND Embedding IS NOT NULL AND EmbeddingModel = @model
            ORDER BY COSINE_DISTANCE(Embedding, @vector), EntityId
            LIMIT @limit
        """,
            arguments,
        )

    @staticmethod
    def lexical_query(query: str) -> str:
        # SEARCH operators cannot be injected through arbitrary natural-language text.
        # Bounded OR terms recall candidates; the model later assesses their relevance.
        terms = list(dict.fromkeys(re.findall(r"[a-z0-9]+", query.lower()[:20000])))
        bounded = [term for term in terms if term not in STOP_WORDS and len(term) <= 64][:16]
        return " OR ".join(bounded)

    async def lexical_search(self, query: str, limit: int = 15) -> tuple[str, ...]:
        arguments = self._arguments(limit)
        normalized = self.lexical_query(query)
        if not normalized:
            return ()
        arguments["params"]["query"] = normalized
        arguments["param_types"]["query"] = sql_types().STRING
        return await asyncio.to_thread(
            self._query,
            """
            SELECT EntityId FROM SearchEntity
            WHERE BundleId = @bundle AND Kind IN UNNEST(@kinds) AND Status = 'ACTIVE'
              AND SEARCH(SearchTokens, @query)
            ORDER BY SCORE(SearchTokens, @query) DESC, EntityId
            LIMIT @limit
        """,
            arguments,
        )

    async def hybrid_search(
        self, embedding: tuple[float, ...], query: str, *, retrieval_limit: int = 15, limit: int = 8
    ) -> tuple[FusedCandidate, ...]:
        vector, lexical = await asyncio.gather(
            self.vector_search(embedding, retrieval_limit),
            self.lexical_search(query, retrieval_limit),
        )
        return reciprocal_rank_fusion(vector, lexical, k=60, limit=limit)

    @bounded_operation
    def index_entities(self, entities: tuple[SearchEntity, ...]) -> None:
        """Explicit index build, without calling models or changing baseline rows."""
        if (
            not entities
            or len(entities) > 1000
            or len({row.id for row in entities}) != len(entities)
        ):
            raise ValueError("Index batches need 1 to 1000 unique entities")
        for entity in entities:
            if entity.kind not in ALLOWED_KINDS or not entity.id or not entity.text.strip():
                raise ValueError("Index entity needs an allowed kind, ID and text")
            if entity.embedding is not None:
                self._vector(entity.embedding)
        values = [
            (
                self.scenario_id,
                entity.id,
                entity.kind,
                "ACTIVE",
                entity.text,
                list(entity.embedding) if entity.embedding is not None else None,
                self.embedding_model if entity.embedding is not None else None,
            )
            for entity in entities
        ]
        try:
            self.database.run_in_transaction(
                lambda transaction: transaction.insert_or_update(
                    "SearchEntity",
                    (
                        "BundleId",
                        "EntityId",
                        "Kind",
                        "Status",
                        "SearchText",
                        "Embedding",
                        "EmbeddingModel",
                    ),
                    values,
                ),
                timeout_secs=TRANSACTION_RETRY_SECONDS,
            )
        except Exception as exc:
            raise DomainError(
                "SPANNER_INDEX_FAILED",
                "Unable to build the explicitly requested search index.",
                503,
            ) from exc
