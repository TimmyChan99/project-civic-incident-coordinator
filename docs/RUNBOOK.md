# Incident Runbook

## Service objectives and ownership

- Target availability for the demonstration: best effort within Railway Free limits.
- Health signal: `GET /health` returns HTTP 200.
- Trace objective: every started run has one correlation ID and a node event trail.
- Operational owner: repository maintainer. Add real on-call contacts before public use.

## First response

1. Capture timestamp, user-visible error, `thread_id`, and `correlation_id` if available.
2. Check `/health`, `/metrics`, and `/runs/{correlation_id}`.
3. Review Railway deployment logs and the last GitHub Actions run.
4. Classify the incident: provider/model, application, data store, deployment, or incorrect routing.
5. If unsafe or incorrect routing is possible, activate the kill switch immediately.

## Kill switch (target: under five minutes)

Use the narrowest available action:

1. Railway service → Settings → set replicas to zero or remove the public domain.
2. If UI-only exposure is the concern, remove the generated public domain while preserving logs.
3. Record the last known-good commit SHA and affected correlation IDs.
4. Do not delete monitoring storage during containment.

The application has no automated external dispatch integrations, so disabling HTTP access stops all operational effects.

## Common incidents

### Gemini returns model not found / retired

Expected cause: `gemini-2.5-flash` was shut down by Google on June 1, 2026.

1. Confirm `/health` is green; health does not test the provider.
2. Find the failed run and verify the failing node detail.
3. Keep the service disabled for live demonstrations.
4. Obtain written assignment authorization for a supported model before changing `GEMINI_MODEL`.
5. Update tests, README, Agent Card, and release notes with the approved migration.

### Gemini quota or outbound-network failure

1. Inspect the failed node and provider response in Railway logs.
2. Verify `GEMINI_API_KEY` exists without printing its value.
3. Check Google AI Studio quota and Railway trial outbound-network restrictions.
4. Retry once after the provider recovery window; avoid retry loops that consume quota.

### Pending approval disappeared

Cause: process restart or multiple instances with process-local `MemorySaver`.

1. Confirm a restart/deploy occurred.
2. Ask the operator to submit the report again with a new `thread_id`.
3. Keep one replica for the MVP.
4. For production, schedule a change to a durable LangGraph checkpointer.

### SQLite unavailable or read-only

1. Verify `DATABASE_PATH` and write access to its parent directory.
2. On Railway, verify the volume mount is `/app/data`.
3. The service falls back to memory only if backend creation fails at startup; note that history will be lost on restart.
4. Restore the mount, restart once, and validate a test trace.

### Incorrect emergency/standard route

1. Disable public access if the error can affect operator decisions.
2. Preserve report, work order, audit output, model metadata, and correlation trace.
3. Reproduce with a mocked regression fixture—never with real personal data.
4. Correct prompts or deterministic extraction logic through a reviewed PR.
5. Run emergency, standard, rejection, and malformed-output tests before redeploying.

## Rollback

1. Identify the last green commit and CI run.
2. In Railway Deployments, choose the last known-good deployment and **Redeploy** it, or revert the faulty commit in Git and push the revert.
3. Do not use destructive Git resets on a shared repository.
4. Verify `/health`, `/ui`, `/metrics`, and one mocked/non-sensitive acceptance scenario.
5. Document cause, impact window, affected correlation IDs, containment, and follow-up work.

Rollback does not make a provider-retired model operational; it only restores application code.

## Escalation

| Time | Action |
|---|---|
| Immediately | Remove public access for possible unsafe routing or data exposure |
| 15 minutes | Notify maintainer and preserve logs/traces |
| 1 hour | Escalate provider/platform incident and decide whether to remain offline |
| 1 business day | Complete post-incident review for safety or privacy incidents |

## Recovery checklist

- GitHub Actions is green.
- Docker image builds and `/health` passes.
- No secrets appear in source, logs, or trace payloads.
- Emergency, standard, rejection, missing-key, and malformed-priority tests pass.
- Monitoring events share one correlation ID and show zero unexpected errors.
- Agent Card and architecture docs reflect any changed behavior.
