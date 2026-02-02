from src import validators

def test_validate_threat_spec_valid():
    spec = {
        'alertId': 'A1',
        'llmRecommendation': {'severity': 7},
        'targetPod': {'name': 'pod1', 'namespace': 'default'}
    }
    assert validators.validate_threat_spec(spec) is True

def test_validate_threat_spec_missing_field():
    spec = {
        'llmRecommendation': {'severity': 7},
        'targetPod': {'name': 'pod1', 'namespace': 'default'}
    }
    assert validators.validate_threat_spec(spec) is False

def test_validate_threat_spec_missing_severity():
    spec = {
        'alertId': 'A1',
        'llmRecommendation': {},
        'targetPod': {'name': 'pod1', 'namespace': 'default'}
    }
    assert validators.validate_threat_spec(spec) is False
