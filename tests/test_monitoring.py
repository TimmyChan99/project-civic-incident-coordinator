import uuid

from app import monitoring


def test_correlation_id_is_valid_and_unique():
    first = monitoring.new_correlation_id()
    second = monitoring.new_correlation_id()
    assert uuid.UUID(first)
    assert first != second


def test_memory_run_lifecycle():
    backend = monitoring.MemoryBackend()
    backend.start_run("corr-1", "broken streetlight")
    backend.append_event("corr-1", {"node": "supervisor", "status": "ok"})
    backend.finish_run("corr-1", "completed", {"priority": "STANDARD"})
    run = backend.get_run("corr-1")
    assert run["status"] == "completed"
    assert run["events"][0]["node"] == "supervisor"
    assert run["summary"]["priority"] == "STANDARD"


def test_unknown_run_is_none():
    assert monitoring.get_run("missing") is None


def test_metrics_aggregate_latency_errors_and_tokens():
    monitoring.start_run("corr-2", "water leak")
    monitoring.log_event(
        "corr-2",
        "impact",
        "ok",
        100,
        tokens={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    monitoring.log_event("corr-2", "impact", "error", 50, detail="quota")
    monitoring.finish_run("corr-2", "failed", {})
    stats = monitoring.get_metrics()["per_node"]["impact"]
    assert stats["calls"] == 2
    assert stats["errors"] == 1
    assert stats["duration_ms_avg"] == 75
    assert stats["total_tokens"] == 15


def test_sqlite_backend_persists_a_run(tmp_path):
    path = tmp_path / "monitoring.db"
    first = monitoring.SQLiteBackend(str(path))
    first.start_run("corr-db", "pothole")
    first.append_event("corr-db", {"node": "classification", "status": "ok"})
    first.finish_run("corr-db", "completed", {"priority": "STANDARD"})
    second = monitoring.SQLiteBackend(str(path))
    assert second.get_run("corr-db")["events"][0]["node"] == "classification"


def test_list_runs_returns_summary_shape():
    monitoring.start_run("corr-list", "signal outage")
    row = monitoring.list_runs()[0]
    assert row == {
        "correlation_id": "corr-list",
        "status": "running",
        "started_at": row["started_at"],
        "event_count": 0,
    }
