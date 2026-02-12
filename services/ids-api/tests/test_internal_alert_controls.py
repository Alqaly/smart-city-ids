import sys
import types

from fastapi.testclient import TestClient


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
import main  # noqa: E402


client = TestClient(main.app)


def test_internal_alerts_use_dedup_to_avoid_repeat_llm_calls():
    calls = {"count": 0}

    async def fake_analyze(alert_dict):
        calls["count"] += 1
        return (
            {
                "summary": "ok",
                "severity": 5,
                "threat_type": "Unknown",
                "confidence": 0.7,
                "recommendations": [],
                "automated_actions": [],
            },
            "xai",
            0.01,
        )

    original = main.analyze_with_fallback
    main.analyze_with_fallback = fake_analyze
    try:
        if main.deduplicator:
            main.deduplicator.clear_cache()

        payload = {
            "output": "duplicate-test",
            "priority": "Warning",
            "rule": "INTERNAL DUP TEST",
            "time": "2026-02-11T12:00:00Z",
            "output_fields": {
                "container.name": "dup-test-pod",
                "proc.cmdline": "/bin/sh -c id",
            },
        }

        r1 = client.post("/api/alerts/internal", json=payload)
        r2 = client.post("/api/alerts/internal", json=payload)

        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert calls["count"] == 1, "LLM should only be called once for duplicate internal alerts"
    finally:
        main.analyze_with_fallback = original
