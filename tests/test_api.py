from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_root_redirects_to_ui():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_health_is_quota_free_and_names_required_model():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model"] == "gemini-2.5-flash"


def test_ui_is_functional_html():
    response = client.get("/ui")
    assert response.status_code == 200
    assert "submitIncident" in response.text
    assert "/incidents" in response.text


def test_create_incident_endpoint():
    expected = {"thread_id": "t1", "status": "awaiting_human_review"}
    with patch("app.api.start_incident", return_value=expected):
        response = client.post("/incidents", json={"report": "pothole", "thread_id": "t1"})
    assert response.status_code == 200
    assert response.json() == expected


def test_blank_report_is_rejected():
    assert client.post("/incidents", json={"report": "   "}).status_code == 400


def test_missing_api_key_is_service_unavailable():
    error = RuntimeError("GEMINI_API_KEY is not configured")
    with patch("app.api.start_incident", side_effect=error):
        response = client.post("/incidents", json={"report": "pothole"})
    assert response.status_code == 503


def test_duplicate_thread_returns_conflict():
    with patch("app.api.start_incident", side_effect=ValueError("thread_id already exists")):
        response = client.post("/incidents", json={"report": "pothole", "thread_id": "used"})
    assert response.status_code == 409


def test_review_endpoint():
    expected = {"thread_id": "t1", "status": "completed"}
    with patch("app.api.review_incident", return_value=expected):
        response = client.post("/incidents/t1/review", json={"approved": True})
    assert response.json() == expected


def test_unknown_review_returns_404():
    with patch("app.api.review_incident", side_effect=KeyError("unknown")):
        response = client.post("/incidents/nope/review", json={"approved": True})
    assert response.status_code == 404


def test_observability_endpoints():
    assert client.get("/runs").status_code == 200
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "per_node" in metrics.json()
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Monitoring Agent Dashboard" in dashboard.text


def test_unknown_correlation_id_returns_404():
    assert client.get("/runs/no-such-run").status_code == 404
