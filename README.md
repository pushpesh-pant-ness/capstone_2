# Project Plan & Technical Blueprint: Autonomous Post-Deployment Incident & Remediation Agent

## 1. Executive Summary & Plain-English Explanation

### What is this project?
When new software is deployed into production, unexpected problems can occur—for instance, database connections might time out, memory usage might spike, or microservices might return `500 Internal Server Error` responses. Traditionally, human Site Reliability Engineers (SREs) and DevOps engineers receive alerts (e.g., via PagerDuty), manually search through logs, trace where the error occurred, inspect historical incident tickets, run scripts to fix the issue, and verify that system health has returned to normal.

This project creates an **Autonomous Post-Deployment Incident & Remediation Agent**—an intelligent AI assistant that automates the entire incident lifecycle:
1. **Detects** anomalous application behavior from telemetry (logs, metrics, traces).
2. **Diagnoses** the core issue using Large Language Models (LLMs) trained to correlate errors with system state.
3. **Searches** past incident knowledge bases to check how similar issues were resolved previously.
4. **Drafts** a clear fix plan (e.g., rolling back a deployment, scaling up Kubernetes replicas, or clearing a saturated cache).
5. **Requests Human Approval** via interactive platforms like Slack, Teams, or a web dashboard before taking high-risk actions (**Human-in-the-Loop**).
6. **Executes** the remediation automatically upon receiving approval.
7. **Validates** application recovery through automated health checks.
8. **Audits** every action, reasoning step, and decision path for safety and compliance.

---

## 2. Core Operational Workflow

The agent uses **LangGraph** to model the incident lifecycle as a deterministic, stateful state machine.

```
+------------------+     +--------------------+     +-----------------------+
|  1. Monitoring   | --> | 2. Incident Trigger| --> |  3. Telemetry Fetch   |
| (Prometheus/Loki)|     | (Alertmanager/Sentry)    | (Logs, Metrics, Traces)|
+------------------+     +--------------------+     +-----------------------+
                                                                |
                                                                v
+------------------+     +--------------------+     +-----------------------+
| 6. Plan Fix &    | <-- | 5. RAG Retrieval   | <-- | 4. Root Cause Analysis|
|    Set Severity  |     | (VectorDB / Vector Search)|  (LLM Reasoning)     |
+------------------+     +--------------------+     +-----------------------+
         |
         v
+-----------------------+     +-----------------------+     +-----------------------+
| 7. Human Approval Gate| --> | 8. Auto Remediation   | --> | 9. Post-Fix Validation|
| (Slack/Dashboard HITL)|     | (Kubernetes / AWS API)|     | (Synthetic Checks)    |
+-----------------------+     +-----------------------+     +-----------------------+
                                                                        |
                                                                        v
                                                            +-----------------------+
                                                            | 10. Audit & Close     |
                                                            | (LangSmith / Jira)    |
                                                            +-----------------------+
```

| Step | Component | Description |
| :--- | :--- | :--- |
| **1. Monitor & Trigger** | Prometheus & Grafana | Continuous monitoring of metric thresholds ($CPU > 90\%$, 5xx error rate $> 5\%$). Alerts trigger a webhook to the FastAPI backend. |
| **2. Telemetry Ingestion** | Grafana Loki & Tempo | The agent queries logs around the alert timestamp and extracts distributed traces to isolate failing services. |
| **3. Root Cause Analysis** | LangChain / LLM Node | Correlates logs, metrics, and trace IDs to pinpoint the primary failure mechanism. |
| **4. Historical Context** | Vector Database (e.g., Qdrant / Pinecone) | Performs semantic search against past incident post-mortems using RAG (Retrieval-Augmented Generation). |
| **5. Action Planning** | LangGraph State Node | Classifies incident severity (**SEV-1** to **SEV-4**) and generates an executable remediation plan (e.g., `kubectl rollout undo deployment/api-service`). |
| **6. Human Approval (HITL)** | Slack App / Webhook Interrupt | Uses LangGraph's native `interrupt` state to halt execution until a designated engineer clicks **Approve** or **Reject**. |
| **7. Execution & Validation** | Kubernetes API / Terraform | Runs the approved fix and immediately monitors post-remediation health endpoints for 5 minutes. |
| **8. Observability & Audit** | LangSmith / LangFuse | Captures all agent prompts, execution traces, tool calls, and human approvals in an immutable log. |

---

## 3. End-to-End System Architecture

```
                                +-------------------------------------------+
                                |             Target Kubernetes             |
                                |                Cluster                    |
                                |                                           |
                                |  +---------------+     +---------------+  |
                                |  | Microservice A|     | Microservice B|  |
                                |  +-------+-------+     +-------+-------+  |
                                +----------|---------------------|----------+
                                           | Telemetry           |
                                           v                     v
+-----------------------------------------------------------------------------------+
|                            Observability Layer                                    |
|                                                                                   |
|   +------------------------+   +-------------------+   +----------------------+   |
|   |   Prometheus (Metrics) |   |   Loki (Logs)     |   |   Tempo (Traces)     |   |
|   +-----------+------------+   +---------+---------+   +----------+-----------+   |
+---------------|--------------------------|------------------------|---------------+
                +--------------------------+------------------------+
                                           | Alert Webhook
                                           v
+-----------------------------------------------------------------------------------+
|                        Autonomous Agent Core (FastAPI App)                         |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   | LangGraph Workflow Engine                                                 |   |
|   |                                                                           |   |
|   |  +--------------------+   +--------------------+   +-------------------+  |   |
|   |  | Ingestion & Triage |   | Root Cause & RAG   |   | Action Generator  |  |   |
|   |  +---------+----------+   +---------+----------+   +---------+---------+  |   |
|   |            |                        |                        |            |   |
|   +------------|------------------------|------------------------|------------+   |
|                |                        |                        |                |
|                v                        v                        v                |
|      +-------------------+    +--------------------+   +-------------------+      |
|      | Vector Search DB  |    |  LangSmith / Fuse  |   | Kubernetes Agent  |      |
|      | (Historical Inc.) |    |  (Tracing & Audit) |   | Tool / AWS SDK    |      |
|      +-------------------+    +--------------------+   +---------+---------+      |
+------------------------------------------------------------------|----------------+
                                                                   |
                                                                   v
                                                        +---------------------+
                                                        | Human Approval UI   |
                                                        | (Slack / Web UI)    |
                                                        +---------------------+
```

---

## 4. Required Deliverables & Implementation Roadmap

To fulfill all requirements of the capstone project, implementation should follow this step-by-step deliverable structure:

### Phase 1: Infrastructure & Observability Setup (Deliverables 5, 7)
* **Infrastructure-as-Code (Terraform):** Provision an AWS EKS cluster, Amazon ElastiCache (Redis), and PostgreSQL DB for agent persistence.
* **Observability Stack:** Deploy Prometheus, Grafana, Loki, and Tempo inside Kubernetes using Helm charts.
* **Monitoring Dashboards:** Build a Grafana dashboard showing key service metrics alongside agent remediation markers.

### Phase 2: Core Agent & Tooling Layer (Deliverables 1, 2, 3, 4)
* **FastAPI Service:** Expose endpoints for receiving alerts (`/api/v1/alerts`), human feedback (`/api/v1/approval`), and querying status (`/api/v1/incidents/{id}`).
* **Agent Tool Suite:**
  * `query_prometheus_metrics(query, start_time, end_time)`
  * `fetch_loki_logs(service_name, trace_id, limit)`
  * `search_historical_incidents(embedding_vector)`
  * `execute_k8s_action(action_type, target_resource)`
* **RAG Engine:** Store historical post-mortems in vector format for similarity retrieval during triage.

### Phase 3: Human-in-the-Loop & CI/CD Pipeline (Deliverables 6, 8, 9)
* **Slack / Web Approval Integration:** Implement interactive cards with **Approve**, **Modify**, and **Reject** buttons to control action execution safely.
* **CI/CD Pipeline (GitHub Actions):** Automate linting, unit tests, container builds (Dockerized FastAPI backend), and helm deployments to EKS.
* **LLM Tracing & Auditing:** Integrate **LangSmith** or **LangFuse** to track execution latency, token consumption, and agent decision trees.

### Phase 4: Validation, Security & Documentation (Deliverables 10, 11, 12, 13)
* **Security & Governance:** Apply Least-Privilege IAM roles, Kubernetes RBAC, API key rotation, and secret encryption via AWS Secrets Manager.
* **Failure Injection Testing (Chaos Engineering):** Test the agent against simulated scenarios:
  * Memory Leak leading to `OOMKilled` pods (Fix: Scale up or restart pod).
  * Faulty software release returning `500` errors (Fix: Automated Helm rollback).
  * Database connection exhaustion (Fix: Restart connection pool / scale read-replicas).
* **Final Deliverables Documentation:** Complete the System Architecture Document, Deployment Guide, Evaluation Report, and Video Demonstration.

---

## 5. Security & Risk Governance Architecture

Deploying autonomous agents into production environments presents significant operational risks. The system enforces strict security guardrails:

```
+------------------------------------------------------------------------------+
|                         Security & Risk Architecture                         |
+------------------------------------------------------------------------------+
|                                                                              |
|  [ Least-Privilege Access ]                                                  |
|  * K8s RBAC strictly scopes the Agent service account to allowed             |
|    namespaces and read/write verbs.                                          |
|                                                                              |
|  [ Action Risk Matrix ]                                                      |
|  * Low-Risk (Read Logs/Metrics) ----------> Executed Autonomously            |
|  * Medium-Risk (Restart Pod / Scale) -------> Requires Human Approval        |
|  * High-Risk (Database Migration Rollback) -> Requires Multi-Approver Escalation |
|                                                                              |
|  [ Safety Air-Gapping & Circuit Breakers ]                                   |
|  * Max Retries: Limit execution attempts per incident to prevent loops.       |
|  * Rate Limiting: Cap maximum auto-remediations per hour system-wide.        |
|                                                                              |
|  [ Immutable Audit Trail ]                                                   |
|  * Every agent prompt, context window, vector match, human action, and       |
|    terminal payload is logged immutably in LangSmith/LangFuse & Postgres.    |
|                                                                              |
+------------------------------------------------------------------------------+
```
