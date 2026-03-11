#!/usr/bin/env bash
set -euo pipefail

# Apply LLM API keys from a local .env file into the Kubernetes Secret
# that the ids-api Deployment already references.
#
# - Reads:  XAI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, KIMI_API_KEY
# - Writes: ids-secrets keys: xai-api-key, openai-api-key, anthropic-api-key, gemini-api-key, kimi-api-key
#
# Usage:
#   ./scripts/apply-llm-env-to-k8s-secret.sh [path_to_env]
#
# Defaults:
#   path_to_env = ./.env
#   namespace   = smart-city
#   secret      = ids-secrets

show_help() {
  cat <<'EOF'
Usage:
  bash scripts/apply-llm-env-to-k8s-secret.sh [path_to_env]

Purpose:
  Apply LLM API keys and model settings from a local .env file into the live
  Kubernetes secret used by ids-api, then restart ids-api so the changes take effect.

What it updates:
  - Kubernetes secret: smart-city/ids-secrets
  - ids-api model and priority environment values
  - ids-api deployment rollout

Default:
  path_to_env = .env

Typical workflow:
  1. Edit .env and update provider keys or model names
  2. Run this script
  3. Verify with: bash scripts/llm-manager.sh check

Notes:
  - This changes the live cluster configuration
  - Missing keys are skipped rather than cleared
  - Billing/quota issues are provider-side and are not fixed by this script
EOF
}

case "${1:-}" in
  --help|-h)
    show_help
    exit 0
    ;;
esac

ENV_FILE="${1:-.env}"
NAMESPACE="${NAMESPACE:-smart-city}"
SECRET_NAME="${SECRET_NAME:-ids-secrets}"
RESTART_DEPLOYMENT="${RESTART_DEPLOYMENT:-ids-api}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

# Load .env safely (ignores comments/blank lines).
# Preserve KUBECONFIG so the .env value never overrides the shell's working config.
_KC_SAVED="${KUBECONFIG:-}"
set -a
# shellcheck disable=SC1090
source <(grep -vE '^[[:space:]]*#' "$ENV_FILE" | grep -vE '^[[:space:]]*$')
set +a
[[ -n "$_KC_SAVED" ]] && export KUBECONFIG="$_KC_SAVED"

# Only include keys that are actually set in the .env
args=()
[[ -n "${XAI_API_KEY:-}" ]] && args+=("--from-literal=xai-api-key=${XAI_API_KEY}")
[[ -n "${OPENAI_API_KEY:-}" ]] && args+=("--from-literal=openai-api-key=${OPENAI_API_KEY}")
[[ -n "${ANTHROPIC_API_KEY:-}" ]] && args+=("--from-literal=anthropic-api-key=${ANTHROPIC_API_KEY}")
[[ -n "${GEMINI_API_KEY:-}" ]] && args+=("--from-literal=gemini-api-key=${GEMINI_API_KEY}")
[[ -n "${KIMI_API_KEY:-}" ]] && args+=("--from-literal=kimi-api-key=${KIMI_API_KEY}")

if [[ ${#args[@]} -eq 0 ]]; then
  echo "ERROR: No LLM keys found in $ENV_FILE (expected one of XAI_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY/GEMINI_API_KEY/KIMI_API_KEY)." >&2
  exit 1
fi

# Create/update secret idempotently
kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  "${args[@]}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Updated secret $NAMESPACE/$SECRET_NAME from $ENV_FILE"

# ── Patch deployment: ensure Anthropic uses secretKeyRef (not inline value) ──
# Also sync LLM_PRIORITY and model names from .env
echo "Patching deployment env vars from .env…"
PATCH_ENV_ARGS=()
[[ -n "${LLM_PRIORITY:-}" ]]       && PATCH_ENV_ARGS+=("LLM_PRIORITY=${LLM_PRIORITY}")
[[ -n "${ANTHROPIC_MODEL:-}" ]]    && PATCH_ENV_ARGS+=("ANTHROPIC_MODEL=${ANTHROPIC_MODEL}")
[[ -n "${OPENAI_MODEL:-}" ]]       && PATCH_ENV_ARGS+=("OPENAI_MODEL=${OPENAI_MODEL}")
[[ -n "${XAI_MODEL:-}" ]]          && PATCH_ENV_ARGS+=("XAI_MODEL=${XAI_MODEL}")
[[ -n "${GEMINI_MODEL:-}" ]]       && PATCH_ENV_ARGS+=("GEMINI_MODEL=${GEMINI_MODEL}")
[[ -n "${KIMI_MODEL:-}" ]]         && PATCH_ENV_ARGS+=("KIMI_MODEL=${KIMI_MODEL}")
[[ -n "${LLM_TEMPERATURE:-}" ]]    && PATCH_ENV_ARGS+=("LLM_TEMPERATURE=${LLM_TEMPERATURE}")
[[ -n "${CRITICAL_SEVERITY_THRESHOLD:-}" ]] && PATCH_ENV_ARGS+=("CRITICAL_SEVERITY_THRESHOLD=${CRITICAL_SEVERITY_THRESHOLD}")
[[ -n "${HIGH_SEVERITY_THRESHOLD:-}" ]]     && PATCH_ENV_ARGS+=("HIGH_SEVERITY_THRESHOLD=${HIGH_SEVERITY_THRESHOLD}")
[[ -n "${DEDUPLICATOR_TTL_SECONDS:-}" ]]    && PATCH_ENV_ARGS+=("DEDUPLICATOR_TTL_SECONDS=${DEDUPLICATOR_TTL_SECONDS}")

if [[ ${#PATCH_ENV_ARGS[@]} -gt 0 ]]; then
  kubectl -n "$NAMESPACE" set env deployment/"$RESTART_DEPLOYMENT" "${PATCH_ENV_ARGS[@]}"
fi

# Normalize the full ids-api env list from the canonical manifest so repeated
# key-sync runs do not append duplicate secret-backed variables.
normalize_ids_api_env() {
  local desired_env_json patch_payload
  desired_env_json="$(python - <<'PY'
import json
import yaml

with open("k8s-manifests/ids-api-FINAL.yaml", "r", encoding="utf-8") as fh:
    for doc in yaml.safe_load_all(fh):
        if doc and doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "ids-api":
            print(json.dumps(doc["spec"]["template"]["spec"]["containers"][0]["env"]))
            break
PY
)"
  [[ -n "$desired_env_json" ]] || return 0
  patch_payload="$(jq -cn --argjson env "$desired_env_json" '[{"op":"replace","path":"/spec/template/spec/containers/0/env","value":$env}]')"
  kubectl patch deployment "$RESTART_DEPLOYMENT" -n "$NAMESPACE" --type=json -p "$patch_payload" >/dev/null
}

normalize_ids_api_env
echo "✅ ids-api env normalized from k8s-manifests/ids-api-FINAL.yaml"

echo "Restarting deployment $NAMESPACE/$RESTART_DEPLOYMENT to pick up all changes…"
kubectl -n "$NAMESPACE" rollout restart deployment "$RESTART_DEPLOYMENT"
kubectl -n "$NAMESPACE" rollout status deployment "$RESTART_DEPLOYMENT" --timeout=120s

echo ""
echo "✅ Done. Verify with:  bash scripts/llm-manager.sh check"
