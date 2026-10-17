"""Approved impact-path contract shared by local and cloud graph repositories."""

from dataclasses import dataclass

from app.domain.models import Relationship, SeedBundle


@dataclass(frozen=True, order=True)
class ApprovedControlPath:
    mandate_id: str
    policy_id: str
    control_id: str
    mandate_policy_edge_id: str
    policy_control_edge_id: str


def approved_control_paths(bundle: SeedBundle, mandate_id: str) -> tuple[ApprovedControlPath, ...]:
    """Local equivalent of the approved baseline mandate-policy-control GQL pattern."""
    if not any(
        mandate.id == mandate_id and mandate.status == "BASELINE_APPROVED"
        for mandate in bundle.mandates
    ):
        return ()
    policies = tuple(
        edge
        for edge in bundle.edges
        if edge.source_id == mandate_id
        and edge.relationship == Relationship.ADDRESSED_BY
        and edge.status == "APPROVED"
    )
    controls = tuple(
        edge
        for edge in bundle.edges
        if edge.relationship == Relationship.IMPLEMENTED_BY and edge.status == "APPROVED"
    )
    return tuple(
        sorted(
            {
                ApprovedControlPath(
                    mandate_id, policy.target_id, control.target_id, policy.id, control.id
                )
                for policy in policies
                for control in controls
                if control.source_id == policy.target_id
            }
        )
    )
