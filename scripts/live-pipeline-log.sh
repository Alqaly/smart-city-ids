#!/usr/bin/env bash
# ============================================================================
# live-pipeline-log.sh — Real-time IDS event observer
#
# Shows processed alert events from the IDS SSE stream:
#   detector -> IDS API -> LLM analysis -> governance/actions
#
# For raw component logs (IoT services, broker, Falco, Suricata, forwarders,
# ids-api), use: bash scripts/tail-pipeline-pods.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

IDS_URL="${IDS_URL:-}"
if [[ -z "$IDS_URL" ]]; then
  IDS_URL="$(resolve_ids_api_url || true)"
fi
IDS_URL="${IDS_URL:-http://localhost:30800}"
FILTER_SOURCE=""
LAUNCH_ATTACKS=false
ATTACK_DURATION="${ATTACK_DURATION:-20}"
ATTACK_MODE="${ATTACK_MODE:-protocol}"

for arg in "$@"; do
  case "$arg" in
    --falco)    FILTER_SOURCE="falco" ;;
    --suricata) FILTER_SOURCE="suricata" ;;
    --attacks)  LAUNCH_ATTACKS=true ;;
    --help|-h)
      echo "Usage: $0 [--falco|--suricata] [--attacks]"
      echo "  --falco      Show only Falco-sourced alerts"
      echo "  --suricata   Show only Suricata-sourced alerts"
      echo "  --attacks    Launch run-live-attacks.sh in background (default mode: protocol)"
      echo ""
      echo "Notes:"
      echo "  - This script shows processed IDS events from /api/alerts/live"
      echo "  - For raw pod logs across IoT services, broker, Falco, Suricata, forwarders, and ids-api:"
      echo "      bash scripts/tail-pipeline-pods.sh"
      exit 0 ;;
  esac
done

R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'
M='\033[0;35m'; C='\033[0;36m'; W='\033[1;37m'; D='\033[0;90m'; N='\033[0m'
sep()  { printf "${D}%.0s─${N}" {1..78}; echo; }
tstp() { date '+%H:%M:%S'; }

printf "\n${W}╔═══════════════════════════════════════════════════════════════════╗${N}\n"
printf "${W}║         Smart City IDS — Live Pipeline Feed Observer             ║${N}\n"
printf "${W}╚═══════════════════════════════════════════════════════════════════╝${N}\n\n"
printf "  IDS API:  ${C}${IDS_URL}${N}\n"
printf "  Filter:   ${Y}${FILTER_SOURCE:-all sources}${N}\n"
printf "  Time:     ${D}$(date '+%Y-%m-%d %H:%M:%S')${N}\n\n"

curl -sf "${IDS_URL}/health" >/dev/null
printf "  ${G}✓ IDS API healthy${N}\n"
printf "  ${G}✓ SSE stream endpoint configured at /api/alerts/live${N}\n"
printf "  ${D}  Tip: use bash scripts/tail-pipeline-pods.sh for raw component logs${N}\n"

ALERT_COUNT=0
TOTAL_LATENCY=0
ATTACK_PID=""

cleanup() {
  echo
  sep
  if [ $ALERT_COUNT -gt 0 ]; then
    AVG=$(( TOTAL_LATENCY / ALERT_COUNT ))
    printf "\n${W}  Session Summary${N}\n"
    printf "  Alerts observed:  ${G}${ALERT_COUNT}${N}\n"
    printf "  Avg latency:      ${C}${AVG}ms${N}\n"
  fi
  [ -n "$ATTACK_PID" ] && kill "$ATTACK_PID" 2>/dev/null || true
  printf "\n${D}  Feed observer ended at $(date '+%H:%M:%S')${N}\n\n"
  exit 0
}
trap cleanup INT TERM

sep
printf "\n${W}  Listening for processed alerts... ${D}(Ctrl+C to stop)${N}\n\n"

if $LAUNCH_ATTACKS; then
  printf "  ${Y}► Launching run-live-attacks.sh in background (mode=${ATTACK_MODE}, duration=${ATTACK_DURATION}s)${N}\n\n"
  bash "$SCRIPT_DIR/run-live-attacks.sh" --mode "$ATTACK_MODE" --duration "$ATTACK_DURATION" --show-alerts 6 --verbose >/tmp/live-pipeline-log.attacks 2>&1 &
  ATTACK_PID=$!
fi

curl -sN "${IDS_URL}/api/alerts/live" 2>/dev/null | while IFS= read -r line; do
  [[ "$line" != data:* ]] && continue
  json="${line#data: }"
  [[ "$json" == "heartbeat" || -z "$json" ]] && continue

  status=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null) || continue
  [[ "$status" != "processed" && "$status" != "throttled" ]] && continue

  source=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('source','?'))" 2>/dev/null)
  [[ -n "$FILTER_SOURCE" && "$source" != "$FILTER_SOURCE" ]] && continue

  alert_id='?'; rule='?'; severity='0'; threat_type='Unknown'; summary=''; engine='unknown'; latency_ms='0'; confidence=''; recs_count=0; actions_count=0
  unset rec0 rec1 rec2 act0 act1 act2 || true
  eval "$(echo "$json" | python3 -c "
import sys, json, shlex

d=json.load(sys.stdin)
a=d.get('analysis', {})
print(f'alert_id={shlex.quote(str(d.get("alert_id","?")))}')
print(f'rule={shlex.quote(str(d.get("rule","?")))}')
print(f'severity={shlex.quote(str(d.get("severity","0")))}')
print(f'threat_type={shlex.quote(str(d.get("threat_type","Unknown")))}')
print(f'summary={shlex.quote(str(d.get("summary","")))}')
print(f'engine={shlex.quote(str(d.get("llm_engine",a.get("analysis_engine","unknown"))))}')
print(f'latency_ms={shlex.quote(str(d.get("processing_time_ms","0")))}')
print(f'confidence={shlex.quote(str(a.get("confidence","")))}')
recs=a.get('recommendations', d.get('recommendations', []))
print(f'recs_count={len(recs)}')
for i, r in enumerate(recs[:3]):
    print(f'rec{i}={shlex.quote(str(r))}')
actions=d.get('automated_actions', [])
print(f'actions_count={len(actions)}')
for i, act in enumerate(actions[:3]):
    print(f'act{i}={shlex.quote(str(act) if isinstance(act, str) else json.dumps(act))}')
" 2>/dev/null)" || continue

  ALERT_COUNT=$((ALERT_COUNT + 1))
  lat_num="${latency_ms:-0}"
  lat_num="${lat_num//[^0-9]/}"
  [ -n "$lat_num" ] && TOTAL_LATENCY=$((TOTAL_LATENCY + lat_num))

  sev_num="${severity//[^0-9]/}"
  if [ "${sev_num:-0}" -ge 8 ]; then SEV_C="$R"; SEV_LABEL="CRITICAL"
  elif [ "${sev_num:-0}" -ge 6 ]; then SEV_C="$Y"; SEV_LABEL="HIGH"
  elif [ "${sev_num:-0}" -ge 4 ]; then SEV_C="$C"; SEV_LABEL="MEDIUM"
  else SEV_C="$G"; SEV_LABEL="LOW"; fi

  printf "${D}[%s]${N} ${SEV_C}%s %s/10${N} | ${Y}%s${N} | ${W}%s${N} | engine:%s\n" "$(tstp)" "$SEV_LABEL" "$severity" "$threat_type" "$rule" "$engine"
  printf "  source: %s\n" "$source"
  printf "  summary: %s\n" "$summary"
  if [[ ( "$rule" == "?" || "$summary" == "" || "${severity:-0}" == "0" ) && "$alert_id" =~ ^[0-9]+$ ]]; then
    detail_json="$(curl -s "${IDS_URL}/api/alerts?limit=50&include_legacy=true" 2>/dev/null || true)"
    if [[ -n "$detail_json" ]]; then
      eval "$(python3 - "$alert_id" <<'PY2'
import json, shlex, sys
alert_id=sys.argv[1]
try:
    d=json.load(sys.stdin)
except Exception:
    print('')
    raise SystemExit(0)
alerts=d.get('alerts', []) if isinstance(d, dict) else []
m=next((a for a in alerts if str(a.get('id'))==alert_id or str(a.get('alert_id'))==alert_id), None)
if not m:
    raise SystemExit(0)
print(f'rule={shlex.quote(str(m.get("rule") or m.get("output_fields",{}).get("alert.signature") or "?"))}')
print(f'severity={shlex.quote(str(m.get("severity", "0")))}')
print(f'threat_type={shlex.quote(str(m.get("threat_type") or "Unknown"))}')
print(f'summary={shlex.quote(str(m.get("summary") or ""))}')
print(f'engine={shlex.quote(str(m.get("llm_engine") or "unknown"))}')
PY2
<<<"$detail_json")" || true
    fi
  fi

  if [ "${recs_count:-0}" -gt 0 ]; then
    for i in $(seq 0 $((recs_count - 1))); do var="rec${i}"; printf "  rec: %s\n" "${!var}"; done
  fi
  if [ "${actions_count:-0}" -gt 0 ]; then
    for i in $(seq 0 $((actions_count - 1))); do var="act${i}"; printf "  action: %s\n" "${!var}"; done
  fi
  printf "  latency: %sms\n\n" "$latency_ms"
done
