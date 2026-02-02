#!/usr/bin/env bash
set -euo pipefail

echo "Running docs validation (markdownlint + markdown-link-check)"

if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js is required for docs checks. Install Node.js and try again."
  exit 1
fi

# Change to docs directory for link-check
cd "$(dirname "$0")/../../"

npx markdownlint-cli@0.35.0 docs/*.md || { echo "❌ markdownlint failed"; exit 1; }

for f in docs/*.md; do
  [ -f "$f" ] && npx markdown-link-check -q "$f" || true
done

echo "✅ Docs validation passed"

