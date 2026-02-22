"""
Health and Dashboard UI Router
==============================

Serves two complementary concerns:

1. **Service discovery / root endpoint** (``GET /``) — Returns a JSON
   manifest describing the IDS API surface so that operators and
   automated probes can discover available endpoints at runtime.

2. **Dashboard UI** (``GET /ui``) — Serves the single-page security
   analyst dashboard (``static/index.html``) built with vanilla HTML/JS.
   The dashboard communicates with the API routes defined in sibling
   modules (alerts, governance, operator, IoT, LLM, metrics).

The module also exposes a ``_get_app_deps()`` helper that lazily imports
shared application state from ``api._state``.  This lazy-import pattern
is essential to break circular-import chains that would otherwise occur
because ``main.py`` registers routers *before* it finishes initialising
the dependency objects (LLM manager, K8s client, caches, etc.).
"""

import os
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# ── Router instance — no prefix; serves the root and /ui paths ────────────
router = APIRouter(tags=["health"])


def _get_app_deps():
    """Lazily import shared application-state singletons.

    This function exists to break **circular import chains**.  During
    application startup ``main.py`` first imports every router module
    (including this one) to register routes, and only *afterwards*
    creates and wires the runtime dependency objects (LLM manager,
    Kubernetes client, caches, etc.) by calling
    ``api._state.set_dependencies(…)``.  If the router modules imported
    ``api._state`` at module level the references would still be
    ``None`` because ``set_dependencies`` had not yet been called.

    By deferring the import to request time we guarantee the objects
    have been fully initialised.

    Returns:
        dict: A mapping of dependency name → live singleton reference
        with the following keys:

        * ``llm_manager``     — Multi-provider LLM orchestrator
        * ``k8s_automation``  — Kubernetes automation client
        * ``alert_cache``     — Recent-alert LRU cache
        * ``rate_limiter``    — Token-bucket rate limiter
        * ``circuit_breaker`` — Per-engine circuit breaker
        * ``request_queue``   — Bounded async request queue
        * ``deduplicator``    — Fingerprint-based alert deduplicator
        * ``metrics``         — In-memory metrics counters dict
        * ``STATIC_DIR``      — Absolute path to the static UI assets
    """
    # These module-level variables are set by main.py at startup
    # via ``api._state.set_dependencies()``.
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
async def root(request: Request):
    """Return a JSON service manifest for automated discovery.

    This is the default landing page of the IDS API.  It enumerates all
    major endpoint groups so that monitoring tools, CI smoke-tests, and
    human operators can verify that the service is reachable and discover
    the API surface without consulting external documentation.

    Returns:
        dict: Service name, version, operational status, LLM backend
        summary, and a list of principal endpoint paths.
    """
    base_url = str(request.base_url).rstrip("/")
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
            "/ui",
        ],
        "ui": f"{base_url}/ui",
    }


@router.get("/ui")
async def serve_ui():
    """Serve the single-page security analyst dashboard.

    The dashboard is a static HTML/JavaScript application located at
    ``static/index.html``.  It communicates with the IDS API via
    ``fetch()`` calls to the ``/api/*`` endpoints using the JWT token
    obtained from ``/api/auth/login``.

    If the static directory or ``index.html`` is missing (e.g., in a
    headless CI environment), a JSON fallback message is returned
    instead of a 404, allowing health probes to pass gracefully.

    Returns:
        FileResponse: The dashboard HTML page, or a JSON message if
        the static assets are not available.
    """
    deps = _get_app_deps()
    static = deps["STATIC_DIR"]
    if static:
        ui_file = os.path.join(static, "index.html")
        if os.path.exists(ui_file):
            return FileResponse(
                ui_file,
                media_type="text/html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
    return {"message": "UI not found"}
