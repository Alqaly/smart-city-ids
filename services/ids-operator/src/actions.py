import kubernetes.client
import logging

logger = logging.getLogger(__name__)

def isolate_pod(pod_name, namespace):
    """
    Isolate a pod by adding a network policy or scaling to zero.
    """
    logger.info(f"[ACTION] Isolating pod: {pod_name} in {namespace}")
    # Example: scale deployment to zero replicas
    apps_v1 = kubernetes.client.AppsV1Api()
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace)
        for dep in deployments.items:
            if pod_name in dep.metadata.name:
                dep.spec.replicas = 0
                apps_v1.patch_namespaced_deployment(dep.metadata.name, namespace, dep)
                logger.info(f"  ✅ Scaled deployment {dep.metadata.name} to zero.")
                return True
    except Exception as e:
        logger.error(f"  ❌ Failed to isolate pod: {e}")
        return False
    return False

def scale_service(service_name, namespace, replicas=2):
    """
    Scale a service up (or down) by adjusting deployment replicas.
    """
    logger.info(f"[ACTION] Scaling service: {service_name} in {namespace} to {replicas} replicas")
    apps_v1 = kubernetes.client.AppsV1Api()
    try:
        dep = apps_v1.read_namespaced_deployment(service_name, namespace)
        dep.spec.replicas = replicas
        apps_v1.patch_namespaced_deployment(service_name, namespace, dep)
        logger.info(f"  ✅ Scaled deployment {service_name} to {replicas} replicas.")
        return True
    except Exception as e:
        logger.error(f"  ❌ Failed to scale service: {e}")
        return False
    return False
