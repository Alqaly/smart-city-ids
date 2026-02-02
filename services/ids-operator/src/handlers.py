import kopf
import kubernetes.client
from kubernetes.client.rest import ApiException
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@kopf.on.event(
    "ids.smartcity.local", "v1alpha1", "ThreatResponse",
    labels={"phase": "pending"}
)
def validate_and_execute(body, spec, status, **kwargs):
    """
    Main handler: Validate threat and execute security actions
    """
    name = body['metadata']['name']
    namespace = body['metadata']['namespace']
    logger.info(f"[HANDLER] Processing threat: {name}")
    try:
        alert_id = spec.get('alertId', 'unknown')
        llm_rec = spec.get('llmRecommendation', {})
        severity = llm_rec.get('severity', 0)
        target_pod = spec.get('targetPod', {})
        logger.info(f"  Alert: {alert_id}, Severity: {severity}")
        if severity < 5:
            logger.info(f"  Severity too low ({severity}). Skipping.")
            return
        v1 = kubernetes.client.CoreV1Api()
        pod_name = target_pod.get('name')
        pod_namespace = target_pod.get('namespace', namespace)
        try:
            pod = v1.read_namespaced_pod(pod_name, pod_namespace)
            logger.info(f"  ✅ Found target pod: {pod_name}")
        except ApiException as e:
            logger.warning(f"  ⚠️ Target pod not found: {e}")
            raise kopf.TemporaryError(f"Pod {pod_name} not found")
        kopf.patch(
            body,
            {'status': {
                'phase': 'Validating',
                'conditions': [{
                    'type': 'Validated',
                    'status': 'True',
                    'reason': 'ValidationPassed'
                }]
            }},
            body=body
        )
        logger.info(f"  ✅ Validation passed. Ready to execute actions.")
        # ...existing code for action execution will be added next...
    except Exception as e:
        logger.error(f"  ❌ Error: {e}")
        kopf.patch(body, {'status': {
            'phase': 'Failed',
            'lastError': str(e)
        }})
        raise

if __name__ == '__main__':
    kopf.run()
