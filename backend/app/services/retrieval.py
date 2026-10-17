from dataclasses import dataclass


@dataclass(frozen=True)
class FusedCandidate:
    id: str
    score: float
    vector_rank: int | None
    lexical_rank: int | None
    rrf_rank: int


def reciprocal_rank_fusion(
    vector_ids: tuple[str, ...], lexical_ids: tuple[str, ...], *, k: int = 60, limit: int = 8
) -> tuple[FusedCandidate, ...]:
    """Fuse one-based ranks, suppress duplicates per list, break ties by stable ID."""
    if k <= 0 or limit <= 0:
        raise ValueError("k and limit must be positive")
    vector = {entity_id: rank for rank, entity_id in enumerate(dict.fromkeys(vector_ids), 1)}
    lexical = {entity_id: rank for rank, entity_id in enumerate(dict.fromkeys(lexical_ids), 1)}
    scores = {
        entity_id: (1 / (k + vector[entity_id]) if entity_id in vector else 0)
        + (1 / (k + lexical[entity_id]) if entity_id in lexical else 0)
        for entity_id in vector.keys() | lexical.keys()
    }
    ordered = sorted(scores, key=lambda entity_id: (-scores[entity_id], entity_id))[:limit]
    return tuple(
        FusedCandidate(
            entity_id, scores[entity_id], vector.get(entity_id), lexical.get(entity_id), rank
        )
        for rank, entity_id in enumerate(ordered, 1)
    )
