import kopf
import logging

from kubernetes import client, config

logger = logging.getLogger(__name__)


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except Exception:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")


@kopf.on.create("ids.smartcity.local", "v1alpha1", "threatresponses")
def handle_threatresponse(spec, status, namespace, name, **kwargs):
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
        return {"phase": "Failed", "appliedActions": [], "reason": "spec.alertId is required"}

    if severity < 6:
        logger.info("Severity %s below threshold; no action taken", severity)
        return {"phase": "Pending", "appliedActions": []}

    v1 = client.CoreV1Api()
    try:
        v1.read_namespaced_pod(alert_id, namespace)
    except Exception as exc:
        logger.warning("Target pod not found: %s", exc)
        return {"phase": "Failed", "appliedActions": [], "reason": "target_pod_not_found"}

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
        return {"phase": "Failed", "appliedActions": [], "reason": "pod_label_failed"}

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
    except Exception as exc:
        logger.error("Failed to create NetworkPolicy: %s", exc)
        return {"phase": "Failed", "appliedActions": [], "reason": "networkpolicy_create_failed"}

    return {"phase": "Executed", "appliedActions": ["isolate_pod"]}


def main() -> None:
    kopf.run()


if __name__ == "__main__":
    main()
