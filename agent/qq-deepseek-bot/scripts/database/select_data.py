#!/usr/bin/env python3
"""Read-only, allowlisted inspection commands."""
import argparse, json
from common import connect, require_confirmation
CONFIRM="READ_AGENT_DATA"

QUERIES={
 "affinity":"SELECT user_id,affinity,blocked,block_reason,updated_at FROM agent_user_state ORDER BY affinity DESC,user_id LIMIT %s",
 "memories":"SELECT id,user_id,content,created_at FROM agent_memories ORDER BY id DESC LIMIT %s",
 "conversations":"SELECT id,conversation_id,role,content,created_at FROM agent_conversation_messages ORDER BY id DESC LIMIT %s",
 "usage":"SELECT request_id,created_at,model,conversation_id,operation,prompt_tokens,completion_tokens FROM agent_llm_usage ORDER BY created_at DESC LIMIT %s",
 "style":"SELECT id,content,created_at FROM agent_owner_style_samples ORDER BY id DESC LIMIT %s",
}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("dataset",choices=QUERIES)
    parser.add_argument("--limit",type=int,default=50); parser.add_argument("--confirm",required=True); args=parser.parse_args()
    require_confirmation(args.confirm,CONFIRM)
    if not 1 <= args.limit <= 500: raise SystemExit("limit must be 1..500")
    db=connect(autocommit=True)
    try:
        with db.cursor() as cursor:
            cursor.execute(QUERIES[args.dataset],(args.limit,)); names=[x[0] for x in cursor.description]
            print(json.dumps([dict(zip(names,row)) for row in cursor.fetchall()],ensure_ascii=False,default=str,indent=2))
    finally: db.close()


if __name__ == "__main__": main()
