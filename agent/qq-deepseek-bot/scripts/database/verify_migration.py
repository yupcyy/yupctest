#!/usr/bin/env python3
"""Read-only row-count comparison; does not inspect non-agent MySQL tables."""
import sqlite3
from migrate_sqlite import sqlite_path
import argparse
from common import connect, require_confirmation
CONFIRM="VERIFY_AGENT_MIGRATION"

MAPPING={"conversation_messages":"agent_conversation_messages","user_memories":"agent_memories",
         "owner_style_samples":"agent_owner_style_samples","llm_usage":"agent_llm_usage"}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--confirm",required=True); args=parser.parse_args()
    require_confirmation(args.confirm,CONFIRM)
    source=sqlite3.connect(f"{sqlite_path().as_uri()}?mode=ro",uri=True); target=connect(autocommit=True)
    try:
        existing={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with target.cursor() as c:
            ok=True
            for old,new in MAPPING.items():
                old_count=source.execute(f"SELECT COUNT(*) FROM {old}").fetchone()[0] if old in existing else 0
                c.execute(f"SELECT COUNT(*) FROM {new}"); new_count=c.fetchone()[0]
                passed=new_count>=old_count; ok &= passed
                print(old,"=>",new,old_count,new_count,"OK" if passed else "MISMATCH")
            source_users=set()
            for table in ("user_affinity","interaction_guard","sleep_sessions","affinity_daily_gifts"):
                if table in existing:
                    source_users.update(int(r[0]) for r in source.execute(f"SELECT DISTINCT user_id FROM {table}"))
            c.execute("SELECT COUNT(*) FROM agent_user_state"); user_count=c.fetchone()[0]
            passed=user_count>=len(source_users);ok &= passed
            print("combined user state => agent_user_state",len(source_users),user_count,"OK" if passed else "MISMATCH")
            preference_count=source.execute("SELECT COUNT(*) FROM chat_preferences").fetchone()[0] if "chat_preferences" in existing else 0
            c.execute("SELECT COUNT(*) FROM agent_chat_preferences"); remote_preferences=c.fetchone()[0]
            passed=remote_preferences>=preference_count;ok &= passed
            print("chat_preferences => agent_chat_preferences",preference_count,remote_preferences,"OK" if passed else "MISMATCH")
            runtime_count=sum(source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("proactive_state","gomoku_games") if table in existing)
            c.execute("SELECT COUNT(*) FROM agent_runtime_state"); remote_runtime=c.fetchone()[0]
            passed=remote_runtime>=runtime_count;ok &= passed
            print("runtime state => agent_runtime_state",runtime_count,remote_runtime,"OK" if passed else "MISMATCH")
        raise SystemExit(0 if ok else 1)
    finally: source.close(); target.close()


if __name__ == "__main__": main()
