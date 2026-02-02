import logging

logger = logging.getLogger(__name__)

def validate_threat_spec(spec):
    """
    Validate the incoming ThreatResponse spec for required fields and values.
    """
    required_fields = ['alertId', 'llmRecommendation', 'targetPod']
    for field in required_fields:
        if field not in spec:
            logger.error(f"[VALIDATOR] Missing required field: {field}")
            return False
    llm_rec = spec.get('llmRecommendation', {})
    if 'severity' not in llm_rec:
        logger.error("[VALIDATOR] Missing severity in llmRecommendation")
        return False
    return True
