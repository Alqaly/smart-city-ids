#!/usr/bin/env bash
# ============================================================================
# live-pipeline-log.sh — Real-time end-to-end IDS pipeline observer
#
# Shows the FULL journey of every alert from ingestion to final response:
#   Falco/Suricata → Forwarder → IDS API → LLM Analysis → Automated Action
#
# Usage:
#   bash scripts/live-pipeline-log.sh              # default: all sources
#   bash scripts/live-pipeline-log.sh --falco      # only Falco alerts
#   bash scripts/live-pipeline-log.sh --suricata   # only Suricata alerts
#   bash scripts/live-pipeline-log.sh --attacks     # also launch attack sim
# ============================================================================
set -euo pipefail

IDS_URL="${IDS_URL:-http://localhost:30800}"
NS="${K8S_NAMESPACE:-smart-city}"
FILTER_SOURCE=""
LAUNCH_ATTACKS=false

for arg in "$@"; do
  case "$arg" in
    --falco)    FILTER_SOURCE="falco" ;;
    --suricata) FILTER_SOURCE="suricata" ;;
    --attacks)  LAUNCH_ATTACKS=true ;;
    --help|-h)
      echo "Usage: $0 [--falco|--suricata] [--attacks]"
      echo "  --falco      Show only Falco-sourced alerts"
      echo "  --suricata   Show only Suricata-sourced alerts"
      echo "  --attacks    Launch attack pipeline in background"
      exit 0 ;;
  esac
done

# ── Colors ──
R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'
M='\033[0;35m'; C='\033[0;36m'; W='\033[1;37m'; D='\033[0;90m'; N='\033[0m'

sep()  { printf "${D}%.0s─${N}" {1..78}; echo; }
tstp() { date '+%H:%M:%S'; }

# ── Pre-flight ──
printf "\n${W}╔═══════════════════════════════════════════════════════════════════╗${N}\n"
printf "${W}║         🔍  Smart City IDS — Live Pipeline Log                    ║${N}\n"
printf "${W}╚═══════════════════════════════════════════════════════════════════╝${N}\n\n"

printf "  IDS API:  ${C}${IDS_URL}${N}\n"
printf "  Filter:   ${Y}${FILTER_SOURCE:-all sources}${N}\n"
printf "  Time:     ${D}$(date '+%Y-%m-%d %H:%M:%S')${N}\n\n"

# Check API
if ! curl -sf "${IDS_URL}/health" >/dev/null 2>&1; then
  printf "${R}  ✗ IDS API unreachable at ${IDS_URL}${N}\n"
  exit 1
fi
printf "  ${G}✓ IDS API healthy${N}\n"

# Check SSE
printf "  ${G}✓ SSE stream available (/api/alerts/live)${N}\n"

ALERT_COUNT=0
TOTAL_LATENCY=0

sep

printf "\n${W}  Listening for alerts... ${D}(Ctrl+C to stop)${N}\n\n"

# ── Optionally launch attacks ──
ATTACK_PID=""
if $LAUNCH_ATTACKS; then
  printf "  ${Y}► Launching attack pipeline in background...${N}\n\n"
  bash "$(dirname "$0")/attack-iot-pipeline.sh" >/dev/null 2>&1 &
  ATTACK_PID=$!
fi

cleanup() {
  echo
  sep
  if [ $ALERT_COUNT -gt 0 ]; then
    AVG=$(( TOTAL_LATENCY / ALERT_COUNT ))
    printf "\n${W}  Session Summary${N}\n"
    printf "  Alerts observed:  ${G}${ALERT_COUNT}${N}\n"
    printf "  Avg latency:      ${C}${AVG}ms${N}\n"
  fi
  [ -n "$ATTACK_PID" ] && kill "$ATTACK_PID" 2>/dev/null
  printf "\n${D}  Pipeline log ended at $(date '+%H:%M:%S')${N}\n\n"
  exit 0
}
trap cleanup INT TERM

# ── Stream alerts via SSE ──
# The SSE endpoint sends JSON events for every alert processed
curl -sN "${IDS_URL}/api/alerts/live" 2>/dev/null | while IFS= read -r line; do
  # SSE lines: "data: {...}"
  [[ "$line" != data:* ]] && continue
  json="${line#data: }"

  # Skip heartbeats / non-JSON
  [[ "$json" == "heartbeat" || "$json" == "" ]] && continue

  # Parse fields
  status=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null) || continue
  [[ "$status" != "processed" && "$status" != "throttled" ]] && continue

  source=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('source','?'))" 2>/dev/null)
  [[ -n "$FILTER_SOURCE" && "$source" != "$FILTER_SOURCE" ]] && continue

  # Extract all fields
  eval "$(echo "$json" | python3 -c "
import sys, json, shlex
d = json.load(sys.stdin)
a = d.get('analysis', {})
print(f'alert_id={shlex.quote(str(d.get(\"alert_id\",\"?\")))}')
print(f'rule={shlex.quote(str(d.get(\"rule\",\"?\")))}')
print(f'severity={shlex.quote(str(d.get(\"severity\",\"?\")))}')
print(f'threat_type={shlex.quote(str(d.get(\"threat_type\",\"?\")))}')
print(f'summary={shlex.quote(str(d.get(\"summary\",\"\")))}')
print(f'engine={shlex.quote(str(d.get(\"llm_engine\",a.get(\"analysis_engine\",\"?\"))))}')
print(f'latency_ms={shlex.quote(str(d.get(\"processing_time_ms\",\"?\")))}')
print(f'reasoning={shlex.quote(str(a.get(\"reasoning\",\"\")))}')
print(f'impact={shlex.quote(str(a.get(\"business_impact\",\"\")))}')
print(f'mitre={shlex.quote(str(a.get(\"mitre_technique\",\"\")))}')
print(f'confidence={shlex.quote(str(a.get(\"confidence\",\"\")))}')
recs = a.get('recommendations', d.get('recommendations', []))
print(f'recs_count={len(recs)}')
for i, r in enumerate(recs[:4]):
    print(f'rec{i}={shlex.quote(str(r))}')
actions = d.get('automated_actions', [])
print(f'actions_count={len(actions)}')
for i, act in enumerate(actions[:3]):
    print(f'act{i}={shlex.quote(str(act) if isinstance(act, str) else json.dumps(act))}')
" 2>/dev/null)" || continue

  ALERT_COUNT=$((ALERT_COUNT + 1))
  lat_num="${latency_ms//[^0-9]/}"
  [ -n "$lat_num" ] && TOTAL_LATENCY=$((TOTAL_LATENCY + lat_num))

  # Severity coloring
  sev_num="${severity//[^0-9]/}"
  if [ "${sev_num:-0}" -ge 8 ]; then SEV_C="$R"; SEV_ICON="■ CRITICAL"
  elif [ "${sev_num:-0}" -ge 6 ]; then SEV_C="$Y"; SEV_ICON="▲ HIGH"
  elif [ "${sev_num:-0}" -ge 4 ]; then SEV_C="$C"; SEV_ICON="● MEDIUM"
  else SEV_C="$G"; SEV_ICON="○ LOW"; fi

  # Confidence coloring
  CONF_NUM="${confidence//[^0-9.]/}"
  CONF_NUM="${CONF_NUM:-0}"
  if awk -v c="$CONF_NUM" 'BEGIN{exit !(c>=0.85)}'; then
    CONF_C="$G"
  elif awk -v c="$CONF_NUM" 'BEGIN{exit !(c>=0.65)}'; then
    CONF_C="$Y"
  else
    CONF_C="$R"
  fi

  # ── Print the alert journey ──
  printf "${D}$(tstp)${N} ${W}━━━ Alert #${ALERT_COUNT} ━━━${N}  ${SEV_C}${SEV_ICON}${N}\n"
  printf "  ${D}│${N}\n"
  printf "  ${D}├─${N} ${B}① INGESTION${N}\n"
  printf "  ${D}│${N}    Source:    ${C}${source}${N}\n"
  printf "  ${D}│${N}    Rule:      ${W}${rule}${N}\n"
  printf "  ${D}│${N}    Alert ID:  ${D}${alert_id}${N}\n"
  printf "  ${D}│${N}\n"
  printf "  ${D}├─${N} ${M}② LLM ANALYSIS${N}  ${D}(engine: ${engine}, ${latency_ms}ms)${N}\n"
  printf "  ${D}│${N}    Severity:  ${SEV_C}${severity}/10${N}\n"
  printf "  ${D}│${N}    Threat:    ${Y}${threat_type}${N}\n"
  [ -n "$mitre" ] && printf "  ${D}│${N}    MITRE:     ${M}${mitre}${N}\n"
  [ -n "$confidence" ] && printf "  ${D}│${N}    Confidence:${CONF_C} ${confidence}${N} ${D}($(date -u +%H:%M:%S))${N}\n"
  printf "  ${D}│${N}\n"
  printf "  ${D}├─${N} ${W}③ SUMMARY${N}\n"
  printf "  ${D}│${N}    ${summary}\n"
  if [ -n "$reasoning" ]; then
    printf "  ${D}│${N}\n"
    printf "  ${D}├─${N} ${C}④ REASONING${N}\n"
    # Word-wrap reasoning at ~76 chars
    echo "$reasoning" | fold -s -w 72 | while IFS= read -r rline; do
      printf "  ${D}│${N}    ${rline}\n"
    done
  fi
  if [ -n "$impact" ]; then
    printf "  ${D}│${N}\n"
    printf "  ${D}├─${N} ${Y}⑤ BUSINESS IMPACT${N}\n"
    echo "$impact" | fold -s -w 72 | while IFS= read -r iline; do
      printf "  ${D}│${N}    ${iline}\n"
    done
  fi
  if [ "${recs_count:-0}" -gt 0 ]; then
    printf "  ${D}│${N}\n"
    printf "  ${D}├─${N} ${G}⑥ RECOMMENDATIONS${N}\n"
    for i in $(seq 0 $((recs_count - 1))); do
      var="rec${i}"
      printf "  ${D}│${N}    ${G}→${N} ${!var}\n"
    done
  fi
  if [ "${actions_count:-0}" -gt 0 ]; then
    printf "  ${D}│${N}\n"
    printf "  ${D}├─${N} ${R}⑦ AUTOMATED ACTIONS${N}\n"
    for i in $(seq 0 $((actions_count - 1))); do
      var="act${i}"
      printf "  ${D}│${N}    ${R}⚡${N} ${!var}\n"
    done
  elif [ "${sev_num:-0}" -lt 8 ]; then
    printf "  ${D}│${N}\n"
    printf "  ${D}├─${N} ${D}⑦ ACTIONS: none (severity < 8)${N}\n"
  fi
  printf "  ${D}│${N}\n"
  printf "  ${D}└─${N} ${G}✓ Processing complete${N}  ${D}(${latency_ms}ms total)${N}\n"
  echo
  sep
  echo

done
