#!/usr/bin/env python3
import argparse
from pathlib import Path

from common import connect, require_confirmation

CONFIRM = "CREATE_AGENT_SCHEMA"


def main():
    parser=argparse.ArgumentParser(description="Create only the agent_ prefixed MySQL tables")
    parser.add_argument("--confirm",required=True)
    args=parser.parse_args(); require_confirmation(args.confirm,CONFIRM)
    sql=Path(__file__).with_name("schema_mysql.sql").read_text(encoding="utf-8")
    statements=[item.strip() for item in sql.split(";") if item.strip()]
    db=connect()
    try:
        with db.cursor() as cursor:
            for statement in statements: cursor.execute(statement)
        db.commit(); print(f"Created/verified {len(statements)} agent tables.")
    except BaseException:
        db.rollback(); raise
    finally: db.close()


if __name__ == "__main__": main()
