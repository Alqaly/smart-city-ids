#!/bin/bash
# =============================================================================
# Smart City IDS - Shared Script Utilities
# Common functions, logging, error handling for all scripts
# =============================================================================
# Source this in any script: source "$(dirname "$0")/lib/script-utils.sh"
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# COLORS & FORMATTING
# ─────────────────────────────────────────────────────────────────────────────
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'
readonly BOLD='\033[1m'

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
if [[ -n "${KUBECONFIG:-}" ]]; then
    if [[ -r "$KUBECONFIG" ]]; then
        export KUBECONFIG
    elif [[ -r "$HOME/.kube/config" ]]; then
        export KUBECONFIG="$HOME/.kube/config"
    else
        export KUBECONFIG
    fi
elif [[ -r "$HOME/.kube/config" ]]; then
    export KUBECONFIG="$HOME/.kube/config"
else
    export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
fi
export SCRIPT_DEBUG="${SCRIPT_DEBUG:-0}"

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

log_debug() {
    if [[ $SCRIPT_DEBUG -eq 1 ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
    fi
}

log_info() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $*"
}

log_error() {
    echo -e "${RED}[✗]${NC} $*" >&2
}

log_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}${BOLD}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_subsection() {
    echo -e "${CYAN}── $1${NC}"
}

# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLING
# ─────────────────────────────────────────────────────────────────────────────

die() {
    log_error "$@"
    exit 1
}

ensure_root() {
    if [[ $EUID -ne 0 ]]; then
        log_warn "This script requires root privileges. Re-invoking with sudo..."
        exec sudo "$0" "$@"
    fi
}

ensure_command() {
    local cmd=$1
    if ! command -v "$cmd" &>/dev/null; then
        die "Required command not found: $cmd"
    fi
}

ensure_commands() {
    local missing=0
    for cmd in "$@"; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Required command not found: $cmd"
            missing=1
        fi
    done
    if [[ $missing -eq 1 ]]; then
        die "One or more required commands are missing"
    fi
}

ensure_file() {
    local file=$1
    if [[ ! -f "$file" ]]; then
        die "Required file not found: $file"
    fi
}

ensure_kubeconfig() {
    if [[ ! -f "$KUBECONFIG" ]]; then
        die "KUBECONFIG not found: $KUBECONFIG"
    fi
    if [[ ! -r "$KUBECONFIG" ]]; then
        die "KUBECONFIG is not readable: $KUBECONFIG (use ~/.kube/config or adjust permissions)"
    fi
    log_debug "Using KUBECONFIG: $KUBECONFIG"
}

# ─────────────────────────────────────────────────────────────────────────────
# KUBERNETES HELPERS
# ─────────────────────────────────────────────────────────────────────────────

k8s_cluster_ready() {
    if kubectl cluster-info &>/dev/null; then
        return 0
    else
        return 1
    fi
}

k8s_wait_ready() {
    local namespace="${1:-default}"
    local timeout="${2:-300}"
    local elapsed=0

    log_info "Waiting for Kubernetes cluster to be ready (timeout: ${timeout}s)..."
    
    while ! k8s_cluster_ready; do
        if [[ $elapsed -ge $timeout ]]; then
            die "Kubernetes cluster failed to become ready within ${timeout}s"
        fi
        echo -n "."
        sleep 5
        ((elapsed += 5))
    done
    echo ""
    log_info "Kubernetes cluster is ready"
}

k8s_pod_ready() {
    local namespace=$1
    local pod=$2
    local timeout="${3:-300}"
    local elapsed=0

    log_debug "Waiting for pod $pod in namespace $namespace..."
    
    while true; do
        local status=$(kubectl get pod "$pod" -n "$namespace" -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
        if [[ "$status" == "Running" ]]; then
            return 0
        elif [[ "$status" == "Failed" ]]; then
            return 1
        elif [[ $elapsed -ge $timeout ]]; then
            return 1
        fi
        sleep 2
        ((elapsed += 2))
    done
}

k8s_deployment_ready() {
    local namespace=$1
    local deployment=$2
    local timeout="${3:-300}"
    local elapsed=0

    log_info "Waiting for deployment $deployment in namespace $namespace..."
    
    while true; do
        local desired=$(kubectl get deployment "$deployment" -n "$namespace" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        local ready=$(kubectl get deployment "$deployment" -n "$namespace" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        
        if [[ "$desired" == "$ready" ]] && [[ "$desired" != "0" ]]; then
            log_info "Deployment $deployment is ready"
            return 0
        elif [[ $elapsed -ge $timeout ]]; then
            log_error "Deployment $deployment failed to become ready within ${timeout}s"
            return 1
        fi
        echo -n "."
        sleep 3
        ((elapsed += 3))
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM CHECKS
# ─────────────────────────────────────────────────────────────────────────────

get_system_ram_gb() {
    free -g | awk '/^Mem:/ {print $2}'
}

get_available_disk_gb() {
    df / | awk '/\// {printf "%.0f", $4 / 1024 / 1024}'
}

get_cpu_cores() {
    nproc 2>/dev/null || echo "1"
}

# ─────────────────────────────────────────────────────────────────────────────
# NETWORKING
# ─────────────────────────────────────────────────────────────────────────────

get_node_ip() {
    local ips
    ips=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
    if [[ -n "$ips" ]]; then
        # Prefer IPv4 for URL formatting in scripts/output.
        local ipv4
        ipv4=$(echo "$ips" | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -1 || true)
        if [[ -n "$ipv4" ]]; then
            echo "$ipv4"
            return 0
        fi
        # Fallback to first returned address (may be IPv6).
        echo "$ips" | tr ' ' '\n' | head -1
        return 0
    fi
    echo "localhost"
}

get_service_nodeport() {
    local service_name=$1
    local namespace=$2
    local default_port=${3:-}
    local nodeport

    nodeport=$(kubectl get svc "$service_name" -n "$namespace" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || true)
    if [[ -n "$nodeport" ]]; then
        echo "$nodeport"
        return 0
    fi

    if [[ -n "$default_port" ]]; then
        echo "$default_port"
        return 0
    fi

    return 1
}

is_port_open() {
    local host="${1:-localhost}"
    local port=$2
    timeout 2 bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null || return 1
}

wait_port_open() {
    local host="${1:-localhost}"
    local port=$2
    local timeout="${3:-60}"
    local elapsed=0

    log_info "Waiting for port $port on $host to be open (timeout: ${timeout}s)..."
    
    while ! is_port_open "$host" "$port"; do
        if [[ $elapsed -ge $timeout ]]; then
            log_error "Port $port on $host did not open within ${timeout}s"
            return 1
        fi
        echo -n "."
        sleep 2
        ((elapsed += 2))
    done
    echo ""
    log_info "Port $port on $host is now open"
}

start_port_forward_checked() {
    local namespace="$1"
    local service="$2"
    local mapping="$3"
    local health_url="$4"
    local log_file="$5"
    local pid_file="$6"
    local wait_seconds="${7:-20}"
    local required="${8:-1}"

    mkdir -p "$(dirname "$pid_file")"
    rm -f "$pid_file"

    setsid kubectl --kubeconfig "$KUBECONFIG" -n "$namespace" \
        port-forward "svc/$service" "$mapping" --address 127.0.0.1 \
        >"$log_file" 2>&1 < /dev/null &
    local pf_pid=$!
    echo "$pf_pid" > "$pid_file"

    local ok=0
    local i
    for i in $(seq 1 "$wait_seconds"); do
        if curl -fsS --max-time 2 "$health_url" >/dev/null 2>&1; then
            ok=1
            break
        fi
        if ! kill -0 "$pf_pid" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    if [[ "$ok" -eq 1 ]]; then
        return 0
    fi

    if [[ -f "$log_file" ]]; then
        log_warn "Port-forward failed for $service ($mapping). Recent log:"
        tail -n 20 "$log_file" || true
    fi

    if [[ "$required" -eq 1 ]]; then
        return 1
    fi
    return 0
}

stop_port_forward_checked() {
    local pid_file="$1"
    local pattern="${2:-}"
    if [[ -f "$pid_file" ]]; then
        local pf_pid
        pf_pid="$(cat "$pid_file" 2>/dev/null || true)"
        if [[ -n "$pf_pid" ]] && kill -0 "$pf_pid" 2>/dev/null; then
            kill "$pf_pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pf_pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi
    if [[ -n "$pattern" ]]; then
        pkill -f "$pattern" 2>/dev/null || true
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# CONFIRMATION PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

confirm() {
    local prompt="$1"
    local default="${2:-n}"  # y or n
    
    read -p "$(echo -e "${YELLOW}$prompt${NC}") [${default}]: " response
    response=${response:-$default}
    
    [[ "$response" =~ ^[Yy]$ ]]
}

confirm_destructive() {
    local prompt="$1"
    
    echo ""
    log_warn "$prompt"
    read -p "$(echo -e "${YELLOW}Type 'yes' to confirm:${NC} ")" confirmation
    [[ "$confirmation" == "yes" ]]
}

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

pkill_safe() {
    local pattern=$1
    local signal="${2:-TERM}"
    
    local count=$(pgrep -f "$pattern" 2>/dev/null | wc -l || echo "0")
    if [[ $count -gt 0 ]]; then
        log_info "Killing $count process(es) matching: $pattern"
        pkill -"$signal" -f "$pattern" 2>/dev/null || true
        sleep 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# TIMER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

timer_start() {
    echo $(date +%s)
}

timer_elapsed() {
    local start=$1
    local end=$(date +%s)
    echo $((end - start))
}

timer_format() {
    local seconds=$1
    local mins=$((seconds / 60))
    local secs=$((seconds % 60))
    printf "%02d:%02d" $mins $secs
}

# ─────────────────────────────────────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────────────────────────────────────

api_call() {
    local method=$1
    local url=$2
    local data="${3:-}"
    local timeout="${4:-10}"
    
    if [[ -z "$data" ]]; then
        curl -s -X "$method" "$url" --connect-timeout "$timeout" --max-time "$timeout" || return 1
    else
        curl -s -X "$method" "$url" -H "Content-Type: application/json" -d "$data" --connect-timeout "$timeout" --max-time "$timeout" || return 1
    fi
}

resolve_ids_api_url() {
    # Order:
    #  1) explicit IDS_API_URL
    #  2) local port-forward (:8000)
    #  3) local NodePort (:30800)
    #  4) detected NodePort from cluster service
    local preferred="${IDS_API_URL:-}"
    if [[ -n "$preferred" ]] && curl -fsS --max-time 2 "${preferred%/}/health" >/dev/null 2>&1; then
        echo "${preferred%/}"
        return 0
    fi

    local candidates=(
        "http://localhost:8000"
        "http://127.0.0.1:8000"
        "http://localhost:30800"
        "http://127.0.0.1:30800"
    )
    local c
    for c in "${candidates[@]}"; do
        if curl -fsS --max-time 2 "${c}/health" >/dev/null 2>&1; then
            echo "$c"
            return 0
        fi
    done

    if command -v kubectl >/dev/null 2>&1; then
        local node_ip ids_port
        node_ip="$(get_node_ip 2>/dev/null || echo "localhost")"
        ids_port="$(get_service_nodeport ids-api-service smart-city 30800 2>/dev/null || echo "30800")"
        local derived="http://${node_ip}:${ids_port}"
        if curl -fsS --max-time 2 "${derived}/health" >/dev/null 2>&1; then
            echo "$derived"
            return 0
        fi
    fi

    return 1
}

ids_login_token() {
    local base_url="$1"
    local user="${2:-admin}"
    local pass="${3:-admin}"
    curl -fsS -X POST "${base_url%/}/api/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${user}\",\"password\":\"${pass}\"}" 2>/dev/null \
        | jq -r '.access_token // empty' 2>/dev/null || true
}

# ─────────────────────────────────────────────────────────────────────────────
# FILE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

backup_file() {
    local file=$1
    if [[ -f "$file" ]]; then
        local backup="${file}.backup.$(date +%s)"
        cp "$file" "$backup"
        log_info "Backed up: $file → $backup"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# VERSION CHECKING
# ─────────────────────────────────────────────────────────────────────────────

version_gte() {
    # Returns 0 if $1 >= $2, 1 otherwise
    printf '%s\\n%s' "$2" "$1" | sort -V -C
}

# ─────────────────────────────────────────────────────────────────────────────
# HELP & USAGE
# ─────────────────────────────────────────────────────────────────────────────

print_help() {
    echo -e "${BOLD}USAGE:${NC} $1"
    echo ""
    echo -e "${BOLD}OPTIONS:${NC}"
    echo "  --help            Show this help message"
    echo "  --debug           Enable debug logging"
    echo "  --dry-run         Show what would be done without doing it"
    echo "  --verbose         Enable verbose output"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# BANNER & INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

print_banner() {
    local title="$1"
    local version="${2:-v1.0}"
    
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${BOLD}$title${NC}${CYAN}                    ${NC}"
    echo -e "${CYAN}║${NC} Version: $version${CYAN}                                       ${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Script initialization - can be called at start of main script
# Usage: init_script "$0" "My Script Title"
init_script() {
    local script_name="$1"
    local title="${2:-Smart City IDS Script}"
    
    print_banner "$title"
    
    # Setup error trap
    trap cleanup_on_exit EXIT
    trap 'die "Script interrupted"' INT TERM
    
    log_debug "Starting: $script_name"
    log_debug "PID: $$"
    log_debug "User: $(whoami)"
    log_debug "PWD: $PWD"
}

cleanup_on_exit() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Script exited with code $exit_code"
    fi
    return $exit_code
}

# Export all functions
export -f log_debug log_info log_warn log_error log_section log_subsection
export -f die ensure_root ensure_command ensure_commands ensure_file ensure_kubeconfig
export -f k8s_cluster_ready k8s_wait_ready k8s_pod_ready k8s_deployment_ready
export -f get_system_ram_gb get_available_disk_gb get_cpu_cores
export -f get_node_ip is_port_open wait_port_open
export -f start_port_forward_checked stop_port_forward_checked
export -f confirm confirm_destructive
export -f pkill_safe
export -f timer_start timer_elapsed timer_format
export -f api_call backup_file version_gte
export -f resolve_ids_api_url ids_login_token
export -f print_help print_banner init_script cleanup_on_exit
