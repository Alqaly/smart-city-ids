import kopf
import logging
import os
import time

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)


PROM_TR_HANDLED_TOTAL = Counter(
    "smartcity_ids_operator_threatresponses_handled_total",
    "Total ThreatResponse resources handled by the operator.",
    ["result"],
)
PROM_ACTIONS_EXECUTED_TOTAL = Counter(
    "smartcity_ids_operator_actions_executed_total",
    "Total automated actions executed by the operator.",
    ["action"],
)
PROM_HANDLE_SECONDS = Histogram(
    "smartcity_ids_operator_handle_seconds",
    "ThreatResponse handler duration (seconds).",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5),
)


def _start_metrics_server() -> None:
    port_str = os.getenv("OPERATOR_METRICS_PORT", "8001")
    try:
        port = int(port_str)
    except ValueError:
        logger.warning("Invalid OPERATOR_METRICS_PORT=%r; metrics disabled", port_str)
        return

    try:
        start_http_server(port)
        logger.info("Operator Prometheus metrics exposed on :%s/metrics", port)
    except Exception as exc:
        logger.warning("Failed to start operator metrics server: %s", exc)


_start_metrics_server()


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except Exception:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")


@kopf.on.create("ids.smartcity.local", "v1alpha1", "threatresponses")
def handle_threatresponse(spec, namespace, name, patch, **kwargs):
    started = time.perf_counter()
    _load_kube_config()

    alert_id = spec.get("alertId")
    severity = spec.get("severity", 0)
    actions = spec.get("actions", [])

    logger.info(
        "Received ThreatResponse: %s (alertId=%s, severity=%s, actions=%s)",
        name,
        alert_id,
        severity,
        actions,
    )

    if not alert_id:
        patch.status["phase"] = "Failed"
        patch.status["appliedActions"] = []
        patch.status["reason"] = "spec.alertId is required"
        PROM_TR_HANDLED_TOTAL.labels(result="failed").inc()
        PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
        return

    if severity < 6:
        logger.info("Severity %s below threshold; no action taken", severity)
        patch.status["phase"] = "Pending"
        patch.status["appliedActions"] = []
        PROM_TR_HANDLED_TOTAL.labels(result="pending").inc()
        PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
        return

    v1 = client.CoreV1Api()
    try:
        v1.read_namespaced_pod(alert_id, namespace)
    except Exception as exc:
        logger.warning("Target pod not found: %s", exc)
        patch.status["phase"] = "Failed"
        patch.status["appliedActions"] = []
        patch.status["reason"] = "target_pod_not_found"
        PROM_TR_HANDLED_TOTAL.labels(result="failed").inc()
        PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
        return

    isolate_label_key = "ids.smartcity.local/isolate"
    isolate_label_value = "true"

    try:
        v1.patch_namespaced_pod(
            name=alert_id,
            namespace=namespace,
            body={"metadata": {"labels": {isolate_label_key: isolate_label_value}}},
        )
        logger.info("Labeled pod %s with %s=%s", alert_id, isolate_label_key, isolate_label_value)
    except Exception as exc:
        logger.error("Failed to label target pod: %s", exc)
        patch.status["phase"] = "Failed"
        patch.status["appliedActions"] = []
        patch.status["reason"] = "pod_label_failed"
        PROM_TR_HANDLED_TOTAL.labels(result="failed").inc()
        PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
        return

    net_api = client.NetworkingV1Api()
    np_name = f"isolate-{alert_id}"
    np_body = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": np_name, "namespace": namespace},
        "spec": {
            "podSelector": {"matchLabels": {isolate_label_key: isolate_label_value}},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [],
            "egress": [],
        },
    }

    try:
        net_api.create_namespaced_network_policy(namespace, np_body)
        logger.info("NetworkPolicy %s created to isolate pod %s", np_name, alert_id)
    except ApiException as exc:
        if exc.status == 409:
            logger.info("NetworkPolicy %s already exists; treating as success", np_name)
        else:
            logger.error("Failed to create NetworkPolicy: %s", exc)
            patch.status["phase"] = "Failed"
            patch.status["appliedActions"] = []
            patch.status["reason"] = "networkpolicy_create_failed"
            PROM_TR_HANDLED_TOTAL.labels(result="failed").inc()
            PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
            return
    except Exception as exc:
        logger.error("Failed to create NetworkPolicy: %s", exc)
        patch.status["phase"] = "Failed"
        patch.status["appliedActions"] = []
        patch.status["reason"] = "networkpolicy_create_failed"
        PROM_TR_HANDLED_TOTAL.labels(result="failed").inc()
        PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
        return

    patch.status["phase"] = "Executed"
    patch.status["appliedActions"] = ["isolate_pod"]
    PROM_TR_HANDLED_TOTAL.labels(result="executed").inc()
    PROM_ACTIONS_EXECUTED_TOTAL.labels(action="isolate_pod").inc()
    PROM_HANDLE_SECONDS.observe(time.perf_counter() - started)
    return


def main() -> None:
    kopf.run()


if __name__ == "__main__":
    main()
