"""Demo control endpoints — IoT fleet scaling + Chaos Mode.

Provides two operator-facing API endpoints:

1. **IoT Fleet Scaling** — ``POST /api/iot/scale`` and ``GET /api/iot/scale``
   allow the dashboard to dynamically scale the 5 IoT emulator deployments
   up or down (1–10 replicas each).

2. **Chaos Mode** — ``POST /api/demo/chaos`` triggers the 13-scenario
   attack pipeline script (``scripts/attack-iot-pipeline.sh``) in a
   background process.  Returns immediately with a run-id.
"""

import logging
import os
import subprocess
import uuid
from typing import Dict, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["demo"])

# ── IoT service deployment names ─────────────────────────────────────────
# Maps logical service names to the Kubernetes Deployment object names.
IOT_DEPLOYMENTS = {
    "traffic-camera": "traffic-camera",
    "parking-system": "parking-system",
    "healthcare-api": "healthcare-api",
    "env-sensor": "env-sensor",
    "street-lighting": "street-lighting",
}

NAMESPACE = "smart-city"


def _k8s():
    """Get the K8s automation singleton."""
    from api._state import k8s_automation
    return k8s_automation


# ══════════════════════════════════════════════════════════════════════════════
# IoT Fleet Scale — GET (current replicas) + POST (set replicas)
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/api/iot/scale")
async def get_iot_scale():
    """Return current replica count for each IoT deployment."""
    k8s = _k8s()
    result: Dict[str, dict] = {}
    if not k8s:
        return {"error": "K8s not available", "services": {}}
    try:
        for svc, dep_name in IOT_DEPLOYMENTS.items():
            try:
                dep = k8s.apps_v1.read_namespaced_deployment(
                    name=dep_name, namespace=NAMESPACE
                )
                result[svc] = {
                    "replicas": dep.spec.replicas or 0,
                    "ready": dep.status.ready_replicas or 0,
                    "available": dep.status.available_replicas or 0,
                }
            except Exception as e:
                result[svc] = {"replicas": 0, "ready": 0, "error": str(e)}
    except Exception as e:
        logger.error(f"Failed to read deployments: {e}")
        return {"error": str(e), "services": {}}

    total_replicas = sum(s.get("replicas", 0) for s in result.values())
    total_ready = sum(s.get("ready", 0) for s in result.values())
    return {
        "services": result,
        "total_replicas": total_replicas,
        "total_ready": total_ready,
    }


@router.post("/api/iot/scale")
async def set_iot_scale(replicas: int = 3, service: Optional[str] = None):
    """Scale IoT deployments.

    Query params:
        replicas: Target replica count (1–10).  Default 3.
        service:  If provided, scale only this service; otherwise scale all.
    """
    replicas = max(1, min(10, replicas))
    k8s = _k8s()
    if not k8s:
        return {"error": "K8s not available"}

    targets = {service: IOT_DEPLOYMENTS[service]} if service and service in IOT_DEPLOYMENTS else IOT_DEPLOYMENTS
    results: Dict[str, str] = {}

    for svc, dep_name in targets.items():
        try:
            dep = k8s.apps_v1.read_namespaced_deployment(
                name=dep_name, namespace=NAMESPACE
            )
            dep.spec.replicas = replicas
            k8s.apps_v1.patch_namespaced_deployment(
                name=dep_name, namespace=NAMESPACE, body=dep
            )
            results[svc] = f"scaled to {replicas}"
            logger.info(f"Scaled {dep_name} to {replicas} replicas")
        except Exception as e:
            results[svc] = f"error: {e}"
            logger.error(f"Failed to scale {dep_name}: {e}")

    return {"replicas": replicas, "results": results}


# ══════════════════════════════════════════════════════════════════════════════
# Chaos Mode — triggers the attack-iot-pipeline.sh script
# ══════════════════════════════════════════════════════════════════════════════

# Track running chaos processes
_chaos_processes: Dict[str, subprocess.Popen] = {}


@router.post("/api/demo/chaos")
async def run_chaos_mode(mode: str = "quick"):
    """Trigger the IoT attack pipeline script in the background.

    Query params:
        mode: 'quick' (5 fast attacks) or 'full' (all 13 scenarios).
    """
    run_id = f"chaos-{uuid.uuid4().hex[:8]}"

    # Locate the script
    script_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "attack-iot-pipeline.sh"),
        "/app/scripts/attack-iot-pipeline.sh",
        os.path.join(os.getcwd(), "scripts", "attack-iot-pipeline.sh"),
    ]
    script_path = None
    for candidate in script_candidates:
        resolved = os.path.realpath(candidate)
        if os.path.isfile(resolved):
            script_path = resolved
            break

    if not script_path:
        return {"error": "attack-iot-pipeline.sh not found", "searched": script_candidates}

    args = ["bash", script_path]
    if mode == "quick":
        args.append("--quick")

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "IDS_API_URL": "http://localhost:8000"},
        )
        _chaos_processes[run_id] = proc
        logger.info(f"Chaos mode started: {run_id} (mode={mode}, pid={proc.pid})")
        return {
            "status": "started",
            "run_id": run_id,
            "mode": mode,
            "pid": proc.pid,
            "script": script_path,
        }
    except Exception as e:
        logger.error(f"Failed to start chaos mode: {e}")
        return {"error": str(e)}


@router.get("/api/demo/chaos/status")
async def chaos_status():
    """Check status of running chaos processes."""
    active = {}
    for rid, proc in list(_chaos_processes.items()):
        poll = proc.poll()
        if poll is None:
            active[rid] = {"status": "running", "pid": proc.pid}
        else:
            active[rid] = {"status": "finished", "exit_code": poll}
    return {"processes": active}
