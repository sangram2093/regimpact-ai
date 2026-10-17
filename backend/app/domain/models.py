from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Classification(StrEnum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    NEW = "NEW"
    REMOVED = "REMOVED"
    UNRESOLVED = "UNRESOLVED"


class AssessmentStatus(StrEnum):
    CARRY_FORWARD_PENDING_ACK = "CARRY_FORWARD_PENDING_ACK"
    SCENARIO_ACKNOWLEDGED = "SCENARIO_ACKNOWLEDGED"
    RE_REVIEW_REQUIRED = "RE_REVIEW_REQUIRED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    SCENARIO_APPROVED = "SCENARIO_APPROVED"
    SCENARIO_REJECTED = "SCENARIO_REJECTED"
    NO_POLICY_MAPPING = "NO_POLICY_MAPPING"


class NodeType(StrEnum):
    MANDATE = "MANDATE"
    POLICY_REQUIREMENT = "POLICY_REQUIREMENT"
    CONTROL_OBJECTIVE = "CONTROL_OBJECTIVE"
    RISK_TYPE = "RISK_TYPE"
    RISK_DRIVER = "RISK_DRIVER"


class Relationship(StrEnum):
    ADDRESSED_BY = "ADDRESSED_BY"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    CLASSIFIED_AS = "CLASSIFIED_AS"
    DRIVEN_BY = "DRIVEN_BY"


MANDATE_RELATIONSHIPS = frozenset(
    {Relationship.ADDRESSED_BY, Relationship.CLASSIFIED_AS, Relationship.DRIVEN_BY}
)


class Evidence(FrozenModel):
    id: str
    source_id: str
    title: str
    source_url: str
    paragraph_ref: str
    page: int | None = None
    text: str
    text_kind: Literal["VERIFIED_EXCERPT", "PARAPHRASE"]
    verification_status: str
    data_origin: Literal["PUBLIC_REGULATORY_SOURCE", "SYNTHETIC_HACKATHON"]


class RegulatoryInstrument(FrozenModel):
    id: str
    title: str
    regulator: str
    publication_date: str
    status: str
    source_url: str
    data_origin: Literal["PUBLIC_REGULATORY_SOURCE"] = "PUBLIC_REGULATORY_SOURCE"
    verification_status: str = "PENDING_VERIFICATION"


class RegulationVersion(FrozenModel):
    id: str
    instrument_id: str
    legal_force: Literal["GUIDANCE"] = "GUIDANCE"
    status: Literal["IN_FORCE"] = "IN_FORCE"


class ChangeProposal(FrozenModel):
    id: str
    source_id: str
    baseline_version_id: str
    status: Literal["PROPOSED"] = "PROPOSED"
    legal_force_after: Literal["PROPOSED_BINDING"] = "PROPOSED_BINDING"


class Provision(FrozenModel):
    id: str
    regulation_version_id: str
    title: str
    evidence_ids: tuple[str, ...]


class Mandate(FrozenModel):
    id: str
    title: str
    provision_id: str | None
    evidence_ids: tuple[str, ...]
    status: Literal["BASELINE_APPROVED", "PROPOSED"]
    data_origin: Literal["PUBLIC_REGULATORY_SOURCE", "SYNTHETIC_HACKATHON"]


class CatalogNode(FrozenModel):
    id: str
    title: str
    text: str = ""
    type: NodeType
    data_origin: Literal["SYNTHETIC_HACKATHON"] = "SYNTHETIC_HACKATHON"


class EdgeProvenance(FrozenModel):
    proposed_by: Literal["SEED", "DETERMINISTIC_RETRIEVAL", "AI"] = "SEED"
    decision_source: Literal["GOLDEN_LABELS", "HUMAN_REVIEW"] = "GOLDEN_LABELS"
    model: str | None = None
    prompt_version: str | None = None
    reviewer: str = "Curated demonstration fixture"
    reviewed_at: str | None = None
    vector_rank: int | None = None
    lexical_rank: int | None = None
    rrf_rank: int | None = None
    rrf_score: float | None = None
    agent_run_id: str | None = None
    reason: str
    alternative: str | None = None
    alternative_reason: str | None = None


class BaselineEdge(FrozenModel):
    id: str
    source_id: str
    target_id: str
    relationship: Relationship
    status: Literal["APPROVED", "PROPOSED", "REJECTED"] = "APPROVED"
    evidence_ids: tuple[str, ...] = ()
    provenance: EdgeProvenance
    data_origin: Literal["SYNTHETIC_HACKATHON"] = "SYNTHETIC_HACKATHON"


class ProposedChangeStatement(FrozenModel):
    id: str
    proposal_id: str
    summary: str
    target_mandate_ids: tuple[str, ...]
    global_scope: bool = False
    evidence_ids: tuple[str, ...]


class SafetyChecks(FrozenModel):
    high_confidence_pcs_target: bool
    applicable_global_overlay: bool
    no_effect_result: Literal["NO_EFFECT_SUPPORTED", "EFFECT_POSSIBLE", "NOT_RUN"]
    human_change_confirmed: bool
    scope_basis: str
    decision_source: Literal["GOLDEN_LABELS"] = "GOLDEN_LABELS"


class ChangeItem(FrozenModel):
    id: str
    title: str
    classification: Classification
    change_nature: tuple[str, ...]
    summary: str
    mandate_id: str
    baseline_evidence_ids: tuple[str, ...]
    proposal_evidence_ids: tuple[str, ...]
    safety_checks: SafetyChecks
    is_proposal: Literal[True] = True


class ImpactScenario(FrozenModel):
    id: str
    title: str
    regulator: str
    baseline_label: str
    proposal_label: str
    status: Literal["PROPOSED"] = "PROPOSED"
    proposal_notice: str = "PROPOSED — NOT AN IN-FORCE REQUIREMENT"
    baseline_version_id: str
    proposal_id: str
    baseline_mandate_ids: tuple[str, ...]
    disclosure: str


class ScenarioMappingAssessment(FrozenModel):
    id: str
    scenario_id: str
    baseline_edge_id: str
    mandate_id: str
    classification: Classification
    status: AssessmentStatus
    recommendation: str
    reason: str
    eligible_for_carry_forward: bool
    reviewed_by: str | None = None
    rationale: str | None = None
    reviewed_at: str | None = None


class ReviewDecision(FrozenModel):
    assessment_id: str
    decision: Literal["APPROVE", "REJECT", "ACKNOWLEDGE"]
    reviewer: str
    role: Literal["Policy Owner", "Risk Steward", "Regulatory Specialist"]
    rationale: str
    reviewed_at: str


class ImpactAssessment(FrozenModel):
    control_id: str
    change_id: str
    impact_type: Literal["PROSPECTIVE_REVIEW"] = "PROSPECTIVE_REVIEW"


class AgentRun(FrozenModel):
    id: str = "SEED-RUN-001"
    kind: Literal["SEED"] = "SEED"
    status: Literal["READY"] = "READY"
    model: None = None
    timestamp: None = None
    duration_ms: None = None
    label: str = "Curated demonstration fixture — no live AI run"


class SeedBundle(FrozenModel):
    instruments: tuple[RegulatoryInstrument, ...]
    versions: tuple[RegulationVersion, ...]
    proposals: tuple[ChangeProposal, ...]
    provisions: tuple[Provision, ...]
    mandates: tuple[Mandate, ...]
    evidence: tuple[Evidence, ...]
    catalog: tuple[CatalogNode, ...]
    edges: tuple[BaselineEdge, ...]
    proposed_change_statements: tuple[ProposedChangeStatement, ...]
    changes: tuple[ChangeItem, ...]
    scenario: ImpactScenario

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        collections = (
            self.instruments,
            self.versions,
            self.proposals,
            self.provisions,
            self.mandates,
            self.evidence,
            self.catalog,
            self.edges,
            self.proposed_change_statements,
            self.changes,
        )
        all_ids: set[str] = set()
        for collection in collections:
            for item in collection:
                if item.id in all_ids:
                    raise ValueError(f"Duplicate seed ID: {item.id}")
                all_ids.add(item.id)
        mandate_ids = {m.id for m in self.mandates}
        evidence_ids = {e.id for e in self.evidence}
        instrument_ids = {i.id for i in self.instruments}
        provision_ids = {p.id for p in self.provisions}
        version_ids = {v.id for v in self.versions}
        proposal_ids = {p.id for p in self.proposals}
        node_types = {m.id: NodeType.MANDATE for m in self.mandates} | {
            n.id: n.type for n in self.catalog
        }
        expected_types = {
            Relationship.ADDRESSED_BY: (NodeType.MANDATE, NodeType.POLICY_REQUIREMENT),
            Relationship.IMPLEMENTED_BY: (NodeType.POLICY_REQUIREMENT, NodeType.CONTROL_OBJECTIVE),
            Relationship.CLASSIFIED_AS: (NodeType.MANDATE, NodeType.RISK_TYPE),
            Relationship.DRIVEN_BY: (NodeType.MANDATE, NodeType.RISK_DRIVER),
        }
        for evidence in self.evidence:
            if evidence.source_id not in instrument_ids:
                raise ValueError(f"Unknown evidence source: {evidence.source_id}")
        for version in self.versions:
            if version.instrument_id not in instrument_ids:
                raise ValueError("Unknown instrument for version")
        for proposal in self.proposals:
            if (
                proposal.source_id not in instrument_ids
                or proposal.baseline_version_id not in version_ids
            ):
                raise ValueError("Invalid proposal source or baseline")
        for provision in self.provisions:
            if provision.regulation_version_id not in version_ids:
                raise ValueError("Unknown version for provision")
        for mandate in self.mandates:
            if mandate.provision_id is not None and mandate.provision_id not in provision_ids:
                raise ValueError("Unknown mandate provision")
        for edge in self.edges:
            pair = (node_types.get(edge.source_id), node_types.get(edge.target_id))
            if pair != expected_types[edge.relationship]:
                raise ValueError(f"Invalid lineage relationship: {edge.id}")
        for item in (
            *self.provisions,
            *self.mandates,
            *self.edges,
            *self.proposed_change_statements,
        ):
            if not set(item.evidence_ids) <= evidence_ids:
                raise ValueError(f"Unknown evidence reference on {item.id}")
        for pcs in self.proposed_change_statements:
            if (
                pcs.proposal_id not in proposal_ids
                or not set(pcs.target_mandate_ids) <= mandate_ids
            ):
                raise ValueError("Invalid PCS proposal or target")
        for change in self.changes:
            if change.mandate_id not in mandate_ids:
                raise ValueError(f"Unknown change mandate: {change.id}")
            if not set(change.baseline_evidence_ids + change.proposal_evidence_ids) <= evidence_ids:
                raise ValueError(f"Unknown change evidence: {change.id}")
        if len({c.mandate_id for c in self.changes}) != len(self.changes):
            raise ValueError("Each mandate must have a single scenario change classification")
        if not set(self.scenario.baseline_mandate_ids) <= mandate_ids:
            raise ValueError("Unknown baseline mandate in scenario")
        if self.scenario.baseline_version_id not in version_ids:
            raise ValueError("Unknown baseline version in scenario")
        if self.scenario.proposal_id not in proposal_ids:
            raise ValueError("Unknown proposal in scenario")
        return self


class ReviewMetrics(FrozenModel):
    existing_mapping_items: int = Field(ge=0)
    carry_forward_candidates: int = Field(ge=0)
    acknowledged_mappings: int = Field(ge=0)
    individual_rechecks: int = Field(ge=0)
    completed_rechecks: int = Field(ge=0)
    unresolved_items: int = Field(ge=0)
    bulk_ack_actions: int = Field(ge=0, le=1)
    estimated_review_reduction: float | None
    review_reduction: float | None
    carry_forward_rate: float | None
    new_obligations: int = Field(ge=0)
