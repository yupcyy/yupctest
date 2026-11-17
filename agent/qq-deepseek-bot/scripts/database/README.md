# Agent MySQL migration commands

These scripts only reference the seven `agent_` tables declared in `schema_mysql.sql`. They never accept arbitrary SQL or table names. Every database connection, including read-only inspection, requires an explicit confirmation phrase.

Prepared sequence (do not run without the owner's approval):

```bash
uv run python scripts/database/create_schema.py --confirm CREATE_AGENT_SCHEMA
uv run python scripts/database/migrate_sqlite.py --confirm MIGRATE_SQLITE_TO_MYSQL
uv run python scripts/database/verify_migration.py --confirm VERIFY_AGENT_MIGRATION
```

After verification, set `DATABASE_TYPE=mysql`, restart and smoke-test. Only then retire the SQLite runtime files:

```bash
uv run python scripts/database/retire_sqlite.py --confirm RETIRE_SQLITE_RUNTIME
```

Add `--include-old-backups` only if the owner separately approves deleting historical SQLite backups.

Allowlisted read commands:

```bash
uv run python scripts/database/select_data.py affinity --limit 50 --confirm READ_AGENT_DATA
uv run python scripts/database/select_data.py memories --limit 50 --confirm READ_AGENT_DATA
```

Memory deletion examples:

```bash
uv run python scripts/database/delete_memories.py --kind all --user-id 123456 --confirm DELETE_AGENT_MEMORY
uv run python scripts/database/delete_memories.py --kind all --all-users --confirm DELETE_AGENT_MEMORY
```

For database-level isolation, the MySQL account in `.env` should have CRUD permissions only on the seven `agent_` tables after schema creation. The application code itself contains fixed, parameterized SQL for those tables and has no generic SQL execution method.
