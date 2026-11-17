#!/usr/bin/env python3
import argparse
from common import connect, require_confirmation

CONFIRM="DELETE_AGENT_MEMORY"


def main():
    parser=argparse.ArgumentParser(description="Delete only agent memory/conversation tables")
    parser.add_argument("--kind",choices=("memories","conversations","owner-style","all"),required=True)
    parser.add_argument("--user-id",type=int); parser.add_argument("--all-users",action="store_true")
    parser.add_argument("--confirm",required=True); args=parser.parse_args()
    require_confirmation(args.confirm,CONFIRM)
    if (args.user_id is None) == (not args.all_users):
        raise SystemExit("Choose exactly one of --user-id or --all-users")
    targets=[]
    if args.kind in {"memories","all"}:
        targets.append(("agent_memories","" if args.all_users else " WHERE user_id=%s"))
    if args.kind in {"conversations","all"}:
        targets.append(("agent_conversation_messages","" if args.all_users else " WHERE conversation_id=%s"))
    if args.kind in {"owner-style","all"}:
        if not args.all_users: raise SystemExit("owner-style deletion requires --all-users")
        targets.append(("agent_owner_style_samples",""))
    db=connect()
    try:
        with db.cursor() as cursor:
            for table,where in targets:
                value=(f"private:{args.user_id}",) if table.endswith("messages") and where else ((args.user_id,) if where else ())
                cursor.execute("DELETE FROM "+table+where,value); print(table,"deleted",cursor.rowcount)
        db.commit()
    except BaseException: db.rollback(); raise
    finally: db.close()


if __name__ == "__main__": main()
