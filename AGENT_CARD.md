# Agent Card — Civic Incident Coordinator

| Field | Value |
|---|---|
| Name | Civic Incident Coordinator |
| Version | 1.0.0 |
| Pattern | Supervisor with parallel specialists, HITL, audit, and router |
| Domain | Municipal infrastructure incident triage |
| Owner | Project maintainer (set repository CODEOWNERS before production) |
| Runtime | Python 3.12, LangGraph, FastAPI |
| Required model | Google Gemini `gemini-2.5-flash` |
| Data store | Local SQLite monitoring store; in-memory graph checkpoints |

## Purpose

Convert unstructured resident infrastructure reports into a structured work order for a human municipal operator. The system helps classify an asset, estimate community impact, suggest a dispatch team, audit the work order, and route an approved item to an emergency or standard queue.

## Agent roster

| Agent | Responsibility | Authority boundary |
|---|---|---|
| Supervisor | Select relevant specialists | Cannot dispatch or approve |
| Classification | Identify asset/category, hazards, and missing facts | Cannot invent location or confirm damage |
| Community Impact | Estimate safety and service impact | Advisory estimate only |
| Dispatch Planning | Suggest team, equipment, and next steps | Cannot claim a crew was sent |
| Work Order | Synthesize specialist outputs | Must expose uncertainty |
| Human Operator | Approve/reject the work order | Required before routing |
| Audit | Check consistency and under-prioritization | Cannot bypass operator review |
| Priority Extractor | Normalize `EMERGENCY` or `STANDARD` | Defaults to `STANDARD` on ambiguity |
| Monitoring Agent | Validate trace integrity and node errors | Does not alter operational priority |

## Inputs and outputs

Input: free-text civic infrastructure report, maximum 5,000 characters. Avoid names, phone numbers, precise household details, or other unnecessary personal data.

Output: draft work order, supervisor rationale, human-review state, normalized priority, routing recommendation, monitoring report, and correlation ID.

## Human oversight and safety

- Every work order pauses before the `human_review` node.
- Rejecting a work order ends the run before audit/routing.
- `EMERGENCY` is an escalation recommendation, not an automated emergency call.
- Operators must follow local policy and contact emergency services independently when life safety is threatened.
- The service must not be used as the sole channel for urgent public reports.

## Observability

Every execution receives a UUID correlation ID. Each graph node records status, duration, token metadata, timestamp, and a truncated error detail. Operators can use `/runs/{correlation_id}`, `/metrics`, and `/dashboard` to investigate a run.

## Known limitations

1. Pending human-review checkpoints are process-local and do not survive restarts.
2. SQLite is designed for one application instance in this MVP.
3. Outputs can be incomplete, incorrect, or biased and require human judgment.
4. Authentication, rate limiting, moderation, and municipal system integrations are out of MVP scope.

## Secrets and configuration

`GEMINI_API_KEY` is read only from the environment and must never be logged or committed. `.env.example` contains placeholders. `DATABASE_PATH` and `LOG_LEVEL` are non-secret configuration. The model name is fixed in code to preserve assignment compliance.

## Change governance

Changes to prompts, priority logic, routing messages, model, or human-review behavior require pull-request review and green CI. Update this card and the runbook for material behavior changes. Before release, exercise one emergency, one standard, one rejected, and one provider-failure scenario.
