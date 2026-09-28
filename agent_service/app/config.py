"""Central configuration, read from environment variables (set via the
k8s Deployment / Secret, see infra/agent-service.yaml)."""
import os

# --- Postgres (historical incident store) ---
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres.incident-agent.svc.cluster.local")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "incident_agent")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "incident_agent")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "incident_agent_dev_password")

# --- Observability backends ---
LOKI_URL = os.environ.get("LOKI_URL", "http://loki.observability.svc.cluster.local:3100")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus.otel-demo.svc.cluster.local:9090")
JAEGER_URL = os.environ.get("JAEGER_URL", "http://jaeger.otel-demo.svc.cluster.local:16686")

# --- Target application namespace (what we investigate/remediate) ---
APP_NAMESPACE = os.environ.get("APP_NAMESPACE", "otel-demo")

# --- AWS Bedrock ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_TEXT_MODEL_ID = os.environ.get("BEDROCK_TEXT_MODEL_ID", "amazon.nova-pro-v1:0")
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")

# --- GitHub remediation tool ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # "owner/repo"

# --- Fault registry (mounted from scripts/faults/registry.yaml via ConfigMap) ---
FAULT_REGISTRY_PATH = os.environ.get("FAULT_REGISTRY_PATH", "/app/fault-registry/registry.yaml")
