# Civic Incident Coordinator

A lightweight multi-agent supervisor that turns resident reports about public infrastructure into operator-reviewed municipal work orders. It is a new use case built from the architectural standards of the reference project—not a medical-system copy.

The MVP includes a LangGraph supervisor, three parallel specialists, human-in-the-loop approval, an audit and priority router, a monitoring agent, correlation-ID observability, a FastAPI API, a functional browser UI, a monitoring dashboard, SQLite persistence, tests, Docker Compose, GitHub Actions, and Railway configuration.


## Use case and workflow

A resident reports a damaged or disrupted civic asset such as a traffic signal, road, water main, drain, streetlight, or public facility.

```text
Resident report
      ↓
Supervisor Agent
      ↓
Classification ─┬─ Community Impact ─┬─ Dispatch Planning  (parallel)
                └──────────┬──────────┘
                           ↓
                  Structured Work Order
                           ↓
                  Human Operator Review
                     ↙ reject   approve ↘
                   END          Audit Agent
                                      ↓
                              Priority Extractor
                                      ↓
                             Emergency / Standard
                                      ↓
                               Monitoring Agent
                                      ↓
                                     END
```

The system only recommends routing. It does not contact emergency services, create a municipal ticket, or claim that dispatch occurred.

## Requirements traceability

| Assignment criterion | Implementation |
|---|---|
| Multi-agent supervisor/router | LangGraph `StateGraph` in `app/graph.py` |
| Specialized sector workflow | Civic infrastructure classification, impact, and dispatch agents |
| Monitoring agent | Final `monitoring_agent` node plus `app/monitoring.py` |
| Correlation ID on every execution | UUID propagated in state and every node event |
| Automated tests | Offline pytest suite with mocked LLM; coverage threshold in CI |
| Governance | `AGENT_CARD.md`, architecture, limitations, and change controls |
| Containerization | Non-root production `Dockerfile` and `docker-compose.yml` |
| API and UI | FastAPI, operations desk at `/ui`, Swagger at `/docs` |
| Incident handling | Kill switch, diagnosis, rollback, and escalation in `docs/RUNBOOK.md` |
| Technical documentation | `docs/ARCHITECTURE.md`, `docs/VALIDATION.md`, BPMN file |
| Demo video | Intentionally excluded as requested |

## Project layout

```text
project-civic-incident-coordinator/
├── app/
│   ├── api.py            # API endpoints and health probe
│   ├── config.py         # environment and fixed assignment model
│   ├── graph.py          # supervisor graph and HITL workflow
│   ├── monitoring.py     # correlation traces, metrics, SQLite
│   └── web.py            # operations UI and monitoring dashboard
├── tests/                # unit, integration, and API tests
├── docs/                 # architecture, runbook, validation guide
├── .github/workflows/    # lint, format, test, structure, Docker build
├── Dockerfile
├── docker-compose.yml
├── railway.json
└── civic_incident_coordinator.bpmn
```

## Local setup with the required `.venv`

Prerequisites: Python 3.12 and Git. Docker is optional.

```bash
cd project-civic-incident-coordinator
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Open `.env` and replace the placeholder:

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_PATH=data/monitoring.db
LOG_LEVEL=INFO
PORT=8000
```

Never commit `.env`. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey). The key cannot make the retired model endpoint available; it only configures authentication.

Run quality checks:

```bash
ruff check .
ruff format --check .
pytest --cov=app --cov-report=term-missing
```

Start the service:

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

Open:

- Operations UI: `http://localhost:8000/ui`
- Monitoring dashboard: `http://localhost:8000/dashboard`
- Interactive API docs: `http://localhost:8000/docs`
- Health probe: `http://localhost:8000/health`

The health endpoint deliberately does not call Gemini, so platform health checks do not spend quota.

## API walkthrough

Start a report (the graph pauses before operator review):

```bash
curl -X POST http://localhost:8000/incidents \
  -H 'Content-Type: application/json' \
  -d '{"report":"A large water leak is flooding the crossing beside North Primary School.","thread_id":"demo-001"}'
```

Approve and resume:

```bash
curl -X POST http://localhost:8000/incidents/demo-001/review \
  -H 'Content-Type: application/json' \
  -d '{"approved":true,"comment":"Location confirmed by duty operator"}'
```

Inspect the returned `correlation_id`:

```bash
curl http://localhost:8000/runs/REPLACE_WITH_CORRELATION_ID
curl http://localhost:8000/metrics
```

## Docker Compose local development

After creating `.env`:

```bash
docker compose config
docker compose up --build
```

The UI is then available at `http://localhost:8000`. The named `monitoring_data` volume keeps SQLite traces between container recreations.

Stop the service without deleting data:

```bash
docker compose down
```

Delete the local monitoring volume only when you intentionally want to erase it:

```bash
docker compose down --volumes
```

## Build and run the production image

```bash
docker build -t civic-incident-coordinator:local .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v civic-monitoring:/app/data \
  civic-incident-coordinator:local
```

The image runs as an unprivileged user and includes a Docker health check.

## Railway Free deployment

As of July 2026, Railway documents a $0/month Free plan with **$1 of monthly resource credit**; new accounts first receive a 30-day/$5 trial. Resource use above the included credit or platform policy changes may require payment. Review the current [Railway pricing page](https://docs.railway.com/pricing) before deploying.

### Deploy from GitHub

1. Create a new Git repository with this directory as its root and push it to GitHub.
2. Sign in to Railway and choose **New Project → Deploy from GitHub repo**.
3. Select the repository. Railway detects the root `Dockerfile`; `railway.json` supplies the `/health` probe and restart policy.
4. In the service **Variables** panel, add:

   ```text
   GEMINI_API_KEY=your_gemini_api_key_here
   DATABASE_PATH=/app/data/monitoring.db
   LOG_LEVEL=INFO
   ```

   Do not set `PORT`; Railway injects it.
5. Optional persistence: attach a Railway Volume mounted at `/app/data`. Without a volume, monitoring data is ephemeral and resets on redeploy. Volumes consume plan resources.
6. In **Settings → Networking**, choose **Generate Domain**.
7. Verify `https://YOUR_DOMAIN/health`, then `/ui`, `/dashboard`, and `/docs`.

Railway's official [FastAPI deployment guide](https://docs.railway.com/guides/fastapi) confirms GitHub/Dockerfile deployment and public-domain generation. Limited-trial accounts can have restricted outbound network access; Gemini calls require allowed HTTPS egress.

### Continuous delivery

GitHub Actions validates linting, formatting, structure, tests/coverage, and the Docker build on every push and pull request. Once CI is green, a push to the branch connected to Railway triggers Railway's own Docker build and deployment. No registry credentials are needed for this path.

## Persistence and free-tier choices

- SQLite is embedded, free, and open source. No paid database is required.
- LangGraph uses an in-process checkpoint store for the short pause/resume workflow. Run one Uvicorn worker; pending approvals do not survive a process restart.
- A Railway volume is optional for monitoring history. The application safely creates the database on startup.
- No queue or vector database is used because this MVP does not need one.

For a production municipality, replace in-memory checkpoints with a durable LangGraph checkpointer and add authentication/RBAC before exposing resident or operator data.

## Operational limitations

- The required Gemini model is retired, so live graph execution is currently blocked by the provider.
- The API has no authentication; deploy only as a controlled demonstration.
- Resident text may contain personal data. Do not submit sensitive data to a demonstration instance.
- Model output is advisory and must pass operator review.
- A single process is required because pending LangGraph checkpoints are held in memory.

See [AGENT_CARD.md](AGENT_CARD.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/RUNBOOK.md](docs/RUNBOOK.md) for governance and operations.
