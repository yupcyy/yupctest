# Database approval boundary

- Do not connect to, inspect, query, create, alter, migrate, delete, or otherwise operate on any production/local configured database without the user's explicit approval for the exact operation in the current conversation.
- Preparing code, SQL, or migration scripts without executing them is allowed. Temporary SQLite databases created solely inside the automated test temporary directory are allowed.
- Production runtime SQL must remain restricted to fixed, parameterized statements against the `agent_` tables. Do not add an arbitrary SQL execution interface or inspect unrelated schemas/tables.
- Do not change `DATABASE_TYPE`, execute scripts under `scripts/database`, retire SQLite artifacts, or restart into a new database backend without explicit approval.
- Before an approved destructive operation, state the exact tables/files and confirmation phrase involved. Historical SQLite backups require separate approval to delete.

## Testing Policy

- Do NOT run full test suites unless explicitly requested by the user.
- By default, run only targeted tests directly relevant to the modified code.
- Do NOT run repository-wide tests, builds, linting, or type checks unless explicitly requested or strictly necessary.
- Prefer lightweight validation and static inspection.
- Do NOT add or modify tests unless necessary for the requested changes.
- If broader testing is recommended, inform the user instead of executing it automatically.
- Never claim unexecuted tests have passed.