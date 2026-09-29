# Running the project locally

Prerequisites: Python 3.11+, Docker Desktop (with Compose), [kind](https://kind.sigs.k8s.io/), and `kubectl`.

## 1. Python environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in AWS Bedrock credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`). If left blank, the agent falls back to `agent/heuristics.py` instead of calling the LLM.

## 3. Start infrastructure

One command now brings up **everything** (Postgres + OpenTelemetry Collector +
Loki/Promtail + Prometheus + Alertmanager + Grafana) — no more separate
observability file:

```powershell
docker compose -f infra/docker-compose.yaml up -d
```

> **No kind cluster yet?** Everything still degrades gracefully:
> - [agent/nodes/investigate.py](agent/nodes/investigate.py) catches Loki/Prometheus/K8s
>   lookup failures and records them as evidence instead of crashing.
> - Remediation actions (restart_pod/rollback_deployment/scale_deployment) will
>   fail at execution time since there's no cluster to target — fine for
>   testing detection → severity → RCA → plan → approval, not for the actual
>   remediate/validate steps.
>
> Start the kind cluster + otel-demo app later with `scripts\setup.ps1` (or
> `kind create cluster --config infra/kind-cluster.yaml` +
> `helm install otel-demo open-telemetry/opentelemetry-demo -n otel-demo -f infra/otel-demo-values.yaml`)
> when you need real telemetry.

Grafana comes up at http://localhost:3001 (anonymous Viewer access for local
dev — host port 3000 is reserved by `infra/kind-cluster.yaml`'s control-plane
NodePort mapping) with Prometheus + Loki pre-wired as data sources and an
"Incident Agent Overview" dashboard (error rate, p95 latency, pod restarts,
live logs) already provisioned — see [infra/grafana](infra/grafana).

The OpenTelemetry Collector (`infra/otel-collector-config.yaml`) receives OTLP
logs/metrics/traces from the otel-demo app (see `infra/otel-demo-values.yaml`,
which points every demo component at `host.docker.internal:4317`/`4318`) and
fans them out: logs → Loki (visible in Grafana Explore / the dashboard's live
logs panel), metrics → Prometheus (via its OTLP receiver), traces → the
collector's own debug log output (`docker compose -f infra/docker-compose.yaml
logs -f otel-collector`). Health check: http://localhost:13133/ ; live
internal state (zpages): http://localhost:55679/debug/tracez .

## 4. Apply the DB migration

```powershell
Get-Content db/migrations/0001_init.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
Get-Content db/migrations/0002_add_escalation_reason.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
Get-Content db/migrations/0003_add_rejected_by.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
```

## 5. (Optional) Seed historical incidents

```powershell
python scripts/seed_historical_incidents.py
```

## 6. Run the Agent API

```powershell
uvicorn api.main:app --reload --port 8090
```

- API + UI: http://localhost:8090
- Health check: http://localhost:8090/healthz

> Note: port 8000 is reserved by `infra/kind-cluster.yaml`'s Docker port mapping
> (for an in-cluster agent deployment we don't use locally) — use 8090 for the
> locally-run process, matching `infra/alertmanager.yml`'s webhook URL.

## 7. Try it out

Run one incident through the full agent pipeline without the API/UI:

```powershell
python scripts/run_agent_cli.py --alert-name HighHttpErrorRate --service payment
```

Or trigger via the webhook route once `uvicorn` is running (see [api/routers/alerts.py](api/routers/alerts.py)), then approve/reject via:

```
POST /incidents/{incident_id}/approve
POST /incidents/{incident_id}/reject
```

## 8. Run tests

```powershell
pytest
```

## Teardown

```powershell
scripts\teardown.ps1
```

## Reference — service ports

| Service                    | Port        |
|----------------------------|-------------|
| Agent API/UI               | 8090        |
| Postgres                   | 5432        |
| Opentelemetry              |             |
| Loki                       | 3100        |
| Prometheus                 | 9090        |
| Alertmanager               | 9093        |
| Grafana                    | 3001        |
