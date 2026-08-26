# Database setup

PostgreSQL 16 with the `vector` extension, per ARCHITECTURE.md §8.

## 1. Why there is a bootstrap step

`pgvector` is **not a trusted extension**. `CREATE EXTENSION vector` therefore
requires a superuser, and the application role must not be one. The extension is
created once by a superuser; the Alembic migration then issues
`CREATE EXTENSION IF NOT EXISTS vector`, which is a privilege-free no-op once it
is present.

For the same reason the initial migration's `downgrade()` does **not** drop the
extension. It is database-level infrastructure that the migration does not own.

## 2. Install

Homebrew:

```bash
brew install postgresql@16 && brew services start postgresql@16
```

pgvector's Homebrew bottle is built only for PostgreSQL 17 and 18. For 16 it must
be compiled against the matching `pg_config`:

```bash
git clone --depth 1 --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector && make PG_CONFIG=/opt/homebrew/opt/postgresql@16/bin/pg_config && make install PG_CONFIG=/opt/homebrew/opt/postgresql@16/bin/pg_config
```

## 3. Bootstrap, as a superuser

```bash
psql -d postgres -c "CREATE ROLE biet LOGIN PASSWORD 'biet';"
createdb -O biet biet
psql -d biet -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Then point `BIET_DATABASE_URL` in `.env` at it.

## 4. Port

Check which port the server is actually on before assuming 5432 — a machine with
more than one PostgreSQL installed will not put 16 there:

```bash
head -4 /opt/homebrew/var/postgresql@16/postmaster.pid | tail -1
```

## 5. Migrate

```bash
cd backend && ../.venv/bin/alembic upgrade head
```

Useful checks:

```bash
../.venv/bin/alembic check              # model/database drift; must say "No new upgrade operations"
../.venv/bin/alembic downgrade base     # reversibility; leaves only alembic_version
```
