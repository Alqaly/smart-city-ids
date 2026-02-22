"""Demo control endpoints — IoT fleet scaling.

Synthetic “attack registry / chaos mode / injected alerts” endpoints were
removed. This project runs LIVE attacks only (real traffic that triggers
Falco/Suricata).
"""

import logging
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
