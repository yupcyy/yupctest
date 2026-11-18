-- DRAFT ONLY: requires separate database approval before application.
-- SQLite migration; transactional application required. No existing tables changed.
CREATE TABLE IF NOT EXISTS agent_memory_candidates (
    candidate_id TEXT PRIMARY KEY,
    subject_user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('private_confirmation','verified_event')),
    source_event_ids TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence BETWEEN 0.9 AND 1.0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','deleted')),
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL CHECK(expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS agent_memory_candidates_subject ON agent_memory_candidates(subject_user_id, status);
CREATE TABLE IF NOT EXISTS agent_memory_candidate_audit (
    audit_id INTEGER PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    subject_user_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('approve','reject','delete')),
    created_at REAL NOT NULL
);
-- Rollback (separate destructive approval required; loses candidate/audit records):
-- DROP TABLE agent_memory_candidate_audit;
-- DROP TABLE agent_memory_candidates;
