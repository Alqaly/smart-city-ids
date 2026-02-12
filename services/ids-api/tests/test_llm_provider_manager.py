import asyncio
import sys
from unittest.mock import patch

sys.path.insert(0, "services/ids-api/src")

from llm_providers.base import ProviderConfig
from llm_providers.manager import LLMManager


class _FakeProvider:
    def __init__(self, name: str, should_fail: bool = False, error_message: str = None):
        self.NAME = name
        self.model = f"{name}-model"
        self.base_url = f"https://{name}.example.com/v1"
        self._should_fail = should_fail
        self._error_message = error_message or f"{self.NAME} failed"
        self.calls = 0

    async def analyze(self, alert):
        self.calls += 1
        if self._should_fail:
            return {
                "status": "error",
                "error": self._error_message,
                "provider": self.NAME,
                "model": self.model,
                "latency_ms": 1,
            }
        return {
            "status": "success",
            "analysis": {"summary": "ok", "severity": 5},
            "provider": self.NAME,
            "model": self.model,
            "latency_ms": 1,
        }


def test_manager_respects_priority_order():
    providers = [_FakeProvider("openai"), _FakeProvider("gemini"), _FakeProvider("xai")]
    config = ProviderConfig(priority=["xai", "gemini", "openai"])

    with patch("llm_providers.manager.get_available_providers", return_value=providers):
        manager = LLMManager(config=config)

    assert manager.get_available_providers() == ["xai", "gemini", "openai"]


def test_manager_failover_and_runtime_stats():
    providers = [_FakeProvider("xai", should_fail=True), _FakeProvider("openai", should_fail=False)]
    config = ProviderConfig(priority=["xai", "openai"])

    with patch("llm_providers.manager.get_available_providers", return_value=providers):
        manager = LLMManager(config=config)

    result = asyncio.run(manager.analyze({"rule": "test"}))

    assert result["status"] == "success"
    assert result["provider"] == "openai"
    assert result["providers_tried"] == ["xai", "openai"]

    status = manager.get_status()
    assert status["details"]["xai"]["attempts"] == 1
    assert status["details"]["xai"]["failures"] == 1
    assert status["details"]["openai"]["attempts"] == 1
    assert status["details"]["openai"]["successes"] == 1


def test_provider_cooldown_after_quota_error():
    xai = _FakeProvider(
        "xai",
        should_fail=True,
        error_message="API error 429: resource has been exhausted: used all available credits",
    )
    openai = _FakeProvider("openai", should_fail=False)
    config = ProviderConfig(priority=["xai", "openai"])

    with patch("llm_providers.manager.get_available_providers", return_value=[xai, openai]):
        manager = LLMManager(config=config)
        manager.cooldown_seconds = 300

    first = asyncio.run(manager.analyze({"rule": "test"}))
    assert first["status"] == "success"
    assert first["providers_tried"] == ["xai", "openai"]
    assert xai.calls == 1
    assert openai.calls == 1

    second = asyncio.run(manager.analyze({"rule": "test2"}))
    assert second["status"] == "success"
    assert second["providers_tried"] == ["openai"]
    assert xai.calls == 1
    assert openai.calls == 2
