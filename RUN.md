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

> **Minimal / no-Docker-cluster path:** for now we're skipping the kind cluster
> and the Loki/Prometheus/Alertmanager stack and starting **only Postgres**
> (Docker is still needed for that — the API always connects to a DB on
> startup). Everything else degrades gracefully:
> - [agent/nodes/investigate.py](agent/nodes/investigate.py) catches Loki/Prometheus/K8s
>   lookup failures and records them as evidence instead of crashing.
> - Remediation actions (restart_pod/rollback_deployment/scale_deployment) will
>   fail at execution time since there's no cluster to target — fine for
>   testing detection → severity → RCA → plan → approval, not for the actual
>   remediate/validate steps.
>
> Start the full stack (kind + observability) later with `scripts\setup.ps1` or
> the commands below when you need those steps too.

```powershell
docker compose -f infra/docker-compose.yaml up -d
```

## 4. Apply the DB migration

```powershell
Get-Content db/migrations/0001_init.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
Get-Content db/migrations/0002_add_escalation_reason.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
```

## 5. (Optional) Seed historical incidents

```powershell
python scripts/seed_historical_incidents.py
```

## 6. Run the Agent API

```powershell
uvicorn api.main:app --reload --port 8000
```

- API + UI: http://localhost:8000
- Health check: http://localhost:8000/healthz

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

| Service      | Port |
|--------------|------|
| Agent API/UI | 8000 |
| Postgres     | 5432 |
| Loki         | 3100 |
| Prometheus   | 9090 |
| Alertmanager | 9093 |
