"""Shared MySQL connection helpers. No arbitrary table or SQL input."""
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_TABLES = frozenset({
    "agent_conversation_messages", "agent_memories", "agent_owner_style_samples",
    "agent_user_state", "agent_chat_preferences", "agent_runtime_state", "agent_llm_usage",
})


def config():
    env = dotenv_values(PROJECT_ROOT / ".env")
    raw = (env.get("DATABASE_URL") or "").strip()
    if raw.startswith("jdbc:"): raw = raw[5:]
    parsed = urlsplit(raw)
    if parsed.scheme not in {"mysql", "mariadb"}:
        raise RuntimeError("DATABASE_URL must be a MySQL/MariaDB URL")
    database = parsed.path.strip("/")
    if not parsed.hostname or not database:
        raise RuntimeError("DATABASE_URL must include host and database name")
    return {
        "host": parsed.hostname, "port": parsed.port or 3306, "database": database,
        "user": env.get("DATABASE_USERNAME") or parsed.username,
        "password": env.get("DATABASE_PASSWORD") or parsed.password,
        "charset": "utf8mb4", "autocommit": False,
        "connect_timeout": 10, "read_timeout": 20, "write_timeout": 20,
    }


def connect(*, autocommit=False):
    import pymysql
    values = config(); values["autocommit"] = autocommit
    if not values["user"] or values["password"] is None:
        raise RuntimeError("DATABASE_USERNAME and DATABASE_PASSWORD are required")
    return pymysql.connect(**values)


def require_confirmation(actual, expected):
    if actual != expected:
        raise SystemExit(f"Refusing mutation: --confirm must equal {expected}")
