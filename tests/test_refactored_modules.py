"""Unit tests for the refactored modular architecture.

Tests cover:
- Models (Pydantic validation)
- Infrastructure (auth, middleware, metrics definitions)
- API state helpers (classify_llm_error, is_protected_service, etc.)
- Config security improvements
"""

import sys
import os
import time
import asyncio

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ids-api", "src"))


# ── Model Tests ──────────────────────────────────────────────────────────────

class TestAlertModel:
    def test_valid_alert(self):
        from models.alert import Alert
        a = Alert(
            output="Test alert triggered",
            priority="Critical",
            rule="Test_Rule",
            time="2025-01-01T00:00:00Z",
            output_fields={"container.name": "test-pod"},
        )
        assert a.rule == "Test_Rule"
        assert a.priority == "Critical"

    def test_invalid_priority(self):
        from models.alert import Alert
        import pytest
        with pytest.raises(Exception):
            Alert(
                output="Test",
                priority="INVALID",
                rule="Test_Rule",
                time="2025-01-01T00:00:00Z",
            )

    def test_alert_response_fields(self):
        from models.alert import AlertResponse
        r = AlertResponse(status="processed", alert_id=1, severity=8, threat_type="Malware")
        assert r.status == "processed"
        assert r.severity == 8


class TestAuthModel:
    def test_login_request(self):
        from models.auth import LoginRequest
        req = LoginRequest(username="analyst", password="analyst")
        assert req.username == "analyst"

    def test_login_response(self):
        from models.auth import LoginResponse
        resp = LoginResponse(access_token="abc123", user="analyst")
        assert resp.token_type == "bearer"


class TestIoTModel:
    def test_iot_sensor_data(self):
        from models.iot import IoTSensorData
        d = IoTSensorData(
            device_id="pi-001",
            device_type="motion_sensor",
            event_type="heartbeat",
        )
        assert d.device_id == "pi-001"
        assert d.metadata == {}


# ── Infrastructure Auth Tests ────────────────────────────────────────────────

class TestAuth:
    def test_jwt_roundtrip(self):
        from infrastructure.auth import create_jwt_token, verify_jwt_token
        token = create_jwt_token("testuser")
        assert isinstance(token, str)
        username = verify_jwt_token(token)
        assert username == "testuser"

    def test_authenticate_valid(self):
        from infrastructure.auth import authenticate_user
        assert authenticate_user("analyst", "analyst") is True
        assert authenticate_user("operator", "operator") is True

    def test_authenticate_invalid(self):
        from infrastructure.auth import authenticate_user
        assert authenticate_user("bad", "bad") is False

    def test_invalid_token(self):
        from infrastructure.auth import verify_jwt_token
        result = verify_jwt_token("invalid_token_string")
        assert result is None


# ── Infrastructure Middleware Tests ──────────────────────────────────────────

class TestAlertCache:
    def test_cache_hit_miss(self):
        from infrastructure.middleware import AlertCache
        cache = AlertCache(max_size=10, ttl_seconds=60)
        alert = {"rule": "TestRule", "output_fields": {"proc.cmdline": "ls", "container.name": "test"}}
        assert cache.get(alert) is None
        cache.set(alert, {"severity": 5})
        result = cache.get(alert)
        assert result == {"severity": 5}
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_expiry(self):
        from infrastructure.middleware import AlertCache
        cache = AlertCache(max_size=10, ttl_seconds=0)  # 0s TTL = immediate expiry
        alert = {"rule": "R", "output_fields": {"proc.cmdline": "", "container.name": ""}}
        cache.set(alert, {"severity": 1})
        time.sleep(0.01)
        assert cache.get(alert) is None


class TestRateLimiter:
    def test_allows_within_limit(self):
        from infrastructure.middleware import RateLimiter
        rl = RateLimiter(requests_per_minute=60, burst_size=5)
        loop = asyncio.new_event_loop()
        allowed, reason = loop.run_until_complete(rl.acquire())
        assert allowed is True
        assert reason == "OK"
        loop.close()


class TestCircuitBreaker:
    def test_initial_state(self):
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(engines=["xai", "openai"])
        can, reason = cb.can_execute("xai")
        assert can is True

    def test_opens_after_failures(self):
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3, engines=["xai"])
        for _ in range(3):
            cb.record_failure("xai")
        can, reason = cb.can_execute("xai")
        assert can is False
        assert "OPEN" in reason

    def test_recovery(self):
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0, engines=["xai"])
        cb.record_failure("xai")
        cb.record_failure("xai")
        can, _ = cb.can_execute("xai")  # Should transition to half_open (timeout=0)
        cb.record_success("xai")
        assert cb.engine_stats["xai"]["state"] == "closed"


class TestRequestQueue:
    def test_queue_limits(self):
        from infrastructure.middleware import RequestQueue
        rq = RequestQueue(max_queue_size=2)
        loop = asyncio.new_event_loop()
        ok1, _ = loop.run_until_complete(rq.try_enqueue())
        ok2, _ = loop.run_until_complete(rq.try_enqueue())
        ok3, _ = loop.run_until_complete(rq.try_enqueue())
        assert ok1 and ok2
        assert not ok3
        loop.close()


# ── Metrics Definitions ─────────────────────────────────────────────────────

class TestMetrics:
    def test_all_core_metrics_exist(self):
        from infrastructure import metrics as m
        # Spot-check that key metrics are defined
        assert m.PROM_ALERTS_RECEIVED_TOTAL is not None
        assert m.PROM_ALERTS_PROCESSED_TOTAL is not None
        assert m.PROM_UPTIME_SECONDS is not None
        assert m.PROM_LLM_REQUESTS_TOTAL is not None
        assert m.PROM_IOT_DEVICES_ACTIVE is not None
        assert m.PROM_CRITICAL_ALERTS_TOTAL is not None


# ── State Helper Tests ───────────────────────────────────────────────────────

class TestStateHelpers:
    def test_classify_llm_error(self):
        from api._state import classify_llm_error
        assert "API key" in classify_llm_error("invalid api key provided")
        assert "Rate limited" in classify_llm_error("rate limit exceeded")
        assert "Unknown" in classify_llm_error("")

    def test_is_protected_service(self):
        from api._state import is_protected_service
        assert is_protected_service("healthcare-api-pod-abc") is True
        assert is_protected_service("ids-api-pod-xyz") is True
        assert is_protected_service("traffic-camera-pod") is False

    def test_can_execute_action_dry_run(self):
        from api._state import can_execute_action
        from config import Config
        original = Config.AUTOMATION_MODE
        Config.AUTOMATION_MODE = "dry-run"
        ok, reason = can_execute_action("isolate_pod", "test-pod")
        assert ok is False
        assert "DRY-RUN" in reason
        Config.AUTOMATION_MODE = original

    def test_classify_decision_outcome(self):
        from api._state import classify_decision_outcome
        assert classify_decision_outcome(9) == "malicious"
        assert classify_decision_outcome(6) == "suspicious"
        assert classify_decision_outcome(3) == "benign"

    def test_alert_trace_id(self):
        from api._state import alert_trace_id
        assert alert_trace_id(42) == "alert-42"


# ── Config Security ──────────────────────────────────────────────────────────

class TestConfigSecurity:
    def test_secret_key_not_hardcoded(self):
        from config import Config
        assert Config.SECRET_KEY != "smart-city-ids-demo-secret-change-in-production"
        assert len(Config.SECRET_KEY) >= 20  # Random token is 43+ chars
