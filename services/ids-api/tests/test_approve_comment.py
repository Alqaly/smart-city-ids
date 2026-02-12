import sys
import types
from fastapi.testclient import TestClient

# Minimal dependency shims for local environments missing optional SDKs.
try:
    import prometheus_client  # noqa: F401
except Exception:
    class _Metric:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            return None
        def set(self, *args, **kwargs):
            return None
        def observe(self, *args, **kwargs):
            return None
    sys.modules["prometheus_client"] = types.SimpleNamespace(
        CONTENT_TYPE_LATEST="text/plain; version=0.0.4",
        Counter=lambda *args, **kwargs: _Metric(),
        Gauge=lambda *args, **kwargs: _Metric(),
        Histogram=lambda *args, **kwargs: _Metric(),
        generate_latest=lambda: b"",
    )

try:
    import openai  # noqa: F401
except Exception:
    class _DummyAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))
        async def _create(self, *args, **kwargs):
            raise RuntimeError("openai SDK unavailable in local test environment")
    sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=_DummyAsyncOpenAI)

try:
    import kubernetes  # noqa: F401
except Exception:
    class _DummyApi:
        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                return None
            return _noop
    class _DummyApiException(Exception):
        def __init__(self, status=500, *args, **kwargs):
            super().__init__(*args)
            self.status = status
    kube_client_mod = types.SimpleNamespace(
        AppsV1Api=lambda *args, **kwargs: _DummyApi(),
        CoreV1Api=lambda *args, **kwargs: _DummyApi(),
        NetworkingV1Api=lambda *args, **kwargs: _DummyApi(),
    )
    kube_config_mod = types.SimpleNamespace(
        load_incluster_config=lambda: (_ for _ in ()).throw(Exception("no incluster config")),
        load_kube_config=lambda: None,
    )
    kube_rest_mod = types.SimpleNamespace(ApiException=_DummyApiException)
    sys.modules["kubernetes"] = types.SimpleNamespace(client=kube_client_mod, config=kube_config_mod)
    sys.modules["kubernetes.client"] = kube_client_mod
    sys.modules["kubernetes.config"] = kube_config_mod
    sys.modules["kubernetes.client.rest"] = kube_rest_mod

sys.path.insert(0, "services/ids-api/src")
from main import app
import governance


client = TestClient(app)


def test_approve_records_comment_via_public_api():
    login = client.post("/api/auth/login", json={"username": "operator", "password": "operator"})
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure governance is in MANUAL mode so actions are queued
    try:
        governance.governance.mode = governance.AutomationMode.MANUAL
    except Exception:
        pass

    # Request an automated action via the governance public helper (real code path)
    res = governance.request_automated_action(
        action_type="isolate_pod",
        target="pod-integration-test",
        severity=9,
        reason="integration-test",
    )

    assert res.get("status") == "pending_approval"
    action = res.get("action")
    assert action and action.get("id")
    action_id = action.get("id")

    # Approve via the HTTP API endpoint (real execution path)
    resp = client.post(
        f"/api/governance/approve/{action_id}?operator=integration_test&comment=LGTM",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "approved_and_executed"
    assert data.get("action", {}).get("operator_comment") in ("LGTM", "LGTM")
