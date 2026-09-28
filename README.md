# Incident Remediation Agent — Local Build

Everything for this capstone project lives in this folder. Nothing outside
`incident-remediation-agent/` is touched (see repo root README.md / update.md).

Start with [ARCHITECTURE.md](ARCHITECTURE.md) for the full design (diagrams,
fault scenarios, agent stages, tool allow-list, demo UI requirements). Once
setup succeeds, see [WORKING.md](WORKING.md) to verify everything is healthy,
exercise every API endpoint, and run the demo.

## What's here

```
ARCHITECTURE.md        Full design doc — read this first
.env.example           Template for secrets/config — copy to .env
app/                    OpenTelemetry Demo Helm values overrides
observability/          Loki Helm values (Prometheus + Alertmanager + Grafana are
                        the demo's own bundled sub-charts, just reconfigured)
infra/                  kind cluster config, Postgres+pgvector manifests,
                        incident-agent service manifests (Deployment/RBAC/Service)
agent_service/          FastAPI + LangGraph agent + static demo UI (one deployable
                        Python service — see agent_service/app/)
scripts/faults/         Fault registry (registry.yaml) + a standalone CLI
                        (inject.py) for triggering/clearing faults from your
                        own machine, independent of the UI
scripts/setup.ps1       One-shot local setup (idempotent, safe to re-run)
scripts/update-secrets.ps1   Re-syncs .env into the cluster after you edit it
scripts/teardown.ps1    Deletes the kind cluster
```

## Prerequisites

| Tool | Verified version on this machine |
|---|---|
| Docker Desktop | 29.6.1 |
| kind | v0.32.0 |
| kubectl | v1.36.0 |
| helm | v4.2.3 |
| Python | 3.14.6 (only needed for the optional `scripts/faults/inject.py` CLI) |

If any of these are missing: `winget install Docker.DockerDesktop`, and for
kind/kubectl/helm, `winget install Kubernetes.kind Kubernetes.kubectl Helm.Helm`
(or see each tool's own install docs). Docker Desktop must be running before
any step below.

**Resource note:** this stack runs ~15 demo microservices + Loki + Postgres +
the agent, all on a 3-node kind cluster. Give Docker Desktop at least 6-8GB RAM
and 4 CPUs (Docker Desktop Settings → Resources) or things will be slow/flaky.

## First-time setup

### 1. Configure secrets

```powershell
cd incident-remediation-agent
Copy-Item .env.example .env
notepad .env   # or any editor
```

Fill in (see comments in the file for details):
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` — needed for the
  agent's AI reasoning (Bedrock/Amazon Nova) and historical-incident embeddings
  (Titan). **You must enable model access** for Amazon Nova and Titan Text
  Embeddings V2 in the AWS Console → Bedrock → Model access, in the region you set.
- `GITHUB_TOKEN` / `GITHUB_REPO` — optional, only needed for the agent's
  "create GitHub issue" remediation action.

You can leave everything blank and run the whole thing anyway — the agent
degrades gracefully (falls back to fault-registry hints instead of LLM
reasoning, and the GitHub tool just reports itself as unconfigured), which is
still a fully working demo of the pipeline, detection, HITL approval flow, and
Kubernetes remediation actions that don't need an LLM.

`.env` is git-ignored — it never gets committed.

### 2. Run setup

```powershell
./scripts/setup.ps1
```

This is idempotent (safe to re-run if it fails partway) and does, in order:
1. Creates the `incident-agent` kind cluster (3 nodes) if it doesn't exist
2. Creates the `otel-demo`, `observability`, `incident-agent` namespaces
3. Adds/updates the required Helm repos
4. Deploys the OpenTelemetry Demo app into `otel-demo` (Alertmanager enabled
   with our custom alert rules, OpenSearch disabled)
5. Deploys Loki into `observability`
6. Deploys Postgres+pgvector into `incident-agent`
7. Creates the `fault-registry` ConfigMap from `scripts/faults/registry.yaml`
8. Creates/updates the `incident-agent-secrets` Secret from your `.env`
9. Builds the `incident-agent-service:local` Docker image and loads it into
   the kind cluster's worker nodes (no external registry needed)
10. Deploys the incident-agent service (RBAC + Service + Deployment)

**This takes a while the first time** — pulling ~15 demo microservice images
plus Loki/Postgres can take 10-20 minutes depending on your connection and
disk speed. Subsequent re-runs are much faster (everything is cached).

### 3. Verify everything is up

```powershell
kubectl get pods -A | Select-String -NotMatch "Running|Completed"
```

This should print nothing (empty output = every pod is healthy). If something
is stuck, see **Troubleshooting** below before assuming it's broken — this
stack briefly stresses a local Docker Desktop VM and some control-plane
hiccups are normal and self-heal.

### 4. Open the demo

http://localhost:8000 — the live agent UI. You should see the "Trigger Fault"
panel on the left and an (initially empty, or already-populated if an alert
fired naturally) incident list.

## URLs

| What | URL |
|---|---|
| **Incident Agent demo UI / API** | http://localhost:8000 |
| Shop frontend | http://localhost:8080 |
| Grafana (admin/admin) | http://localhost:8080/grafana/ |
| Jaeger UI (traces) | http://localhost:8080/jaeger/ui/ |
| Feature Flags UI (flagd) | http://localhost:8080/feature/ |
| Prometheus | `kubectl port-forward -n otel-demo svc/prometheus 9090:9090` |
| Alertmanager | `kubectl port-forward -n otel-demo svc/alertmanager 9093:9093` |

## Running a demo / triggering an incident

Either click a button in the "Trigger Fault" panel at http://localhost:8000,
or from the CLI:

```powershell
pip install -r scripts/requirements.txt
python scripts/faults/inject.py list
python scripts/faults/inject.py trigger paymentFailure
```

What happens next, all visible live in the UI:
1. Within ~1-2 minutes the relevant Prometheus alert rule fires (see
   `app/otel-demo-values.yaml`'s `serverFiles.alerting_rules.yml`)
2. Alertmanager webhooks the incident-agent service
3. A new incident appears in the UI; the agent runs detect → investigate →
   diagnose → assess severity → plan, streaming every step live
4. The agent pauses and asks for **human approval** of its remediation plan
5. Click **Approve** (enter any name) — the agent executes the remediation
   (e.g. toggles the fault's feature flag back off), validates recovery, and
   resolves the incident
6. Clear the fault (or click "Clear" in the UI) so the app returns to normal

To reject instead (simulating an unsafe plan): click **Reject** — the incident
is marked escalated and nothing is executed.

## Updating secrets after setup

If you edit `.env` after the first `./scripts/setup.ps1` run (e.g. to add your
AWS keys later):

```powershell
./scripts/update-secrets.ps1
```

This re-syncs the Secret and restarts the deployment. Watch it come back with
`kubectl get pods -n incident-agent -w`.

## Tearing down

```powershell
./scripts/teardown.ps1
```

Deletes the entire kind cluster. `.env` is untouched, so re-running
`./scripts/setup.ps1` later doesn't require re-entering credentials.

## Troubleshooting

**`docker build` / `kind load docker-image` seems to hang for a long time.**
This local Docker Desktop setup can be genuinely slow (we saw the image-export
step take 3 minutes on first build vs. 10 seconds once things settled). Give
it time; if a terminal command times out it's still running in the background
— don't kill it, just check again later.

**`kubectl get pods -n kube-system` shows `kube-scheduler` or
`kube-controller-manager` in `CrashLoopBackOff`.** This happens when the host
is under heavy load (e.g. during the big initial image pulls / docker build)
and the control plane briefly can't renew its leader-election lease in time.
It self-heals once load drops — wait a minute or two and check again. It is
**not** a sign anything is misconfigured.

**A pod stays `Pending` with no events, or a `Deployment` never creates a
`ReplicaSet`.** Same root cause as above (controller-manager/scheduler
temporarily down). Once they recover (see previous point), reconciliation
resumes automatically — you don't need to re-apply anything.

**`curl http://localhost:8000/...` intermittently returns "Connection was
reset" or hangs.** Retry once. This is host/Docker Desktop network-path
flakiness under load, not an application bug — a `200 OK` on retry confirms
the service itself is fine.

**Fault trigger doesn't seem to do anything.** Check `kubectl get configmap
flagd-config -n otel-demo -o jsonpath='{.data.demo\.flagd\.json}'` to confirm
the flag's `defaultVariant` actually changed. flagd picks up ConfigMap changes
via a mounted-file watch, which can take up to ~1 minute to propagate through
the kubelet's ConfigMap sync period.

**`kubectl edit secret ...` fails with exit code 1 / opens no editor.**
Don't use `kubectl edit` on Windows PowerShell without `$env:KUBE_EDITOR` set
— use `./scripts/update-secrets.ps1` instead (edits `.env`, not the cluster
object, directly).

**`./scripts/setup.ps1` fails at step 2 (`kubectl` errors with `dial tcp
127.0.0.1:PORT: ... actively refused it`).** The kind cluster's Docker
containers exist but aren't running — this happens after a Docker Desktop
restart, a host reboot/sleep, or `wsl --shutdown`, which stops (but doesn't
remove) the `incident-agent-*` containers while `kind get clusters` still
lists the cluster, so `setup.ps1` skips re-creating it and goes straight to a
dead API server. Fix by starting the containers back up, then re-run setup:

```powershell
docker start incident-agent-control-plane incident-agent-worker incident-agent-worker2
kubectl get nodes   # confirm it responds (may need a few seconds after start)
./scripts/setup.ps1
```

If `docker ps -a` doesn't show those containers at all, the cluster was fully
removed — just re-run `./scripts/setup.ps1`, which will `kind create cluster`
from scratch.

## Known limitations of this local build

- Single replica, in-memory LangGraph checkpointer and SSE event bus (see
  code comments in `agent_service/app/events.py` and `graph/build.py`) — fine
  for a demo, not for production HA.
- Loki runs as a single binary with filesystem storage, no caching layer —
  sized for a local demo, not production log volumes.
- Postgres has no backups/replication — it's the historical-incident store
  for this demo only.
- AWS Bedrock and GitHub credentials live in a plain Kubernetes Secret (from
  `.env`), fine for a local demo; use a real secrets manager (AWS Secrets
  Manager, Vault, IRSA) for anything beyond that.
