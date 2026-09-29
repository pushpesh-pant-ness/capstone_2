# How-To Guide: Running the Project & Creating an Incident ("Issue")

This project doesn't track GitHub-style issues — "issue" here means an
**incident** row that flows through the agent pipeline (investigate → severity
→ historical → RCA/auto-plan → plan → guardrail → human approval →
remediate → validate). This guide covers running the app, the three ways to
create an incident from existing scenarios, and how to add brand-new error
scenarios/alert rules to the project.

## 1. Running the project

Full details (prerequisites, env vars, Grafana, teardown) are in
[../RUN.md](../RUN.md). Quick path:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # fill in AWS Bedrock creds, or leave blank to use agent/heuristics.py

docker compose -f infra/docker-compose.yaml up -d       # Postgres + OTel Collector + Loki/Prometheus/Alertmanager/Grafana

Get-Content db/migrations/0001_init.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
Get-Content db/migrations/0002_add_escalation_reason.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent
Get-Content db/migrations/0003_add_rejected_by.sql | docker exec -i $(docker compose -f infra/docker-compose.yaml ps -q postgres) psql -U incident_agent -d incident_agent

uvicorn api.main:app --port 8090
```

Dashboard/API: http://localhost:8090 — health check at `/healthz`.

> On Windows, prefer running `uvicorn` **without** `--reload` while actively
> iterating on code — `kill_terminal`/Ctrl+C often leaves the reloader's
> worker subprocess orphaned and still bound to the port, silently serving
> stale code. Kill by PID (`Get-CimInstance Win32_Process -Filter
> "Name='python.exe'"`) and restart a single instance instead.

## 2. Creating an incident

Only remediation actions on `tools/allowlist.yaml` (`restart_pod`,
`rollback_deployment`, `scale_deployment`) are ever executed, and nothing runs
against Kubernetes until a human approves via the dashboard or API — see
[api/routers/approvals.py](../api/routers/approvals.py).

### Option A — CLI script (fastest, no cluster/Alertmanager required)

Runs the exact same pipeline as the webhook (`api/pipeline.py`), end-to-end,
and prints the result:

```powershell
python scripts/run_agent_cli.py --alert-name HighHttpErrorRate --service checkout
```

- `--alert-name` should match a rule in [infra/alert_rules.yml](../infra/alert_rules.yml)
  (`HighHttpErrorRate`, `HighLatencyP95`, `PodCrashLooping`) for realistic
  severity/RCA behavior, but any string works.
- `--service` should be a real Deployment name in the target namespace if you
  want remediation actions to actually succeed against a cluster.

### Option B — Fault injection against a real cluster (most realistic)

Toggles a real feature flag (flagd) or patches a real bad liveness probe on
the `opentelemetry-demo` cluster, so Prometheus/Loki evidence is genuine
(requires the full stack — kind cluster + observability compose — actually up
and its metrics genuinely wired, see caveat below):

```powershell
python scripts/faults/inject.py list                    # see available fault ids
python scripts/faults/inject.py trigger productCatalogFailure
python scripts/faults/inject.py status
python scripts/faults/inject.py clear productCatalogFailure
python scripts/faults/inject.py clear-all                # always run this after a rehearsal session
```

Fault ids and their expected alert/root cause/remediation are documented in
[scripts/faults/registry.yaml](../scripts/faults/registry.yaml).

> Caveat verified 2026-09-28: the `opentelemetry-demo` Helm chart as deployed
> here has no Prometheus exporter port on `otel-collector` (only
> OTLP/Jaeger/Zipkin), so `HighHttpErrorRate`/`HighLatencyP95` can never
> actually fire from real traffic — use Option A or C to still exercise the
> pipeline, and treat `error_rate`/`p95_latency` evidence of `0.0` as "no
> data", not "no errors", until that's fixed with a Helm values change.

### Option C — Simulate the real Alertmanager webhook

Exercises the actual intake path ([api/routers/alerts.py](../api/routers/alerts.py))
instead of bypassing it:

```powershell
$body = @{
  status = "firing"
  alerts = @(@{
    status      = "firing"
    labels      = @{ alertname = "HighHttpErrorRate"; service = "checkout" }
    annotations = @{ summary = "High HTTP 5xx error rate on checkout" }
    fingerprint = "manual-test-$(Get-Random)"
  })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8090/webhooks/alertmanager" -Method Post -ContentType "application/json" -Body $body
```

If `ALERTMANAGER_WEBHOOK_TOKEN` is set in `.env`, add
`-Headers @{ Authorization = "Bearer <token>" }`.

### Approving / rejecting

```powershell
Invoke-RestMethod -Uri "http://localhost:8090/incidents/<incident_id>/approve" -Method Post -ContentType "application/json" -Body '{"approved_by":"<name>"}'
Invoke-RestMethod -Uri "http://localhost:8090/incidents/<incident_id>/reject" -Method Post -ContentType "application/json" -Body '{"rejected_by":"<name>","reason":"<why>"}'
```

Or use the dashboard's Approve/Reject buttons at http://localhost:8090.

### Cleaning up test incidents

Ad-hoc incidents created via Options A/C for testing aren't auto-deleted —
remove them directly so they don't confuse a real demo/user:

```powershell
docker exec infra-postgres-1 psql -U incident_agent -d incident_agent -c "DELETE FROM incidents WHERE incident_id = '<incident_id>';"
```

(`audit_log` rows cascade-delete automatically, see [db/schema.sql](../db/schema.sql).)

## 3. Creating new fault scenarios / error conditions (extending the project)

Everything below is about adding a **new** kind of error for the project to
detect, not just triggering an existing one. Note
[scripts/faults/registry.yaml](../scripts/faults/registry.yaml) is reference
data only — the agent's Plan node always derives its own plan from
[tools/allowlist.yaml](../tools/allowlist.yaml), independent of this registry.

### New flagd-based fault (a feature-flag-driven bug)

1. Find (or add) the flag in the `otel-demo` cluster's `flagd-config`
   ConfigMap: `kubectl get configmap flagd-config -n otel-demo -o json`. If
   the flag doesn't exist yet, it must be added to the
   `open-telemetry/opentelemetry-demo` chart's flag definitions (a Helm
   values change) — check with the user before changing shared chart config.
2. Add an entry to `scripts/faults/registry.yaml`:
   ```yaml
   - id: myNewFault
     type: flagd
     flag_key: myNewFault        # must match a real key in the ConfigMap
     on_variant: "on"            # the failure-inducing variant
     off_variant: "off"          # the healthy variant
     target_service: some-service
     severity: warning
     expected_alert: HighHttpErrorRate
     expected_root_cause: "Description of what breaks and why"
     expected_remediation: toggle_flag_off   # descriptive only — not in the MVP allow-list
   ```
3. Trigger it the same way as any other fault:
   `python scripts/faults/inject.py trigger myNewFault`.

### New crash-loop-based fault (a pod that crash-loops)

Add an entry with `type: crash_loop` instead:
```yaml
- id: myNewCrashFault
  type: crash_loop
  target_deployment: some-deployment   # real Deployment name in otel-demo
  target_service: some-deployment
  severity: critical
  expected_alert: PodCrashLooping
  expected_root_cause: "Container crash-looping (failing liveness probe)"
  expected_remediation: rollback_deployment
```
This reuses [scripts/faults/_handlers.py](../scripts/faults/_handlers.py)'s
`set_crash_liveness_probe` (patches a guaranteed-failing liveness probe onto
the Deployment's first container) — no new handler code needed.

### A genuinely new fault *type* (neither flagd nor crash-loop)

1. Add a handler function to `scripts/faults/_handlers.py` (shell out to
   `kubectl`, matching the existing style — e.g. patching resource limits,
   deleting a Secret/ConfigMap key, scaling to 0).
2. Wire it into `apply_fault()` in `scripts/faults/inject.py`:
   ```python
   elif fault["type"] == "my_new_type":
       h.my_new_handler(fault["some_field"], enable=on)
   ```
3. Add a matching registry entry with `type: my_new_type` and whatever extra
   fields your handler needs.

### New alert rule (a new class of detectable error)

Add a rule group entry to
[infra/alert_rules.yml](../infra/alert_rules.yml), e.g.:
```yaml
- alert: MyNewAlert
  expr: <PromQL expression>
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "..."
    description: "..."
```
Then reload Prometheus so it picks up the new rule file (no `--web.enable-lifecycle`
flag is set, so restart the container rather than trying a `/-/reload` POST):
```powershell
docker compose -f infra/docker-compose.yaml restart prometheus
```
Verify it loaded: http://localhost:9090/rules.
