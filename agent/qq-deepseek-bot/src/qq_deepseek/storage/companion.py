"""Fixed statements for approved companion schema; never creates tables on startup."""
import json


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_companion_state (
 scope TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_companion_journal (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('diary','dream')),
 content TEXT NOT NULL, created_at REAL NOT NULL
);
"""


class CompanionStore:
    def __init__(self, connection):
        self.connection = connection

    def save(self, scope, payload, now):
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 8192:
            raise ValueError("companion state too large")
        with self.connection:
            self.connection.execute(
                "INSERT INTO agent_companion_state(scope,payload,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(scope) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (scope, encoded, now))

    def load(self, scope):
        row = self.connection.execute(
            "SELECT payload FROM agent_companion_state WHERE scope=?", (scope,)).fetchone()
        return json.loads(row[0]) if row else None

    def append_journal(self, owner_id, kind, content, now):
        if kind not in {"diary", "dream"} or not content.strip() or len(content) > 2000:
            raise ValueError("invalid journal entry")
        with self.connection:
            self.connection.execute(
                "INSERT INTO agent_companion_journal(owner_id,kind,content,created_at) VALUES(?,?,?,?)",
                (owner_id, kind, content, now))
            self.connection.execute(
                "DELETE FROM agent_companion_journal WHERE owner_id=? AND id NOT IN "
                "(SELECT id FROM agent_companion_journal WHERE owner_id=? ORDER BY id DESC LIMIT 60)",
                (owner_id, owner_id))

    def journal(self, owner_id):
        return self.connection.execute(
            "SELECT kind,content,created_at FROM agent_companion_journal "
            "WHERE owner_id=? ORDER BY id DESC LIMIT 30", (owner_id,)).fetchall()
