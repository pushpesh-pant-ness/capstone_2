# Full local setup: kind cluster -> OTel Demo + Loki + Alertmanager -> Postgres+pgvector
# -> incident-agent service. Safe to re-run (uses helm upgrade --install and kubectl apply).
#
# Prereqs (see README.md): docker, kind, kubectl, helm, all already verified present.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== 1. kind cluster ==" -ForegroundColor Cyan
$existing = kind get clusters 2>$null
if ($existing -notcontains "incident-agent") {
    kind create cluster --config "$root\infra\kind-cluster.yaml"
} else {
    Write-Host "cluster 'incident-agent' already exists, skipping create"
}

Write-Host "== 2. namespaces ==" -ForegroundColor Cyan
foreach ($ns in @("otel-demo", "observability", "incident-agent")) {
    kubectl get namespace $ns 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { kubectl create namespace $ns }
}

Write-Host "== 3. helm repos ==" -ForegroundColor Cyan
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts 2>$null | Out-Null
helm repo add grafana https://grafana.github.io/helm-charts 2>$null | Out-Null
helm repo update | Out-Null

Write-Host "== 4. OTel Demo app ==" -ForegroundColor Cyan
# --force-conflicts: fault injection (agent_service/app/tools/k8s_tools.py) edits
# flagd-config's data.demo.flagd.json at runtime via the k8s python client (field
# manager "OpenAPI-Generator"), which otherwise conflicts with helm 4's default
# server-side apply on re-run. Helm reclaiming ownership here is intended: it
# resets flags to chart defaults on every setup.ps1 run.
helm upgrade --install otel-demo open-telemetry/opentelemetry-demo -n otel-demo -f "$root\app\otel-demo-values.yaml" --force-conflicts

Write-Host "== 5. Loki ==" -ForegroundColor Cyan
helm upgrade --install loki grafana/loki -n observability -f "$root\observability\loki-values.yaml"

Write-Host "== 6. Postgres + pgvector ==" -ForegroundColor Cyan
kubectl apply -f "$root\infra\postgres.yaml"

Write-Host "== 7. fault registry configmap ==" -ForegroundColor Cyan
kubectl create configmap fault-registry -n incident-agent `
    --from-file=registry.yaml="$root\scripts\faults\registry.yaml" `
    --dry-run=client -o yaml | kubectl apply -f -

Write-Host "== 8. secrets from .env ==" -ForegroundColor Cyan
$envFile = "$root\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$root\.env.example" $envFile
    Write-Host "Created $envFile from .env.example - it is currently empty (AI reasoning" -ForegroundColor Yellow
    Write-Host "and the GitHub tool will run in degraded/disabled mode until you fill it in)." -ForegroundColor Yellow
}
kubectl create secret generic incident-agent-secrets -n incident-agent `
    --from-env-file="$envFile" --dry-run=client -o yaml | kubectl apply -f -

Write-Host "== 9. build + load incident-agent image ==" -ForegroundColor Cyan
docker build -t incident-agent-service:local "$root\agent_service"
kind load docker-image incident-agent-service:local --name incident-agent --nodes incident-agent-worker,incident-agent-worker2

Write-Host "== 10. deploy incident-agent service ==" -ForegroundColor Cyan
kubectl apply -f "$root\infra\agent-service.yaml"
kubectl rollout restart deployment/incident-agent -n incident-agent 2>$null | Out-Null

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Demo UI / API:      http://localhost:8000"
Write-Host "Shop frontend:      http://localhost:8080"
Write-Host "Grafana:            http://localhost:8080/grafana/ (admin/admin)"
Write-Host "Feature Flags UI:   http://localhost:8080/feature/"
Write-Host "Jaeger UI:          http://localhost:8080/jaeger/ui/"
Write-Host ""
if ((Get-Content $envFile -Raw) -match "AWS_ACCESS_KEY_ID=\s*(\r?\n|$)") {
    Write-Host "NOTE: $envFile has no AWS credentials yet - edit it, then run:" -ForegroundColor Yellow
    Write-Host "  ./scripts/update-secrets.ps1" -ForegroundColor Yellow
}
