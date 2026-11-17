#!/usr/bin/env python3
"""One-way, idempotent migration from the production SQLite file to agent_ MySQL tables."""
import argparse, os, sqlite3
from pathlib import Path
from dotenv import dotenv_values
from common import PROJECT_ROOT, connect, require_confirmation

CONFIRM="MIGRATE_SQLITE_TO_MYSQL"


def sqlite_path():
    env=dotenv_values(PROJECT_ROOT/".env"); path=Path(env.get("DATABASE_PATH") or "data/agent.sqlite3").expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT/path).resolve()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--confirm",required=True); args=parser.parse_args()
    require_confirmation(args.confirm,CONFIRM)
    path=sqlite_path()
    source=sqlite3.connect(f"{path.as_uri()}?mode=ro",uri=True)
    source.row_factory=sqlite3.Row; target=connect()
    tables={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def rows(table): return source.execute(f"SELECT * FROM {table}").fetchall() if table in tables else []
    counts={}
    try:
        with target.cursor() as c:
            for r in rows("conversation_messages"):
                c.execute("INSERT INTO agent_conversation_messages(source_sqlite_id,conversation_id,role,content,created_at) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE conversation_id=VALUES(conversation_id),role=VALUES(role),content=VALUES(content),created_at=VALUES(created_at)",
                          (r["id"],r["conversation_id"],r["role"],r["content"],r["created_at"]))
            counts["conversations"]=len(rows("conversation_messages"))
            for r in rows("user_memories"):
                c.execute("INSERT INTO agent_memories(source_sqlite_id,user_id,content,created_at) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),content=VALUES(content),created_at=VALUES(created_at)",
                          (r["id"],r["user_id"],r["content"],r["created_at"]))
            counts["memories"]=len(rows("user_memories"))
            for r in rows("owner_style_samples"):
                c.execute("INSERT INTO agent_owner_style_samples(source_sqlite_id,content,created_at) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE content=VALUES(content),created_at=VALUES(created_at)",
                          (r["id"],r["content"],r["created_at"]))
            counts["style"]=len(rows("owner_style_samples"))
            states={}
            for r in rows("user_affinity"): states.setdefault(int(r["user_id"]),{}).update(affinity=r["score"])
            for r in rows("interaction_guard"): states.setdefault(int(r["user_id"]),{}).update(
                blocked=r["blocked"],block_reason=r["reason"],rate_window_start=r["window_start"],rate_call_count=r["call_count"])
            for r in rows("sleep_sessions"): states.setdefault(int(r["user_id"]),{}).update(sleep_started_at=r["slept_at"])
            for r in sorted(rows("affinity_daily_gifts"),key=lambda x:x["gift_day"]):
                states.setdefault(int(r["user_id"]),{}).update(gift_day=r["gift_day"],gift_count=r["gift_count"])
            for uid,s in states.items():
                c.execute("INSERT INTO agent_user_state(user_id,affinity,blocked,block_reason,rate_window_start,rate_call_count,gift_day,gift_count,sleep_started_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE affinity=VALUES(affinity),blocked=VALUES(blocked),block_reason=VALUES(block_reason),rate_window_start=VALUES(rate_window_start),rate_call_count=VALUES(rate_call_count),gift_day=VALUES(gift_day),gift_count=VALUES(gift_count),sleep_started_at=VALUES(sleep_started_at)",
                          (uid,s.get("affinity",0),s.get("blocked",0),s.get("block_reason",""),s.get("rate_window_start",0),s.get("rate_call_count",0),s.get("gift_day"),s.get("gift_count",0),s.get("sleep_started_at")))
            counts["users"]=len(states)
            for r in rows("chat_preferences"):
                c.execute("INSERT INTO agent_chat_preferences(scope,target_id,name,value) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE value=VALUES(value)",(r["scope"],r["target_id"],r["name"],r["value"]))
            counts["preferences"]=len(rows("chat_preferences"))
            for r in rows("proactive_state"):
                raw=int(r["group_id"]); scope="private" if raw<0 else "group"; target_id=abs(raw)
                c.execute("INSERT INTO agent_runtime_state(state_key,last_proactive_at) VALUES (%s,%s) ON DUPLICATE KEY UPDATE last_proactive_at=VALUES(last_proactive_at)",(f"proactive:{scope}:{target_id}",r["last_sent"]))
            for r in rows("gomoku_games"):
                c.execute("INSERT INTO agent_runtime_state(state_key,game_board,game_updated_at) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE game_board=VALUES(game_board),game_updated_at=VALUES(game_updated_at)",(f'game:{r["conversation_id"]}',r["board"],r["updated_at"]))
            counts["runtime"]=len(rows("proactive_state"))+len(rows("gomoku_games"))
            for r in rows("llm_usage"):
                c.execute("INSERT INTO agent_llm_usage(request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens,cache_hit_tokens,cache_miss_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE model=VALUES(model),conversation_id=VALUES(conversation_id),operation=VALUES(operation),prompt_tokens=VALUES(prompt_tokens),completion_tokens=VALUES(completion_tokens),cache_hit_tokens=VALUES(cache_hit_tokens),cache_miss_tokens=VALUES(cache_miss_tokens)",tuple(r))
            counts["usage"]=len(rows("llm_usage"))
        target.commit()
    except BaseException: target.rollback(); raise
    finally: target.close(); source.close()
    print("Migration committed:",counts)
    print("Skipped deprecated group_observations by design.")


if __name__ == "__main__": main()
