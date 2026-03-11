#!/bin/bash
# LLM Control Library - Smart City IDS
# Simple version that works without API dependencies

[[ -n "${_LLM_CONTROL_LOADED:-}" ]] && return 0
_LLM_CONTROL_LOADED=1

# Colors using tput for better compatibility
if command -v tput >/dev/null 2>&1 && [ -t 1 ]; then
    ncolors=$(tput colors 2>/dev/null || echo 0)
    if [ $ncolors -ge 8 ]; then
        _r=$(tput setaf 1)
        _g=$(tput setaf 2)
        _y=$(tput setaf 3)
        _c=$(tput setaf 6)
        _b=$(tput bold)
        _n=$(tput sgr0)
    fi
fi
# Fallback if tput fails
_r=${_r:-''}
_g=${_g:-''}
_y=${_y:-''}
_c=${_c:-''}
_b=${_b:-''}
_n=${_n:-''}

# Logging
llm_info() { echo "${_g}[LLM]${_n} $1"; }
llm_warn() { echo "${_y}[LLM]${_n} $1"; }
llm_error() { echo "${_r}[LLM]${_n} $1"; }
llm_section() {
    echo ""
    echo "${_c}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_n}"
    echo "${_c}${_b}$1${_n}"
    echo "${_c}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_n}"
}

# Provider info
declare -A LLM_NAMES=(
    [xai]="xAI Grok"
    [anthropic]="Anthropic Claude"
    [openai]="OpenAI GPT"
    [gemini]="Google Gemini"
    [kimi]="Moonshot Kimi"
)

# Check environment keys
llm_check_env_keys() {
    local count=0
    echo ""
    echo "${_b}API Key Status:${_n}"
    echo ""
    
    for provider in xai anthropic openai gemini kimi; do
        local var_name="${provider^^}_API_KEY"
        local var_value="${!var_name:-}"
        
        if [[ -n "$var_value" && ${#var_value} -gt 10 ]]; then
            echo "  ${_g}✓${_n} ${LLM_NAMES[$provider]:-$provider}: configured (${#var_value} chars)"
            ((count++))
        else
            echo "  ${_r}✗${_n} ${LLM_NAMES[$provider]:-$provider}: not set"
        fi
    done
    
    echo ""
    echo "Total: $count/5 configured"
    
    if [[ $count -eq 0 ]]; then
        llm_warn "No LLM providers configured!"
        echo ""
        echo "Set at least one API key in .env:"
        echo "  XAI_API_KEY=your-key"
        echo "  OPENAI_API_KEY=your-key"
        return 1
    fi
    return 0
}

# Show priority
llm_show_priority() {
    local priority="${LLM_PRIORITY:-kimi,xai,anthropic,openai,gemini}"
    echo ""
    echo "${_b}Current Priority:${_n} ${_c}$priority${_n}"
    echo ""
    echo "Order (highest first):"
    IFS=',' read -ra arr <<< "$priority"
    local i=1
    for p in "${arr[@]}"; do
        echo "  $i. ${LLM_NAMES[$p]:-$p}"
        ((i++))
    done
}

# Set priority
llm_set_priority() {
    local new="$1"
    llm_section "Setting Priority"
    llm_info "New: $new"
    
    # Validate
    IFS=',' read -ra providers <<< "$new"
    for p in "${providers[@]}"; do
        if [[ -z "${LLM_NAMES[$p]:-}" ]]; then
            llm_error "Unknown provider: $p"
            return 1
        fi
    done
    
    export LLM_PRIORITY="$new"
    
    # Update .env
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        if grep -q "^LLM_PRIORITY=" "$PROJECT_ROOT/.env"; then
            sed -i "s/^LLM_PRIORITY=.*/LLM_PRIORITY=$new/" "$PROJECT_ROOT/.env"
        else
            echo "LLM_PRIORITY=$new" >> "$PROJECT_ROOT/.env"
        fi
        llm_info "Updated .env"
    fi
    
    llm_info "Priority set to: $new"
}

# Force provider
llm_force_provider() {
    local provider="$1"
    llm_section "Force Provider"
    
    if [[ -z "${LLM_NAMES[$provider]:-}" ]]; then
        llm_error "Unknown: $provider"
        return 1
    fi
    
    local var_name="${provider^^}_API_KEY"
    if [[ -z "${!var_name:-}" ]]; then
        llm_error "No API key for $provider"
        return 1
    fi
    
    llm_set_priority "$provider"
    echo ""
    echo "${_g}✓${_n} Using only: ${LLM_NAMES[$provider]}"
}

# Show full status
llm_show_status() {
    llm_section "LLM Provider Status"
    llm_check_env_keys || true
    llm_show_priority
    echo ""
    llm_info "To change: ./scripts/llm-manager.sh priority xai,openai,gemini"
}

# Check credits via IDS API (public endpoint)
# Usage: llm_check_credits [timeout_seconds=2.0] [pretty=true|false]
llm_check_credits() {
    local timeout="${1:-2.0}"
    local pretty="${2:-true}"
    local base=""
    if [[ -n "${LLM_CREDITS_URL:-}" ]]; then
        local url="${LLM_CREDITS_URL}"
    else
        if declare -F resolve_ids_api_url >/dev/null 2>&1; then
            base="$(resolve_ids_api_url || true)"
        fi
        base="${base:-http://localhost:8000}"
        local url="${base%/}/api/llm/credits/"
    fi

    if ! command -v curl >/dev/null 2>&1; then
        llm_error "curl is required for llm_check_credits"
        return 1
    fi

    local out
    out="$(curl -sS --max-time "$timeout" "$url" 2>/dev/null || true)"
    if [[ -z "$out" ]]; then
        llm_warn "Credits endpoint not reachable: $url"
        return 1
    fi

    if [[ "$pretty" == "true" ]] && command -v jq >/dev/null 2>&1; then
        echo "$out" | jq . || { echo "$out"; return 1; }
    else
        echo "$out"
    fi
    return 0
}

export -f llm_info llm_warn llm_error llm_section
export -f llm_check_env_keys llm_show_priority llm_set_priority llm_force_provider llm_show_status
export -f llm_check_credits
