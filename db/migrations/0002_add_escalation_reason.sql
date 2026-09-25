-- Migration 0002: add escalation_reason (docs/AGENTS.md §3 — agent-driven
-- escalation from rca/guardrail, distinct from the existing human-driven
-- rejection_reason column).

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS escalation_reason TEXT;
