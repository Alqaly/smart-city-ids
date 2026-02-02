import pytest
import kopf
from unittest.mock import patch, MagicMock
from src import handlers

def test_validate_and_execute_low_severity(caplog):
    body = {
        'metadata': {'name': 'threat1', 'namespace': 'default'}
    }
    spec = {
        'alertId': 'A1',
        'llmRecommendation': {'severity': 3},
        'targetPod': {'name': 'pod1', 'namespace': 'default'}
    }
    status = {}
    with caplog.at_level('INFO'):
        handlers.validate_and_execute(body, spec, status)
    assert "Severity too low" in caplog.text

@patch('src.handlers.kubernetes.client.CoreV1Api')
def test_validate_and_execute_valid_pod(mock_corev1, caplog):
    body = {
        'metadata': {'name': 'threat2', 'namespace': 'default'}
    }
    spec = {
        'alertId': 'A2',
        'llmRecommendation': {'severity': 8},
        'targetPod': {'name': 'pod2', 'namespace': 'default'}
    }
    status = {}
    mock_corev1.return_value.read_namespaced_pod.return_value = MagicMock()
    with caplog.at_level('INFO'):
        handlers.validate_and_execute(body, spec, status)
    assert "Validation passed" in caplog.text
