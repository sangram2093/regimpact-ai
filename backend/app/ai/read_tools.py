"""The complete Ask capability surface: six read-only tools with a per-run fact ledger."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.ai.contracts import AskCitation, AskToolCall
from app.domain.errors import DomainError
from app.domain.models import Relationship, SeedBundle
from app.services.impact import ImpactService


@dataclass(frozen=True)
class ToolFact:
    fact_id: str
    text: str
    references: tuple[str, ...]
    legal_status: str


class ReadOnlyTools:
    TOOL_NAMES = (
        "search_entities",
        "get_lineage",
        "get_change_impact",
        "explain_edge",
        "list_coverage_gaps",
        "get_source_evidence",
    )

    def __init__(self, bundle: SeedBundle, impact: ImpactService, *, max_calls: int = 8) -> None:
        if not 1 <= max_calls <= 12:
            raise ValueError("Ask tool-call limit must be between one and twelve")
        self.bundle = bundle
        self.impact = impact
        self.max_calls = max_calls
        self.calls: list[AskToolCall] = []
        self.facts: dict[str, ToolFact] = {}
        self.returned_ids: set[str] = set()
        self.citations = self._build_citations()

    def _build_citations(self) -> dict[str, AskCitation]:
        citations = {
            item.id: AskCitation(id=item.id, label=item.title, type="MANDATE")
            for item in self.bundle.mandates
        }
        citations.update(
            {
                item.id: AskCitation(id=item.id, label=item.title, type=item.type)
                for item in self.bundle.catalog
            }
        )
        citations.update(
            {
                item.id: AskCitation(
                    id=item.id, label=item.title, type="SOURCE", source_url=item.source_url
                )
                for item in self.bundle.instruments
            }
        )
        citations.update(
            {
                item.id: AskCitation(
                    id=item.id,
                    label=f"{item.title} · {item.paragraph_ref}",
                    type="EVIDENCE",
                    excerpt=item.text if item.text_kind == "VERIFIED_EXCERPT" else None,
                    source_url=item.source_url,
                )
                for item in self.bundle.evidence
            }
        )
        citations.update(
            {
                item.id: AskCitation(
                    id=item.id,
                    label=item.title,
                    type="PROPOSED_CHANGE" if item.is_proposal else "FINAL_CHANGE",
                )
                for item in self.bundle.changes
            }
        )
        citations.update(
            {
                item.id: AskCitation(
                    id=item.id, label=f"{item.source_id} → {item.target_id}", type="RELATIONSHIP"
                )
                for item in self.bundle.edges
            }
        )
        citations[self.bundle.scenario.id] = AskCitation(
            id=self.bundle.scenario.id,
            label=self.bundle.scenario.title,
            type="PROPOSED_SCENARIO" if self.bundle.scenario.status == "PROPOSED" else "SCENARIO",
        )
        return citations

    @staticmethod
    def fact(text: str, references: tuple[str, ...], legal_status: str) -> ToolFact:
        raw = json.dumps([text, references, legal_status], ensure_ascii=False)
        fact_id = "FACT-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        return ToolFact(fact_id, text, references, legal_status)

    def _start(self, name: str) -> None:
        if len(self.calls) >= self.max_calls:
            raise DomainError("ASK_TOOL_LIMIT", "Ask reached its read-only tool limit.", 429)
        self.calls.append(AskToolCall(name=name, status="FAILED", summary="Tool did not complete."))

    def _record(self, facts: list[ToolFact]) -> dict[str, Any]:
        if len(facts) > 60:
            facts = facts[:60]
        for fact in facts:
            if not set(fact.references) <= self.citations.keys():
                raise ValueError("Tool fact references an unknown graph entity")
            self.facts[fact.fact_id] = fact
            self.returned_ids.update(fact.references)
        self.calls[-1] = self.calls[-1].model_copy(
            update={
                "status": "SUCCEEDED",
                "summary": f"Returned {len(facts)} evidence-backed graph facts.",
            }
        )
        return {
            "facts": [
                {
                    "fact_id": fact.fact_id,
                    "text": fact.text,
                    "references": fact.references,
                    "legal_status": fact.legal_status,
                }
                for fact in facts
            ]
        }

    def search_entities(self, query: str, types: list[str] | None = None) -> dict[str, Any]:
        """Search graph labels. Types may include MANDATE, POLICY_REQUIREMENT or PROPOSED_CHANGE."""
        self._start("search_entities")
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        allowed_types = set(types or [])
        facts = []
        for entity_id, citation in self.citations.items():
            if allowed_types and citation.type not in allowed_types:
                continue
            words = set(re.findall(r"[a-z0-9]+", f"{entity_id} {citation.label}".lower()))
            if not terms & words:
                continue
            is_proposed = citation.type.startswith("PROPOSED") or any(
                mandate.id == entity_id and mandate.status == "PROPOSED"
                for mandate in self.bundle.mandates
            )
            prefix = "Proposed" if is_proposed else "Catalog or baseline"
            facts.append(
                self.fact(
                    f"{prefix} {citation.type.lower().replace('_', ' ')}: {citation.label}.",
                    (entity_id,),
                    "PROPOSED" if is_proposed else "BASELINE",
                )
            )
        return self._record(facts[:15])

    def get_lineage(self, entity_id: str, direction: str = "downstream") -> dict[str, Any]:
        """Read approved direct mandate-policy-control lineage, never shared risk paths."""
        self._start("get_lineage")
        if direction not in {"downstream", "upstream"}:
            raise ValueError("Lineage direction must be downstream or upstream")
        if entity_id not in self.citations:
            raise DomainError("ENTITY_NOT_FOUND", "Graph entity not found.", 404)
        facts = []
        frontier = {entity_id}
        visited: set[str] = set()
        for _ in range(2):
            next_frontier: set[str] = set()
            for edge in self.bundle.edges:
                source = edge.source_id if direction == "downstream" else edge.target_id
                target = edge.target_id if direction == "downstream" else edge.source_id
                if (
                    source not in frontier
                    or edge.id in visited
                    or edge.status != "APPROVED"
                    or edge.relationship
                    not in {Relationship.ADDRESSED_BY, Relationship.IMPLEMENTED_BY}
                ):
                    continue
                visited.add(edge.id)
                next_frontier.add(target)
                facts.append(
                    self.fact(
                        f"Approved baseline relationship: {self.citations[edge.source_id].label} → "
                        f"{self.citations[edge.target_id].label}. "
                        "Enterprise mappings are synthetic fixtures.",
                        (edge.source_id, edge.id, edge.target_id),
                        "BASELINE",
                    )
                )
            frontier = next_frontier
        return self._record(facts)

    def get_change_impact(self, change_event_id: str) -> dict[str, Any]:
        """Read prospective change impact over approved baseline compliance paths."""
        self._start("get_change_impact")
        change = next((c for c in self.bundle.changes if c.id == change_event_id), None)
        if change is None:
            raise DomainError("CHANGE_NOT_FOUND", "Proposed change not found.", 404)
        impact = self.impact.change_impact(change_event_id)
        refs = (change.id, change.mandate_id)
        final = not change.is_proposal
        status = "FINAL" if final else "PROPOSED"
        facts = [
            self.fact(
                f"Final change ({self.bundle.scenario.proposal_label}): {change.summary}"
                if final
                else f"Proposed change: {change.summary} This is not an in-force requirement.",
                refs + change.proposal_evidence_ids,
                status,
            )
        ]
        if not impact.controls:
            facts.append(
                self.fact(
                    impact.gap_reason
                    or "No approved control path exists for this proposed mandate.",
                    refs,
                    status,
                )
            )
        mandate = self.citations[change.mandate_id].label
        nature = ", ".join(item.lower().replace("_", " ") for item in change.change_nature)
        for control in impact.controls:
            # Explain the approved path that makes this control relevant; the policy comes
            # from the same traversal, so the reason never relies on shared risk tags.
            policy_ids = tuple(
                dict.fromkeys(
                    edge.source
                    for edge in impact.edges
                    if edge.target == control.id and edge.source in self.citations
                )
            )
            policies = " and ".join(self.citations[item].label for item in policy_ids)
            why = (
                f" Why: it implements {policies}, which addresses the "
                f"{change.classification.value.lower()} mandate '{mandate}'"
                + (f"; change nature: {nature}." if nature else ".")
                if policy_ids
                else ""
            )
            facts.append(
                self.fact(
                    (
                        f"Control to review under the final guideline: {control.title}."
                        if final
                        else "Prospective control to review if the proposal is adopted: "
                        f"{control.title}."
                    )
                    + why,
                    refs + policy_ids + (control.id,),
                    status,
                )
            )
        return self._record(facts)

    def explain_edge(self, edge_id: str) -> dict[str, Any]:
        """Read relationship evidence and provenance; this tool cannot approve a mapping."""
        self._start("explain_edge")
        explanation = self.impact.explain_edge(edge_id)
        if explanation.status != "APPROVED":
            return self._record([])
        references = (edge_id, explanation.source_id, explanation.target_id) + tuple(
            evidence.id for evidence in explanation.evidence
        )
        text = (
            f"Approved baseline mapping rationale: {explanation.provenance.reason} "
            "Provenance is SEED / GOLDEN_LABELS; "
            "no live model or real reviewer approval is claimed."
        )
        return self._record([self.fact(text, references, "BASELINE")])

    def list_coverage_gaps(self, change_event_id: str) -> dict[str, Any]:
        """List explicit policy or control gaps for a proposed change or scenario."""
        self._start("list_coverage_gaps")
        changes = (
            self.bundle.changes
            if change_event_id == self.bundle.scenario.id
            else tuple(change for change in self.bundle.changes if change.id == change_event_id)
        )
        if not changes:
            raise DomainError("CHANGE_NOT_FOUND", "Proposed change or scenario not found.", 404)
        facts = []
        for change in changes:
            impact = self.impact.change_impact(change.id)
            if impact.coverage != "COMPLETE":
                facts.append(
                    self.fact(
                        f"Prospective coverage gap for {change.title}: {impact.gap_reason}",
                        (change.id, change.mandate_id),
                        "PROPOSED",
                    )
                )
        if not facts:
            facts.append(
                self.fact(
                    "The selected proposed change has complete baseline policy/control lineage. "
                    "This does not establish compliance with a future proposal.",
                    (change_event_id,),
                    "PROPOSED",
                )
            )
        return self._record(facts)

    def get_source_evidence(self, entity_id: str) -> dict[str, Any]:
        """Read public source evidence, preserving paraphrase and proposal labels."""
        self._start("get_source_evidence")
        evidence_ids: set[str] = set()
        for mandate in self.bundle.mandates:
            if mandate.id == entity_id:
                evidence_ids.update(mandate.evidence_ids)
        for change in self.bundle.changes:
            if change.id == entity_id:
                evidence_ids.update(change.baseline_evidence_ids + change.proposal_evidence_ids)
        for edge in self.bundle.edges:
            if edge.id == entity_id:
                evidence_ids.update(edge.evidence_ids)
        if any(evidence.id == entity_id for evidence in self.bundle.evidence):
            evidence_ids.add(entity_id)
        proposed_sources = {p.source_id for p in self.bundle.proposals}
        facts = []
        for evidence in self.bundle.evidence:
            if evidence.id not in evidence_ids:
                continue
            status = "PROPOSED" if evidence.source_id in proposed_sources else "BASELINE"
            label = "Source paraphrase" if evidence.text_kind == "PARAPHRASE" else "Source excerpt"
            facts.append(
                self.fact(
                    f"{status} {label} ({evidence.paragraph_ref}): {evidence.text}",
                    (evidence.id, evidence.source_id),
                    status,
                )
            )
        return self._record(facts)
