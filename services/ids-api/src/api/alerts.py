"""Alert processing API router.

Contains:
- POST /api/alerts (authenticated)
- POST /api/alerts/internal (cluster-internal, no auth)
- GET  /api/alerts
- GET  /api/alerts/live (SSE)
"""

import asyncio
import json as json_mod
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

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
from models.alert import Alert, AlertResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alerts"])


def _deps():
    from api._state import (
        alerts_db,
        alert_fatigue_stats,
        alert_rate_limiter,
        db,
        deduplicator,
        k8s_automation,
        metrics_dict,
        operator_interface,
        rate_limiter,
        request_queue,
        sse_clients,
    )
    from api._state import (
        alert_trace_id,
        analyze_with_fallback,
        can_execute_action,
        classify_decision_outcome,
        compute_human_review_required,
        detect_alert_source,
        sse_broadcast,
    )
    from governance import get_automation_mode

    return {
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
    """Server-Sent Events stream of real-time alert processing."""
    from api._state import sse_clients

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    sse_clients.append(q)
    logger.info(f"SSE client connected (total: {len(sse_clients)})")

    async def event_generator():
        try:
            yield (
                f"event: connected\n"
                f"data: {json_mod.dumps({'type': 'connected', 'message': 'Live pipeline stream connected', 'clients': len(sse_clients)})}\n\n"
            )
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"event: alert\ndata: {json_mod.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in sse_clients:
                sse_clients.remove(q)
            logger.info(f"SSE client disconnected (remaining: {len(sse_clients)})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─── Core alert processing logic ────────────────────────────────────────────

async def _process_alert_core(alert: Alert, endpoint: str, started: float, d: dict) -> AlertResponse:
    """Shared alert processing pipeline for both authenticated and internal endpoints."""
    source = d["detect_source"](alert)
    d["metrics"]["total_alerts"] += 1
    d["metrics"]["alerts_by_source"][source] += 1
    PROM_ALERTS_RECEIVED_TOTAL.labels(source=source, priority=alert.priority).inc()
    PROM_ALERTS_RAW_TOTAL.labels(source=source).inc()
    d["fatigue"]["raw_total"] += 1

    # ── Alert rate limiting (flood prevention) ──
    if d["alert_rate_limiter"]:
        should_process, throttle_reason = d["alert_rate_limiter"].should_process(
            {"rule": alert.rule, "source": source}
        )
        if not should_process:
            logger.warning(f"Alert throttled: {alert.rule} (reason: {throttle_reason.value})")
            PROM_ALERTS_PROCESSED_TOTAL.labels(result="throttled").inc()
            PROM_ALERTS_THROTTLED_TOTAL.labels(reason=throttle_reason.value).inc()
            d["db"].add_throttled_alert(alert={**alert.dict(), "source": source}, throttle_reason=throttle_reason.value)
            await d["request_queue"].dequeue()
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

    # ── Deduplication (LLM cost reduction) ──
    analysis = None
    llm_used = "none"
    analysis_cached = False
    llm_latency = 0.0

    if d["deduplicator"]:
        should_analyze, cached_analysis = d["deduplicator"].should_analyze(alert.dict())
        if not should_analyze and cached_analysis:
            analysis = cached_analysis
            llm_used = "cached"
            analysis_cached = True
            logger.info(f"✓ Alert dedup HIT: severity={analysis.get('severity')}")

    # ── LLM analysis ──
    if analysis is None:
        logger.info("Analyzing alert with LLM...")
        analysis, llm_used, llm_latency = await d["analyze"](alert.dict())
        PROM_ALERTS_AFTER_DEDUP_TOTAL.inc()
        PROM_LLM_TRIAGED_ALERTS_TOTAL.inc()
        d["fatigue"]["after_dedup_total"] += 1
        d["fatigue"]["llm_triaged_total"] += 1
        if d["deduplicator"]:
            d["deduplicator"].cache_analysis(alert.dict(), analysis)

    severity = analysis.get("severity", 5)
    threat_type = analysis.get("threat_type", "Unknown")
    requires_review = d["human_review"](int(severity))
    if requires_review:
        PROM_HUMAN_REVIEW_REQUIRED_TOTAL.inc()
        d["fatigue"]["human_review_required_total"] += 1
    else:
        d["fatigue"]["auto_handled_total"] += 1

    PROM_SEVERITY_DISTRIBUTION.labels(severity=str(severity)).inc()
    PROM_THREAT_TYPES_TOTAL.labels(threat_type=threat_type).inc()
    PROM_LLM_DECISION_OUTCOME.labels(outcome=d["classify_outcome"](severity)).inc()

    if severity >= 8:
        d["metrics"]["critical_alerts"] += 1
        PROM_CRITICAL_ALERTS_TOTAL.inc()

    # ── Automated actions ──
    actions_taken = []
    action_records = []

    if d["k8s"] and severity >= 8:
        container_name = alert.output_fields.get("container.name", "")
        if container_name:
            can_exec, reason = d["can_execute"]("isolate_pod", container_name)
            if can_exec:
                actions_taken.append("isolate_pod")
                d["metrics"]["automated_actions"] += 1
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action="isolate_pod").inc()
                PROM_AUTOMATED_DECISIONS.labels(action_type="isolate_pod").inc()
                PROM_K8S_PODS_ISOLATED_TOTAL.inc()
                PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                action_records.append({
                    "action_type": "isolate_pod",
                    "target_resource": container_name,
                    "target_namespace": Config.K8S_NAMESPACE,
                    "status": "executed",
                    "execution_time_ms": int((time.perf_counter() - started) * 1000),
                    "mode": d["get_mode"](),
                    "triggered_by": llm_used,
                })
            else:
                actions_taken.append(f"BLOCKED: {reason}")
                _record_blocked_action("isolate_pod", container_name, reason, d, llm_used, action_records)

    elif d["k8s"] and severity >= 6:
        service_name = alert.output_fields.get("container.name", "").split("-")[0]
        if service_name:
            can_exec, reason = d["can_execute"]("scale_up", service_name)
            if can_exec:
                actions_taken.append("scale_up")
                d["metrics"]["automated_actions"] += 1
                PROM_ACTIONS_EXECUTED_TOTAL.labels(action="scale_up").inc()
                PROM_AUTOMATED_DECISIONS.labels(action_type="scale_up").inc()
                PROM_K8S_SCALE_OPERATIONS.labels(operation="scale_up", service=service_name).inc()
                PROM_TIME_TO_MITIGATION.observe(time.perf_counter() - started)
                action_records.append({
                    "action_type": "scale_up",
                    "target_resource": service_name,
                    "target_namespace": Config.K8S_NAMESPACE,
                    "status": "executed",
                    "execution_time_ms": int((time.perf_counter() - started) * 1000),
                    "mode": d["get_mode"](),
                    "triggered_by": llm_used,
                })
            else:
                actions_taken.append(f"BLOCKED: {reason}")
                PROM_ACTIONS_BLOCKED_TOTAL.labels(action="scale_up", reason="blocked").inc()
                action_records.append({
                    "action_type": "scale_up",
                    "target_resource": service_name,
                    "target_namespace": Config.K8S_NAMESPACE,
                    "status": "blocked",
                    "error_message": reason,
                    "mode": d["get_mode"](),
                    "triggered_by": llm_used,
                })

    # ── Persist ──
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
    alert_id = d["db"].add_alert(alert_record)
    alert_record["id"] = alert_id
    trace_id = d["trace_id"](alert_id)
    alert_record["trace_id"] = trace_id

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
    for action in action_records:
        action["alert_id"] = alert_id
        d["db"].add_automation_action(action)

    # Operator incident view
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

    d["alerts_db"].append(alert_record)

    if d["metrics"]["total_alerts"] > 0:
        d["metrics"]["automation_rate"] = (d["metrics"]["automated_actions"] / d["metrics"]["total_alerts"]) * 100

    PROM_ALERTS_PROCESSED_TOTAL.labels(result="success").inc()
    PROM_API_REQUESTS_TOTAL.labels(endpoint=endpoint, method="POST", status="success").inc()
    PROM_ALERT_PROCESSING_SECONDS.observe(time.perf_counter() - started)

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
    """Record a blocked action with appropriate Prometheus labels."""
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


# ─── POST /api/alerts (authenticated) ───────────────────────────────────────

@router.post("/api/alerts")
async def process_alert(alert: Alert, request: Request, token=Depends(verify_token)) -> AlertResponse:
    """Process security alert with LLM analysis (authenticated)."""
    d = _deps()
    rate_allowed, rate_reason = await d["rate_limiter"].acquire()
    PROM_RATE_LIMIT_TOKENS.set(d["rate_limiter"].tokens)
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()

    queue_ok, queue_reason = await d["request_queue"].try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")

    started = time.perf_counter()
    PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts", method="POST", status="received").inc()

    try:
        resp = await _process_alert_core(alert, "/api/alerts", started, d)
        await d["broadcast"]({"type": "alert_processed", "source": d["detect_source"](alert), "endpoint": "/api/alerts", "trace_id": resp.trace_id, **resp.dict()})
        return resp
    except Exception as e:
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
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── POST /api/alerts/internal (no auth) ────────────────────────────────────

@router.post("/api/alerts/internal")
async def process_alert_internal(alert: Alert) -> AlertResponse:
    """Process security alert (no auth - cluster-internal only)."""
    d = _deps()
    rate_allowed, rate_reason = await d["rate_limiter"].acquire()
    PROM_RATE_LIMIT_TOKENS.set(d["rate_limiter"].tokens)
    if not rate_allowed:
        PROM_RATE_LIMIT_REQUESTS.labels(result="rejected").inc()
        raise HTTPException(status_code=429, detail=rate_reason)
    PROM_RATE_LIMIT_REQUESTS.labels(result="allowed").inc()

    queue_ok, queue_reason = await d["request_queue"].try_enqueue()
    PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)
    if not queue_ok:
        PROM_REQUEST_QUEUE_REJECTED.inc()
        raise HTTPException(status_code=503, detail=f"Server overloaded: {queue_reason}")

    started = time.perf_counter()
    PROM_API_REQUESTS_TOTAL.labels(endpoint="/api/alerts/internal", method="POST", status="received").inc()

    try:
        resp = await _process_alert_core(alert, "/api/alerts/internal", started, d)
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
        await d["request_queue"].dequeue()
        PROM_REQUEST_QUEUE_SIZE.set(d["request_queue"].queue_size)


# ─── GET /api/alerts ────────────────────────────────────────────────────────

@router.get("/api/alerts")
async def get_alerts(limit: int = 10, source: Optional[str] = None):
    """Get alerts from database."""
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
