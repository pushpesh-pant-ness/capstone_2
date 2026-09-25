-- Incident + audit_log schema (SRS.md §6). Applied in order by files under
-- db/migrations/. This file is the canonical "current" schema for reference;
-- db/migrations/0001_init.sql is what actually runs against a fresh database.

CREATE TABLE IF NOT EXISTS incidents (
    incident_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_fingerprint    TEXT NOT NULL,
    title                TEXT NOT NULL,
    description          TEXT,
    status               TEXT NOT NULL DEFAULT 'detected',
    -- detected, investigating, diagnosed, pending_approval, approved, rejected,
    -- remediating, validating, resolved, escalated
    severity             TEXT,                    -- P1..P4
    service_name         TEXT,
    deployment_version   TEXT,
    detected_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at          TIMESTAMPTZ,
    evidence             JSONB,                   -- logs/metrics snapshot from Investigate
    baseline             JSONB,                    -- pre-incident metric baseline for validation
    root_cause_summary   TEXT,
    confidence_score     REAL,                     -- 0..1, from RCA node
    remediation_plan     JSONB,                    -- ordered list of allow-listed actions
    similar_incident_ids UUID[] DEFAULT '{}',
    approved_by          TEXT,
    approved_at          TIMESTAMPTZ,
    rejection_reason     TEXT,
    validation_result    JSONB                     -- {"recovered": bool, "evidence": {...}}
);

CREATE UNIQUE INDEX IF NOT EXISTS incidents_open_fingerprint_idx
    ON incidents (alert_fingerprint)
    WHERE status NOT IN ('resolved', 'escalated');

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id   UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    actor         TEXT NOT NULL,        -- agent | human | system
    action_type   TEXT NOT NULL,        -- llm_call | tool_call | approval_decision | state_transition
    payload       JSONB,                -- secrets redacted before insert
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_incident_idx ON audit_log (incident_id, created_at);
