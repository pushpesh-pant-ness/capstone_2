# Tears down everything this project created for local dev: the kind cluster
# (K8s remediation target) and the Docker Compose stack (Postgres + OTel
# Collector + observability).

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

docker compose -f "$root\infra\docker-compose.yaml" down -v
kind delete cluster --name incident-agent
