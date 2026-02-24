#!/usr/bin/env bash
# =============================================================================
# Smart City IDS — IoT Attack Pipeline v3 (67 Scenarios + 5 Campaigns)
# =============================================================================
echo "ERROR: scripts/attack-iot-pipeline-v3.sh was removed (it runs synthetic scenarios and can POST fake alerts)." >&2
echo "Use live attacks only:" >&2
echo "  bash scripts/run-live-attacks.sh --duration 30" >&2
exit 2
#!/bin/bash
# =============================================================================
# Smart City IDS — IoT Attack Pipeline v3 (67 Scenarios + 5 Campaigns)
# =============================================================================
#
# Upgraded pipeline that leverages the Python scenario_registry for a
# comprehensive 67-scenario + 5-campaign attack suite.
#
# Three execution modes:
#   1. Shell-native (fallback) — original 13 scenarios for environments
#      without Python
#   2. Python-powered — delegates to attack_runner.py for the full 67+5
#   3. Hybrid — shell handles K8s live-exec, Python handles payloads
#
# Usage:
#   bash scripts/attack-iot-pipeline-v3.sh                    # Phase 1 (20 core)
#   bash scripts/attack-iot-pipeline-v3.sh --phase 2          # Phase 2 (45 + campaigns)
#   bash scripts/attack-iot-pipeline-v3.sh --all              # All 67 + 5 campaigns
#   bash scripts/attack-iot-pipeline-v3.sh --category network # All 15 network attacks
#   bash scripts/attack-iot-pipeline-v3.sh --campaign M1      # Single campaign
#   bash scripts/attack-iot-pipeline-v3.sh --campaigns        # All 5 campaigns
#   bash scripts/attack-iot-pipeline-v3.sh --quick            # Quick 5 attacks (legacy)
#   bash scripts/attack-iot-pipeline-v3.sh --live             # Real kubectl exec
#   bash scripts/attack-iot-pipeline-v3.sh --random 15        # 15 random scenarios
#   bash scripts/attack-iot-pipeline-v3.sh --rapid            # Stress test (30 alerts)
#   bash scripts/attack-iot-pipeline-v3.sh --list             # List all scenarios
#   bash scripts/attack-iot-pipeline-v3.sh --json             # Export JSON registry
#   bash scripts/attack-iot-pipeline-v3.sh --legacy           # Original 13-scenario mode
# =============================================================================

set -euo pipefail

# ── Colors ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
PURPLE='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

# ── Config ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ATTACK_DIR="${PROJECT_ROOT}/attack-simulator"
IDS_API="${IDS_API_URL:-http://localhost:30800}"
NAMESPACE="smart-city"
DELAY="${ATTACK_DELAY:-2}"
PYTHON="${PYTHON:-python3}"
LEGACY=false

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# ── Check Python runner availability ──
has_python_runner() {
    [[ -f "${ATTACK_DIR}/attack_runner.py" ]] && [[ -f "${ATTACK_DIR}/scenario_registry.py" ]]
}

# ── Parse args (pass-through to Python runner) ──
ARGS=("$@")
PASS_THROUGH_ARGS=()
LIVE=false
SHOW_LIST=false
SHOW_JSON=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --legacy)   LEGACY=true; shift ;;
        --live)     LIVE=true; PASS_THROUGH_ARGS+=("$1"); shift ;;
        --list)     SHOW_LIST=true; PASS_THROUGH_ARGS+=("$1"); shift ;;
        --json)     SHOW_JSON=true; PASS_THROUGH_ARGS+=("$1"); shift ;;
        --url)      IDS_API="$2"; PASS_THROUGH_ARGS+=("$1" "$2"); shift 2 ;;
        --delay)    DELAY="$2"; PASS_THROUGH_ARGS+=("$1" "$2"); shift 2 ;;
        *)          PASS_THROUGH_ARGS+=("$1"); shift ;;
    esac
done

# ═══════════════════════════════════════════════════════════════════════════════
# Python-powered execution (preferred)
# ═══════════════════════════════════════════════════════════════════════════════

if ! $LEGACY && has_python_runner; then
    # Pre-flight: check for requests library
    if ! $PYTHON -c "import requests" 2>/dev/null; then
        echo -e "${YELLOW}Installing Python requests library...${RESET}"
        $PYTHON -m pip install requests -q 2>/dev/null || true
    fi

    # List/JSON modes don't need IDS API
    if $SHOW_LIST || $SHOW_JSON; then
        exec $PYTHON "${ATTACK_DIR}/attack_runner.py" "${PASS_THROUGH_ARGS[@]}"
    fi

    # Banner
    echo ""
    echo -e "${BOLD}╔═══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║    Smart City IDS — IoT Attack Pipeline v3                   ║${RESET}"
    echo -e "${BOLD}║    Powered by scenario_registry.py (67 + 5 campaigns)        ║${RESET}"
    echo -e "${BOLD}╚═══════════════════════════════════════════════════════════════╝${RESET}"
    echo ""

    # Pod status
    echo -e "${BOLD}K8s Pod Status:${RESET}"
    for svc in ids-api traffic-camera healthcare-api parking-system env-sensor street-lighting iot-devices-enhanced mqtt-broker; do
        cnt=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -c "^${svc}.*Running" || true)
        [[ "$cnt" -gt 0 ]] && echo -e "  ${GREEN}✓${RESET} ${svc}: ${cnt} pod(s)"
    done
    echo ""

    # Delegate to Python runner
    exec $PYTHON "${ATTACK_DIR}/attack_runner.py" \
        --url "$IDS_API" \
        --delay "$DELAY" \
        "${PASS_THROUGH_ARGS[@]}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Legacy shell-native execution (13 scenarios - fallback)
# ═══════════════════════════════════════════════════════════════════════════════

echo -e "${YELLOW}Using legacy shell mode (13 scenarios). Install Python for full 67+5 suite.${RESET}"
echo ""

# Source the original attack-iot-pipeline.sh if it exists
if [[ -f "${SCRIPT_DIR}/attack-iot-pipeline.sh" ]]; then
    exec bash "${SCRIPT_DIR}/attack-iot-pipeline.sh" "${ARGS[@]}"
else
    echo -e "${RED}Legacy attack-iot-pipeline.sh not found${RESET}"
    exit 1
fi
