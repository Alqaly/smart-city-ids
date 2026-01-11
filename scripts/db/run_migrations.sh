#!/usr/bin/env bash
set -euo pipefail

MIGRATIONS_DIR="infrastructure/database/migrations"
DB_URI="${DATABASE_URL:-}"

if [ -z "$DB_URI" ]; then
  echo "❌ DATABASE_URL is not set. Export DATABASE_URL (e.g., postgres://user:pass@host:port/dbname)"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "❌ psql not found. Install PostgreSQL client."
  exit 1
fi

for f in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
  echo "Applying migration: $f"
  psql -d "$DB_URI" -v ON_ERROR_STOP=1 -f "$f" || { echo "❌ Migration failed: $f"; exit 1; }
done

echo "✅ Migrations applied successfully"
