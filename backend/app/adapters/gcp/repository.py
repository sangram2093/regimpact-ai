"""Immutable, scenario-scoped relational baseline plus approved graph traversal."""

from typing import Any

from app.adapters.gcp.common import json_value, spanner_json, sql_types
from app.adapters.gcp.timeouts import (
    TRANSACTION_RETRY_SECONDS,
    bounded_operation,
    rpc_options,
)
from app.domain.errors import DomainError
from app.domain.graph import ApprovedControlPath
from app.domain.models import BaselineEdge, SeedBundle

# Table names are application constants, never user-supplied SQL identifiers.
NODE_TABLES = {
    "instruments": "RegulatoryInstrument",
    "versions": "RegulationVersion",
    "proposals": "ChangeProposal",
    "provisions": "RegulatoryProvision",
    "mandates": "Mandate",
    "evidence": "Evidence",
    "proposed_change_statements": "ProposedChangeStatement",
    "changes": "ChangeItem",
}
CATALOG_TABLES = {
    "POLICY_REQUIREMENT": "PolicyRequirement",
    "CONTROL_OBJECTIVE": "ControlObjective",
    "RISK_TYPE": "RiskType",
    "RISK_DRIVER": "RiskDriver",
}
EDGE_TABLES = {
    "ADDRESSED_BY": "MandateAddressedBy",
    "IMPLEMENTED_BY": "PolicyImplementedBy",
    "CLASSIFIED_AS": "MandateClassifiedAs",
    "DRIVEN_BY": "MandateDrivenBy",
}


class SpannerRegulatoryRepository:
    def __init__(self, database: Any, scenario_id: str) -> None:
        if not scenario_id:
            raise ValueError("An explicit scenario ID is required")
        self.database, self.scenario_id = database, scenario_id

    def _params(self) -> dict[str, Any]:
        return {
            "params": {"bundle": self.scenario_id},
            "param_types": {"bundle": sql_types().STRING},
        }

    @bounded_operation
    def snapshot(self) -> SeedBundle:
        try:
            with self.database.snapshot(multi_use=True) as snapshot:

                def rows(table: str) -> list[dict[str, Any]]:
                    return [
                        json_value(row[0])
                        for row in snapshot.execute_sql(
                            f"SELECT Payload FROM {table} WHERE BundleId = @bundle ORDER BY Id",
                            **self._params(),
                            **rpc_options(),
                        )
                    ]

                scenarios = rows("ImpactScenario")
                if len(scenarios) != 1:
                    raise DomainError(
                        "CLOUD_DATA_MISSING",
                        "The configured Spanner scenario is absent. "
                        "Import an explicitly approved bundle first.",
                        503,
                    )
                payload = {field: rows(table) for field, table in NODE_TABLES.items()}
                payload["catalog"] = [
                    item for table in CATALOG_TABLES.values() for item in rows(table)
                ]
                payload["edges"] = [item for table in EDGE_TABLES.values() for item in rows(table)]
                payload["scenario"] = scenarios[0]
                bundle = SeedBundle.model_validate(payload)
                if bundle.scenario.id != self.scenario_id:
                    raise ValueError("Stored scenario ID does not match the selected bundle")
                return bundle
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "SPANNER_READ_FAILED",
                "Unable to read a valid scenario from Spanner. Check schema, data and access.",
                503,
            ) from exc

    @bounded_operation
    def approved_outgoing(self, node_id: str) -> tuple[BaselineEdge, ...]:
        types = sql_types()
        params = {"bundle": self.scenario_id, "node": node_id}
        try:
            edges: list[BaselineEdge] = []
            with self.database.snapshot(multi_use=True) as snapshot:
                for table in EDGE_TABLES.values():
                    rows = snapshot.execute_sql(
                        f"SELECT Payload FROM {table} WHERE BundleId = @bundle "
                        "AND SourceId = @node AND Status = 'APPROVED' ORDER BY Id",
                        params=params,
                        param_types={"bundle": types.STRING, "node": types.STRING},
                        **rpc_options(),
                    )
                    for row in rows:
                        edge = BaselineEdge.model_validate(json_value(row[0]))
                        if edge.status != "APPROVED" or edge.source_id != node_id:
                            raise ValueError(
                                "Indexed edge metadata disagrees with its immutable payload"
                            )
                        edges.append(edge)
            return tuple(sorted(edges, key=lambda edge: edge.id))
        except Exception as exc:
            raise DomainError(
                "SPANNER_GRAPH_FAILED", "Unable to read approved relationships from Spanner.", 503
            ) from exc

    @bounded_operation
    def approved_control_paths(self, mandate_id: str) -> tuple[ApprovedControlPath, ...]:
        """GQL impact paths exclude risk edges and proposed/rejected relationships."""
        query = """
            GRAPH RegImpactGraph
            MATCH (m:Mandate)-[mp:ADDRESSED_BY]->(p:PolicyRequirement)
                  -[pc:IMPLEMENTED_BY]->(c:ControlObjective)
            WHERE m.BundleId = @bundle AND m.Id = @mandate
              AND m.Status = 'BASELINE_APPROVED'
              AND mp.Status = 'APPROVED' AND pc.Status = 'APPROVED'
              AND p.Status = 'ACTIVE' AND c.Status = 'ACTIVE'
            RETURN DISTINCT m.Id AS mandate_id, p.Id AS policy_id, c.Id AS control_id,
                            mp.Id AS mandate_policy_edge_id, pc.Id AS policy_control_edge_id
            ORDER BY mandate_id, policy_id, control_id,
                     mandate_policy_edge_id, policy_control_edge_id
        """
        types = sql_types()
        try:
            with self.database.snapshot() as snapshot:
                return tuple(
                    ApprovedControlPath(*row)
                    for row in snapshot.execute_sql(
                        query,
                        params={"bundle": self.scenario_id, "mandate": mandate_id},
                        param_types={"bundle": types.STRING, "mandate": types.STRING},
                        **rpc_options(),
                    )
                )
        except Exception as exc:
            raise DomainError(
                "SPANNER_GRAPH_FAILED", "Approved Spanner Graph traversal is unavailable.", 503
            ) from exc

    @bounded_operation
    def import_bundle(self, bundle: SeedBundle) -> None:
        """Explicit insert-only admin operation. Never called by startup or review APIs."""
        if bundle.scenario.id != self.scenario_id:
            raise ValueError("Bundle scenario ID must match the configured scenario")

        def insert(transaction: Any) -> None:
            def node(table: str, value: Any) -> None:
                payload = value.model_dump(mode="json")
                transaction.insert(
                    table,
                    ("BundleId", "Id", "Status", "Payload"),
                    [
                        (
                            self.scenario_id,
                            value.id,
                            payload.get("status", "ACTIVE"),
                            spanner_json(payload),
                        )
                    ],
                )

            for field, table in NODE_TABLES.items():
                for value in getattr(bundle, field):
                    node(table, value)
            for value in bundle.catalog:
                if value.type not in CATALOG_TABLES:
                    raise ValueError("Catalog contains a non-catalog node type")
                node(CATALOG_TABLES[value.type], value)
            node("ImpactScenario", bundle.scenario)
            for edge in bundle.edges:
                transaction.insert(
                    EDGE_TABLES[edge.relationship],
                    ("BundleId", "Id", "SourceId", "TargetId", "Status", "Payload"),
                    [
                        (
                            self.scenario_id,
                            edge.id,
                            edge.source_id,
                            edge.target_id,
                            edge.status,
                            spanner_json(edge.model_dump(mode="json")),
                        )
                    ],
                )

        try:
            self.database.run_in_transaction(insert, timeout_secs=TRANSACTION_RETRY_SECONDS)
        except Exception as exc:
            raise DomainError(
                "SPANNER_IMPORT_FAILED",
                "Immutable bundle import failed. Existing baseline rows are never overwritten.",
                503,
            ) from exc
