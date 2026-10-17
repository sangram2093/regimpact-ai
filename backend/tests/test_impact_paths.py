from dataclasses import replace

import pytest
from conftest import MemoryRepository

from app.adapters.local_json import LocalJsonRepository
from app.config.settings import Settings
from app.domain.errors import DomainError
from app.domain.graph import approved_control_paths
from app.domain.models import SeedBundle
from app.services.impact import ImpactService


def changed_edges(bundle, transform):
    values = bundle.model_dump()
    values["edges"] = transform(values["edges"])
    return SeedBundle.model_validate(values)


def test_local_paths_preserve_real_baseline_controls_and_no_new_obligation_path(bundle):
    repository = LocalJsonRepository(Settings().data_dir)
    service = ImpactService(bundle, repository)
    paths = repository.approved_control_paths("M-GIFT")
    assert {path.control_id for path in paths} == {"CO-GIFT-01", "CO-GIFT-02"}
    assert repository.approved_control_paths("M-INTENT-CONSENT") == ()
    assert repository.approved_control_paths("unknown") == ()
    assert service.change_impact("CHANGE-GIFT").coverage == "COMPLETE"
    assert service.change_impact("CHANGE-INTENT-CONSENT").coverage == "NO_POLICY_MAPPING"
    assert all("RISK" not in path.policy_control_edge_id for path in paths)


def test_control_paths_must_come_from_graph_even_when_relational_edges_exist(bundle):
    class NoPaths(MemoryRepository):
        def approved_control_paths(self, mandate_id):
            return ()

        def approved_outgoing(self, node_id):
            assert not node_id.startswith("PR-"), "Impact controls must use path traversal"
            return super().approved_outgoing(node_id)

    result = ImpactService(bundle, NoPaths(bundle)).change_impact("CHANGE-GIFT")
    assert result.coverage == "PARTIAL"
    assert result.controls == ()
    assert any(node.id == "PR-GIFT-01" for node in result.nodes)
    assert result.risk_tags  # Risk metadata remains visible but cannot create a control path.


def test_policy_with_no_control_keeps_partial_coverage_when_another_path_exists(bundle):
    def add_uncovered_policy(edges):
        original = next(
            e for e in edges if e["source_id"] == "M-GIFT" and e["relationship"] == "ADDRESSED_BY"
        )
        return (*edges, {**original, "id": "E-SYNTHETIC-UNCOVERED", "target_id": "PR-CONSENT-01"})

    revised = changed_edges(bundle, add_uncovered_policy)
    result = ImpactService(revised, MemoryRepository(revised)).change_impact("CHANGE-GIFT")
    assert result.coverage == "PARTIAL"
    assert len(result.controls) == 2
    assert {node.id for node in result.nodes if node.type == "POLICY_REQUIREMENT"} == {
        "PR-GIFT-01",
        "PR-CONSENT-01",
    }


@pytest.mark.parametrize("status", ["PROPOSED", "REJECTED"])
def test_unapproved_control_relationships_never_form_paths(bundle, status):
    def reject_controls(edges):
        return tuple(
            {**edge, "status": status} if edge["source_id"] == "PR-GIFT-01" else edge
            for edge in edges
        )

    revised = changed_edges(bundle, reject_controls)
    assert approved_control_paths(revised, "M-GIFT") == ()
    result = ImpactService(revised, MemoryRepository(revised)).change_impact("CHANGE-GIFT")
    assert result.coverage == "PARTIAL" and result.controls == ()


def test_duplicate_graph_rows_do_not_duplicate_controls_or_displayed_edges(bundle):
    class DuplicatedPaths(MemoryRepository):
        def approved_control_paths(self, mandate_id):
            paths = super().approved_control_paths(mandate_id)
            return paths + paths

    result = ImpactService(bundle, DuplicatedPaths(bundle)).change_impact("CHANGE-GIFT")
    assert len(result.controls) == 2
    assert len(result.edges) == len({edge.id for edge in result.edges}) == 3


def test_graph_path_mismatch_and_provider_failure_fail_closed(bundle):
    class InvalidPaths(MemoryRepository):
        def approved_control_paths(self, mandate_id):
            path = super().approved_control_paths(mandate_id)[0]
            return (replace(path, control_id="CO-IDENTITY-01"),)

    with pytest.raises(DomainError) as caught:
        ImpactService(bundle, InvalidPaths(bundle)).change_impact("CHANGE-GIFT")
    assert caught.value.code == "INVALID_GRAPH_PATH"

    class UnavailableGraph(MemoryRepository):
        def approved_control_paths(self, mandate_id):
            raise DomainError("SPANNER_GRAPH_FAILED", "synthetic graph failure", 503)

    with pytest.raises(DomainError) as caught:
        ImpactService(bundle, UnavailableGraph(bundle)).change_impact("CHANGE-GIFT")
    assert caught.value.code == "SPANNER_GRAPH_FAILED"
