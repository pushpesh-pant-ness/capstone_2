# Local dev setup (BUILD_PLAN.md Phase 0): kind cluster (K8s remediation target)
# + Postgres + observability stack via Docker Compose + apply the DB migration.
# The Agent API itself runs as a local process (SRS.md §2.4), not a container
# here — start it yourself once this completes (see README.md).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== 1. kind cluster (K8s remediation target) ==" -ForegroundColor Cyan
$existing = kind get clusters 2>$null
if ($existing -notcontains "incident-agent") {
    kind create cluster --config "$root\infra\kind-cluster.yaml"
} else {
    Write-Host "cluster 'incident-agent' already exists, skipping create"
}

Write-Host "== 2. Postgres + observability stack (Docker Compose) ==" -ForegroundColor Cyan
docker compose -f "$root\infra\docker-compose.yaml" up -d
docker compose -f "$root\infra\docker-compose.observability.yaml" up -d

Write-Host "== 3. .env ==" -ForegroundColor Cyan
$envFile = "$root\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$root\.env.example" $envFile
    Write-Host "Created $envFile from .env.example - fill in AWS Bedrock credentials." -ForegroundColor Yellow
}

Write-Host "== 4. apply DB migration ==" -ForegroundColor Cyan
$pgContainer = (docker compose -f "$root\infra\docker-compose.yaml" ps -q postgres)
for ($i = 0; $i -lt 10; $i++) {
    docker exec $pgContainer pg_isready -U incident_agent | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 3
}
Get-Content "$root\db\migrations\0001_init.sql" | docker exec -i $pgContainer psql -U incident_agent -d incident_agent

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start the Agent API:   uvicorn api.main:app --reload --port 8000"
Write-Host "Seed historical data:  python scripts/seed_historical_incidents.py"
Write-Host "Rehearse the pipeline: python scripts/run_agent_cli.py --alert-name HighHttpErrorRate --service payment"
