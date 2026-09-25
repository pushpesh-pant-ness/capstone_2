-- Migration 0001: initial schema (incidents, audit_log). Mirrors db/schema.sql.
-- Plain numbered SQL files, run in order (BUILD_PLAN.md §2.2) — no migration
-- framework, this is a hackathon.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS incidents (
    incident_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_fingerprint     TEXT NOT NULL,
    title                 TEXT NOT NULL,
    description           TEXT,
    status                TEXT NOT NULL DEFAULT 'detected',
    severity              TEXT,
    service_name          TEXT,
    deployment_version    TEXT,
    detected_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at           TIMESTAMPTZ,
    evidence              JSONB,
    baseline              JSONB,
    root_cause_summary    TEXT,
    confidence_score      REAL,
    remediation_plan      JSONB,
    similar_incident_ids  UUID[] DEFAULT '{}',
    approved_by           TEXT,
    approved_at           TIMESTAMPTZ,
    rejection_reason      TEXT,
    validation_result     JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS incidents_open_fingerprint_idx
    ON incidents (alert_fingerprint)
    WHERE status NOT IN ('resolved', 'escalated');

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id   UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    actor         TEXT NOT NULL,
    action_type   TEXT NOT NULL,
    payload       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_incident_idx ON audit_log (incident_id, created_at);
