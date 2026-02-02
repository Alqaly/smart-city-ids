import pytest
import kopf
from unittest.mock import patch, MagicMock
from src import handlers, actions, validators

def test_threat_response_lifecycle(monkeypatch):
    # Simulate a full lifecycle: validate, execute, update status
    body = {
        'metadata': {'name': 'threatX', 'namespace': 'default'}
    }
    spec = {
        'alertId': 'A99',
        'llmRecommendation': {'severity': 9},
        'targetPod': {'name': 'pod99', 'namespace': 'default'}
    }
    status = {}
    monkeypatch.setattr(actions, 'isolate_pod', lambda n, ns: True)
    monkeypatch.setattr(validators, 'validate_threat_spec', lambda s: True)
    with patch('src.handlers.kubernetes.client.CoreV1Api') as mock_corev1:
        mock_corev1.return_value.read_namespaced_pod.return_value = MagicMock()
        handlers.validate_and_execute(body, spec, status)
        # If no exception, lifecycle passes
        assert True

def test_threat_response_invalid_spec(monkeypatch):
    body = {
        'metadata': {'name': 'threatY', 'namespace': 'default'}
    }
    spec = {
        'alertId': 'A100',
        'llmRecommendation': {},
        'targetPod': {'name': 'pod100', 'namespace': 'default'}
    }
    status = {}
    monkeypatch.setattr(validators, 'validate_threat_spec', lambda s: False)
    with pytest.raises(Exception):
        handlers.validate_and_execute(body, spec, status)
