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
  Kubernetes secret and ConfigMap used by ids-api, then restart ids-api so the
  changes take effect.

What it updates:
  - Kubernetes secret: smart-city/ids-secrets
  - Kubernetes ConfigMap: smart-city/ids-config (LLM model/priority settings)
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

# ── Sync the ids-config ConfigMap so envFrom no longer re-injects stale models ──
echo "Updating ids-config ConfigMap from .env…"
CONFIGMAP_DATA_JSON="$(jq -cn \
  --arg llm_priority "${LLM_PRIORITY:-}" \
  --arg anthropic_model "${ANTHROPIC_MODEL:-}" \
  --arg openai_model "${OPENAI_MODEL:-}" \
  --arg xai_model "${XAI_MODEL:-}" \
  --arg gemini_model "${GEMINI_MODEL:-}" \
  --arg kimi_model "${KIMI_MODEL:-}" \
  '
  {
    data: (
      {}
      + (if $llm_priority != "" then {LLM_PRIORITY:$llm_priority} else {} end)
      + (if $anthropic_model != "" then {ANTHROPIC_MODEL:$anthropic_model} else {} end)
      + (if $openai_model != "" then {OPENAI_MODEL:$openai_model} else {} end)
      + (if $xai_model != "" then {XAI_MODEL:$xai_model} else {} end)
      + (if $gemini_model != "" then {GEMINI_MODEL:$gemini_model} else {} end)
      + (if $kimi_model != "" then {KIMI_MODEL:$kimi_model} else {} end)
    )
  }'
)"
kubectl patch configmap ids-config -n "$NAMESPACE" --type=merge -p "$CONFIGMAP_DATA_JSON" >/dev/null
echo "✅ ids-config LLM settings updated from $ENV_FILE"

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
