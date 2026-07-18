# Assignment Validation Guide

This file provides reproducible evidence without requiring a demo video.

## Automated evidence

```bash
source .venv/bin/activate
ruff check .
ruff format --check .
pytest --cov=app --cov-report=term-missing
docker build -t civic-incident-coordinator:validation .
docker compose config
```

The tests mock Gemini and make no network calls. They cover node selection, parallel result handling, human approval/rejection, audit routing, monitoring persistence/aggregation, correlation propagation, UI/API endpoints, missing configuration, and error paths.

## Manual evidence checklist

| Criterion | Evidence |
|---|---|
| Supervisor architecture | `app/graph.py`, `docs/ARCHITECTURE.md`, BPMN |
| Monitoring agent | `monitoring_agent_node`, `/dashboard` |
| Correlation ID | Submit a run and open `/runs/{correlation_id}` |
| Successful tests | CI `quality` job / local pytest output |
| Complete Agent Card | `AGENT_CARD.md` |
| API deployed | Railway `/health`, `/docs`, and `/ui` |
| Incident runbook | `docs/RUNBOOK.md` |
| Container | CI `docker-build` job and local health check |

## Acceptance scenarios

1. Emergency: dark traffic signal at a busy intersection with near collisions.
2. Standard: one non-hazardous park bench has a broken slat, area can be cordoned.
3. Rejection: operator rejects a work order that lacks a usable location.
4. Provider failure: missing API key returns HTTP 503 and the run is traceable as failed.
5. Ambiguous priority: extractor output defaults to `STANDARD`.

Because the required provider model is retired, use mocked tests as the executable assignment evidence until a model migration is authorized.
