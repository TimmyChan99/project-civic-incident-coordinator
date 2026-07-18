import json

from app import graph, monitoring


class FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def state(**overrides):
    value = graph.initial_state("A traffic light is dark at Main and First.", "corr-test")
    value.update(overrides)
    return value


def fake_invoke(system_prompt: str, _user_content: str):
    if "supervise" in system_prompt:
        return FakeResponse(
            json.dumps(
                {
                    "activate_classification": True,
                    "activate_impact": True,
                    "activate_dispatch": True,
                    "reason": "Traffic-control asset requires coordinated assessment.",
                }
            )
        )
    if "Classify" in system_prompt:
        return FakeResponse('{"category":"traffic signal"}')
    if "community impact" in system_prompt:
        return FakeResponse('{"impact_level":"high"}')
    if "operational dispatch" in system_prompt:
        return FakeResponse('{"recommended_team":"signals"}')
    if "work order" in system_prompt.lower() and "audit" not in system_prompt.lower():
        return FakeResponse("Incident Summary\nTraffic signal outage")
    if "Audit" in system_prompt:
        return FakeResponse("Immediate traffic hazard.\nPRIORITY: EMERGENCY")
    if "Extract" in system_prompt:
        return FakeResponse("EMERGENCY")
    raise AssertionError(f"Unexpected prompt: {system_prompt}")


def test_extract_json_accepts_surrounding_text():
    assert graph.extract_json('result: {"category":"road"} done') == {"category": "road"}


def test_extract_json_rejects_invalid_content():
    assert graph.extract_json("not json") == {}


def test_extract_tokens_supports_gemini_usage():
    assert graph.extract_tokens(FakeResponse("ok"))["total_tokens"] == 15


def test_supervisor_reads_agent_switches(monkeypatch):
    monkeypatch.setattr(graph, "invoke", fake_invoke)
    result = graph.supervisor_node(state())
    assert result["activate_dispatch"] is True
    assert "coordinated" in result["supervisor_reason"]


def test_specialist_can_be_skipped_without_llm(monkeypatch):
    monkeypatch.setattr(graph, "invoke", lambda *_: (_ for _ in ()).throw(AssertionError()))
    result = graph.classification_node(state(activate_classification=False))
    assert json.loads(result["classification_result"])["status"] == "not_requested"


def test_combine_contains_all_specialist_outputs():
    result = graph.combine_node(
        state(classification_result="class", impact_result="impact", dispatch_result="dispatch")
    )
    assert all(word in result["combined_analysis"] for word in ("class", "impact", "dispatch"))


def test_priority_extractor_is_fail_safe_standard(monkeypatch):
    monkeypatch.setattr(graph, "invoke", lambda *_: FakeResponse("unknown"))
    result = graph.priority_extractor_node(state(audit_result="ambiguous"))
    assert result["priority"] == "STANDARD"


def test_priority_routes():
    assert graph.route_priority(state(priority="EMERGENCY")) == "emergency_route"
    assert graph.route_priority(state(priority="STANDARD")) == "standard_route"


def test_route_nodes_set_distinct_decisions():
    assert "EMERGENCY" in graph.emergency_route_node(state())["routing_decision"]
    assert "STANDARD" in graph.standard_route_node(state())["routing_decision"]


def test_monitored_decorator_records_error(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        monitoring,
        "log_event",
        lambda *args, **kwargs: captured.update(status=args[2], detail=kwargs.get("detail", "")),
    )

    @graph.monitored("broken")
    def broken(_state):
        raise ValueError("bad node")

    try:
        broken(state())
    except ValueError:
        pass
    assert captured == {"status": "error", "detail": "bad node"}


def test_full_graph_pauses_then_completes(monkeypatch):
    monkeypatch.setattr(graph, "invoke", fake_invoke)
    started = graph.start_incident("Traffic signal dark at Main and First", "thread-full")
    assert started["status"] == "awaiting_human_review"
    assert started["work_order"].startswith("Incident Summary")
    completed = graph.review_incident("thread-full", True, "approved")
    assert completed["status"] == "completed"
    assert completed["priority"] == "EMERGENCY"
    run = monitoring.get_run(completed["correlation_id"])
    assert run["status"] == "completed"
    assert len({event["correlation_id"] for event in run["events"]}) == 1
    assert any(event["node"] == "monitoring_agent" for event in run["events"])


def test_rejected_review_stops_before_audit(monkeypatch):
    monkeypatch.setattr(graph, "invoke", fake_invoke)
    started = graph.start_incident("Broken bench in park", "thread-reject")
    result = graph.review_incident("thread-reject", False, "needs a photo")
    assert result["status"] == "rejected"
    assert monitoring.get_run(started["correlation_id"])["status"] == "rejected"
    try:
        graph.review_incident("thread-reject", True, "second decision")
    except KeyError:
        pass
    else:
        raise AssertionError("A rejected review must be final")


def test_duplicate_thread_id_is_rejected(monkeypatch):
    monkeypatch.setattr(graph, "invoke", fake_invoke)
    graph.start_incident("Broken bench", "duplicate-thread")
    try:
        graph.start_incident("Different report", "duplicate-thread")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected duplicate thread rejection")


def test_unknown_thread_is_rejected():
    try:
        graph.review_incident("not-found", True)
    except KeyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("Expected KeyError")
