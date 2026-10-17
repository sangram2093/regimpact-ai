import asyncio
import copy
import re
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import SimpleNamespace

import pytest

from app.adapters.gcp import repository as repository_module
from app.adapters.gcp import search as search_module
from app.adapters.gcp import sessions as sessions_module
from app.adapters.gcp.repository import SpannerRegulatoryRepository
from app.adapters.gcp.search import SearchEntity, SpannerSearchRepository
from app.adapters.gcp.sessions import QUOTA_SESSION_ID, SpannerSessionBackend
from app.domain.errors import DomainError
from app.domain.graph import approved_control_paths
from app.services.impact import ImpactService


@pytest.fixture(autouse=True)
def no_sdk_required(monkeypatch):
    """Fakes check adapter contracts; they make no claim of Spanner execution."""
    types = SimpleNamespace(
        STRING="STRING",
        INT64="INT64",
        FLOAT32="FLOAT32",
        TIMESTAMP="TIMESTAMP",
        Array=lambda item: ("ARRAY", item),
    )
    for module in (repository_module, search_module, sessions_module):
        monkeypatch.setattr(module, "sql_types", lambda: types)
        if hasattr(module, "spanner_json"):
            monkeypatch.setattr(module, "spanner_json", copy.deepcopy)


class Database:
    def __init__(self):
        self.tables = {}
        self.calls = []
        self.lock = RLock()

    def snapshot(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run_in_transaction(self, operation, **kwargs):
        assert kwargs == {"timeout_secs": 20.0}
        with self.lock:
            before = copy.deepcopy(self.tables)
            try:
                return operation(self)
            except Exception:
                self.tables = before
                raise

    def insert(self, table, columns, values):
        for values_row in values:
            row = dict(zip(columns, values_row, strict=True))
            key = (row["BundleId"], row["Id"])
            target = self.tables.setdefault(table, {})
            if key in target:
                raise ValueError("Already exists")
            target[key] = row

    def insert_or_update(self, table, columns, values):
        for values_row in values:
            row = dict(zip(columns, values_row, strict=True))
            key = (
                row["SessionId"] if table == "DemoSessions" else (row["BundleId"], row["EntityId"])
            )
            self.tables.setdefault(table, {})[key] = row

    def execute_update(self, sql, params=None, **kwargs):
        self.calls.append((sql, params))
        states = self.tables.setdefault("DemoSessions", {})
        if "cutoff" in params:
            for key, row in list(states.items()):
                if row["TouchedAt"] <= params["cutoff"] and key != params["quota"]:
                    del states[key]
        else:
            states.pop(params["session"], None)

    def execute_sql(self, sql, params=None, **kwargs):
        self.calls.append((sql, params))
        if "FROM DemoSessions" in sql:
            states = self.tables.setdefault("DemoSessions", {})
            if "COUNT(*)" in sql:
                return [(len(states),)]
            row = states.get(params["session"])
            if row is None or (
                "cutoff" in params
                and row["TouchedAt"] <= params["cutoff"]
                and params["session"] != params["quota"]
            ):
                return []
            return [(copy.deepcopy(row["StateJson"]),)]
        if "GRAPH RegImpactGraph" in sql:
            return []
        table = re.search(r"FROM (\w+)", sql).group(1)
        rows = self.tables.get(table, {}).values()
        return [
            (copy.deepcopy(row["Payload"]),)
            for row in rows
            if row["BundleId"] == params["bundle"]
            and (
                "node" not in params
                or (row["SourceId"] == params["node"] and row["Status"] == "APPROVED")
            )
        ]


def test_relational_round_trip_is_scoped_immutable_and_has_approved_edge_boundary(bundle):
    database = Database()
    repository = SpannerRegulatoryRepository(database, bundle.scenario.id)
    repository.import_bundle(bundle)
    loaded = repository.snapshot()
    assert loaded.scenario == bundle.scenario
    assert {row.id for row in loaded.edges} == {row.id for row in bundle.edges}
    before = copy.deepcopy(database.tables)
    with pytest.raises(DomainError) as caught:
        repository.import_bundle(bundle)
    assert caught.value.code == "SPANNER_IMPORT_FAILED"
    assert database.tables == before
    expected = {
        edge.id for edge in bundle.edges if edge.source_id == "M-GIFT" and edge.status == "APPROVED"
    }
    assert {edge.id for edge in repository.approved_outgoing("M-GIFT")} == expected
    with pytest.raises(DomainError) as caught:
        SpannerRegulatoryRepository(database, "other-scenario").snapshot()
    assert caught.value.code == "CLOUD_DATA_MISSING"
    assert database.tables == before


def test_gql_only_traverses_approved_mandate_policy_control_path():
    database = Database()
    SpannerRegulatoryRepository(database, "scenario").approved_control_paths("mandate")
    sql, parameters = database.calls[-1]
    assert ":ADDRESSED_BY" in sql and ":IMPLEMENTED_BY" in sql
    assert "mp.Status = 'APPROVED'" in sql and "pc.Status = 'APPROVED'" in sql
    assert "CLASSIFIED_AS" not in sql and "DRIVEN_BY" not in sql
    assert "RETURN DISTINCT" in sql and "BASELINE_APPROVED" in sql
    assert parameters == {"bundle": "scenario", "mandate": "mandate"}


def test_impact_service_executes_gql_and_retains_distinct_controls(bundle):
    class GraphDatabase(Database):
        def execute_sql(self, sql, params=None, **kwargs):
            if "GRAPH RegImpactGraph" in sql:
                self.calls.append((sql, params))
                return [
                    (
                        path.mandate_id,
                        path.policy_id,
                        path.control_id,
                        path.mandate_policy_edge_id,
                        path.policy_control_edge_id,
                    )
                    for path in approved_control_paths(bundle, params["mandate"])
                ]
            return super().execute_sql(sql, params, **kwargs)

    database = GraphDatabase()
    repository = SpannerRegulatoryRepository(database, bundle.scenario.id)
    repository.import_bundle(bundle)
    service = ImpactService(repository.snapshot(), repository)
    impact = service.change_impact("CHANGE-GIFT")
    assert impact.coverage == "COMPLETE"
    assert {control.id for control in impact.controls} == {"CO-GIFT-01", "CO-GIFT-02"}
    gql_calls = [(sql, params) for sql, params in database.calls if "GRAPH RegImpactGraph" in sql]
    assert len(gql_calls) == 1
    assert gql_calls[0][1] == {"bundle": bundle.scenario.id, "mandate": "M-GIFT"}
    assert "mp.Status = 'APPROVED'" in gql_calls[0][0]
    assert "pc.Status = 'APPROVED'" in gql_calls[0][0]
    assert "p.Status = 'ACTIVE'" in gql_calls[0][0] and "c.Status = 'ACTIVE'" in gql_calls[0][0]


def test_spanner_sessions_isolation_expiry_capacity_reset_and_atomic_rollback():
    database = Database()
    now = [datetime(2026, 10, 17, tzinfo=UTC)]
    backend = SpannerSessionBackend(database, 60, 2, clock=lambda: now[0])
    assert backend.load("a") == {}
    backend.atomic("a", lambda state: state.update(review="approved"))
    backend.atomic("b", lambda state: state.update(review="rejected"))
    assert backend.load("a") == {"review": "approved"}
    assert backend.load("b") == {"review": "rejected"}
    with pytest.raises(DomainError) as caught:
        backend.atomic("c", lambda state: state.update(review="new"))
    assert caught.value.code == "DEMO_CAPACITY_REACHED"

    def failing(state):
        state["review"] = "should rollback"
        raise DomainError("CONFLICT", "test", 409)

    with pytest.raises(DomainError):
        backend.atomic("a", failing)
    assert backend.load("a") == {"review": "approved"}
    detached = backend.load("a")
    detached["review"] = "external mutation"
    assert backend.load("a")["review"] == "approved"
    backend.reset("a")
    assert backend.load("a") == {}
    assert backend.load("b")["review"] == "rejected"
    now[0] += timedelta(seconds=61)
    assert backend.load("b") == {}
    backend.atomic("c", lambda state: state.update(review="fresh"))
    assert set(database.tables["DemoSessions"]) == {"c"}


def test_quota_state_survives_demo_ttl_cleanup():
    database = Database()
    now = [datetime(2026, 10, 17, tzinfo=UTC)]
    backend = SpannerSessionBackend(database, 60, 5, clock=lambda: now[0])
    backend.atomic(QUOTA_SESSION_ID, lambda state: state.update(calls_today=5))
    backend.atomic("ordinary", lambda state: state.update(review=1))
    now[0] += timedelta(hours=5)
    assert backend.load(QUOTA_SESSION_ID) == {"calls_today": 5}
    backend.atomic("new", lambda state: state.update(review=2))
    assert set(database.tables["DemoSessions"]) == {QUOTA_SESSION_ID, "new"}
    deletes = [
        (sql, params)
        for sql, params in database.calls
        if sql.startswith("DELETE") and "cutoff" in params
    ]
    assert all(
        "SessionId != @quota" in sql and params["quota"] == QUOTA_SESSION_ID
        for sql, params in deletes
    )


def test_oversized_session_uses_wire_size_and_rolls_back_atomically(monkeypatch):
    assert sessions_module.MAX_SESSION_JSON_BYTES == 8 * 1024 * 1024
    monkeypatch.setattr(sessions_module, "MAX_SESSION_JSON_BYTES", 256)
    database = Database()
    now = [datetime(2026, 10, 17, tzinfo=UTC)]
    backend = SpannerSessionBackend(database, 60, 5, clock=lambda: now[0])
    backend.atomic("expired", lambda state: state.update(review="old session"))
    now[0] += timedelta(seconds=30)
    backend.atomic("active", lambda state: state.update(review="approved"))
    now[0] += timedelta(seconds=31)
    before = copy.deepcopy(database.tables)

    # Thirty emoji are 120 UTF-8 bytes but 360 bytes in the SDK's ASCII-escaped
    # JSON representation. The attempted mutation must preserve the prior audit.
    with pytest.raises(DomainError) as caught:
        backend.atomic("active", lambda state: state.update(output="\U0001f600" * 30))
    assert caught.value.code == "DEMO_SESSION_SIZE_LIMIT"
    assert caught.value.status_code == 409
    assert database.tables == before
    assert backend.load("active") == {"review": "approved"}

    # Rejecting an oversized first write must not create an empty session either.
    with pytest.raises(DomainError, match="storage limit"):
        backend.atomic("new", lambda state: state.update(output="x" * 256))
    assert database.tables == before


def test_session_failure_never_uses_an_in_memory_fallback():
    database = SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    with pytest.raises(DomainError) as caught:
        SpannerSessionBackend(database, 60, 5).load("a")
    assert caught.value.code == "SPANNER_SESSION_FAILED"


def test_search_uses_bound_vectors_kind_scope_and_stable_rank_fusion():
    class SearchDatabase(Database):
        def execute_sql(self, sql, params=None, **kwargs):
            self.calls.append((sql, params))
            if "COSINE_DISTANCE" in sql:
                return [("p2",), ("p1",)]
            return [("p1",), ("p3",)]

    database = SearchDatabase()
    repository = SpannerSearchRepository(database, "scenario")
    result = asyncio.run(repository.hybrid_search((1.0,) + (0.0,) * 767, "Gift AND consent: -bad"))
    assert result[0].id == "p1"
    assert result[0].vector_rank == 2 and result[0].lexical_rank == 1
    assert result[0].score == pytest.approx(1 / 62 + 1 / 61)
    vector = next(call for call in database.calls if "COSINE_DISTANCE" in call[0])
    assert vector[1]["model"] == "gemini-embedding-001"
    assert vector[1]["bundle"] == "scenario" and vector[1]["kinds"] == ["POLICY_REQUIREMENT"]
    assert "EntityId" in vector[0] and "Status = 'ACTIVE'" in vector[0]
    lexical = next(call for call in database.calls if "SEARCH(" in call[0])
    assert lexical[1]["query"] == "gift OR consent OR bad"


@pytest.mark.parametrize("embedding", [(1.0,), (0.0,) * 768, (float("nan"),) + (1.0,) * 767])
def test_vector_dimension_or_nonfinite_data_rejected_before_query(embedding):
    database = Database()
    with pytest.raises(DomainError):
        asyncio.run(SpannerSearchRepository(database, "scenario").vector_search(embedding))
    assert not database.calls


def test_index_build_never_touches_baseline_or_silently_generates_vectors():
    database = Database()
    repository = SpannerSearchRepository(database, "scenario")
    repository.index_entities((SearchEntity("p1", "POLICY_REQUIREMENT", "Gift policy"),))
    assert set(database.tables) == {"SearchEntity"}
    stored = database.tables["SearchEntity"][("scenario", "p1")]
    assert stored["Embedding"] is None and stored["EmbeddingModel"] is None


def test_lexical_query_escapes_operators_and_is_bounded():
    query = SpannerSearchRepository.lexical_query('"gifts" OR (benefits) -control a AND the')
    assert query == "gifts OR benefits OR control"
    assert (
        len(
            SpannerSearchRepository.lexical_query(" ".join(f"word{i}" for i in range(1000))).split(
                " OR "
            )
        )
        == 16
    )
