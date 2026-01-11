#!/usr/bin/env bash
set -euo pipefail

echo "Running docs validation (markdownlint + markdown-link-check)"

if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js is required for docs checks. Install Node.js and try again."
  exit 1
fi

npx markdownlint-cli@0.35.0 README.md docs/*.md || { echo "❌ markdownlint failed"; exit 1; }

for f in README.md docs/*.md; do
  npx markdown-link-check -q "$f" || { echo "❌ broken links found in $f"; exit 1; }
done

echo "✅ Docs validation passed"
