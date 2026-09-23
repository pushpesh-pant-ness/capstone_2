## Architecture
```
Application
(Python/FastAPI + Docker/Kubernetes)
        │
        ├──────── Logs ────────► Loki
        ├──────── Metrics ─────► Prometheus
        └──────── Traces ──────► OpenTelemetry
                                  │
                                  ▼
                     Incident Detection
                     (Alertmanager)
                                  │
                                  ▼
                       AI Incident Agent
                    (LangGraph + LangChain)
                                  │
             ┌────────────────────┼────────────────────┐
             ▼                    ▼                    ▼
       Diagnosis             Severity             Historical
       (LLM + Tools)         (Rules + LLM)        (PostgreSQL
                                                  + pgvector)
             │                    │                    │
             └────────────────────┼────────────────────┘
                                  ▼
                       Root Cause Analysis
                          (LLM + LangGraph)
                                  │
                                  ▼
                       Remediation Planning
                          (LLM + LangGraph)
                                  │
                                  ▼
                        Human Approval / HITL
                           (FastAPI + UI)
                                  │
                                  ▼
                       Automated Remediation
                    (Kubernetes / AWS / GitHub)
                                  │
                                  ▼
                    Post-Remediation Validation
                  (Prometheus + K8s Health Checks)
                                  │
                                  ▼
                       Incident Resolution
                           (FastAPI + DB)
                                  │
                                  ▼
                       Audit & Observability
                    (PostgreSQL + LangSmith/
                              LangFuse)
```

