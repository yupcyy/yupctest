# Database approval boundary

- Do not connect to, inspect, query, create, alter, migrate, delete, or otherwise operate on any production/local configured database without the user's explicit approval for the exact operation in the current conversation.
- Preparing code, SQL, or migration scripts without executing them is allowed. Temporary SQLite databases created solely inside the automated test temporary directory are allowed.
- Production runtime SQL must remain restricted to fixed, parameterized statements against the `agent_` tables. Do not add an arbitrary SQL execution interface or inspect unrelated schemas/tables.
- Do not change `DATABASE_TYPE`, execute scripts under `scripts/database`, retire SQLite artifacts, or restart into a new database backend without explicit approval.
- Before an approved destructive operation, state the exact tables/files and confirmation phrase involved. Historical SQLite backups require separate approval to delete.
