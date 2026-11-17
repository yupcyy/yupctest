-- Approval required before execution. Additive SQLite schema only.
CREATE TABLE IF NOT EXISTS agent_companion_state (
    scope TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_companion_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('diary', 'dream')),
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
