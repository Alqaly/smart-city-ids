#!/usr/bin/env bash
set -e

echo "Checking environment..."

# Required commands
for cmd in python pip psql bun node docker; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "⚠️  $cmd not found"
  else
    echo "✅ $cmd found: $(which $cmd)"
  fi
done

# K3s / docker check
if kubectl version --client >/dev/null 2>&1; then
  echo "✅ kubectl available"
else
  echo "⚠️  kubectl not available / cannot reach K8s cluster"
fi

# Env vars
if [ -z "${GROQ_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ] ; then
  echo "⚠️  Neither GROQ_API_KEY nor OPENAI_API_KEY set. Set one to run IDS API."
else
  echo "✅ LLM API key present"
fi

if [ -z "${MORPH_API_KEY:-}" ]; then
  echo "⚠️  MORPH_API_KEY not set (Morph Fast Apply will be disabled)"
else
  echo "✅ MORPH_API_KEY set"
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "⚠️  DATABASE_URL not set. Migrations / DB access will fail."
else
  echo "✅ DATABASE_URL set"
fi

echo "Done. Fix any warnings above before continuing."
