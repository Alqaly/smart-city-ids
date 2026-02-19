"""Alert processing API router — the core pipeline of the Intrusion Detection System.

This module implements the central alert ingestion, analysis, and response pipeline
for the Smart City IDS.  It is the critical path through which every security event
flows: raw alerts arrive from Falco (container-runtime anomalies) or Suricata
(network-level signatures), are deduplicated to reduce redundant LLM calls, sent
through an LLM-based threat analyzer for severity scoring and classification, and
finally trigger automated Kubernetes remediation actions when thresholds are met.

Architecture overview (request flow)::

    Falco / Suricata  ──►  POST /api/alerts  or  /api/alerts/internal
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

- **POST /api/alerts/internal** — Unauthenticated endpoint restricted to
  cluster-internal traffic (Kubernetes NetworkPolicy enforced).  Used by
  in-cluster Falco/Suricata sidecars that already share the trust boundary.

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
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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
        can_execute_action,          # governance check: mode + protected-service guard
        classify_decision_outcome,   # maps severity int → outcome label for metrics
        compute_human_review_required,  # threshold check: does a human need to approve?
        detect_alert_source,         # heuristic: "falco" | "suricata" | "unknown"
        sse_broadcast,               # fans out an event dict to all connected SSE queues
    )
    # --- Governance mode (autonomous / supervised / manual) ---
    from governance import get_automation_mode

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
        "can_execute": can_execute_action,
        "classify_outcome": classify_decision_outcome,
        "human_review": compute_human_review_required,
        "detect_source": detect_alert_source,
        "broadcast": sse_broadcast,
        "get_mode": get_automation_mode,
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
    d["metrics"]["total_alerts"] += 1
    d["metrics"]["alerts_by_source"][source] += 1
    PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=alert.priority).inc()
    PROM_ALERTS_RAW_TOTAL.labels(source=source).inc()
    d["fatigue"]["raw_total"] += 1

    # ===================================================================
    # Stage 2: Per-rule alert rate limiting (flood prevention)
    # ===================================================================
    # The alert rate limiter is separate from the global request rate
    # limiter checked in the endpoint handlers.  It operates on *alert
    # content* (rule name + source) and suppresses repeated firings of
    # the same Falco/Suricata rule within a short window.  This prevents
    # a single noisy rule from consuming all LLM quota.
    if d["alert_rate_limiter"]:
        should_process, throttle_reason = d["alert_rate_limiter"].should_process(
            {"rule": alert.rule, "source": source}
        )
        if not should_process:
            logger.warning(f"Alert throttled: {alert.rule} (reason: {throttle_reason.value})")
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="throttled").inc()
            PROM_ALERTS_THROTTLED_TOTAL.labels(reason=throttle_reason.value).inc()
            # Persist the throttled alert for auditability (the operator can
            # review how many alerts were suppressed per rule)
            d["db"].add_throttled_alert(alert={**alert.dict(), "source": source}, throttle_reason=throttle_reason.value)
            await d["request_queue"].dequeue()  # release the queue slot
            return AlertResponse(
                status="throttled",
                alert_id=f"throttled-{int(time.time()*1000)}",
                severity=0,
                summary=f"Alert throttled: {throttle_reason.value}",
                threat_type="Throttled",
                automated_actions=[],
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

    if d["deduplicator"]:
        should_analyze, cached_analysis = d["deduplicator"].should_analyze(alert.dict())
        if not should_analyze and cached_analysis:
            # Cache HIT — reuse the previously computed LLM analysis
            analysis = cached_analysis
            llm_used = "cached"
            analysis_cached = True
            logger.info(f"✓ Alert dedup HIT: severity={analysis.get('severity')}")

    # ===================================================================
    # Stage 4: LLM-based threat analysis
    # ===================================================================
    # If deduplication did not yield a cached result, invoke the LLM engine.
    # ``analyze_with_fallback`` tries the primary engine (xAI Grok) and, on
    # failure, falls back to OpenAI or a conservative static analysis object
    # to ensure the pipeline never stalls on an LLM outage.
    if analysis is None:
        logger.info("Analyzing alert with LLM...")
        analysis, llm_used, llm_latency = await d["analyze"](alert.dict())
        # Update dedup-related metrics (this alert was *not* a duplicate)
        PROM_ALERTS_AFTER_DEDUP_TOTAL.inc()
        PROM_LLM_TRIAGED_ALERTS_TOTAL.inc()
        d["fatigue"]["after_dedup_total"] += 1
        d["fatigue"]["llm_triaged_total"] += 1
        # Cache the fresh analysis so future duplicates skip the LLM
        if d["deduplicator"]:
            d["deduplicator"].cache_analysis(alert.dict(), analysis)

    # --- Extract key fields from the LLM analysis for downstream logic ---
    severity = analysis.get("severity", 5)        # 1–10 scale; default 5 (medium)
    threat_type = analysis.get("threat_type", "Unknown")

    # Determine whether a human operator must review this alert before
    # any (further) automated action is taken.  The threshold is
    # configurable and depends on the current governance mode.
    requires_review = d["human_review"](int(severity))
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
    container_name = alert.output_fields.get("container.name", "")
    # Derive service name: strip hash suffix (e.g., "traffic-camera-abc123" → "traffic-camera")
    service_name = "-".join(container_name.split("-")[:-2]) if container_name.count("-") >= 2 else container_name.split("-")[0] if container_name else ""
    src_ip = alert.output_fields.get("fd.sip", alert.output_fields.get("src.ip", ""))

    # Get LLM-recommended actions
    llm_recommended_actions = analysis.get("automated_actions", []) if isinstance(analysis, dict) else []

    def _try_action(action_type, target, action_label=None):
        """Try to execute a K8s action with governance checks and verbose logging."""
        label = action_label or f"{action_type}({target})"
        can_exec, reason = d["can_execute"](action_type, target)
        if can_exec:
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
                "mode": d["get_mode"](),
                "triggered_by": llm_used,
                "severity": severity,
                "reason": f"LLM recommended '{action_type}' | Severity {severity}/10 | Threat: {threat_type}",
            })
            logger.info(
                f"✅ ACTION EXECUTED: {action_type} → {target} "
                f"(severity={severity}, threat={threat_type}, engine={llm_used}, "
                f"mode={d['get_mode']()}, latency={int((time.perf_counter() - started) * 1000)}ms)"
            )
        else:
            blocked_label = f"BLOCKED:{action_type}({target}):{reason}"
            actions_taken.append(blocked_label)
            PROM_ACTIONS_BLOCKED_TOTAL.labels(action=action_type, reason="blocked").inc()
            action_records.append({
                "action_type": action_type,
                "target_resource": target,
                "target_namespace": Config.K8S_NAMESPACE,
                "status": "blocked",
                "error_message": reason,
                "mode": d["get_mode"](),
                "triggered_by": llm_used,
                "severity": severity,
                "reason": f"Governance blocked: {reason}",
            })
            logger.warning(
                f"🚫 ACTION BLOCKED: {action_type} → {target} "
                f"(reason={reason}, severity={severity}, mode={d['get_mode']()})"
            )

    if d["k8s"]:
        # Execute LLM-recommended actions (validated against severity thresholds)
        executed_actions = set()

        # --- Critical severity (>= 8): isolate_pod + any LLM-recommended actions ---
        if severity >= 8 and container_name:
            if "isolate_pod" not in executed_actions:
                _try_action("isolate_pod", container_name, f"isolate_pod({container_name})")
                executed_actions.add("isolate_pod")

            # Execute additional LLM-recommended actions
            for action in llm_recommended_actions:
                if action in executed_actions:
                    continue
                if action == "block_ip" and src_ip:
                    _try_action("block_ip", src_ip, f"block_ip({src_ip})")
                    executed_actions.add("block_ip")
                elif action == "cordon_node" and container_name:
                    _try_action("cordon_node", container_name, f"cordon_node({container_name})")
                    executed_actions.add("cordon_node")
                elif action == "restart_pod" and container_name:
                    _try_action("restart_pod", container_name, f"restart_pod({container_name})")
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
                _try_action("scale_up", service_name, f"scale_up({service_name})")
                executed_actions.add("scale_up")

            # Execute additional LLM-recommended actions for high severity
            for action in llm_recommended_actions:
                if action in executed_actions:
                    continue
                if action == "isolate_pod" and container_name:
                    _try_action("isolate_pod", container_name, f"isolate_pod({container_name})")
                    executed_actions.add("isolate_pod")
                elif action == "block_ip" and src_ip:
                    _try_action("block_ip", src_ip, f"block_ip({src_ip})")
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
    alert_record = {
        "timestamp": alert.time,
        "source": source,
        "rule": alert.rule,
        "priority": alert.priority,
        "severity": severity,
        "summary": analysis.get("summary", ""),
        "threat_type": analysis.get("threat_type", ""),
        "recommendations": analysis.get("recommendations", []),
        "automated_actions": actions_taken,
        "raw_alert": alert.dict(),
        "analysis": analysis,
    }
    alert_id = d["db"].add_alert(alert_record)  # returns auto-generated unique ID
    alert_record["id"] = alert_id
    # Generate a deterministic trace ID for cross-referencing this alert
    # across the pipeline (logs, metrics, operator dashboard)
    trace_id = d["trace_id"](alert_id)
    alert_record["trace_id"] = trace_id

    # Persist the LLM analysis result as a separate record linked to the
    # alert.  This enables querying analysis history independently (e.g.,
    # comparing model performance over time).
    d["db"].add_analysis_result(
        alert_id,
        {
            "model": llm_used,
            "analysis": analysis,
            "analysis_time_ms": int(llm_latency * 1000),
            "confidence_score": analysis.get("confidence") if isinstance(analysis, dict) else None,
            "analyzed_at": datetime.now(),
        },
    )
    # Persist each automation action (executed or blocked) for auditability
    for action in action_records:
        action["alert_id"] = alert_id
        d["db"].add_automation_action(action)

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
            alert_data=alert.dict(),
            analysis=analysis,
            llm_model_used=llm_used,
            analysis_duration_ms=int(llm_latency * 1000),
            automation_mode=Config.AUTOMATION_MODE,
            protected_services=Config.PROTECTED_SERVICES,
        )
    except Exception as e:
        logger.warning(f"Could not build operator incident: {e}")

    # Append to the in-memory alert list for fast GET /api/alerts access
    d["alerts_db"].append(alert_record)

    # Recompute the running automation rate (percentage of alerts that
    # triggered at least one automated action)
    if d["metrics"]["total_alerts"] > 0:
        d["metrics"]["automation_rate"] = (d["metrics"]["automated_actions"] / d["metrics"]["total_alerts"]) * 100

    # Final pipeline-wide metrics
    PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc()
    PROM_API_REQUESTS_TOTAL.labels(endpoint=endpoint, method="POST", status="success").inc()
    PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)

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
        # Broadcast the result to all SSE-connected dashboard clients
        await d["broadcast"]({"type": "alert_processed", "source": d["detect_source"](alert), "endpoint": "/api/alerts", "trace_id": resp.trace_id, **resp.dict()})
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
            "raw_alert": alert.dict(), "analysis": {"error": str(e)},
        }
        alert_id = d["db"].add_alert(alert_record)
        d["alerts_db"].append({**alert_record, "id": alert_id})
        return AlertResponse(status="error", alert_id=alert_id, trace_id=d["trace_id"](alert_id), error=str(e))
    finally:
        # Always release the request queue slot, even on error, to prevent
        # queue starvation from leaked slots.
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── POST /api/alerts/internal (cluster-internal, no auth) ────────────────

@router.post("/api/alerts/internal")
async def process_alert_internal(alert: Alert) -> AlertResponse:
    """Process a security alert through the IDS pipeline (cluster-internal, no auth).

    This endpoint mirrors ``process_alert()`` but omits the bearer-token
    authentication requirement.  It is intended for in-cluster Falco/Suricata
    forwarders that already operate within the Kubernetes trust boundary and
    are protected by NetworkPolicy rules restricting access to the IDS API
    pod.

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
        # Broadcast with enriched payload for internal dashboard consumers
        await d["broadcast"]({
            "type": "alert_processed", "source": d["detect_source"](alert),
            "endpoint": "/api/alerts/internal", "rule": alert.rule,
            "priority": alert.priority, "output": alert.output,
            "output_fields": alert.output_fields,
            "container_name": (alert.output_fields or {}).get("container.name", ""),
            "trace_id": resp.trace_id, **resp.dict(),
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
            "priority": alert.priority, "severity": 0,
            "summary": f"Error: {str(e)}", "threat_type": "unknown",
            "recommendations": [], "automated_actions": [],
            "raw_alert": alert.dict(), "analysis": {"error": str(e)},
        }
        alert_id = d["db"].add_alert(alert_record)
        d["alerts_db"].append({**alert_record, "id": alert_id})
        return AlertResponse(status="error", alert_id=alert_id, trace_id=d["trace_id"](alert_id), error=str(e))
    finally:
        # Release the queue slot to prevent starvation
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── GET /api/alerts (paginated retrieval) ────────────────────────────────

@router.get("/api/alerts")
async def get_alerts(limit: int = 10, source: Optional[str] = None):
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

    Returns:
        dict: JSON object with keys ``total`` (total matching count),
        ``showing`` (number returned in this response), ``storage``
        (backend type, e.g., ``"sqlite"``), and ``alerts`` (list of
        alert dicts).
    """
    from api._state import db, alert_trace_id

    alerts = db.get_alerts(limit=limit, source=source)
    for a in alerts:
        if "trace_id" not in a or not a.get("trace_id"):
            a["trace_id"] = alert_trace_id(a.get("id", "unknown"))
    total = db.get_alert_count(source=source)
    return {
        "total": total,
        "showing": len(alerts),
        "storage": db.get_stats()["storage_type"],
        "alerts": alerts,
    }


# ─── POST /api/alerts/{id}/reanalyze — re-send alert to a specific LLM ───

@router.post("/api/alerts/{alert_id}/reanalyze")
async def reanalyze_alert(alert_id: int, engine: Optional[str] = None, _=Depends(verify_token)):
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
        result = await llm_manager.analyze(alert_dict, preferred_engine=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM analysis failed: {str(e)}")

    llm_duration = time.perf_counter() - started
    engine_used = result.get("provider") or result.get("engine", "unknown")

    if result.get("status") != "success":
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned error: {result.get('error', 'unknown')}"
        )

    analysis = result.get("analysis", {})
    new_severity = analysis.get("severity", 5)
    new_summary = analysis.get("summary", "")
    new_threat = analysis.get("threat_type", "Unknown")
    prev_severity = alert_record.get("severity", 0)

    # 4. Update the DB with the new analysis
    updated = db.update_alert_analysis(
        alert_id, analysis, new_severity, new_summary, new_threat
    )

    logger.info(
        f"Re-analyzed alert {alert_id} with {engine_used}: "
        f"severity {prev_severity} → {new_severity} ({llm_duration:.2f}s)"
    )

    return {
        "alert_id": alert_id,
        "engine_used": engine_used,
        "latency_s": round(llm_duration, 3),
        "previous_severity": prev_severity,
        "new_severity": new_severity,
        "analysis": analysis,
        "updated": updated,
    }
