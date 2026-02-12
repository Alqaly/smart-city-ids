#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MIGRATIONS_DIR="$PROJECT_ROOT/infrastructure/database/migrations"

# Load project env if present.
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

if [[ -n "${KUBECONFIG:-}" && ! -r "${KUBECONFIG}" && -r "$HOME/.kube/config" ]]; then
  export KUBECONFIG="$HOME/.kube/config"
fi

DB_URI="${DATABASE_URL:-}"

if [[ -z "$DB_URI" ]]; then
  DB_HOST="${DB_HOST:-localhost}"
  DB_PORT="${DB_PORT:-5432}"
  DB_USER="${POSTGRES_USER:-postgres}"
  DB_PASSWORD="${POSTGRES_PASSWORD:-idspassword}"
  DB_NAME="${POSTGRES_DB:-smartcity_ids}"
  DB_URI="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
  echo "ℹ️  DATABASE_URL not set; using derived connection: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
fi

if [ -z "$DB_URI" ]; then
  echo "❌ DATABASE_URL is not set. Export DATABASE_URL (e.g., postgres://user:pass@host:port/dbname)"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "❌ psql not found. Install PostgreSQL client."
  exit 1
fi

shopt -s nullglob
mapfile -t migration_files < <(printf '%s\n' "$MIGRATIONS_DIR"/*.sql | sort)
if [[ ${#migration_files[@]} -eq 0 ]]; then
  echo "❌ No migration files found in: $MIGRATIONS_DIR"
  exit 1
fi

apply_migrations_local() {
  for f in "${migration_files[@]}"; do
    echo "Applying migration (local DB): $f"
    psql -d "$DB_URI" -v ON_ERROR_STOP=1 -f "$f" || { echo "❌ Migration failed: $f"; return 1; }
  done
}

apply_migrations_k8s() {
  if ! command -v kubectl >/dev/null 2>&1; then
    return 1
  fi

  local k8s_ns="${K8S_NAMESPACE:-smart-city}"
  if ! kubectl get deploy postgres -n "$k8s_ns" >/dev/null 2>&1; then
    return 1
  fi

  local k8s_user
  local k8s_db
  k8s_user="$(kubectl get secret postgres-credentials -n "$k8s_ns" -o jsonpath='{.data.username}' 2>/dev/null | base64 -d 2>/dev/null || echo "postgres")"
  k8s_db="$(kubectl get deploy postgres -n "$k8s_ns" -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="POSTGRES_DB")].value}' 2>/dev/null || echo "smartcity_ids")"
  [[ -n "$k8s_user" ]] || k8s_user="postgres"
  [[ -n "$k8s_db" ]] || k8s_db="smartcity_ids"

  echo "ℹ️  Falling back to in-cluster PostgreSQL: namespace=${k8s_ns}, user=${k8s_user}, db=${k8s_db}"
  for f in "${migration_files[@]}"; do
    echo "Applying migration (k8s postgres): $f"
    kubectl exec -i -n "$k8s_ns" deploy/postgres -- psql -U "$k8s_user" -d "$k8s_db" -v ON_ERROR_STOP=1 < "$f" \
      || { echo "❌ Migration failed: $f"; return 1; }
  done
}

if psql -d "$DB_URI" -tAc 'SELECT 1' >/dev/null 2>&1; then
  apply_migrations_local
else
  echo "⚠️  Local PostgreSQL not reachable via DATABASE_URL/derived connection."
  apply_migrations_k8s || {
    echo "❌ Unable to apply migrations: local DB unreachable and k8s postgres fallback unavailable."
    exit 1
  }
fi

echo "✅ Migrations applied successfully"
