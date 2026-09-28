# Verifying the Stack & Running the Demo (Browser-Only)

Use this after `./scripts/setup.ps1` completes. Everything below is checked
by opening a URL in your browser — no terminal needed for the normal flow.
See [README.md](README.md) for setup and [ARCHITECTURE.md](ARCHITECTURE.md)
for design details.

## Bookmarks — open all of these once, keep tabs open

| # | What it tells you | URL |
|---|---|---|
| 1 | **Agent is alive** | http://localhost:8000/healthz |
| 2 | **Agent demo UI** (the main screen you'll drive the demo from) | http://localhost:8000 |
| 3 | **Shop frontend** (where faults become visible to "customers") | http://localhost:8080 |
| 4 | **Grafana** (dashboards, metrics, traces) | http://localhost:8080/grafana/ |
| 5 | **Jaeger** (distributed traces) | http://localhost:8080/jaeger/ui/ |
| 6 | **Feature Flags UI** (see flags flip when a fault triggers/clears) | http://localhost:8080/feature/ |

Grafana logs in anonymously as Admin — no password needed. If asked anyway,
it's `admin` / `admin`.

## 1. Is everything up? (2-minute check, tabs 1–6)

1. **Tab 1** (`/healthz`) should show `{"status":"ok"}`. If it hangs or shows
   a browser connection error, the agent pod isn't ready yet — give it a
   minute and refresh.
2. **Tab 2** (agent UI) should load with a **Trigger Fault** panel on the left
   and an **Incidents** table on the right (empty is fine on first load).
3. **Tab 3** (shop) should show the "Astronomy Shop" storefront with products.
4. **Tab 4** (Grafana) should load a dashboard list — open **Dashboards** in
   the left nav and confirm at least one OTel Demo dashboard renders with
   live data (graphs moving, not "No data").
5. **Tab 5** (Jaeger) — in the **Service** dropdown you should see services
   like `frontend`, `checkout`, `payment`; click **Find Traces** and confirm
   traces appear.
6. **Tab 6** (Feature Flags UI) should list all flags (e.g. `paymentFailure`,
   `adHighCpu`, ...) all currently **off**.

If any tab won't load at all (connection refused), see **Troubleshooting** in
[README.md](README.md#troubleshooting) — most likely the kind cluster
containers stopped (Docker Desktop restart) and need `docker start`.

## 2. Watch the agent actually work (the real test)

This is the real proof the whole pipeline works end-to-end, all from tab 2
and tab 6:

1. Go to **tab 2** (http://localhost:8000). In the **Trigger Fault** panel,
   click **Trigger** next to `paymentFailure`.
2. Switch to **tab 6** (Feature Flags UI) and refresh — `paymentFailure`
   should now show as **on**. This confirms the fault-injection API worked.
3. Switch to **tab 3** (shop) and try to check out — you should see the
   checkout fail. This confirms the fault is actually affecting the app.
4. Back on **tab 2**, within ~1-2 minutes a new row appears in the
   **Incidents** table automatically (no refresh needed — the UI polls/streams
   live). This confirms Prometheus alerted → Alertmanager webhooked → the
   agent started a run.
5. Click that incident row. You'll see the **Live Agent Timeline** filling in
   live, step by step: `detect` → `investigate` → `diagnose` →
   `assess_severity` → `plan`. This confirms the LangGraph pipeline and the
   live SSE stream both work.
6. The **Approval Required** panel appears with the agent's proposed plan.
   Type any name and click **Approve & Remediate**.
7. Watch the timeline continue with the remediation step, then an
   **Outcome** panel appears showing the incident resolved.
8. Switch back to **tab 6** — `paymentFailure` should now show **off** again
   (the agent's remediation flipped it back). Switch to **tab 3** — checkout
   should work again.

If steps 1-3 work but step 4 never happens (no incident appears after ~2-3
minutes), check **tab 4** (Grafana) → left nav **Alerting** → **Alert rules**:
you should see `HighHttpErrorRate` transition to a firing/pending state. If it
never fires, the metrics pipeline (not the agent) is the problem — see
Troubleshooting.

## 3. Optional: see the alert/metrics pipeline in Grafana directly

You don't need raw Prometheus/Alertmanager UIs (they aren't exposed as a
browser URL by default) — everything they show is visible through Grafana:

- **Alerting → Alert rules**: shows every rule from `app/otel-demo-values.yaml`
  (`HighHttpErrorRate`, `HighLatencyP95`, `PodCrashLooping`,
  `KafkaConsumerLagHigh`) and their current state (inactive/pending/firing).
- **Explore**: pick the Prometheus datasource and run a query like
  `rate(http_server_request_duration_seconds_count[2m])` to see live metrics
  from the fault you just triggered.
- **Dashboards**: the bundled OTel Demo dashboards visualize the same traffic.

## 4. Fault scenarios to demo

All from [scripts/faults/registry.yaml](scripts/faults/registry.yaml), triggered
the same way (tab 2's **Trigger Fault** panel):

| Fault id | Severity | Expected alert | Story |
|---|---|---|---|
| `paymentFailure` | critical | HighHttpErrorRate | Payment service fails all charge requests |
| `paymentUnreachable` | critical | HighLatencyP95 | Payment service unreachable, checkout times out |
| `productCatalogFailure` | warning | HighHttpErrorRate | Product catalog fails lookups for one product |
| `adHighCpu` | warning | HighLatencyP95 | Ad service pegged on CPU, degraded latency |
| `kafkaQueueProblems` | warning | KafkaConsumerLagHigh | Kafka consumer lag spikes on the orders topic |
| `podCrashLoop` | critical | PodCrashLooping | Recommendation pod crash-loops (failing liveness probe) |

For a live audience, `paymentFailure` or `podCrashLoop` demo best — a visible
checkout failure (tab 3) or pod restarts, paired with an obvious remediation.

## 5. What to narrate during the demo

- **Live agent reasoning** (tab 2): the timeline streams each LangGraph node's
  output as it happens — no polling/refresh needed.
- **Human-in-the-loop gate**: nothing is remediated automatically — the agent
  pauses at `awaiting_approval` until you click **Approve** or **Reject**.
- **Real, visible effect** (tabs 3 and 6): the fault and its remediation are
  not simulated — the shop actually breaks and actually recovers, and the
  feature flag actually flips.
- **Scoped RBAC**: the agent can only touch pods/configmaps/deployments in
  the `otel-demo` namespace, never its own — see
  [infra/agent-service.yaml](infra/agent-service.yaml).
- **Graceful degradation**: if `.env` has no AWS keys, the agent still runs
  the full pipeline using fault-registry hints instead of LLM reasoning —
  worth mentioning if Bedrock isn't configured on the demo machine.

## Advanced: API/terminal-level checks (optional, not needed for the demo)

Only needed if you want to inspect things below the UI layer (e.g. debugging).
Full endpoint reference: [agent_service/app/routers](agent_service/app/routers).

```powershell
curl http://localhost:8000/incidents
curl http://localhost:8000/faults
kubectl get pods -A | Select-String -NotMatch "Running|Completed"
```

## If something looks wrong

See the **Troubleshooting** section in [README.md](README.md#troubleshooting)
for known transient issues (control-plane hiccups under load, stopped kind
containers after a Docker Desktop restart, flagd propagation delay, etc.)
before assuming something is broken.
