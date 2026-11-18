from pathlib import Path
import sqlite3
import pytest


def test_candidate_schema_in_temporary_database(tmp_path):
    migration = Path(__file__).resolve().parents[3] / 'plan/migrations/companion_candidates.sql'
    with sqlite3.connect(tmp_path / 'migration.sqlite3') as db:
        db.executescript(migration.read_text())
        db.executescript(migration.read_text())
        statement = 'INSERT INTO agent_memory_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        db.execute(statement, ('1', 10, 'tea', 'private_confirmation', '["event1"]', .99, 'pending', 1, 100))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(statement, ('2', 10, 'dream', 'dream', '[]', .99, 'pending', 1, 100))
