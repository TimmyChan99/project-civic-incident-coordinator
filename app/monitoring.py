"""Correlation-ID monitoring with SQLite and in-memory backends.

SQLite is free, open source, and requires no external service. Every graph node
records its latency, token usage, and outcome against one run-level UUID.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.config import settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_correlation_id() -> str:
    return str(uuid.uuid4())


class Backend(Protocol):
    def start_run(self, correlation_id: str, user_input: str) -> None: ...
    def append_event(self, correlation_id: str, event: dict) -> None: ...
    def finish_run(self, correlation_id: str, status: str, summary: dict) -> None: ...
    def get_run(self, correlation_id: str) -> dict | None: ...
    def all_runs(self) -> list[dict]: ...


class MemoryBackend:
    """Thread-safe fallback used by tests and stateless deployments."""

    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}
        self._lock = threading.RLock()

    def start_run(self, correlation_id: str, user_input: str) -> None:
        with self._lock:
            self._runs[correlation_id] = {
                "correlation_id": correlation_id,
                "started_at": utc_now(),
                "user_input": user_input,
                "status": "running",
                "events": [],
                "summary": {},
            }

    def append_event(self, correlation_id: str, event: dict) -> None:
        with self._lock:
            if correlation_id in self._runs:
                self._runs[correlation_id]["events"].append(event)

    def finish_run(self, correlation_id: str, status: str, summary: dict) -> None:
        with self._lock:
            if correlation_id in self._runs:
                self._runs[correlation_id].update(
                    status=status, ended_at=utc_now(), summary=summary
                )

    def get_run(self, correlation_id: str) -> dict | None:
        with self._lock:
            run = self._runs.get(correlation_id)
            return json.loads(json.dumps(run)) if run else None

    def all_runs(self) -> list[dict]:
        with self._lock:
            return json.loads(json.dumps(list(self._runs.values())))


class SQLiteBackend:
    """Small persistent backend suitable for a one-instance MVP."""

    def __init__(self, database_path: str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    correlation_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    user_input TEXT NOT NULL,
                    status TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                )"""
            )

    def start_run(self, correlation_id: str, user_input: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO runs VALUES (?, ?, NULL, ?, 'running', '[]', '{}')",
                (correlation_id, utc_now(), user_input),
            )

    def append_event(self, correlation_id: str, event: dict) -> None:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT events_json FROM runs WHERE correlation_id = ?",
                (correlation_id,),
            ).fetchone()
            if row:
                events = json.loads(row["events_json"])
                events.append(event)
                self._connection.execute(
                    "UPDATE runs SET events_json = ? WHERE correlation_id = ?",
                    (json.dumps(events), correlation_id),
                )

    def finish_run(self, correlation_id: str, status: str, summary: dict) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE runs SET ended_at = ?, status = ?, summary_json = ?
                   WHERE correlation_id = ?""",
                (utc_now(), status, json.dumps(summary), correlation_id),
            )

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["events"] = json.loads(result.pop("events_json"))
        result["summary"] = json.loads(result.pop("summary_json"))
        return result

    def get_run(self, correlation_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE correlation_id = ?", (correlation_id,)
            ).fetchone()
        return self._deserialize(row) if row else None

    def all_runs(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [self._deserialize(row) for row in rows]


def build_backend(database_path: str) -> Backend:
    if database_path == ":memory:":
        return MemoryBackend()
    try:
        return SQLiteBackend(database_path)
    except (OSError, sqlite3.Error):
        return MemoryBackend()


backend: Backend = build_backend(settings.database_path)


def start_run(correlation_id: str, user_input: str) -> None:
    backend.start_run(correlation_id, user_input)


def log_event(
    correlation_id: str,
    node: str,
    status: str,
    duration_ms: float,
    *,
    detail: str = "",
    tokens: dict | None = None,
) -> None:
    backend.append_event(
        correlation_id,
        {
            "correlation_id": correlation_id,
            "node": node,
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "detail": detail[:300],
            "tokens": tokens or {},
            "timestamp": utc_now(),
        },
    )


def finish_run(correlation_id: str, status: str, summary: dict) -> None:
    backend.finish_run(correlation_id, status, summary)


def get_run(correlation_id: str) -> dict | None:
    return backend.get_run(correlation_id)


def list_runs() -> list[dict]:
    return [
        {
            "correlation_id": run["correlation_id"],
            "status": run["status"],
            "started_at": run["started_at"],
            "event_count": len(run["events"]),
        }
        for run in backend.all_runs()
    ]


def get_metrics() -> dict:
    runs = backend.all_runs()
    statuses = {"running": 0, "completed": 0, "rejected": 0, "failed": 0}
    per_node: dict[str, dict] = {}
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for run in runs:
        statuses[run["status"]] = statuses.get(run["status"], 0) + 1
        for event in run["events"]:
            stats = per_node.setdefault(
                event["node"],
                {
                    "calls": 0,
                    "errors": 0,
                    "duration_ms_total": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            )
            stats["calls"] += 1
            stats["errors"] += int(event["status"] == "error")
            stats["duration_ms_total"] += event["duration_ms"]
            for key in total_tokens:
                value = (event.get("tokens") or {}).get(key, 0)
                stats[key] += value
                total_tokens[key] += value

    for stats in per_node.values():
        stats["duration_ms_total"] = round(stats["duration_ms_total"], 2)
        stats["duration_ms_avg"] = round(stats["duration_ms_total"] / stats["calls"], 2)

    return {
        "run_count": len(runs),
        "status_counts": statuses,
        "total_tokens": total_tokens,
        "per_node": per_node,
    }
