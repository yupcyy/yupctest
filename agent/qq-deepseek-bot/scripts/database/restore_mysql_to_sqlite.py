#!/usr/bin/env python3
"""Build a local SQLite recovery copy from the seven fixed agent_ MySQL tables."""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from common import PROJECT_ROOT, connect, require_confirmation

CONFIRM = "RESTORE_MYSQL_TO_SQLITE"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore  # noqa: E402
from qq_deepseek.storage.usage import SQLiteUsageStore  # noqa: E402


def configured_path() -> Path:
    env = dotenv_values(PROJECT_ROOT / ".env")
    value = Path(env.get("DATABASE_PATH") or "data/agent.sqlite3").expanduser()
    return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    require_confirmation(args.confirm, CONFIRM)
    target = configured_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not args.replace:
        raise SystemExit(f"Refusing to overwrite existing SQLite file: {target}; pass --replace explicitly")

    fd, raw_temp = tempfile.mkstemp(prefix="agent-restore-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    temp = Path(raw_temp)
    temp.unlink()
    mysql = None
    sqlite = None
    try:
        # Create exactly the same schema used by the running application.
        SQLiteMemoryStore(temp).close()
        SQLiteUsageStore(temp).close()
        sqlite = sqlite3.connect(temp)
        mysql = connect()
        counts = {}
        with mysql.cursor() as cursor:
            cursor.execute("SELECT id,source_sqlite_id,conversation_id,role,content,created_at FROM agent_conversation_messages ORDER BY id")
            rows = cursor.fetchall()
            sqlite.executemany("INSERT OR REPLACE INTO conversation_messages(id,conversation_id,role,content,created_at) VALUES (?,?,?,?,?)",
                               [(source_id or row_id, cid, role, content, created) for row_id, source_id, cid, role, content, created in rows])
            counts["conversations"] = len(rows)

            cursor.execute("SELECT id,source_sqlite_id,user_id,content,created_at FROM agent_memories ORDER BY id")
            rows = cursor.fetchall()
            sqlite.executemany("INSERT OR REPLACE INTO user_memories(id,user_id,content,created_at) VALUES (?,?,?,?)",
                               [(source_id or row_id, uid, content, created) for row_id, source_id, uid, content, created in rows])
            counts["memories"] = len(rows)

            cursor.execute("SELECT id,source_sqlite_id,content,created_at FROM agent_owner_style_samples ORDER BY id")
            rows = cursor.fetchall()
            sqlite.executemany("INSERT OR REPLACE INTO owner_style_samples(id,content,created_at) VALUES (?,?,?)",
                               [(source_id or row_id, content, created) for row_id, source_id, content, created in rows])
            counts["style"] = len(rows)

            cursor.execute("SELECT user_id,affinity,blocked,block_reason,rate_window_start,rate_call_count,gift_day,gift_count,sleep_started_at FROM agent_user_state")
            rows = cursor.fetchall()
            for uid, affinity, blocked, reason, window, calls, gift_day, gifts, slept_at in rows:
                sqlite.execute("INSERT OR REPLACE INTO user_affinity(user_id,score) VALUES (?,?)", (uid, affinity))
                sqlite.execute("INSERT OR REPLACE INTO interaction_guard(user_id,blocked,window_start,call_count,reason) VALUES (?,?,?,?,?)",
                               (uid, blocked, window, calls, reason))
                if gift_day is not None:
                    sqlite.execute("INSERT OR REPLACE INTO affinity_daily_gifts(user_id,gift_day,gift_count) VALUES (?,?,?)",
                                   (uid, str(gift_day), gifts))
                if slept_at is not None:
                    sqlite.execute("INSERT OR REPLACE INTO sleep_sessions(user_id,slept_at) VALUES (?,?)", (uid, slept_at))
            counts["users"] = len(rows)

            cursor.execute("SELECT scope,target_id,name,value FROM agent_chat_preferences")
            rows = cursor.fetchall()
            sqlite.executemany("INSERT OR REPLACE INTO chat_preferences(scope,target_id,name,value) VALUES (?,?,?,?)", rows)
            counts["preferences"] = len(rows)

            cursor.execute("SELECT state_key,last_proactive_at,game_board,game_updated_at FROM agent_runtime_state")
            rows = cursor.fetchall()
            for key, last_sent, board, updated in rows:
                if key.startswith("proactive:group:"):
                    sqlite.execute("INSERT OR REPLACE INTO proactive_state(group_id,last_sent) VALUES (?,?)",
                                   (int(key.rsplit(":", 1)[1]), last_sent))
                elif key.startswith("proactive:private:"):
                    sqlite.execute("INSERT OR REPLACE INTO proactive_state(group_id,last_sent) VALUES (?,?)",
                                   (-int(key.rsplit(":", 1)[1]), last_sent))
                elif key.startswith("game:") and board is not None:
                    payload = board if isinstance(board, str) else json.dumps(board, ensure_ascii=False)
                    sqlite.execute("INSERT OR REPLACE INTO gomoku_games(conversation_id,board,updated_at) VALUES (?,?,?)",
                                   (key[5:], payload, updated))
            counts["runtime"] = len(rows)

            cursor.execute("SELECT request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens,cache_hit_tokens,cache_miss_tokens FROM agent_llm_usage")
            rows = cursor.fetchall()
            sqlite.executemany("INSERT OR REPLACE INTO llm_usage(request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens,cache_hit_tokens,cache_miss_tokens) VALUES (?,?,?,?,?,?,?,?,?)", rows)
            counts["usage"] = len(rows)

        sqlite.commit()
        result = sqlite.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {result}")
        sqlite.close(); sqlite = None
        mysql.close(); mysql = None
        os.replace(temp, target)
        target.chmod(0o600)
        print("Restore committed:", counts)
        print("SQLite integrity_check: ok")
    finally:
        if sqlite is not None:
            sqlite.close()
        if mysql is not None:
            mysql.close()
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
