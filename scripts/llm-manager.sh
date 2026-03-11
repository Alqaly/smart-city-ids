#!/usr/bin/env bash
# =============================================================================
# LLM Manager — Smart City IDS
# =============================================================================
# Single entry-point for configuring, checking and testing LLM providers.
#
# Architecture: single source of truth
#   .env  ──(apply-llm-env-to-k8s-secret.sh)──>  K8s Secret "ids-secrets"
#                                                       ↓ secretKeyRef
#                                                  ids-api deployment
#
# Usage:
#   ./scripts/llm-manager.sh check        End-to-end health check (recommended)
#   ./scripts/llm-manager.sh status       Provider status from live API
#   ./scripts/llm-manager.sh priority     Show current priority order
#   ./scripts/llm-manager.sh force PROV   Force a single provider
#   ./scripts/llm-manager.sh auto         Restore failover order
#   ./scripts/llm-manager.sh sync         Push .env → K8s secret → redeploy
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/llm-control.sh"
source "$SCRIPT_DIR/lib/script-utils.sh"

# ── Config ─────────────────────────────────────────────────────────────────
API_BASE="${IDS_API_URL:-}"
NAMESPACE="${NAMESPACE:-smart-city}"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"

if [[ -z "$API_BASE" ]]; then
  API_BASE="$(resolve_ids_api_url || true)"
fi
API_BASE="${API_BASE:-http://localhost:30800}"

# ── Helpers ────────────────────────────────────────────────────────────────
_api()      { curl -sf --max-time 8 "${API_BASE}$1" 2>/dev/null; }
_api_post() { curl -sf --max-time 15 -X POST -H "Content-Type: application/json" -d "$2" "${API_BASE}$1" 2>/dev/null; }
_bold()   { printf '\033[1m%s\033[0m\n' "$1"; }
_green()  { printf '\033[32m%s\033[0m\n' "$1"; }
_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
_red()    { printf '\033[31m%s\033[0m\n' "$1"; }
_cyan()   { printf '\033[36m%s\033[0m' "$1"; }

show_help() {
  cat <<'EOF'

LLM Manager — Smart City IDS

USAGE:
  ./scripts/llm-manager.sh check             Full end-to-end health check
  ./scripts/llm-manager.sh status            Live provider status from API
  ./scripts/llm-manager.sh priority          Show current priority order
  ./scripts/llm-manager.sh priority ORDER    Set priority (e.g. "kimi,xai,anthropic")
  ./scripts/llm-manager.sh force PROVIDER    Route all alerts through one provider
  ./scripts/llm-manager.sh auto              Restore automatic failover
  ./scripts/llm-manager.sh sync              Push .env → K8s secret → redeploy

PROVIDERS:  kimi  xai  anthropic  gemini  openai

EXAMPLES:
  # Full pre-run health check
  ./scripts/llm-manager.sh check

  # Force kimi only
  ./scripts/llm-manager.sh force kimi

  # After updating API keys in .env:
  ./scripts/llm-manager.sh sync

EOF
}

# ── check / e2e ──────────────────────────────────────────────────────────────
cmd_check() {
  echo
  echo "═══════════════════════════════════════════════════════════════"
  echo "  Smart City IDS — LLM End-to-End Health Check"
  echo "═══════════════════════════════════════════════════════════════"
  echo

  local overall_ok=true

  # Load .env without overriding KUBECONFIG
  local _KC="${KUBECONFIG:-}"
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    source <(grep -vE '^[[:space:]]*#' "$ENV_FILE" | grep -vE '^[[:space:]]*$') 2>/dev/null || true
    set +a
    [[ -n "$_KC" ]] && export KUBECONFIG="$_KC"
  fi

  # ── 1. .env keys ───────────────────────────────────────────────
  echo "1/5  .env API Key Inventory"
  echo "     ($ENV_FILE)"
  echo
  local ENV_KEY_MAP=("kimi:KIMI_API_KEY:Moonshot Kimi"
                     "xai:XAI_API_KEY:xAI Grok"
                     "anthropic:ANTHROPIC_API_KEY:Anthropic Claude"
                     "gemini:GEMINI_API_KEY:Google Gemini"
                     "openai:OPENAI_API_KEY:OpenAI GPT")
  local env_ok=0
  for entry in "${ENV_KEY_MAP[@]}"; do
    local pid=${entry%%:*}; local rest=${entry#*:}; local var=${rest%%:*}; local label=${rest#*:}
    local val="${!var:-}"
    if [[ -n "$val" && ${#val} -gt 10 ]]; then
      printf "     %-18s %-24s \033[32m✅ set (%d chars)\033[0m\n" "$label" "$var" "${#val}"
      env_ok=$((env_ok+1))
    else
      printf "     %-18s %-24s \033[31m❌ missing\033[0m  →  add to .env\n" "$label" "$var"
      overall_ok=false
    fi
  done
  echo "     $env_ok/5 keys present in .env"

  # ── 2. K8s secret ──────────────────────────────────────────────
  echo
  echo "2/5  K8s Secret (ids-secrets @ $NAMESPACE)"
  echo
  local secret_data
  secret_data=$(kubectl get secret ids-secrets -n "$NAMESPACE" -o jsonpath='{.data}' 2>/dev/null | \
    python3 -c "
import sys,json,base64
try:
    d=json.load(sys.stdin)
    for k,v in d.items(): print(k,len(base64.b64decode(v).decode()))
except: pass
" 2>/dev/null) || secret_data=""

  declare -A K8S_MAP=([kimi]="kimi-api-key" [xai]="xai-api-key" [anthropic]="anthropic-api-key" [gemini]="gemini-api-key" [openai]="openai-api-key")
  local k8s_ok=0
  for pid in kimi xai anthropic gemini openai; do
    local sk="${K8S_MAP[$pid]}"
    local len
    len=$(echo "$secret_data" | awk -v k="$sk" '$1==k{print $2}')
    if [[ -n "$len" && "$len" -gt 10 ]]; then
      printf "     %-26s \033[32m✅ in secret (%s chars)\033[0m\n" "$sk" "$len"
      k8s_ok=$((k8s_ok+1))
    else
      printf "     %-26s \033[33m⚠️  missing →  run: bash scripts/apply-llm-env-to-k8s-secret.sh\033[0m\n" "$sk"
      overall_ok=false
    fi
  done
  echo "     $k8s_ok/5 keys in K8s secret"

  # Check for plain-text inline keys
  local inline_keys
  inline_keys=$(kubectl get deployment ids-api -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].env}' 2>/dev/null | \
    python3 -c "
import sys,json
envs=json.load(sys.stdin)
plain=[e['name'] for e in envs if '_API_KEY' in e.get('name','') and 'value' in e and 'valueFrom' not in e]
print(' '.join(plain))
" 2>/dev/null) || inline_keys=""
  if [[ -z "$inline_keys" || "$inline_keys" == " " ]]; then
    printf "     \033[32m✅ No plain-text API keys in deployment (all via secretKeyRef)\033[0m\n"
  else
    printf "     \033[31m❌ Plain-text keys in deployment: %s\033[0m\n     Run: bash scripts/apply-llm-env-to-k8s-secret.sh\n" "$inline_keys"
    overall_ok=false
  fi

  # ── 3. API reachability ─────────────────────────────────────────
  echo
  echo "3/5  API Reachability ($API_BASE)"
  echo
  local health_status
  if health_status=$(curl -sf --max-time 5 "${API_BASE}/health" 2>/dev/null | \
      python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status','?'))" 2>/dev/null); then
    printf "     \033[32m✅ IDS API healthy: %s\033[0m\n" "$health_status"
  else
    printf "     \033[31m❌ IDS API not reachable at %s\033[0m\n" "$API_BASE"
    echo "     Try: kubectl get pods -n $NAMESPACE"
    overall_ok=false
  fi

  # ── 4. Live provider diagnostics ───────────────────────────────
  echo
  echo "4/5  Live Provider Status"
  echo
  local diag_out op_count=0
  if diag_out=$(curl -sf --max-time 8 "${API_BASE}/api/llm/diagnostics" 2>/dev/null); then
    op_count=$(echo "$diag_out" | python3 -c "
import sys,json
d=json.load(sys.stdin).get('providers',{})
op=0
uv=0
for k,v in d.items():
    st=v.get('status','?')
    reason=v.get('reason','')
    lat=v.get('last_latency_ms')
    lat_s=f'{lat}ms' if lat else '—'
    if st=='operational':
        icon='\033[32m✅\033[0m'; op+=1
    elif st in ('cooldown','recovering','unverified'):
        if st=='unverified':
            uv+=1
        icon='\033[33m⚠️ \033[0m'
    else:
        icon='\033[31m❌\033[0m'
    print(f'     {icon}  {k:<12}  {st:<22} {reason[:50]}')
print(f'SUMMARY:{op}')
print(f'UNVERIFIED:{uv}')
" 2>/dev/null)
    echo "$op_count" | grep -v "^SUMMARY" | grep -v "^UNVERIFIED"
    local n_op
    local n_uv
    n_op=$(echo "$op_count" | grep "^SUMMARY:" | cut -d: -f2)
    n_uv=$(echo "$op_count" | grep "^UNVERIFIED:" | cut -d: -f2)
    echo
    echo "     Operational: ${n_op:-0}/5"
    if [[ "${n_op:-0}" -eq 0 ]]; then
      if [[ "${n_uv:-0}" -gt 0 ]]; then
        printf "     \033[33m⚠️  No providers verified yet in this process (%s unverified). Proceeding to live alert test.\033[0m\n" "${n_uv:-0}"
      else
        printf "     \033[31m❌ No providers operational!\033[0m\n"
        overall_ok=false
      fi
    fi
  else
    printf "     \033[31m❌ Cannot reach /api/llm/diagnostics\033[0m\n"
    overall_ok=false
  fi

  # ── 5. Real alert injection ─────────────────────────────────────
  echo
  echo "5/5  End-to-End Alert Test (inject → LLM analysis)"
  echo

  # Use a unique rule name to avoid dedup cache hit
  local unique_ts; unique_ts=$(date +%s)
  local iso_time; iso_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local test_payload
  test_payload=$(python3 -c "
import json, sys
ts='${unique_ts}'
p={
  'output': 'Test e2e check: Write below etc directory (user=root command=touch /etc/e2e-' + ts + ')',
  'rule': 'Write Below Etc e2e-' + ts,
  'priority': 'Warning',
  'time': '${iso_time}',
  'output_fields': {
    'container.name': 'test-pod',
    'proc.cmdline': 'touch /etc/e2e-' + ts,
    'user.name': 'root'
  },
  'hostname': 'e2e-check',
  'source': 'falco'
}
print(json.dumps(p))
" 2>/dev/null)

  local resp
  if resp=$(curl -sf --max-time 30 -X POST \
      -H "Content-Type: application/json" \
      -H "X-IDS-Internal-Token: change-me" \
      -d "$test_payload" \
      "${API_BASE}/api/alerts/internal" 2>/dev/null); then

    local engine sev status_f summary
    engine=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('llm_engine') or d.get('analysis',{}).get('llm_engine','?'))" 2>/dev/null || echo "?")
    sev=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('severity') or d.get('analysis',{}).get('severity','?'))" 2>/dev/null || echo "?")
    status_f=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
    summary=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('analysis',{}).get('summary','')[:80])" 2>/dev/null || echo "")

    if [[ "$status_f" == "success" || "$status_f" == "duplicate" || "$status_f" == "processed" ]]; then
      printf "     \033[32m✅ Alert processed (status=%s)\033[0m\n" "$status_f"
      printf "     %-22s \033[36m%s\033[0m\n" "Engine:"  "$engine"
      printf "     %-22s %s/10\n"              "Severity:" "$sev"
      printf "     %-22s %s\n"                 "Summary:"  "$summary"
      if [[ "$engine" == "none" ]]; then
        printf "     \033[31m❌ engine=none — LLM was not called for a new alert!\033[0m\n"
        overall_ok=false
      elif [[ "$engine" == "cached" ]]; then
        printf "     \033[33m⚠️  engine=cached (dedup hit) — TTL may be too long for this test\033[0m\n"
      fi
    else
      printf "     \033[31m❌ Alert returned status=%s\033[0m\n" "$status_f"
      echo "$resp" | python3 -m json.tool 2>/dev/null | head -20
      overall_ok=false
    fi
  else
    printf "     \033[31m❌ Alert injection failed — API unreachable or returned error\033[0m\n"
    overall_ok=false
  fi

  # ── Final verdict ───────────────────────────────────────────────
  echo
  echo "═══════════════════════════════════════════════════════════════"
  if [[ "$overall_ok" == "true" ]]; then
    printf "\033[32m  ✅  ALL CHECKS PASSED — system is ready for operation/evaluation\033[0m\n"
  else
    printf "\033[33m  ⚠️   SOME ISSUES FOUND — fix items marked ❌/⚠️ above\033[0m\n"
    echo
    echo "  Common fixes:"
    echo "    1. Update expired keys in .env"
    echo "    2. Run:  bash scripts/apply-llm-env-to-k8s-secret.sh"
    echo
    echo "  Credit top-up:"
    echo "    Anthropic: https://console.anthropic.com  → Plans & Billing"
    echo "    Gemini:    https://aistudio.google.com    → Quota"
    echo "    xAI:       https://console.x.ai           → Billing"
    echo "    OpenAI:    https://platform.openai.com    → Billing"
  fi
  echo "═══════════════════════════════════════════════════════════════"
  echo

  [[ "$overall_ok" == "true" ]] && return 0 || return 1
}

# ── status ───────────────────────────────────────────────────────────────────
cmd_status() {
  llm_section "LLM Provider Status"
  local diag
  if diag=$(curl -sf --max-time 8 "${API_BASE}/api/llm/diagnostics" 2>/dev/null); then
    echo "$diag" | python3 -c "
import sys,json
d=json.load(sys.stdin)
prov=d.get('providers',{})
smry=d.get('summary',{})
print()
print('  Provider      Status               Att  Lat(ms)   Model')
print('  ──────────────────────────────────────────────────────────────')
for k,v in prov.items():
    st=v.get('status','?')
    icon='✅' if st=='operational' else ('⚠️ ' if st in ('cooldown','recovering','unverified') else '❌')
    att=str(v.get('attempts',0))
    lat=str(v.get('last_latency_ms','—'))
    model=(v.get('model','?') or '?')[:28]
    print(f'  {icon}  {k:<11} {st:<20} {att:<5} {lat:<10} {model}')
print()
print(f'  summary: {smry}')
print()
" 2>/dev/null || echo "  (could not parse diagnostics)"
  else
    echo "  ❌ API not reachable at $API_BASE"
    echo "     Try: kubectl get pods -n $NAMESPACE"
  fi
}

# ── main ─────────────────────────────────────────────────────────────────────
case "${1:-check}" in
  check|e2e|test)   cmd_check ;;
  status|s)         cmd_status ;;
  priority|p)
    if [[ -z "${2:-}" ]]; then llm_show_priority
    else llm_set_priority "$2"; fi
    ;;
  force|f)
    [[ -z "${2:-}" ]] && { echo "Usage: llm-manager.sh force <provider>"; exit 1; }
    llm_force_provider "$2"
    ;;
  auto|a)
    llm_set_priority "kimi,xai,anthropic,gemini,openai"
    echo && llm_info "Automatic failover restored: kimi → xai → anthropic → gemini → openai"
    ;;
  sync)
    echo "Syncing .env → K8s secret → deployment restart…"
    bash "$SCRIPT_DIR/apply-llm-env-to-k8s-secret.sh"
    ;;
  -h|--help|help)   show_help ;;
  *)
    llm_error "Unknown command: $1"
    show_help
    exit 1
    ;;
esac
