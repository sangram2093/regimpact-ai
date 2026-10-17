from types import SimpleNamespace

import pytest

from app.adapters.gcp import timeouts


def recording_api():
    calls = []

    class Api:
        def __getattr__(self, name):
            def operation(*args, **kwargs):
                calls.append((name, kwargs))
                return "result"

            return operation

    return Api(), calls


def test_rpc_wrapping_bounds_commit_creation_and_streams_without_global_changes():
    api, calls = recording_api()
    other, untouched = recording_api()
    timeouts.configure_rpc_deadlines(api)
    original_wrapped_commit = api.commit
    timeouts.configure_rpc_deadlines(api)
    assert api.commit is original_wrapped_commit
    for name in ("commit", "create_session", "rollback", "execute_streaming_sql"):
        assert getattr(api, name)(request={}, timeout=3600, retry=object()) == "result"
    assert all(options["timeout"] == 10 and options["retry"] is None for _, options in calls)
    api.commit(request={}, timeout=2)
    assert calls[-1][1]["timeout"] == 2
    other.commit(request={})
    assert "timeout" not in untouched[0][1]


def test_operation_budget_shrinks_across_nested_calls_and_restores_context(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(timeouts, "monotonic", lambda: now[0])
    api, calls = recording_api()
    timeouts.configure_rpc_deadlines(api)

    @timeouts.bounded_operation
    def nested():
        api.execute_streaming_sql(request={})

    @timeouts.bounded_operation
    def operation():
        api.create_session(request={})
        now[0] += 30
        nested()
        now[0] += 6
        api.commit(request={})

    with pytest.raises(TimeoutError, match="deadline"):
        operation()
    assert [options["timeout"] for _, options in calls] == [10, 5]
    # No commit RPC was issued after expiry and this thread is reusable afterward.
    assert timeouts.rpc_options()["timeout"] == 10


def test_api_wrapper_preserves_aborted_exception_for_transaction_runner():
    api, _ = recording_api()
    failure = RuntimeError("synthetic aborted callback")

    def aborted(**kwargs):
        raise failure

    api.commit = aborted
    timeouts.configure_rpc_deadlines(api)
    with pytest.raises(RuntimeError) as caught:
        api.commit(request={})
    assert caught.value is failure


def test_database_factory_installs_limits_without_rpc_or_auth(monkeypatch):
    spanner = pytest.importorskip("google.cloud.spanner")
    from app.adapters.gcp.common import make_database

    api, calls = recording_api()
    database = SimpleNamespace(spanner_api=api)

    def client(*, project, disable_builtin_metrics):
        assert project == "synthetic-project"
        assert disable_builtin_metrics is True
        return SimpleNamespace(
            instance=lambda instance: SimpleNamespace(database=lambda name: database)
        )

    monkeypatch.setattr(spanner, "Client", client)
    assert make_database("synthetic-project", "synthetic-instance", "synthetic-db") is database
    assert calls == []
    api.commit(request={})
    assert calls[0][1]["timeout"] == 10


def test_pinned_sdk_exposes_all_wrapped_methods_without_connecting():
    spanner = pytest.importorskip("google.cloud.spanner_v1.services.spanner")
    from google.auth.credentials import AnonymousCredentials

    client = spanner.SpannerClient(credentials=AnonymousCredentials())
    try:
        timeouts.configure_rpc_deadlines(client)
        assert client.commit._regimpact_bounded
        assert client.execute_streaming_sql._regimpact_bounded
    finally:
        client.transport.close()


def test_pinned_sdk_metrics_opt_out_skips_exporter_initialization(monkeypatch):
    client_module = pytest.importorskip("google.cloud.spanner_v1.client")
    from google.auth.credentials import AnonymousCredentials

    initialized = []
    monkeypatch.setattr(
        client_module, "_initialize_metrics", lambda *args: initialized.append(args)
    )
    monkeypatch.setattr(client_module, "_get_spanner_enable_builtin_metrics_env", lambda: True)
    monkeypatch.setattr(client_module, "HAS_GOOGLE_CLOUD_MONITORING_INSTALLED", True)
    client_module.Client(
        project="synthetic-project",
        credentials=AnonymousCredentials(),
        disable_builtin_metrics=True,
        client_options={"api_endpoint": "localhost:9010"},
    )
    assert initialized == []
