from app.domain.errors import DomainError
from app.domain.models import BaselineEdge, Classification, NodeType, Relationship, SeedBundle
from app.domain.views import ControlImpact, EdgeExplanation, ImpactEdge, ImpactNode, ImpactResponse
from app.repositories.ports import GraphRepository


class ImpactService:
    def __init__(self, bundle: SeedBundle, graph: GraphRepository) -> None:
        self.bundle = bundle
        self.graph = graph
        self.mandates = {m.id: m for m in bundle.mandates}
        self.catalog = {n.id: n for n in bundle.catalog}
        self.evidence = {e.id: e for e in bundle.evidence}
        self.edges = {edge.id: edge for edge in bundle.edges}
        # The approved baseline is immutable for the life of the process, so baseline
        # impact can be computed once per change instead of on every dashboard load.
        self._impact_cache: dict[str, ImpactResponse] = {}

    def risk_tags(self, mandate_id: str) -> tuple[str, ...]:
        return tuple(
            self.catalog[edge.target_id].title
            for edge in self.graph.approved_outgoing(mandate_id)
            if edge.relationship in {Relationship.CLASSIFIED_AS, Relationship.DRIVEN_BY}
        )

    def change_impact(self, change_id: str) -> ImpactResponse:
        cached = self._impact_cache.get(change_id)
        if cached is None:
            cached = self._compute_change_impact(change_id)
            self._impact_cache[change_id] = cached
        return cached.model_copy(deep=True)

    def _compute_change_impact(self, change_id: str) -> ImpactResponse:
        change = next((c for c in self.bundle.changes if c.id == change_id), None)
        if change is None:
            raise DomainError("CHANGE_NOT_FOUND", "The requested change was not found.", 404)
        mandate = self.mandates[change.mandate_id]
        nodes = {
            mandate.id: ImpactNode(
                id=mandate.id, label=mandate.title, type=NodeType.MANDATE, status=mandate.status
            )
        }
        edges: dict[str, ImpactEdge] = {}
        controls: dict[str, ControlImpact] = {}
        policy_edges = tuple(
            edge
            for edge in self.graph.approved_outgoing(mandate.id)
            if edge.relationship == Relationship.ADDRESSED_BY
        )
        policies_by_edge = {edge.id: edge for edge in policy_edges}
        controls_by_policy: dict[str, dict[str, BaselineEdge]] = {}
        # Controls must come from the graph adapter's approved path traversal. In GCP
        # this executes GQL; relational outgoing edges alone cannot manufacture a path.
        for path in self.graph.approved_control_paths(mandate.id):
            policy_edge = policies_by_edge.get(path.mandate_policy_edge_id)
            control_edge = self.edges.get(path.policy_control_edge_id)
            if (
                path.mandate_id != mandate.id
                or mandate.status != "BASELINE_APPROVED"
                or policy_edge is None
                or policy_edge.status != "APPROVED"
                or self.edges.get(policy_edge.id) != policy_edge
                or policy_edge.target_id != path.policy_id
                or control_edge is None
                or control_edge.status != "APPROVED"
                or control_edge.relationship != Relationship.IMPLEMENTED_BY
                or control_edge.source_id != path.policy_id
                or control_edge.target_id != path.control_id
            ):
                raise DomainError(
                    "INVALID_GRAPH_PATH",
                    "The graph returned a path inconsistent with approved baseline lineage.",
                    503,
                )
            controls_by_policy.setdefault(policy_edge.id, {})[control_edge.id] = control_edge
        covered_policies = 0
        for policy_edge in policy_edges:
            policy = self.catalog[policy_edge.target_id]
            nodes[policy.id] = ImpactNode(
                id=policy.id, label=policy.title, type=policy.type, status="APPROVED"
            )
            edges[policy_edge.id] = self._edge_view(policy_edge)
            control_edges = tuple(controls_by_policy.get(policy_edge.id, {}).values())
            covered_policies += bool(control_edges)
            for control_edge in control_edges:
                control = self.catalog[control_edge.target_id]
                nodes[control.id] = ImpactNode(
                    id=control.id, label=control.title, type=control.type, status="APPROVED"
                )
                edges[control_edge.id] = self._edge_view(control_edge)
                controls[control.id] = ControlImpact(id=control.id, title=control.title)
        if not policy_edges:
            coverage = "NO_POLICY_MAPPING"
            gap = (
                "This is a new proposed obligation. No approved policy mapping exists; "
                "a prospective mapping requires specialist review."
                if change.classification == Classification.NEW
                else "No approved policy mapping is available for this mandate."
            )
        elif covered_policies < len(policy_edges):
            coverage = "PARTIAL"
            gap = "At least one mapped policy has no approved control relationship."
        else:
            coverage = "COMPLETE"
            gap = None
        return ImpactResponse(
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            controls=tuple(controls.values()),
            coverage=coverage,
            risk_tags=self.risk_tags(mandate.id),
            gap_reason=gap,
        )

    @staticmethod
    def _edge_view(edge: BaselineEdge) -> ImpactEdge:
        return ImpactEdge(
            id=edge.id,
            source=edge.source_id,
            target=edge.target_id,
            label=edge.relationship,
            status=edge.status,
        )

    def explain_edge(self, edge_id: str) -> EdgeExplanation:
        edge = next((edge for edge in self.bundle.edges if edge.id == edge_id), None)
        if edge is None:
            raise DomainError("EDGE_NOT_FOUND", "The requested relationship was not found.", 404)
        return EdgeExplanation(
            id=edge.id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            relationship=edge.relationship,
            status=edge.status,
            evidence=tuple(self.evidence[evidence_id] for evidence_id in edge.evidence_ids),
            provenance=edge.provenance,
            data_origin=edge.data_origin,
            catalog_relationship=edge.relationship == Relationship.IMPLEMENTED_BY,
        )
