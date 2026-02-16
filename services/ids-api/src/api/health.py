"""Health and system status router."""

import os
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["health"])


def _get_app_deps():
    """Lazy-import shared application state to avoid circular imports."""
    # These are set by main.py at startup via `set_dependencies()`
    from api._state import (
        llm_manager,
        k8s_automation,
        alert_cache,
        rate_limiter,
        circuit_breaker,
        request_queue,
        deduplicator,
        metrics_dict,
        STATIC_DIR,
    )
    return {
        "llm_manager": llm_manager,
        "k8s_automation": k8s_automation,
        "alert_cache": alert_cache,
        "rate_limiter": rate_limiter,
        "circuit_breaker": circuit_breaker,
        "request_queue": request_queue,
        "deduplicator": deduplicator,
        "metrics": metrics_dict,
        "STATIC_DIR": STATIC_DIR,
    }


@router.get("/")
async def root():
    return {
        "service": "Smart City IDS",
        "version": "1.0.0",
        "status": "operational",
        "llm": "Multi-provider LLM manager (priority + failover)",
        "endpoints": [
            "/health",
            "/api/alerts (GET/POST)",
            "/api/metrics",
            "/metrics",
            "/api/auth/login",
            "/api/operator/*",
        ],
        "ui": "http://localhost:8000/ui",
    }


@router.get("/ui")
async def serve_ui():
    """Serve the security analyst dashboard UI."""
    deps = _get_app_deps()
    static = deps["STATIC_DIR"]
    if static:
        ui_file = os.path.join(static, "index.html")
        if os.path.exists(ui_file):
            return FileResponse(ui_file, media_type="text/html")
    return {"message": "UI not found"}
