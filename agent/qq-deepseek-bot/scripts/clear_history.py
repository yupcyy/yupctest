
"""Cloud-side maintenance: clear all QQ conversation data."""

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


CONFIRMATION = "DELETE_ALL_HISTORY"


def main():
    parser = argparse.ArgumentParser(
        description="Delete all conversation history and memories."
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Must equal {CONFIRMATION}",
    )
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        parser.error("Invalid confirmation phrase")

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    raw_path = os.getenv(
        "DATABASE_PATH",
        "data/agent.sqlite3",
    )

    db_path = Path(raw_path).expanduser()

    if not db_path.is_absolute():
        db_path = project_root / db_path

    db_path = db_path.resolve()

    if not db_path.is_file():
        raise SystemExit(
            f"Database does not exist: {db_path}"
        )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    backup_path = db_path.with_name(
        f"{db_path.stem}.backup_{timestamp}{db_path.suffix}"
    )

    db = sqlite3.connect(
        f"{db_path.as_uri()}?mode=rw",
        uri=True,
        timeout=10,
    )

    try:
        db.execute("PRAGMA busy_timeout=10000")

        existing_tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        required_tables = {
            "conversation_messages",
            "user_memories",
        }

        if not required_tables.issubset(existing_tables):
            missing = required_tables - existing_tables
            raise RuntimeError(
                f"Missing tables: {sorted(missing)}"
            )

        counts = {
            table: db.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in required_tables
        }
        counts["group_observations"] = (
            db.execute("SELECT COUNT(*) FROM group_observations").fetchone()[0]
            if "group_observations" in existing_tables else 0
        )
        counts["owner_style_samples"] = (
            db.execute("SELECT COUNT(*) FROM owner_style_samples").fetchone()[0]
            if "owner_style_samples" in existing_tables else 0
        )
        counts["sleep_sessions"] = (
            db.execute("SELECT COUNT(*) FROM sleep_sessions").fetchone()[0]
            if "sleep_sessions" in existing_tables else 0
        )

        # SQLite online backup includes committed WAL data.
        with sqlite3.connect(backup_path) as backup:
            db.backup(backup)

        os.chmod(backup_path, 0o600)

        # One atomic transaction.
        with db:
            db.execute(
                "DELETE FROM conversation_messages"
            )
            db.execute(
                "DELETE FROM user_memories"
            )
            if "group_observations" in existing_tables:
                db.execute("DELETE FROM group_observations")
            if "owner_style_samples" in existing_tables:
                db.execute("DELETE FROM owner_style_samples")
            if "sleep_sessions" in existing_tables:
                db.execute("DELETE FROM sleep_sessions")

        print("History cleared successfully.")
        print(f"Conversations removed: {counts['conversation_messages']}")
        print(f"Long-term memories removed: {counts['user_memories']}")
        print(f"Group observations removed: {counts['group_observations']}")
        print(f"Owner style samples removed: {counts['owner_style_samples']}")
        print(f"Active sleep timers removed: {counts['sleep_sessions']}")
        print(f"Backup: {backup_path}")
        print("Token usage records preserved.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
