"""LangGraph supervisor workflow for civic infrastructure reports."""

from __future__ import annotations

import json
import time
from functools import wraps
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app import monitoring
from app.config import GEMINI_MODEL, settings


def keep_last(_old: Any, new: Any) -> Any:
    """Reducer required for fields updated by parallel graph branches."""
    return new


class IncidentState(TypedDict):
    correlation_id: str
    report: str
    activate_classification: bool
    activate_impact: bool
    activate_dispatch: bool
    supervisor_reason: str
    classification_result: Annotated[str, keep_last]
    impact_result: Annotated[str, keep_last]
    dispatch_result: Annotated[str, keep_last]
    combined_analysis: str
    work_order: str
    review_status: str
    human_approved: bool
    human_comment: str
    audit_result: str
    priority: str
    routing_decision: str
    monitoring_report: str


SUPERVISOR_PROMPT = """You supervise a civic infrastructure incident team.
Available specialists: Classification, Community Impact, and Dispatch Planning.
Select only agents relevant to the resident report. Return JSON only:
{"activate_classification": true, "activate_impact": true,
 "activate_dispatch": true, "reason": "brief reason"}"""

CLASSIFICATION_PROMPT = """Classify a civic infrastructure report. Return JSON only
with category, asset, location_clues, hazards, and missing_information. Do not invent facts."""

IMPACT_PROMPT = """Assess community impact from a civic infrastructure report.
Return JSON only with people_affected, service_disruption, safety_concerns,
impact_level (low|medium|high), and rationale. Do not invent facts."""

DISPATCH_PROMPT = """Propose an operational dispatch for a civic infrastructure report.
Return JSON only with recommended_team, equipment, immediate_actions,
dependencies, and target_response_window. Do not claim a dispatch occurred."""

WORK_ORDER_PROMPT = """Create a concise municipal incident work order from the three
analyses. Use headings: Incident Summary, Observed Hazards, Community Impact,
Recommended Dispatch, Missing Information, Operator Checklist. Clearly label
uncertainty and never claim that emergency services have already been contacted."""

AUDIT_PROMPT = """Audit this proposed civic work order for consistency, unsupported
claims, and under-prioritization. Consider immediate danger, essential-service
outage, traffic obstruction, and vulnerable people. End with exactly one line:
PRIORITY: EMERGENCY or PRIORITY: STANDARD.

WORK ORDER:
{work_order}"""

PRIORITY_PROMPT = """Extract the final priority from this audit. Return exactly one
word, either EMERGENCY or STANDARD, and nothing else.

AUDIT:
{audit}"""

EMERGENCY_DECISION = (
    "EMERGENCY DISPATCH: escalate to the municipal duty officer immediately; "
    "the operator must contact emergency services when life safety is threatened."
)
STANDARD_DECISION = (
    "STANDARD QUEUE: create a normal-priority maintenance ticket and notify the resident."
)

_llm = None
_graph = None


def get_llm():
    """Lazily create the Gemini client so health checks work without a secret."""
    global _llm
    if _llm is None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        from langchain_google_genai import ChatGoogleGenerativeAI

        _llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=settings.gemini_api_key,
            temperature=0.1,
        )
    return _llm


def invoke(system_prompt: str, user_content: str):
    return get_llm().invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    )


def extract_json(text: str) -> dict:
    """Decode the first JSON object, tolerating surrounding model prose."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def extract_tokens(response: Any) -> dict:
    usage = getattr(response, "usage_metadata", None) or {}
    if not usage:
        usage = (getattr(response, "response_metadata", None) or {}).get("usage_metadata", {})
    return (
        {
            "input_tokens": usage.get("input_tokens", usage.get("prompt_token_count", 0)),
            "output_tokens": usage.get("output_tokens", usage.get("candidates_token_count", 0)),
            "total_tokens": usage.get("total_tokens", usage.get("total_token_count", 0)),
        }
        if usage
        else {}
    )


def monitored(node_name: str):
    """Record node latency, errors, and token counts under the run correlation ID."""

    def decorator(function):
        @wraps(function)
        def wrapper(state: IncidentState):
            started = time.perf_counter()
            correlation_id = state.get("correlation_id", "")
            try:
                result = function(state)
                tokens = result.pop("_tokens", {})
                monitoring.log_event(
                    correlation_id,
                    node_name,
                    "ok",
                    (time.perf_counter() - started) * 1000,
                    tokens=tokens,
                )
                return result
            except Exception as exc:
                monitoring.log_event(
                    correlation_id,
                    node_name,
                    "error",
                    (time.perf_counter() - started) * 1000,
                    detail=str(exc),
                )
                raise

        return wrapper

    return decorator


@monitored("supervisor")
def supervisor_node(state: IncidentState) -> dict:
    response = invoke(SUPERVISOR_PROMPT, state["report"])
    data = extract_json(response.content)
    return {
        "activate_classification": bool(data.get("activate_classification", True)),
        "activate_impact": bool(data.get("activate_impact", True)),
        "activate_dispatch": bool(data.get("activate_dispatch", True)),
        "supervisor_reason": str(data.get("reason", "All specialists selected.")),
        "_tokens": extract_tokens(response),
    }


def specialist_node(name: str, activation_key: str, result_key: str, prompt: str):
    @monitored(name)
    def run(state: IncidentState) -> dict:
        if not state.get(activation_key, True):
            return {result_key: json.dumps({"status": "not_requested"})}
        response = invoke(prompt, state["report"])
        return {result_key: response.content, "_tokens": extract_tokens(response)}

    return run


classification_node = specialist_node(
    "classification", "activate_classification", "classification_result", CLASSIFICATION_PROMPT
)
impact_node = specialist_node("community_impact", "activate_impact", "impact_result", IMPACT_PROMPT)
dispatch_node = specialist_node(
    "dispatch_planning", "activate_dispatch", "dispatch_result", DISPATCH_PROMPT
)


@monitored("combine")
def combine_node(state: IncidentState) -> dict:
    combined = (
        f"CLASSIFICATION\n{state.get('classification_result', '{}')}\n\n"
        f"COMMUNITY IMPACT\n{state.get('impact_result', '{}')}\n\n"
        f"DISPATCH PLAN\n{state.get('dispatch_result', '{}')}"
    )
    return {"combined_analysis": combined}


@monitored("work_order")
def work_order_node(state: IncidentState) -> dict:
    response = invoke(WORK_ORDER_PROMPT, state["combined_analysis"])
    return {"work_order": response.content, "_tokens": extract_tokens(response)}


@monitored("human_review")
def human_review_node(state: IncidentState) -> dict:
    return {"human_approved": True}


@monitored("audit")
def audit_node(state: IncidentState) -> dict:
    response = invoke(AUDIT_PROMPT.format(work_order=state["work_order"]), state["report"])
    return {"audit_result": response.content, "_tokens": extract_tokens(response)}


@monitored("priority_extractor")
def priority_extractor_node(state: IncidentState) -> dict:
    response = invoke(PRIORITY_PROMPT.format(audit=state["audit_result"]), "Extract priority")
    raw = response.content.strip().upper()
    priority = "EMERGENCY" if "EMERGENCY" in raw else "STANDARD"
    return {"priority": priority, "_tokens": extract_tokens(response)}


def route_priority(state: IncidentState) -> str:
    return "emergency_route" if state.get("priority") == "EMERGENCY" else "standard_route"


@monitored("emergency_route")
def emergency_route_node(_state: IncidentState) -> dict:
    return {"routing_decision": EMERGENCY_DECISION}


@monitored("standard_route")
def standard_route_node(_state: IncidentState) -> dict:
    return {"routing_decision": STANDARD_DECISION}


@monitored("monitoring_agent")
def monitoring_agent_node(state: IncidentState) -> dict:
    """Deterministic monitoring agent validates trace integrity before completion."""
    run = monitoring.get_run(state["correlation_id"])
    events = (run or {}).get("events", [])
    error_count = sum(event["status"] == "error" for event in events)
    mismatched_ids = sum(event.get("correlation_id") != state["correlation_id"] for event in events)
    report = (
        f"Trace healthy: {len(events)} prior nodes, 0 errors, correlation ID propagated."
        if error_count == 0 and mismatched_ids == 0
        else (
            f"Trace degraded: {error_count} node error(s), {mismatched_ids} mismatched ID(s); "
            "operator review required."
        )
    )
    return {"monitoring_report": report}


def build_graph():
    builder = StateGraph(IncidentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("classification", classification_node)
    builder.add_node("community_impact", impact_node)
    builder.add_node("dispatch_planning", dispatch_node)
    builder.add_node("combine", combine_node)
    builder.add_node("work_order", work_order_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("audit", audit_node)
    builder.add_node("priority_extractor", priority_extractor_node)
    builder.add_node("emergency_route", emergency_route_node)
    builder.add_node("standard_route", standard_route_node)
    builder.add_node("monitoring_agent", monitoring_agent_node)

    builder.add_edge(START, "supervisor")
    for specialist in ("classification", "community_impact", "dispatch_planning"):
        builder.add_edge("supervisor", specialist)
        builder.add_edge(specialist, "combine")
    builder.add_edge("combine", "work_order")
    builder.add_edge("work_order", "human_review")
    builder.add_edge("human_review", "audit")
    builder.add_edge("audit", "priority_extractor")
    builder.add_conditional_edges(
        "priority_extractor",
        route_priority,
        {"emergency_route": "emergency_route", "standard_route": "standard_route"},
    )
    builder.add_edge("emergency_route", "monitoring_agent")
    builder.add_edge("standard_route", "monitoring_agent")
    builder.add_edge("monitoring_agent", END)
    return builder.compile(checkpointer=MemorySaver(), interrupt_before=["human_review"])


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def initial_state(report: str, correlation_id: str) -> IncidentState:
    return {
        "correlation_id": correlation_id,
        "report": report,
        "activate_classification": True,
        "activate_impact": True,
        "activate_dispatch": True,
        "supervisor_reason": "",
        "classification_result": "",
        "impact_result": "",
        "dispatch_result": "",
        "combined_analysis": "",
        "work_order": "",
        "review_status": "pending",
        "human_approved": False,
        "human_comment": "",
        "audit_result": "",
        "priority": "",
        "routing_decision": "",
        "monitoring_report": "",
    }


def start_incident(report: str, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    if get_graph().get_state(config).values:
        raise ValueError(f"thread_id already exists: {thread_id}")
    correlation_id = monitoring.new_correlation_id()
    monitoring.start_run(correlation_id, report)
    try:
        for _ in get_graph().stream(initial_state(report, correlation_id), config):
            pass
        state = get_graph().get_state(config).values
        return {
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "status": "awaiting_human_review",
            "work_order": state.get("work_order", ""),
            "supervisor_reason": state.get("supervisor_reason", ""),
        }
    except Exception as exc:
        monitoring.finish_run(correlation_id, "failed", {"error": str(exc)[:300]})
        raise


def review_incident(thread_id: str, approved: bool, comment: str = "") -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if (
        not snapshot.values
        or snapshot.next != ("human_review",)
        or snapshot.values.get("review_status") != "pending"
    ):
        raise KeyError(f"unknown, expired, or already reviewed thread_id: {thread_id}")
    correlation_id = snapshot.values["correlation_id"]
    graph.update_state(
        config,
        {
            "review_status": "approved" if approved else "rejected",
            "human_approved": approved,
            "human_comment": comment,
        },
    )
    if not approved:
        monitoring.finish_run(correlation_id, "rejected", {"comment": comment})
        return {
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "status": "rejected",
        }
    try:
        for _ in graph.stream(None, config):
            pass
        state = graph.get_state(config).values
        summary = {
            "priority": state["priority"],
            "routing_decision": state["routing_decision"],
            "monitoring_report": state["monitoring_report"],
        }
        monitoring.finish_run(correlation_id, "completed", summary)
        return {
            "thread_id": thread_id,
            "correlation_id": correlation_id,
            "status": "completed",
            "work_order": state["work_order"],
            **summary,
        }
    except Exception as exc:
        monitoring.finish_run(correlation_id, "failed", {"error": str(exc)[:300]})
        raise
