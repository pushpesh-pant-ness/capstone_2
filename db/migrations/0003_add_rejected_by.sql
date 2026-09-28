-- Migration 0003: add rejected_by, distinct from approved_by. Previously
-- db/repository.py record_rejection wrote the rejecter's name into
-- approved_by, which made a rejected incident's audit trail read as if a
-- human had approved it.

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS rejected_by TEXT;
