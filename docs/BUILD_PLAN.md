# Build Plan — Autonomous Post-Deployment Incident & Remediation Agent

> Companion to [SRS.md](./SRS.md). Turns the SRS into a phased plan for a **24–48 hour hackathon**, team of **2**.

---

## 1. Objective & MVP Definition

**MVP (build this first — the whole hackathon deliverable):**
1. Monitored app emits metrics + logs → Prometheus + Loki.
2. Alertmanager fires a real alert → webhook reaches the Agent.
3. LangGraph pipeline (Investigate → Severity → Historical → RCA → Plan) runs on Bedrock and produces a plan restricted to Kubernetes actions.
4. HITL approval UI/API lets a human approve/reject.
5. Approved plan executes a **real Kubernetes remediation** (rollback/restart/scale) against a local `kind`/`minikube` cluster.
6. Post-remediation validation confirms recovery and closes the incident.
7. Every step is written to the audit trail.

**Phase 2 (see SRS §10.C — do not start before the MVP works end-to-end):** AWS remediation, GitHub revert PR flow, OTel traces, pgvector semantic search, LangSmith/LangFuse, RBAC, richer UI.

### Design Principles
1. **LLM has a rule-based fallback** — `agent/llm_client.py` wraps Bedrock behind a common contract; if the call fails or returns unparseable output, fall back to `agent/heuristics.py` (deterministic rules, e.g. "recent deploy + latency spike → rollback") so RCA/Planning never hard-fail.
2. **The executor, not the LLM, enforces safety** — the Planning node filters against `tools/allowlist.yaml`; the Executor re-checks before running anything. Neither trusts the other alone.
3. **One pipeline, two entry points** — the same graph invocation is called by the FastAPI webhook handler and by `scripts/run_agent_cli.py`, so it can be rehearsed/debugged without the full stack running.
4. **Loose coupling everywhere an external system is touched** — every integration (LLM, Loki, Prometheus, each K8s/AWS/GitHub target, the DB) sits behind a small interface owned by the layer that calls it: `agent/llm_client.py` defines the LLM contract, `tools/base.py` defines the tool contract, `db/repository.py` defines the only DB access surface. Concrete implementations (Bedrock, `k8s_tool.py`, Postgres) are swapped or added by pointing config at a new class — never by editing the graph, routers, or other callers. The only things allowed to cross the Track 1 / Track 2 boundary are the three shared contracts: the Incident state schema, `tools/allowlist.yaml`, and the repository functions.

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| APP | OpenTelemetry |
| Agent orchestration | LangGraph + LangChain (Python) |
| LLM | AWS Bedrock (Anthropic Claude 3.x) |
| API | FastAPI |
| DB | PostgreSQL |
| Observability | Grafana Loki, Prometheus, Alertmanager |
| Remediation | `kind`/`minikube` + Kubernetes Python client / `kubectl` |
| UI | Streamlit (or a plain HTML page) |
| Containerization | Docker + Docker Compose (+ `kind` for K8s) |

Phase 2 additions: `pgvector`, OpenTelemetry Collector, `boto3`/LocalStack, PyGithub/GitHub REST API, LangSmith/LangFuse.

---

## 3. Proposed Repository Structure

```
hackathon/
├── readme.md
├── docs/
│   ├── SRS.md
│   ├── BUILD_PLAN.md
│   └── TASKS.md
├── agent/                     # LangGraph + LangChain orchestrator
│   ├── graph.py                # Investigate→Severity→Historical→RCA→Plan
│   ├── state.py                # Incident state schema (pydantic/TypedDict)
│   ├── llm_client.py            # Bedrock wrapper + heuristic fallback
│   ├── heuristics.py            # rule-based RCA/plan fallback + historical similarity scoring
│   ├── nodes/
│   │   ├── investigate.py
│   │   ├── severity.py
│   │   ├── historical.py
│   │   ├── rca.py
│   │   └── plan.py
│   └── prompts/                # versioned prompt templates
├── tools/                     # external-system adapters
│   ├── base.py                  # common adapter interface
│   ├── allowlist.yaml           # Tool Allow-list (SRS §7)
│   ├── loki_tool.py
│   ├── prometheus_tool.py
│   └── k8s_tool.py
├── api/                        # FastAPI service
│   ├── main.py
│   ├── routers/
│   │   ├── alerts.py            # Alertmanager webhook intake
│   │   ├── incidents.py         # incident CRUD/read
│   │   └── approvals.py         # HITL approve/reject
│   └── models.py
├── ui/                         # approval dashboard
├── db/
│   ├── migrations/
│   ├── schema.sql               # incidents, audit_log
│   └── repository.py            # only DB access surface — routers/agent never write raw SQL
├── infra/
│   ├── kind-config.yaml
│   └── docker-compose.observability.yaml   # Loki, Prometheus, Alertmanager
├── tests/
└── scripts/
    ├── seed_historical_incidents.py
    └── run_agent_cli.py         # invoke the graph standalone — fast iteration + demo-rehearsal safety net
```

Phase 2 adds (as new files, not modifications to the above): `tools/otel_tool.py`, `tools/aws_tool.py`, `tools/github_tool.py`, `tools/guard.py` (staleness re-check), a `pgvector`-backed embeddings table, and LangSmith/LangFuse wiring.

---

## 4. Team Roles (2 people)

| Track | Owns |
|---|---|
| Track 1 — Platform & Product | Observability stack, alert rules, FastAPI intake/approval API, DB schema, audit logging, approval UI |
| Track 2 — Agent & Execution | LangGraph agent, Bedrock prompts, historical heuristic, K8s adapter, allow-list enforcement, validation loop |

---

## 5. Phased Timeline

### Phase 0 — Setup & Alignment (Hour 0–2)
- Repo scaffold per §3; confirm Bedrock model access with a smoke-test call.
- Stand up `kind` cluster; confirm `kubectl` context points at it (never a shared cluster).
- Confirm monitored app exposes `/metrics` and structured logs; add minimal instrumentation if missing.
- Deploy Alertmanager as new infra pointed at the monitored app's existing Prometheus — it is not part of the monitored app's own stack and must be stood up ourselves (see [DFD.md](./DFD.md) §5 A2).
- Bring up Postgres, run initial schema migration.

### Phase 1 — Observability & Detection (Hour 2–8)
- Deploy Loki, Prometheus, Alertmanager via Docker Compose (or in-cluster).
- Write alert rules (crash-loop, error rate, latency SLO breach).
- Configure Alertmanager webhook → Agent Intake API.
- Verify: manually trigger a failure in the monitored app and confirm a webhook reaches the API.

### Phase 2 — Agent Core (Hour 2–14, parallel with Phase 1)
- Define Incident state schema.
- Build LangGraph graph with stub nodes first, then wire real Bedrock calls per node.
- Implement prompts for Severity, RCA, and Planning with structured/delimited context (NFR-4).
- Implement plan-output validation against the allow-list.

### Phase 3 — Data Layer (Hour 4–10, parallel)
- Finalize schema: `incidents`, `audit_log`.
- Implement heuristic similarity scoring (title/service/severity overlap) for historical retrieval.
- Seed 3–5 synthetic historical incidents.

### Phase 4 — HITL API & UI (Hour 8–16, parallel)
- FastAPI endpoints: create/list/get incident, propose plan, approve/reject.
- Minimal UI: incident list + detail view with evidence, RCA, plan, Approve/Reject.

### Phase 5 — K8s Remediation (Hour 10–18, parallel)
- K8s adapter: `restart_pod`, `rollback_deployment`, `scale_deployment` against `kind`.
- Dry-run mode.
- Executor re-validates every action against the allow-list before running it.

### Phase 6 — Validation & Resolution Loop (Hour 16–20)
- Poll Prometheus + K8s health checks on a timer after execution.
- Compare to pre-incident baseline; resolve or escalate (never silently retry forever).

### Phase 7 — Audit Trail (Hour 12–20, parallel)
- Persist every LLM call, tool call, and decision to `audit_log`.

### Phase 8 — Integration Testing & Demo Prep (Hour 18–24+)
- Run UC-1/UC-2 (SRS §8) end-to-end at least once each.
- Polish approval UI for readability during judging.
- Record a fallback demo video in case live infra hiccups.

### Phase 9 — Phase 2 backlog (only if 48h+ available)
See SRS §10.C. Do not start until Phase 0–8 all work end-to-end.

---

## 6. Milestones & Definition of Done

| Milestone | Target Hour | Definition of Done |
|---|---|---|
| M0 — Environment Ready | 2 | `kind` cluster up; observability stack running; Bedrock smoke-test call succeeds; Postgres reachable |
| M1 — Alert Reaches Agent | 8 | Synthetic alert flows Alertmanager → webhook → Incident row created |
| M2 — Full AI Pipeline | 14 | Investigate→Severity→Historical→RCA→Plan produces a valid, allow-listed plan |
| M3 — First Real Remediation | 18 | Approved plan executes a real `kubectl rollout undo` in `kind`; validation confirms recovery |
| M4 — Demo-Ready | 22 | UC-1/UC-2 rehearsed end-to-end; audit trail viewable; fallback video recorded |
| M5 — Phase 2 (only if time remains) | 24–48+ | See SRS §10.C |

---

## 7. Cut-Scope Order (if behind schedule within the MVP itself)

Never cut: HITL approval, the audit trail, or allow-list enforcement. Cut in this order:
1. Anything from SRS §10.C (Phase 2) — it should not have been started yet.
2. `scale_deployment` action — keep only `restart_pod` + `rollback_deployment`.
3. UI polish — fall back to a bare HTML/Streamlit view.
4. Second demo scenario (UC-2) — rehearse UC-1 only.

---

## 8. Demo Script

1. **Scenario 1 (must work live)**: Deploy a bad config → CrashLoopBackOff → alert fires → Agent investigates, diagnoses, proposes rollback → approve in UI → live rollback in `kind` → validation confirms recovery → show audit trail.
2. **Scenario 2**: Latency/resource spike → scale-up remediation.
3. **Rejection path**: Show a plan being rejected and the incident escalating.

---

## 9. Environment/Credentials Checklist

- [ ] AWS account with Bedrock model access enabled (note region + model ID)
- [ ] `kind` or `minikube` installed; cluster created; `kubectl` context confirmed
- [ ] Docker + Docker Compose installed
- [ ] Monitored application: repo access confirmed; `/metrics` and log instrumentation confirmed or added in Phase 0

---

## 10. Development Conventions

- Tool execution stays in-process (`agent/` imports `tools/` directly); the Executor re-validates every action against `tools/allowlist.yaml` before running it.
- Put "do X before Y" operational instructions in the per-call user message, not only the system prompt.
- Each track runs its own fast local check (`pytest tools/ agent/` or `pytest api/`) before every Sync Point in `TASKS.md` §4.
- Small, frequent commits directly to `main` — no long-lived feature branches.

Prior research/decision history (OSS reference projects reviewed, options considered and declined) is kept in repo memory rather than in this doc — ask if you need it resurfaced.
