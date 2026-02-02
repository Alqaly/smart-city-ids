import pytest
from src import actions
from unittest.mock import patch, MagicMock

def test_isolate_pod_success():
    with patch('src.actions.kubernetes.client.AppsV1Api') as mock_apps:
        mock_dep = MagicMock()
        mock_dep.metadata.name = 'pod1-deployment'
        mock_dep.spec.replicas = 1
        mock_apps.return_value.list_namespaced_deployment.return_value.items = [mock_dep]
        result = actions.isolate_pod('pod1', 'default')
        assert result is True
        assert mock_dep.spec.replicas == 0

def test_isolate_pod_failure():
    with patch('src.actions.kubernetes.client.AppsV1Api') as mock_apps:
        mock_apps.return_value.list_namespaced_deployment.return_value.items = []
        result = actions.isolate_pod('podX', 'default')
        assert result is False

def test_scale_service_success():
    with patch('src.actions.kubernetes.client.AppsV1Api') as mock_apps:
        mock_dep = MagicMock()
        mock_dep.spec.replicas = 1
        mock_apps.return_value.read_namespaced_deployment.return_value = mock_dep
        result = actions.scale_service('service1', 'default', replicas=3)
        assert result is True
        assert mock_dep.spec.replicas == 3

def test_scale_service_failure():
    with patch('src.actions.kubernetes.client.AppsV1Api') as mock_apps:
        mock_apps.return_value.read_namespaced_deployment.side_effect = Exception('not found')
        result = actions.scale_service('serviceX', 'default', replicas=2)
        assert result is False
