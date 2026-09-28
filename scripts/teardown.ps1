# Tears down everything this project created. Deletes the entire kind cluster
# (fastest, cleanest option - nothing here is meant to persist outside a demo run).

$ErrorActionPreference = "Continue"
kind delete cluster --name incident-agent
