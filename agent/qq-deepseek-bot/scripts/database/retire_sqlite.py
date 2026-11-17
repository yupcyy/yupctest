#!/usr/bin/env python3
"""Remove production SQLite artifacts only after verified MySQL cutover."""
import argparse
from migrate_sqlite import sqlite_path
from common import require_confirmation

CONFIRM="RETIRE_SQLITE_RUNTIME"


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--confirm",required=True)
    parser.add_argument("--include-old-backups",action="store_true"); args=parser.parse_args()
    require_confirmation(args.confirm,CONFIRM)
    path=sqlite_path(); targets=[path,path.with_name(path.name+"-wal"),path.with_name(path.name+"-shm")]
    if args.include_old_backups: targets += list(path.parent.glob(path.stem+".backup_*"+path.suffix))
    for item in targets:
        if item.exists(): item.unlink(); print("deleted",item)


if __name__ == "__main__": main()
