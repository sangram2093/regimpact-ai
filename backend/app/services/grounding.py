"""Deterministic guards; ID membership alone never certifies factual claim support."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSegment:
    id: str
    source_id: str
    text: str


def validate_excerpt(
    source_id: str,
    segment_id: str,
    excerpt: str,
    *,
    sources: frozenset[str],
    segments: dict[str, SourceSegment],
) -> bool:
    segment = segments.get(segment_id)
    return bool(
        source_id in sources
        and segment is not None
        and segment.source_id == source_id
        and excerpt.strip()
        and excerpt in segment.text
    )


def validate_candidate_id(candidate_id: str | None, allowed_ids: frozenset[str]) -> bool:
    return candidate_id is None or candidate_id in allowed_ids


def validate_answer_references(answer: str, run_result_ids: frozenset[str]) -> bool:
    """Only verifies membership in this run. Must not label free-text claims grounded."""
    references = re.findall(r"\[([^\[\]\n]+)\]", answer)
    return bool(references) and all(reference in run_result_ids for reference in references)


@dataclass(frozen=True)
class SupportedClaim:
    text: str
    entity_ids: tuple[str, ...]
    legal_status: str


def validate_supported_claims(
    claims: tuple[SupportedClaim, ...], allowed_claims: tuple[SupportedClaim, ...]
) -> bool:
    """Allow only exact deterministic tool facts, including their legal status.

    This first-slice guard is intentionally conservative. A future free-text Ask
    workflow needs additional claim/evidence support checks, not just valid IDs.
    """
    return bool(claims) and all(claim in allowed_claims for claim in claims)
