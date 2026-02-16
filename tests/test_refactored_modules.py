"""Unit tests for the refactored modular architecture.

This test suite validates the correctness of every layer created
during the refactoring of the monolithic ``main.py`` into a
modular package structure.

Test categories (11 test classes, 24 tests):
    1. **Model validation**  (TestAlertModel, TestAuthModel, TestIoTModel)
       - Pydantic field validators, default values, rejection of invalid input.
    2. **Infrastructure auth** (TestAuth)
       - JWT creation/verification round-trip, demo credential checks.
    3. **Infrastructure middleware** (TestAlertCache, TestRateLimiter,
       TestCircuitBreaker, TestRequestQueue)
       - Cache hit/miss/expiry, token-bucket allows/rejects, circuit-breaker
         state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED), queue limits.
    4. **Metrics definitions** (TestMetrics)
       - Spot-check that all core Prometheus metrics are importable.
    5. **State helpers** (TestStateHelpers)
       - ``classify_llm_error``, ``is_protected_service``,
         ``can_execute_action`` (dry-run mode), ``classify_decision_outcome``.
    6. **Config security** (TestConfigSecurity)
       - Ensures ``SECRET_KEY`` is auto-generated (not hardcoded).

Running:
    cd services/ids-api/src && pytest ../../tests/ -v

Dependencies:
    - pytest
    - All packages in services/ids-api/src/requirements.txt
"""

import sys
import os
import time
import asyncio

# ── Path setup ────────────────────────────────────────────────────────────
# Add the IDS API source directory to sys.path so that imports like
# ``from models.alert import Alert`` resolve correctly in pytest.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ids-api", "src"))


# ══════════════════════════════════════════════════════════════════════════
# MODEL TESTS — Pydantic validation
# ══════════════════════════════════════════════════════════════════════════

class TestAlertModel:
    """Test the Alert Pydantic model validation rules."""

    def test_valid_alert(self):
        """A well-formed alert should parse without errors."""
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
        """An unknown priority value should raise a ValidationError."""
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
        """AlertResponse should accept severity and threat_type fields."""
        from models.alert import AlertResponse
        r = AlertResponse(status="processed", alert_id=1, severity=8, threat_type="Malware")
        assert r.status == "processed"
        assert r.severity == 8


class TestAuthModel:
    """Test the LoginRequest and LoginResponse models."""

    def test_login_request(self):
        """LoginRequest should accept username and password."""
        from models.auth import LoginRequest
        req = LoginRequest(username="analyst", password="analyst")
        assert req.username == "analyst"

    def test_login_response(self):
        """LoginResponse should default token_type to 'bearer'."""
        from models.auth import LoginResponse
        resp = LoginResponse(access_token="abc123", user="analyst")
        assert resp.token_type == "bearer"


class TestIoTModel:
    """Test the IoTSensorData model."""

    def test_iot_sensor_data(self):
        """IoTSensorData should accept minimal fields and default metadata to {}."""
        from models.iot import IoTSensorData
        d = IoTSensorData(
            device_id="pi-001",
            device_type="motion_sensor",
            event_type="heartbeat",
        )
        assert d.device_id == "pi-001"
        assert d.metadata == {}


# ══════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE AUTH TESTS — JWT round-trip and credential checks
# ══════════════════════════════════════════════════════════════════════════

class TestAuth:
    """Test JWT creation/verification and demo credential validation."""

    def test_jwt_roundtrip(self):
        """A token created for 'testuser' should verify back to 'testuser'."""
        from infrastructure.auth import create_jwt_token, verify_jwt_token
        token = create_jwt_token("testuser")
        assert isinstance(token, str)
        username = verify_jwt_token(token)
        assert username == "testuser"

    def test_authenticate_valid(self):
        """Valid demo credentials should return True."""
        from infrastructure.auth import authenticate_user
        assert authenticate_user("analyst", "analyst") is True
        assert authenticate_user("operator", "operator") is True

    def test_authenticate_invalid(self):
        """Invalid credentials should return False."""
        from infrastructure.auth import authenticate_user
        assert authenticate_user("bad", "bad") is False

    def test_invalid_token(self):
        """A garbage token should return None (not raise)."""
        from infrastructure.auth import verify_jwt_token
        result = verify_jwt_token("invalid_token_string")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE MIDDLEWARE TESTS — cache, rate-limiter, circuit-breaker, queue
# ══════════════════════════════════════════════════════════════════════════

class TestAlertCache:
    """Test the LRU+TTL AlertCache."""

    def test_cache_hit_miss(self):
        """First lookup = miss, after set = hit."""
        from infrastructure.middleware import AlertCache
        cache = AlertCache(max_size=10, ttl_seconds=60)
        alert = {"rule": "TestRule", "output_fields": {"proc.cmdline": "ls", "container.name": "test"}}
        assert cache.get(alert) is None          # Miss.
        cache.set(alert, {"severity": 5})
        result = cache.get(alert)
        assert result == {"severity": 5}          # Hit.
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_expiry(self):
        """Entries with TTL=0 should expire immediately."""
        from infrastructure.middleware import AlertCache
        cache = AlertCache(max_size=10, ttl_seconds=0)  # 0s TTL = immediate expiry.
        alert = {"rule": "R", "output_fields": {"proc.cmdline": "", "container.name": ""}}
        cache.set(alert, {"severity": 1})
        time.sleep(0.01)
        assert cache.get(alert) is None  # Should be expired.


class TestRateLimiter:
    """Test the token-bucket RateLimiter."""

    def test_allows_within_limit(self):
        """A fresh rate limiter should allow the first request."""
        from infrastructure.middleware import RateLimiter
        rl = RateLimiter(requests_per_minute=60, burst_size=5)
        loop = asyncio.new_event_loop()
        allowed, reason = loop.run_until_complete(rl.acquire())
        assert allowed is True
        assert reason == "OK"
        loop.close()


class TestCircuitBreaker:
    """Test the per-engine CircuitBreaker state machine."""

    def test_initial_state(self):
        """A new circuit breaker should start in CLOSED state (allow requests)."""
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(engines=["xai", "openai"])
        can, reason = cb.can_execute("xai")
        assert can is True

    def test_opens_after_failures(self):
        """After ``failure_threshold`` failures the circuit should OPEN."""
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=3, engines=["xai"])
        for _ in range(3):
            cb.record_failure("xai")
        can, reason = cb.can_execute("xai")
        assert can is False
        assert "OPEN" in reason

    def test_recovery(self):
        """After recovery timeout, a success should close the circuit."""
        from infrastructure.middleware import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0, engines=["xai"])
        cb.record_failure("xai")
        cb.record_failure("xai")
        can, _ = cb.can_execute("xai")  # Should transition to HALF_OPEN (timeout=0).
        cb.record_success("xai")
        assert cb.engine_stats["xai"]["state"] == "closed"


class TestRequestQueue:
    """Test the bounded RequestQueue."""

    def test_queue_limits(self):
        """Queue should accept up to max_size and reject after that."""
        from infrastructure.middleware import RequestQueue
        rq = RequestQueue(max_queue_size=2)
        loop = asyncio.new_event_loop()
        ok1, _ = loop.run_until_complete(rq.try_enqueue())
        ok2, _ = loop.run_until_complete(rq.try_enqueue())
        ok3, _ = loop.run_until_complete(rq.try_enqueue())
        assert ok1 and ok2       # First two accepted.
        assert not ok3           # Third rejected — queue full.
        loop.close()


# ══════════════════════════════════════════════════════════════════════════
# METRICS DEFINITIONS — importability spot-check
# ══════════════════════════════════════════════════════════════════════════

class TestMetrics:
    """Verify that all core Prometheus metrics are defined and importable."""

    def test_all_core_metrics_exist(self):
        """Spot-check key metrics from each category."""
        from infrastructure import metrics as m
        assert m.PROM_ALERTS_RECEIVED_TOTAL is not None     # Core alerts
        assert m.PROM_ALERTS_PROCESSED_TOTAL is not None    # Core alerts
        assert m.PROM_UPTIME_SECONDS is not None            # System health
        assert m.PROM_LLM_REQUESTS_TOTAL is not None        # LLM analysis
        assert m.PROM_IOT_DEVICES_ACTIVE is not None        # IoT devices
        assert m.PROM_CRITICAL_ALERTS_TOTAL is not None     # Security analysis


# ══════════════════════════════════════════════════════════════════════════
# STATE HELPER TESTS — shared utility functions from api._state
# ══════════════════════════════════════════════════════════════════════════

class TestStateHelpers:
    """Test utility functions exposed by api._state."""

    def test_classify_llm_error(self):
        """Error classifier should map known patterns to human-readable messages."""
        from api._state import classify_llm_error
        assert "API key" in classify_llm_error("invalid api key provided")
        assert "Rate limited" in classify_llm_error("rate limit exceeded")
        assert "Unknown" in classify_llm_error("")

    def test_is_protected_service(self):
        """Protected services (healthcare, IDS) should return True."""
        from api._state import is_protected_service
        assert is_protected_service("healthcare-api-pod-abc") is True
        assert is_protected_service("ids-api-pod-xyz") is True
        assert is_protected_service("traffic-camera-pod") is False

    def test_can_execute_action_dry_run(self):
        """In dry-run mode, all actions should be blocked."""
        from api._state import can_execute_action
        from config import Config
        original = Config.AUTOMATION_MODE
        Config.AUTOMATION_MODE = "dry-run"
        ok, reason = can_execute_action("isolate_pod", "test-pod")
        assert ok is False
        assert "DRY-RUN" in reason
        Config.AUTOMATION_MODE = original  # Restore original mode.

    def test_classify_decision_outcome(self):
        """Decision classifier should map severity to outcome category."""
        from api._state import classify_decision_outcome
        assert classify_decision_outcome(9) == "malicious"    # severity >= 8
        assert classify_decision_outcome(6) == "suspicious"   # severity 5-7
        assert classify_decision_outcome(3) == "benign"        # severity < 5

    def test_alert_trace_id(self):
        """Trace ID should be 'alert-{id}'."""
        from api._state import alert_trace_id
        assert alert_trace_id(42) == "alert-42"


# ══════════════════════════════════════════════════════════════════════════
# CONFIG SECURITY — ensure SECRET_KEY is auto-generated
# ══════════════════════════════════════════════════════════════════════════

class TestConfigSecurity:
    """Verify that the config security improvements are in place."""

    def test_secret_key_not_hardcoded(self):
        """SECRET_KEY must not be the old hardcoded demo value."""
        from config import Config
        assert Config.SECRET_KEY != "smart-city-ids-demo-secret-change-in-production"
        assert len(Config.SECRET_KEY) >= 20  # Random token is 43+ chars.
