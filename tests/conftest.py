"""Shared test isolation for the monitoring store and graph singletons."""

import pytest

from app import graph, monitoring


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(monitoring, "backend", monitoring.MemoryBackend())
    monkeypatch.setattr(graph, "_graph", None)
    monkeypatch.setattr(graph, "_llm", None)
