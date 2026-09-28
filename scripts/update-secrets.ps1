# Re-reads .env and pushes it into the incident-agent-secrets Kubernetes Secret,
# then restarts the deployment so it picks up the change. Run this any time you
# edit .env after the initial ./scripts/setup.ps1 run.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = "$root\.env"

if (-not (Test-Path $envFile)) {
    throw "$envFile not found - copy .env.example to .env first."
}

kubectl create secret generic incident-agent-secrets -n incident-agent `
    --from-env-file="$envFile" --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/incident-agent -n incident-agent

Write-Host "Secrets updated, deployment restarting. Check readiness with:" -ForegroundColor Green
Write-Host "  kubectl get pods -n incident-agent -w"
