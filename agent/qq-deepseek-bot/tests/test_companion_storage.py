import sqlite3

import pytest

from qq_deepseek.storage.companion import CompanionStore, SCHEMA


def test_state_and_journal_isolation_retention(tmp_path):
    with sqlite3.connect(tmp_path / "companion.sqlite3") as db:
        db.executescript(SCHEMA)
        store = CompanionStore(db)
        store.save("private:1", {"mood": .2}, 1)
        assert store.load("private:1") == {"mood": .2}
        assert store.load("group:1") is None
        for i in range(70):
            store.append_journal(1, "dream", f"虚构梦境{i}", i)
        assert len(store.journal(1)) == 30
        assert store.journal(2) == []
        assert db.execute("SELECT COUNT(*) FROM agent_companion_journal").fetchone()[0] == 60
        with pytest.raises(ValueError):
            store.append_journal(1, "fact", "不可作为事实", 1)
