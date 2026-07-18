"""FastAPI surface for the incident workflow, UI, and observability."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import __version__, monitoring
from app.config import GEMINI_MODEL
from app.graph import review_incident, start_incident
from app.web import render_dashboard, render_ui

app = FastAPI(
    title="Civic Incident Coordinator API",
    version=__version__,
    description="Human-reviewed multi-agent coordination for civic infrastructure reports.",
)


class IncidentRequest(BaseModel):
    report: str = Field(min_length=1, max_length=5000)
    thread_id: str | None = Field(default=None, max_length=120)


class ReviewRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui")


@app.get("/ui", response_class=HTMLResponse)
def ui():
    return render_ui()


@app.get("/health")
def health():
    # A liveness probe must not consume model quota or require the model endpoint.
    return {"status": "ok", "version": __version__, "model": GEMINI_MODEL}


@app.post("/incidents")
def create_incident(payload: IncidentRequest):
    if not payload.report.strip():
        raise HTTPException(400, "report must not be blank")
    thread_id = payload.thread_id or str(uuid.uuid4())
    try:
        return start_incident(payload.report.strip(), thread_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/incidents/{thread_id}/review")
def review(thread_id: str, payload: ReviewRequest):
    try:
        return review_incident(thread_id, payload.approved, payload.comment)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/runs")
def runs():
    return monitoring.list_runs()


@app.get("/runs/{correlation_id}")
def run_detail(correlation_id: str):
    run = monitoring.get_run(correlation_id)
    if run is None:
        raise HTTPException(404, "correlation ID not found")
    return run


@app.get("/metrics")
def metrics():
    return monitoring.get_metrics()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return render_dashboard(monitoring.get_metrics(), monitoring.list_runs())
