"""Alert processing API router — the core pipeline of the Intrusion Detection System.

This module implements the central alert ingestion, analysis, and response pipeline
for the Smart City IDS.  It is the critical path through which every security event
flows: raw alerts arrive from Falco (container-runtime anomalies) or Suricata
(network-level signatures), are deduplicated to reduce redundant LLM calls, sent
through an LLM-based threat analyzer for severity scoring and classification, and
finally trigger automated Kubernetes remediation actions when thresholds are met.

Architecture overview (request flow)::

    Falco / Suricata  ──►  POST /api/alerts  or  /api/alerts/internal (token)
                                     │
                           ┌─────────▼──────────┐
                           │  Rate-limit check   │  token-bucket flood protection
                           │  Request queue      │  back-pressure / load-shedding
                           └─────────┬──────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  Alert rate-limiter │  per-rule throttling
                           │  Deduplication      │  content-hash cache
                           └─────────┬──────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  LLM analysis       │  xAI Grok / OpenAI
                           │  (or cache hit)     │  returns severity 1-10
                           └─────────┬──────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  Automated actions  │  severity >= 8 → isolate pod
                           │  (K8s orchestrator) │  severity >= 6 → scale service
                           └─────────┬──────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  Persist + notify   │  SQLite/Postgres, SSE, metrics
                           └─────────────────────┘

Endpoints exposed by this router:

- **POST /api/alerts** — Authenticated endpoint for external alert sources.
  Requires a valid bearer token (``verify_token`` dependency).  Used by Falco
  forwarders running outside the cluster or by manual/test submissions.

- **POST /api/alerts/internal** — Cluster-internal endpoint protected by a
    shared secret header (``X-IDS-Internal-Token``). Used by Falco/Suricata
    forwarders.

  Both POST routes delegate to ``_process_alert_core()`` which contains the
  shared processing pipeline, eliminating ~400 lines of previously duplicated
  code from the original monolithic ``main.py``.

- **GET /api/alerts** — Paginated retrieval of persisted alert records with
  optional source filtering.  Powers the dashboard history view.

- **GET /api/alerts/live** — Server-Sent Events (SSE) stream that pushes
  real-time alert processing results to connected dashboard clients.

Design decisions:

- The ``_deps()`` factory uses *lazy imports* from ``api._state`` to break
  circular import chains that arise because state objects reference models
  that reference config that references this router.
- Prometheus counters/histograms are incremented at every decision point so
  that Grafana dashboards reflect the full pipeline state (received → throttled
  → deduplicated → analyzed → acted-upon → persisted).
- Human-in-the-loop governance is enforced via ``can_execute_action()`` which
  consults the current automation mode (autonomous / supervised / manual) and
  protected-service allow-lists before permitting destructive K8s operations.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Standard-library and third-party imports
# ──────────────────────────────────────────────────────────────────────────────
import asyncio
import json as json_mod          # aliased to avoid shadowing common var names
import logging
import re
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import StreamingResponse

# ──────────────────────────────────────────────────────────────────────────────
# Project-internal imports: configuration, auth, and Prometheus metric handles
# ──────────────────────────────────────────────────────────────────────────────
from config import Config
from infrastructure.auth import verify_token
from infrastructure.metrics import (
    PROM_ACTIONS_BLOCKED_TOTAL,
    PROM_ACTIONS_EXECUTED_TOTAL,
    PROM_ALERT_PROCESSING_SECONDS,
    PROM_ALERTS_AFTER_DEDUP_TOTAL,
    PROM_ALERTS_PROCESSED_TOTAL,
    PROM_ALERTS_RAW_TOTAL,
    PROM_ALERTS_RECEIVED_TOTAL,
    PROM_ALERTS_THROTTLED_TOTAL,
    PROM_API_REQUESTS_TOTAL,
    PROM_AUTOMATED_DECISIONS,
    PROM_CRITICAL_ALERTS_TOTAL,
    PROM_HUMAN_REVIEW_REQUIRED_TOTAL,
    PROM_IOT_DEVICES_ACTIVE,
    PROM_K8S_PODS_ISOLATED_TOTAL,
    PROM_K8S_SCALE_OPERATIONS,
    PROM_LLM_DECISION_OUTCOME,
    PROM_LLM_TRIAGED_ALERTS_TOTAL,
    PROM_PROTECTED_SERVICE_HITS,
    PROM_RATE_LIMIT_REQUESTS,
    PROM_RATE_LIMIT_TOKENS,
    PROM_REQUEST_QUEUE_REJECTED,
    PROM_REQUEST_QUEUE_SIZE,
    PROM_SEVERITY_DISTRIBUTION,
    PROM_THREAT_TYPES_TOTAL,
    PROM_TIME_TO_MITIGATION,
)
from models.alert import Alert, AlertResponse  # Pydantic schemas for request/response validation

logger = logging.getLogger(__name__)

# FastAPI router — all routes in this module share the "alerts" OpenAPI tag
router = APIRouter(tags=["alerts"])


def _deps():
    """Lazily resolve shared application state and helper functions.

    This factory exists to break circular import chains.  The ``api._state``
    module is the single source of truth for mutable singletons (database
    handle, in-memory alert list, SSE client queues, etc.) that are
    initialised at application startup in ``main.py`` and shared across all
    API routers.

    By deferring the import to call-time (rather than module-level), we
    guarantee that ``_state`` is fully populated before any route handler
    accesses it.

    Returns:
        dict: A flat namespace mapping short keys to state objects and
        utility callables used throughout the processing pipeline.  The
        mapping is intentionally flat (no nesting) so callers can write
        ``d["db"]`` instead of navigating nested containers.
    """
    # --- Mutable state singletons (initialised once at app startup) ---
    from api._state import (
        alerts_db,              # in-memory list[dict] — recent alerts for fast /GET
        alert_fatigue_stats,    # counters for alert-fatigue dashboard panel
        alert_rate_limiter,     # per-rule flood suppression (optional)
        db,                     # DatabaseManager — SQLite or Postgres persistence
        deduplicator,           # content-hash dedup cache to skip redundant LLM calls
        k8s_automation,         # KubernetesAutomation — pod isolation / scaling
        metrics_dict,           # lightweight dict counters exposed via /api/metrics
        operator_interface,     # builds human-readable incident objects for the UI
        rate_limiter,           # global token-bucket rate limiter
        request_queue,          # bounded queue for back-pressure / load-shedding
        sse_clients,            # list[asyncio.Queue] — connected SSE dashboard clients
    )
    # --- Pure helper functions (stateless) ---
    from api._state import (
        alert_trace_id,              # generates a deterministic trace ID for an alert
        analyze_with_fallback,       # calls primary LLM, falls back to secondary
        add_audit_event,             # enterprise timeline/audit log helper
        append_alert_memory,         # bounded in-memory alert cache append helper
        classify_decision_outcome,   # maps severity int → outcome label for metrics
        compute_human_review_required,  # threshold check: does a human need to approve?
        detect_alert_source,         # heuristic: "falco" | "suricata" | "unknown"
        sse_broadcast,               # fans out an event dict to all connected SSE queues
    )
    # --- Governance mode (autonomous / supervised / manual) ---
    from governance import get_automation_mode, request_automated_action

    return {
        # State objects
        "alerts_db": alerts_db,
        "fatigue": alert_fatigue_stats,
        "alert_rate_limiter": alert_rate_limiter,
        "db": db,
        "deduplicator": deduplicator,
        "k8s": k8s_automation,
        "metrics": metrics_dict,
        "oi": operator_interface,
        "rate_limiter": rate_limiter,
        "request_queue": request_queue,
        "sse_clients": sse_clients,
        # Helper functions
        "trace_id": alert_trace_id,
        "analyze": analyze_with_fallback,
        "audit": add_audit_event,
        "append_alert": append_alert_memory,
        "classify_outcome": classify_decision_outcome,
        "human_review": compute_human_review_required,
        "detect_source": detect_alert_source,
        "broadcast": sse_broadcast,
        "get_mode": get_automation_mode,
        "request_action": request_automated_action,
    }


# ─── SSE Live Stream ────────────────────────────────────────────────────────

@router.get("/api/alerts/live")
async def alerts_live_stream():
    """Server-Sent Events (SSE) endpoint for real-time alert streaming.

    The dashboard UI opens a persistent HTTP connection to this endpoint and
    receives a continuous stream of ``text/event-stream`` messages.  Each
    message corresponds to a processed alert event, enabling the operator to
    observe the IDS pipeline output in real time without polling.

    Protocol details:

    - On connection, the server immediately sends an ``event: connected``
      frame so the client can confirm the stream is alive.
    - Alert events are sent as ``event: alert`` frames with a JSON payload.
    - A ``: keepalive`` comment line is emitted every 30 seconds of
      inactivity to prevent proxy/load-balancer timeouts (e.g., Nginx
      default ``proxy_read_timeout`` is 60s).
    - When the client disconnects (``CancelledError``), its queue is removed
      from the global ``sse_clients`` list to avoid memory leaks.

    The per-client queue has a ``maxsize=100`` cap to bound memory usage;
    if the client cannot consume events fast enough, backpressure will
    cause the broadcast to skip that client.

    Returns:
        StreamingResponse: An SSE stream with ``Cache-Control: no-cache`` and
        ``X-Accel-Buffering: no`` headers to disable proxy buffering.
    """
    from api._state import sse_clients

    # Create a bounded asyncio queue for this client connection
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    sse_clients.append(q)
    logger.info(f"SSE client connected (total: {len(sse_clients)})")

    async def event_generator():
        """Async generator yielding SSE-formatted text frames."""
        try:
            # Immediately confirm the connection is established
            yield (
                f"event: connected\n"
                f"data: {json_mod.dumps({'type': 'connected', 'message': 'Live pipeline stream connected', 'clients': len(sse_clients)})}\n\n"
            )
            while True:
                try:
                    # Block for up to 30s waiting for the next alert event
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"event: alert\ndata: {json_mod.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Send a comment-only keepalive to prevent proxy timeouts
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass  # Client disconnected — clean up below
        finally:
            # Remove this client’s queue to free memory
            if q in sse_clients:
                sse_clients.remove(q)
            logger.info(f"SSE client disconnected (remaining: {len(sse_clients)})")

    # Disable response buffering so events are pushed immediately
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─── Core alert processing logic (shared pipeline) ──────────────────────────────

async def _process_alert_core(alert: Alert, endpoint: str, started: float, d: dict) -> AlertResponse:
    """Unified alert processing pipeline shared by both POST routes.

    This function was extracted during a major refactor to consolidate ~400
    lines of duplicated processing logic that previously existed in separate
    ``process_alert()`` and ``process_alert_internal()`` handlers.  Both
    endpoints now delegate here after completing their own rate-limiting and
    request-queue admission checks.

    Processing stages (in order):

    1. **Source detection & metric bookkeeping** — Identify whether the alert
       originated from Falco or Suricata and update raw-count Prometheus
       counters.
    2. **Alert rate limiting** — Per-rule flood suppression.  If a rule is
       firing faster than the configured threshold, the alert is immediately
       returned as ``status=throttled`` without consuming LLM tokens.
    3. **Deduplication** — A content-hash cache is checked; if an identical
       alert was recently analyzed, the cached LLM result is reused.
    4. **LLM analysis** — The alert payload is sent to the configured LLM
       engine (xAI Grok or OpenAI) which returns a structured JSON object
       with severity (1–10), threat type, summary, and recommendations.
    5. **Automated actions** — Severity-driven Kubernetes remediation:
       - severity >= 8 → ``isolate_pod`` (cordon + network policy)
       - severity >= 6 → ``scale_up`` (increase replica count)
       Each action is gated by ``can_execute_action()`` which enforces
       governance mode and protected-service allow-lists.
    6. **Persistence** — The alert, LLM analysis, and any automation actions
       are written to the database and appended to the in-memory cache.
    7. **Operator incident** — A human-readable incident summary is built for
       the operator dashboard.
    8. **SSE broadcast** — All connected dashboard clients are notified
       (handled by the calling endpoint after this function returns).

    Args:
        alert: The validated Pydantic ``Alert`` model from the request body.
        endpoint: The originating route path (used for metric labels).
        started: High-resolution timestamp (``time.perf_counter()``) captured
            at request entry, used to compute end-to-end processing latency.
        d: Dependency dict returned by ``_deps()`` containing all shared state
            objects and helper functions.

    Returns:
        AlertResponse: A Pydantic response model containing the alert ID,
        trace ID, LLM analysis results, actions taken, processing time, and
        the LLM engine that was used.
    """

    # ===================================================================
    # Stage 1: Source detection & raw metric counters
    # ===================================================================
    # Identify whether this alert came from Falco (container runtime),
    # Suricata (network IDS), or an unknown/manual source.
    source = d["detect_source"](alert)
    request_trace_id = d["trace_id"](f"pre-{int(time.time() * 1000)}")
    d["metrics"]["total_alerts"] += 1
    d["metrics"]["alerts_by_source"][source] += 1
    PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=alert.priority).inc()
    PROM_ALERTS_RAW_TOTAL.labels(source=source).inc()
    d["fatigue"]["raw_total"] += 1
    d["audit"](
        "ALERT_RECEIVED",
        trace_id=request_trace_id,
        payload={"rule": alert.rule, "source": source, "priority": alert.priority},
    )

    # ===================================================================
    # Stage 2: Alert-level rate limiting (per-rule / per-source flood control)
    # ===================================================================
    # Deduplication alone prevents LLM cost explosions, but it still allows
    # duplicate alerts to flood the DB, SSE stream, and dashboard. Re-enable
    # the alert-level rate limiter here so repeated signatures (e.g. Suricata
    # HTTP flood) are recorded in `throttled_alerts` and suppressed from the
    # main alert stream once they exceed configured thresholds.
    if d.get("alert_rate_limiter") and source in ("falco", "suricata"):
        try:
            should_process, throttle_reason = d["alert_rate_limiter"].should_process(
                {"rule": alert.rule, "source": source}
            )
        except Exception as rl_exc:
            should_process, throttle_reason = True, None
            logger.warning(f"Alert rate limiter failed open for rule={alert.rule}: {rl_exc}")

        if not should_process:
            reason_val = getattr(throttle_reason, "value", str(throttle_reason or "unknown"))
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="throttled").inc()
            PROM_ALERTS_THROTTLED_TOTAL.labels(reason=reason_val).inc()
            d["audit"](
                "ALERT_THROTTLED",
                trace_id=request_trace_id,
                status="throttled",
                payload={"rule": alert.rule, "source": source, "reason": reason_val},
            )
            try:
                d["db"].add_throttled_alert(
                    alert={**alert.model_dump(), "source": source},
                    throttle_reason=reason_val,
                )
            except Exception as db_exc:
                logger.warning(f"Failed to persist throttled alert ({alert.rule}): {db_exc}")

            logger.warning(f"Alert throttled [{source}] rule={alert.rule} reason={reason_val}")
            return AlertResponse(
                status="throttled",
                alert_id=f"throttled-{int(time.time()*1000)}",
                trace_id=request_trace_id,
                severity=0,
                summary=f"Suppressed duplicate alert burst ({reason_val})",
                threat_type="Throttled",
                analysis={"status": "throttled", "reason": reason_val, "_llm_engine": "none"},
                actions_taken=[],
                processing_time_ms=int((time.perf_counter() - started) * 1000),
                llm_engine="none",
            )

    # ===================================================================
    # Stage 3: Deduplication (LLM cost reduction)
    # ===================================================================
    # The deduplicator computes a content hash over the alert payload and
    # checks whether an identical alert was analyzed within a configurable
    # TTL window.  If a cached analysis exists, the LLM call is skipped
    # entirely, saving both latency and API token costs.  This is critical
    # because Falco can emit hundreds of identical alerts per second during
    # a sustained attack.
    analysis = None        # will hold the LLM analysis dict once available
    llm_used = "none"      # tracks which engine produced the analysis
    analysis_cached = False  # flag for metrics: was the result from cache?
    llm_latency = 0.0      # wall-clock seconds spent in the LLM call

    # Only Falco and Suricata alerts are deduplicated (these are the only
    # sources that consume LLM credits. Manual/test alerts bypass dedup.)
    is_security_source = source in ("falco", "suricata")
    
    if d["deduplicator"] and is_security_source:
        should_analyze, cached_analysis = d["deduplicator"].should_analyze(alert.model_dump())
        d["audit"](
            "DEDUP_CHECK",
            trace_id=request_trace_id,
            status="hit" if (not should_analyze and cached_analysis) else "miss",
            payload={
                "cache_hit": bool(not should_analyze and cached_analysis),
                "source": source,
                "is_security_source": is_security_source,
            },
        )
        if not should_analyze and cached_analysis:
            # Cache HIT — reuse the previously computed LLM analysis
            analysis = cached_analysis
            llm_used = "cached"
            analysis_cached = True
            logger.info(f"✓ Alert dedup HIT [{source}]: severity={analysis.get('severity')}")

    # ===================================================================
    # Stage 4: LLM-based threat analysis
    # ===================================================================
    # If deduplication did not yield a cached result, invoke the LLM engine.
    # ``analyze_with_fallback`` tries the primary engine (xAI Grok) and, on
    # failure, falls back to OpenAI or a conservative static analysis object
    # to ensure the pipeline never stalls on an LLM outage.
    if analysis is None:
        # Always use cloud LLM — no cost ceiling bypass, no local fallback
        logger.info("Analyzing alert with LLM...")
        d["audit"]("LLM_ANALYSIS_START", trace_id=request_trace_id, payload={"rule": alert.rule})
        analysis, llm_used, llm_latency = await d["analyze"](alert.model_dump())

        # Update cost tracking
        if llm_used not in ("none", "cached"):
            from api._state import update_cost_tracking, _estimate_engine_call_cost
            cost = _estimate_engine_call_cost(llm_used)
            update_cost_tracking(cost)

        d["audit"](
            "LLM_ANALYSIS_END",
            trace_id=request_trace_id,
            severity=analysis.get("severity") if isinstance(analysis, dict) else None,
            payload={"engine": llm_used, "latency_ms": int(llm_latency * 1000)},
        )
        # Update dedup-related metrics (this alert was *not* a duplicate)
        PROM_ALERTS_AFTER_DEDUP_TOTAL.inc()
        PROM_LLM_TRIAGED_ALERTS_TOTAL.inc()
        d["fatigue"]["after_dedup_total"] += 1
        d["fatigue"]["llm_triaged_total"] += 1
        # Cache the fresh analysis so future duplicates skip the LLM
        if d["deduplicator"] and is_security_source:
            d["deduplicator"].cache_analysis(alert.model_dump(), analysis)
            logger.debug(f"Cached analysis for {source} alert: {alert.rule}")

    # --- Extract key fields from the LLM analysis for downstream logic ---
    severity = analysis.get("severity", 5)        # 1–10 scale; default 5 (medium)
    threat_type = analysis.get("threat_type", "Unknown")
    try:
        confidence = float(analysis.get("confidence", 0.0) if isinstance(analysis, dict) else 0.0)
    except Exception:
        confidence = 0.0

    # Determine whether a human operator must review this alert before
    # any (further) automated action is taken.  The threshold is
    # configurable and depends on the current governance mode.
    requires_review = d["human_review"](int(severity), confidence)
    d["audit"](
        "GOVERNANCE_DECISION",
        trace_id=request_trace_id,
        severity=int(severity),
        payload={
            "mode": d["get_mode"](),
            "requires_review": requires_review,
            "threat_type": threat_type,
        },
    )
    if requires_review:
        PROM_HUMAN_REVIEW_REQUIRED_TOTAL.inc()
        d["fatigue"]["human_review_required_total"] += 1
    else:
        d["fatigue"]["auto_handled_total"] += 1

    # Record severity and threat-type distributions for Grafana dashboards
    PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc()
    PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc()
    PROM_LLM_DECISION_OUTCOME.labels(outcome=d["classify_outcome"](severity)).inc()

    # Track critical alerts separately for the high-severity dashboard panel
    if severity >= 8:
        d["metrics"]["critical_alerts"] += 1
        PROM_CRITICAL_ALERTS_TOTAL.inc()

    # ===================================================================
    # Stage 5: Automated Kubernetes actions (LLM-recommended + severity-driven)
    # ===================================================================
    # The IDS executes automated responses based on BOTH LLM recommendations
    # and severity thresholds.  The LLM may recommend specific actions like
    # isolate_pod, scale_up, block_ip, cordon_node, restart_pod, or alert_team.
    # These are validated against governance rules before execution.
    #
    # Actions apply to ANY pod or service — not just predefined targets.
    # The container name is extracted from the alert and used dynamically.
    actions_taken = []   # human-readable list of action strings for the response
    action_records = []  # structured dicts persisted to the database

    # Extract target identifiers from alert (works for any pod/device)
    container_name = (
        alert.output_fields.get("container.name")
        or alert.output_fields.get("k8s.pod.name")
        or alert.output_fields.get("k8s.pod")
        or ""
    )
    # Derive workload/service name safely:
    # - Pod-like names: "<workload>-<rs-hash>-<pod-suffix>" -> "<workload>"
    # - Plain service/workload names remain unchanged (e.g., "traffic-camera")
    service_name = ""
    if container_name:
        parts = container_name.split("-")
        looks_like_pod_name = (
            len(parts) >= 3
            and re.fullmatch(r"[a-z0-9]{6,}", parts[-2] or "") is not None
            and re.fullmatch(r"[a-z0-9]{5,}", parts[-1] or "") is not None
        )
        service_name = "-".join(parts[:-2]) if looks_like_pod_name else container_name
    src_ip = alert.output_fields.get("fd.sip", alert.output_fields.get("src.ip", ""))

    # Get LLM-recommended actions
    llm_recommended_actions = analysis.get("automated_actions", []) if isinstance(analysis, dict) else []
    
    async def _execute_k8s_action(action_type: str, target: str):
        """Execute supported K8s actions when governance approves auto-execution."""
        if not d["k8s"]:
            return {"success": False, "error": "k8s_automation_unavailable"}
        if action_type == "isolate_pod":
            await d["k8s"].isolate_pod(target, Config.K8S_NAMESPACE)
            return {"success": True}
        if action_type == "scale_up":
            await d["k8s"].scale_deployment(target, 3, Config.K8S_NAMESPACE)
            return {"success": True}
        if action_type == "block_ip":
            workload_scope = service_name or container_name
            await d["k8s"].block_ip(target, Config.K8S_NAMESPACE, target_workload=workload_scope)
            return {"success": True}
        if action_type == "cordon_node":
            await d["k8s"].cordon_node(target)
            return {"success": True}
        return {"success": False, "error": f"unsupported_action:{action_type}"}

    async def _try_action(action_type, target, action_label=None):
        """Route LLM-recommended action through governance mode and execute if approved."""
        label = action_label or f"{action_type}({target})"
        decision = d["request_action"](
            action_type=action_type,
            target=target,
            severity=int(severity or 0),
            reason=f"LLM recommended '{action_type}' for rule '{alert.rule}'",
            recommended_by=llm_used,
            confidence=float(confidence or 0.0),
            alert_id=None,
            context={
                "target_workload": (service_name or container_name),
                "rule": alert.rule,
                "trace_id": request_trace_id,
            },
            execute_fn=None,
        )

        decision_status = str(decision.get("status") or "")
        explanation = str(decision.get("explanation") or decision.get("reason") or "")
        mode_now = d["get_mode"]()

        if decision_status == "executed":
            exec_result = await _execute_k8s_action(action_type, target)
            if exec_result.get("success"):
                actions_taken.append(label)
                d["metrics"]["automated_actions"] += 1
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action=action_type).inc()
                PROM_AUTOMATED_DECISIONS.labels(action_type=action_type).inc()
                PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                if action_type == "isolate_pod":
                    PROM_K8S_PODS_ISOLATED_TOTAL.inc()
                elif action_type == "scale_up":
                    PROM_K8S_SCALE_OPERATIONS.labels(operation="scale_up", service=target).inc()
                action_records.append({
                    "action_type": action_type,
                    "target_resource": target,
                    "target_namespace": Config.K8S_NAMESPACE,
                    "status": "executed",
                    "execution_time_ms": int((time.perf_counter() - started) * 1000),
                    "mode": mode_now,
                    "triggered_by": llm_used,
                    "severity": severity,
                    "reason": explanation or f"Governance auto-approved action in mode={mode_now}",
                })
                d["audit"](
                    "ACTION_EXECUTED",
                    trace_id=request_trace_id,
                    severity=int(severity),
                    payload={"action": action_type, "target": target, "mode": mode_now},
                )
            else:
                err = str(exec_result.get("error") or "execution_failed")
                blocked_label = f"FAILED:{action_type}({target}):{err}"
                actions_taken.append(blocked_label)
                PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="execution_failed").inc()
                action_records.append({
                    "action_type": action_type,
                    "target_resource": target,
                    "target_namespace": Config.K8S_NAMESPACE,
                    "status": "execution_failed",
                    "error_message": err,
                    "mode": mode_now,
                    "triggered_by": llm_used,
                    "severity": severity,
                    "reason": f"Governance approved but K8s execution failed: {err}",
                })
                d["audit"](
                    "ACTION_EXECUTED",
                    trace_id=request_trace_id,
                    severity=int(severity),
                    status="error",
                    payload={"action": action_type, "target": target, "error": err},
                )
                logger.warning(
                    f"⚠️ ACTION APPROVED BUT FAILED: {action_type} → {target} "
                    f"(error={err}, severity={severity}, mode={mode_now})"
                )
            return

        if decision_status == "pending_approval":
            actions_taken.append(f"PENDING:{label}")
            action_records.append({
                "action_type": action_type,
                "target_resource": target,
                "target_namespace": Config.K8S_NAMESPACE,
                "status": "pending_approval",
                "mode": mode_now,
                "triggered_by": llm_used,
                "severity": severity,
                "reason": explanation or "Queued for operator approval",
            })
            d["audit"](
                "ACTION_EXECUTED",
                trace_id=request_trace_id,
                severity=int(severity),
                status="pending_approval",
                payload={"action": action_type, "target": target, "mode": mode_now},
            )
            logger.info(
                f"⏳ ACTION QUEUED: {action_type} → {target} "
                f"(severity={severity}, mode={mode_now}, reason={explanation})"
            )
            return

        blocked_reason = explanation or "governance_rejected"
        blocked_label = f"BLOCKED:{action_type}({target}):{blocked_reason}"
        actions_taken.append(blocked_label)
        PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="governance").inc()
        action_records.append({
            "action_type": action_type,
            "target_resource": target,
            "target_namespace": Config.K8S_NAMESPACE,
            "status": "blocked",
            "error_message": blocked_reason,
            "mode": mode_now,
            "triggered_by": llm_used,
            "severity": severity,
            "reason": f"Governance blocked: {blocked_reason}",
        })
        d["audit"](
            "ACTION_EXECUTED",
            trace_id=request_trace_id,
            severity=int(severity),
            status="blocked",
            payload={"action": action_type, "target": target, "reason": blocked_reason},
        )
        logger.warning(
            f"🚫 ACTION BLOCKED: {action_type} → {target} "
            f"(reason={blocked_reason}, severity={severity}, mode={mode_now})"
        )

    if d["k8s"]:
        # Execute LLM-recommended actions (validated against severity thresholds)
        executed_actions = set()

        # --- Critical severity (>= 8): isolate_pod + any LLM-recommended actions ---
        if severity >= 8 and container_name:
            if "isolate_pod" not in executed_actions:
                await _try_action("isolate_pod", container_name, f"isolate_pod({container_name})")
                executed_actions.add("isolate_pod")

            # Execute additional LLM-recommended actions
            for action in llm_recommended_actions:
                if action in executed_actions:
                    continue
                if action == "block_ip" and src_ip:
                    await _try_action("block_ip", src_ip, f"block_ip({src_ip})")
                    executed_actions.add("block_ip")
                elif action == "cordon_node" and container_name:
                    await _try_action("cordon_node", container_name, f"cordon_node({container_name})")
                    executed_actions.add("cordon_node")
                elif action == "restart_pod" and container_name:
                    await _try_action("restart_pod", container_name, f"restart_pod({container_name})")
                    executed_actions.add("restart_pod")
                elif action == "alert_team":
                    actions_taken.append("alert_team")
                    action_records.append({
                        "action_type": "alert_team",
                        "target_resource": "soc-team",
                        "status": "executed",
                        "mode": d["get_mode"](),
                        "triggered_by": llm_used,
                        "severity": severity,
                        "reason": f"LLM recommended team alert for severity {severity} {threat_type}",
                    })
                    executed_actions.add("alert_team")

        # --- High severity (>= 6): scale_up + LLM-recommended actions ---
        elif severity >= 6 and service_name:
            if "scale_up" not in executed_actions:
                await _try_action("scale_up", service_name, f"scale_up({service_name})")
                executed_actions.add("scale_up")

            # Execute additional LLM-recommended actions for high severity
            for action in llm_recommended_actions:
                if action in executed_actions:
                    continue
                if action == "isolate_pod" and container_name:
                    await _try_action("isolate_pod", container_name, f"isolate_pod({container_name})")
                    executed_actions.add("isolate_pod")
                elif action == "block_ip" and src_ip:
                    await _try_action("block_ip", src_ip, f"block_ip({src_ip})")
                    executed_actions.add("block_ip")
                elif action == "alert_team":
                    actions_taken.append("alert_team")
                    action_records.append({
                        "action_type": "alert_team",
                        "target_resource": "soc-team",
                        "status": "executed",
                        "mode": d["get_mode"](),
                        "triggered_by": llm_used,
                        "severity": severity,
                        "reason": f"LLM recommended team alert for severity {severity} {threat_type}",
                    })
                    executed_actions.add("alert_team")

        # --- Medium severity (>= 4): only LLM-recommended non-destructive actions ---
        elif severity >= 4:
            for action in llm_recommended_actions:
                if action in executed_actions:
                    continue
                if action == "alert_team":
                    actions_taken.append("alert_team")
                    action_records.append({
                        "action_type": "alert_team",
                        "target_resource": "soc-team",
                        "status": "executed",
                        "mode": d["get_mode"](),
                        "triggered_by": llm_used,
                        "severity": severity,
                        "reason": f"LLM recommended monitoring for severity {severity}",
                    })
                    executed_actions.add("alert_team")

        # Log summary of all actions
        if actions_taken:
            logger.info(
                f"📋 AUTOMATION SUMMARY: alert_rule='{alert.rule}' severity={severity} "
                f"threat='{threat_type}' container='{container_name}' service='{service_name}' "
                f"actions={actions_taken} engine={llm_used} mode={d['get_mode']()}"
            )
        else:
            logger.info(
                f"📋 NO AUTOMATION: alert_rule='{alert.rule}' severity={severity} "
                f"threat='{threat_type}' (below threshold or no target identified)"
            )

    # ===================================================================
    # Stage 6: Persistence — write the alert, analysis, and actions to DB
    # ===================================================================
    # Build a denormalised alert record that captures the full processing
    # result.  This record is written to both the relational database
    # (SQLite/Postgres) for durable storage and the in-memory alerts_db
    # list for fast retrieval by GET /api/alerts.
    analysis_for_store = analysis
    if isinstance(analysis, dict):
        analysis_for_store = dict(analysis)
        # Persist the engine used inside the JSON analysis payload so the
        # dashboard can display it even if the SQL schema lacks a llm_engine
        # column (backward-compatible with existing deployments).
        analysis_for_store["_llm_engine"] = llm_used
        analysis_for_store["_analysis_source"] = (
            "cached" if llm_used == "cached" else ("llm" if llm_used not in ("none", "", None) else "none")
        )
        try:
            analysis_for_store["_analysis_latency_ms"] = int(llm_latency * 1000)
        except Exception:
            pass

    alert_record = {
        "timestamp": alert.time,
        "source": source,
        "rule": alert.rule,
        "priority": alert.priority,
        "container_name": container_name,
        "severity": severity,
        "summary": analysis.get("summary", ""),
        "threat_type": analysis.get("threat_type", ""),
        "recommendations": analysis.get("recommendations", []),
        "automated_actions": actions_taken,
        "raw_alert": alert.model_dump(),
        "analysis": analysis_for_store,
        "llm_engine": llm_used,
    }
    alert_id = d["db"].add_alert(alert_record)  # returns auto-generated unique ID
    alert_record["id"] = alert_id
    # Generate a deterministic trace ID for cross-referencing this alert
    # across the pipeline (logs, metrics, operator dashboard)
    trace_id = d["trace_id"](alert_id)
    request_trace_id = trace_id
    alert_record["trace_id"] = trace_id

    # Persist the LLM analysis result as a separate record linked to the
    # alert.  This enables querying analysis history independently (e.g.,
    # comparing model performance over time).
    d["db"].add_analysis_result(
        alert_id,
        {
            "model": llm_used,
            "analysis": analysis_for_store,
            "analysis_time_ms": int(llm_latency * 1000),
            "confidence_score": analysis.get("confidence") if isinstance(analysis, dict) else None,
            "analyzed_at": datetime.now(),
        },
    )
    # Persist each automation action (executed or blocked) for auditability
    for action in action_records:
        action["alert_id"] = alert_id
        d["db"].add_automation_action(action)

    if d["k8s"] and hasattr(d["k8s"], "create_threat_response"):
        for action in action_records:
            if action.get("status") != "executed":
                continue
            action_type = str(action.get("action_type") or "")
            if action_type not in {"isolate_pod", "scale_up", "block_ip", "cordon_node", "restart_pod"}:
                continue
            try:
                tr_result = await d["k8s"].create_threat_response(
                    alert_id=str(alert_id),
                    target_resource=str(action.get("target_resource") or ""),
                    severity=int(severity),
                    actions=[action_type],
                    namespace=Config.K8S_NAMESPACE,
                    trace_id=trace_id,
                )
                action["threatresponse"] = tr_result
                d["audit"](
                    "THREATRESPONSE_CREATED",
                    trace_id=trace_id,
                    severity=int(severity),
                    status="ok" if tr_result.get("success") else "error",
                    payload={
                        "action": action_type,
                        "target": action.get("target_resource"),
                        "result": tr_result,
                    },
                )
            except Exception as tr_exc:
                logger.warning(f"ThreatResponse creation failed for alert {alert_id}: {tr_exc}")

    # Add governance action steps to the alert trace so /api/audit/trace/alert-<id>
    # shows decision evidence (pending, executed, blocked) for examiner review.
    for action in action_records:
        d["audit"](
            "GOVERNANCE_ACTION",
            trace_id=trace_id,
            severity=int(action.get("severity") or severity or 0),
            status=str(action.get("status") or "unknown"),
            payload={
                "rule": alert.rule,
                "mode": action.get("mode") or d["get_mode"](),
                "action_type": action.get("action_type"),
                "target": action.get("target_resource"),
                "decision_status": action.get("status"),
                "reason": action.get("reason") or action.get("error_message"),
                "triggered_by": action.get("triggered_by") or llm_used,
            },
        )

    # ===================================================================
    # Stage 7: Operator incident view
    # ===================================================================
    # Build a human-readable incident summary that the operator dashboard
    # can display.  This includes contextual information like the LLM model
    # used, analysis duration, and whether the service is on the protected
    # list.  Failures here are non-fatal — the alert is already persisted.
    try:
        d["oi"].build_incident_for_operator(
            alert_id=alert_id,
            alert_data=alert.model_dump(),
            analysis=analysis,
            llm_model_used=llm_used,
            analysis_duration_ms=int(llm_latency * 1000),
            automation_mode=d["get_mode"](),
            protected_services=Config.PROTECTED_SERVICES,
        )
    except Exception as e:
        logger.warning(f"Could not build operator incident: {e}")

    # Append to the in-memory alert list for fast GET /api/alerts access
    d["append_alert"](alert_record)

    # Recompute the running automation rate (percentage of alerts that
    # triggered at least one automated action)
    if d["metrics"]["total_alerts"] > 0:
        d["metrics"]["automation_rate"] = (d["metrics"]["automated_actions"] / d["metrics"]["total_alerts"]) * 100

    # Final pipeline-wide metrics
    PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc()
    PROM_API_REQUESTS_TOTAL.labels(endpoint=endpoint, method="POST", status="success").inc()
    PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
    d["audit"](
        "ALERT_PROCESSED",
        trace_id=trace_id,
        severity=int(severity),
        payload={"llm_engine": llm_used, "actions_count": len(actions_taken)},
    )

    # ===================================================================
    # Stage 8: Construct and return the AlertResponse
    # ===================================================================
    return AlertResponse(
        status="processed",
        alert_id=alert_id,
        trace_id=trace_id,
        analysis=analysis,
        actions_taken=actions_taken,
        severity=severity,
        threat_type=threat_type,
        summary=analysis.get("summary", "") if isinstance(analysis, dict) else "",
        llm_engine=llm_used,
        processing_time_ms=int((time.perf_counter() - started) * 1000),
    )


def _record_blocked_action(action_type, target, reason, d, llm_used, records):
    """Record a blocked automation action with categorised Prometheus labels.

    When an automated action (e.g., ``isolate_pod``) is prevented by
    governance policy, this helper classifies the *reason* for blocking
    and increments the appropriate Prometheus counter so operators can
    monitor how often the safety rails engage.

    Three blocking categories are distinguished:

    - **protected_service**: The target is on the ``PROTECTED_SERVICES``
      allow-list, meaning the IDS is configured to never automatically
      act on it (human approval required).
    - **dry_run**: The system is in DRY-RUN governance mode, so all
      actions are logged but not executed.
    - **other**: Any other reason (e.g., RBAC failure, K8s API error).

    Args:
        action_type: The action that was blocked (e.g., ``"isolate_pod"``).
        target: The Kubernetes resource name targeted by the action.
        reason: Human-readable explanation of why the action was blocked.
        d: Dependency dict from ``_deps()``.
        llm_used: The LLM engine that recommended the action.
        records: Mutable list to which the structured action record is
            appended (will be persisted to the database by the caller).
    """
    if "protected service" in reason.lower():
        PROM_PROTECTED_SERVICE_HITS.labels(service=target.split("-")[0]).inc()
        PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="protected_service").inc()
    elif "DRY-RUN" in reason:
        PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="dry_run").inc()
    else:
        PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="other").inc()
    records.append({
        "action_type": action_type,
        "target_resource": target,
        "target_namespace": Config.K8S_NAMESPACE,
        "status": "blocked",
        "error_message": reason,
        "mode": d["get_mode"](),
        "triggered_by": llm_used,
    })


# ─── POST /api/alerts (authenticated external endpoint) ─────────────────

@router.post("/api/alerts")
async def process_alert(alert: Alert, request: Request, token=Depends(verify_token)) -> AlertResponse:
    """Process a security alert through the full IDS pipeline (authenticated).

    This is the primary ingestion endpoint for alert sources that reside
    *outside* the Kubernetes cluster (or that do not share the cluster
    trust boundary).  A valid bearer token is required — the ``verify_token``
    dependency rejects unauthenticated requests with HTTP 401.

    Before entering the shared ``_process_alert_core()`` pipeline, this
    handler enforces two layers of admission control:

    1. **Token-bucket rate limiter** — prevents any single client from
       overwhelming the API.  Returns HTTP 429 when tokens are exhausted.
    2. **Bounded request queue** — provides back-pressure when the server
       is saturated.  Returns HTTP 503 when the queue is full.

    On success, the processed result is broadcast to all connected SSE
    clients so the dashboard updates in real time.

    On error, a partial ``AlertResponse`` with ``status="error"`` is
    returned and the raw alert is still persisted for post-mortem analysis.

    Args:
        alert: Validated ``Alert`` Pydantic model from the JSON request body.
        request: The raw FastAPI ``Request`` (available for header inspection).
        token: Injected by the ``verify_token`` dependency; unused directly
            but its presence enforces authentication.

    Returns:
        AlertResponse: Full processing result including LLM analysis,
        severity score, actions taken, and processing latency.

    Raises:
        HTTPException(429): Rate limit exceeded.
        HTTPException(503): Request queue full (server overloaded).
    """
    d = _deps()

    # --- Admission control: global rate limiting ---
    rate_allowed, rate_reason = await d["rate_limiter"].acquire()
    PROM_RATE_LIMIT_TOKENS.set(d["rate_limiter"].tokens)  # gauge: remaining tokens
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()

    # --- Admission control: request queue back-pressure ---
    queue_ok, queue_reason = await d["request_queue"].try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)  # gauge: current depth
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")

    started = time.perf_counter()  # high-resolution timer for latency measurement
    PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="received").inc()

    try:
        resp = await _process_alert_core(alert, "/api/alerts", started, d)
        # Do not flood SSE with throttled duplicates; they are tracked via
        # metrics/throttled_alerts and represented by surviving alert rows.
        if resp.status != "throttled":
            await d["broadcast"]({"type": "alert_processed", "source": d["detect_source"](alert), "endpoint": "/api/alerts", "trace_id": resp.trace_id, **resp.model_dump()})
        return resp
    except Exception as e:
        # On processing failure, still persist the raw alert so no data is
        # lost, then return a degraded response with the error details.
        logger.error(f"Error: {e}")
        PROM_ALERTS_PROCESSED_TOTAL.labels(result="error").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="error").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        source = d["detect_source"](alert)
        alert_record = {
            "timestamp": alert.time, "source": source, "rule": alert.rule,
            "priority": alert.priority, "severity": 0,
            "summary": f"Error processing alert: {str(e)}", "threat_type": "unknown",
            "recommendations": [], "automated_actions": [],
            "raw_alert": alert.model_dump(), "analysis": {"error": str(e)},
        }
        alert_id = d["db"].add_alert(alert_record)
        d["append_alert"]({**alert_record, "id": alert_id})
        return AlertResponse(status="error", alert_id=alert_id, trace_id=d["trace_id"](alert_id), error=str(e))
    finally:
        # Always release the request queue slot, even on error, to prevent
        # queue starvation from leaked slots.
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── POST /api/alerts/internal (cluster-internal, token-gated) ─────────────

@router.post("/api/alerts/internal")
async def process_alert_internal(
    alert: Alert,
    x_ids_internal_token: Optional[str] = Header(default=None, alias="X-IDS-Internal-Token"),
) -> AlertResponse:
    """Process a security alert through the IDS pipeline (cluster-internal, token-gated).

    This endpoint mirrors ``process_alert()`` but uses a shared secret header
    (``X-IDS-Internal-Token``) instead of Bearer auth. It is intended for
    in-cluster Falco/Suricata forwarders.

    The SSE broadcast for this endpoint includes additional raw alert fields
    (``rule``, ``priority``, ``output``, ``output_fields``, ``container_name``)
    because internal consumers (e.g., the cluster-local dashboard) benefit
    from the extra context without the payload-size concerns of public APIs.

    Admission control (rate limiter + request queue) is still enforced to
    protect the LLM backend from internal flood scenarios (e.g., a
    misconfigured Falco rule emitting thousands of alerts per second).

    Args:
        alert: Validated ``Alert`` Pydantic model from the JSON request body.

    Returns:
        AlertResponse: Full processing result.

    Raises:
        HTTPException(429): Rate limit exceeded.
        HTTPException(503): Request queue full.
    """
    # Prevent synthetic injection: forwarders must include a shared secret.
    if not Config.IDS_INTERNAL_ALERT_TOKEN:
        raise HTTPException(status_code=503, detail="Internal ingest disabled (IDS_INTERNAL_ALERT_TOKEN not set)")
    if not x_ids_internal_token or x_ids_internal_token != Config.IDS_INTERNAL_ALERT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized internal ingest")

    d = _deps()

    # --- Admission control: rate limiting (same logic as authenticated route) ---
    rate_allowed, rate_reason = await d["rate_limiter"].acquire()
    PROM_RATE_LIMIT_TOKENS.set(d["rate_limiter"].tokens)  # gauge: remaining tokens
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()

    # --- Admission control: request queue back-pressure ---
    queue_ok, queue_reason = await d["request_queue"].try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)  # gauge: current depth
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")

    started = time.perf_counter()
    PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="received").inc()

    try:
        resp = await _process_alert_core(alert, "/api/alerts/internal", started, d)
        # Broadcast only non-throttled alerts to avoid UI/SSE storms.
        if resp.status != "throttled":
            await d["broadcast"]({
                "type": "alert_processed", "source": d["detect_source"](alert),
                "endpoint": "/api/alerts/internal", "rule": alert.rule,
                "priority": alert.priority, "output": alert.output,
                "output_fields": alert.output_fields,
                "container_name": (alert.output_fields or {}).get("container.name", ""),
                "trace_id": resp.trace_id, **resp.model_dump(),
            })
        return resp
    except Exception as e:
        # Persist raw alert on failure (mirrors authenticated endpoint logic)
        logger.error(f"Error: {e}")
        PROM_ALERTS_PROCESSED_TOTAL.labels(result="error").inc()
        PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="error").inc()
        PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        source = d["detect_source"](alert)
        alert_record = {
            "timestamp": alert.time, "source": source, "rule": alert.rule,
            "priority": alert.priority,
            "container_name": (
                alert.output_fields.get("container.name")
                or alert.output_fields.get("k8s.pod.name")
                or alert.output_fields.get("k8s.pod")
                or ""
            ),
            "severity": 0,
            "summary": f"Error: {str(e)}", "threat_type": "unknown",
            "recommendations": [], "automated_actions": [],
            "raw_alert": alert.model_dump(), "analysis": {"error": str(e)},
        }
        alert_id = d["db"].add_alert(alert_record)
        d["append_alert"]({**alert_record, "id": alert_id})
        return AlertResponse(status="error", alert_id=alert_id, trace_id=d["trace_id"](alert_id), error=str(e))
    finally:
        # Release the queue slot to prevent starvation
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── GET /api/alerts (paginated retrieval) ────────────────────────────────

@router.get("/api/alerts")
async def get_alerts(limit: int = 10, source: Optional[str] = None, include_legacy: bool = False):
    """Retrieve persisted alert records with optional source filtering.

    Powers the dashboard’s alert history table.  Results are ordered by
    most-recent-first and include the full analysis and action records.
    Each alert is enriched with a ``trace_id`` if one was not already
    stored (backward-compatibility with alerts ingested before trace IDs
    were introduced).

    Args:
        limit: Maximum number of alerts to return (default 10).  The
            dashboard typically requests 10–50 at a time.
        source: Optional filter by alert source (``"falco"``,
            ``"suricata"``, etc.).  When ``None``, all sources are returned.
        include_legacy: When ``True``, include archived legacy rows with
            missing provider metadata and severity ``0``. Default ``False``.

    Returns:
        dict: JSON object with keys ``total`` (total matching count),
        ``showing`` (number returned in this response), ``storage``
        (backend type, e.g., ``"sqlite"``), and ``alerts`` (list of
        alert dicts).
    """
    from api._state import db, alert_trace_id

    fetch_limit = limit if include_legacy else max(limit * 5, limit + 50)
    alerts = db.get_alerts(limit=fetch_limit, source=source)
    missing_engine_ids = []
    for a in alerts:
        if a.get("id") and not a.get("llm_engine"):
            missing_engine_ids.append(int(a["id"]))
    analysis_models_by_alert = {}
    if missing_engine_ids and hasattr(db, "get_latest_analysis_models"):
        try:
            analysis_models_by_alert = db.get_latest_analysis_models(missing_engine_ids) or {}
        except Exception:
            analysis_models_by_alert = {}
    for a in alerts:
        if "trace_id" not in a or not a.get("trace_id"):
            a["trace_id"] = alert_trace_id(a.get("id", "unknown"))
        # Backfill analysis metadata for dashboard rendering. Older alerts may
        # not have llm_engine as a top-level field even when they were analyzed.
        analysis = a.get("analysis")
        if isinstance(analysis, str):
            try:
                analysis = json_mod.loads(analysis)
                a["analysis"] = analysis
            except Exception:
                analysis = {}
        if not isinstance(analysis, dict):
            analysis = {}
        a["analysis_present"] = bool(analysis)
        if not a.get("llm_engine"):
            engine = (
                analysis.get("_llm_engine")
                or analysis.get("llm_engine")
                or analysis.get("provider")
                or analysis.get("engine")
            )
            if not engine and a.get("id"):
                engine = analysis_models_by_alert.get(int(a["id"]))
            if engine:
                a["llm_engine"] = engine
    legacy_hidden = 0
    if not include_legacy:
        filtered_alerts = []
        for a in alerts:
            analysis = a.get("analysis") or {}
            if isinstance(analysis, str):
                try:
                    analysis = json_mod.loads(analysis)
                except Exception:
                    analysis = {}
            llm_engine = str(a.get("llm_engine") or "").strip().lower()
            summary = str(a.get("summary") or analysis.get("summary") or "")
            is_legacy = (
                int(a.get("severity") or 0) == 0
                and llm_engine in ("", "none")
                and ("provider missing" in summary.lower() or "error: (404)" in summary.lower())
            )
            if is_legacy:
                legacy_hidden += 1
                continue
            filtered_alerts.append(a)
        alerts = filtered_alerts[:limit]
    else:
        alerts = alerts[:limit]
    total = db.get_alert_count(source=source)
    if not include_legacy:
        total = max(0, total - legacy_hidden)
    return {
        "total": total,
        "showing": len(alerts),
        "storage": db.get_stats()["storage_type"],
        "include_legacy": include_legacy,
        "legacy_hidden": legacy_hidden,
        "alerts": alerts,
    }


# ─── POST /api/alerts/{id}/reanalyze — re-send alert to a specific LLM ───

@router.post("/api/alerts/{alert_id}/reanalyze")
async def reanalyze_alert(
    alert_id: int,
    engine: Optional[str] = None,
    strict: bool = False,
    persist: bool = True,
    _=Depends(verify_token),
):
    """Re-analyze an existing alert using a specific (or default) LLM engine.

    Fetches the stored alert from the database, rebuilds the raw alert payload,
    and sends it through the LLM analysis pipeline — optionally targeting a
    specific engine (e.g. "xai", "openai", "kimi").

    The new analysis replaces the old one in the database so the dashboard
    reflects the updated severity, summary, and threat classification.

    Args:
        alert_id: Database ID of the alert to re-analyze.
        engine:   Optional LLM engine name to use (e.g. "xai", "openai",
              "kimi").  If omitted, uses the default priority
                  order with failover.
        strict:   When True, only the requested engine may answer.
        persist:  When False, do not overwrite the stored alert analysis.

    Returns:
        dict with keys: alert_id, engine_used, latency_s, previous_severity,
        new_severity, analysis (the full LLM result), and updated (bool).
    """
    from api._state import db, llm_manager

    # 1. Fetch the alert from DB
    alert_record = db.get_alert_by_id(alert_id)
    if not alert_record:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    # 2. Reconstruct the raw alert dict for the LLM
    raw = alert_record.get("raw_alert") or {}
    alert_dict = {
        "output": raw.get("output", alert_record.get("summary", "")),
        "rule": alert_record.get("rule", raw.get("rule", "Unknown")),
        "priority": alert_record.get("priority", raw.get("priority", "Warning")),
        "time": str(alert_record.get("timestamp", "")),
        "output_fields": raw.get("output_fields", {}),
        "source": alert_record.get("source", "unknown"),
    }

    # 3. Run LLM analysis (with optional preferred engine)
    started = time.perf_counter()
    try:
        result = await llm_manager.analyze(
            alert_dict,
            preferred_engine=engine,
            allow_fallback=not strict,
        )
    except TypeError:
        result = await llm_manager.analyze(alert_dict, preferred_engine=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM analysis failed: {str(e)}")

    llm_duration = time.perf_counter() - started
    engine_used = result.get("provider") or result.get("engine", "unknown")
    strict_satisfied = (not strict) or (result.get("status") == "success" and str(engine_used).lower() == str(engine or "").lower())

    if result.get("status") != "success":
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned error: {result.get('error', 'unknown')}"
        )
    if strict and not strict_satisfied:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Strict reanalysis requested '{engine}', but analysis executed on "
                f"'{engine_used}'. No fallback allowed."
            ),
        )

    analysis = result.get("analysis", {})
    usage = result.get("usage") or {}
    new_severity = analysis.get("severity", 5)
    new_summary = analysis.get("summary", "")
    new_threat = analysis.get("threat_type", "Unknown")
    prev_severity = alert_record.get("severity", 0)

    # 4. Update the DB with the new analysis when this is an operator action.
    updated = False
    if persist:
        updated = db.update_alert_analysis(
            alert_id, analysis, new_severity, new_summary, new_threat
        )

    logger.info(
        f"Re-analyzed alert {alert_id} with {engine_used}: "
        f"severity {prev_severity} → {new_severity} ({llm_duration:.2f}s), "
        f"strict={strict}, persist={persist}"
    )

    return {
        "alert_id": alert_id,
        "engine_used": engine_used,
        "latency_s": round(llm_duration, 3),
        "previous_severity": prev_severity,
        "new_severity": new_severity,
        "analysis": analysis,
        "usage": usage,
        "strict_requested": strict,
        "strict_satisfied": strict_satisfied,
        "persisted": persist,
        "updated": updated,
    }
