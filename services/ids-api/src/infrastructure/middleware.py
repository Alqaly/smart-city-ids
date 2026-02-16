"""Production middleware — AlertCache, RateLimiter, CircuitBreaker, RequestQueue.

Extracted from main.py so they can be imported and tested independently.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Alert Cache (LRU with TTL)
# ═══════════════════════════════════════════════════════════════════════════

class AlertCache:
    """LRU cache for alert deduplication with TTL."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 60):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _get_hash(self, alert: dict) -> str:
        key = (
            f"{alert.get('rule', '')}:"
            f"{alert.get('output_fields', {}).get('proc.cmdline', '')}:"
            f"{alert.get('output_fields', {}).get('container.name', '')}"
        )
        return hashlib.md5(key.encode()).hexdigest()

    def get(self, alert: dict) -> Optional[dict]:
        alert_hash = self._get_hash(alert)
        if alert_hash in self.cache:
            entry = self.cache[alert_hash]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                self.hits += 1
                self.cache.move_to_end(alert_hash)
                return entry["analysis"]
            else:
                del self.cache[alert_hash]
        self.misses += 1
        return None

    def set(self, alert: dict, analysis: dict):
        alert_hash = self._get_hash(alert)
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[alert_hash] = {"analysis": analysis, "timestamp": time.time()}

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 1) if total > 0 else 0,
            "size": len(self.cache),
            "max_size": self.max_size,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limiter (token bucket)
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Token bucket rate limiter for API protection."""

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 20):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_refill = time.time()
        self.total_requests = 0
        self.rejected_requests = 0
        self.lock = asyncio.Lock()

    async def acquire(self) -> tuple:
        async with self.lock:
            now = time.time()
            time_passed = now - self.last_refill
            tokens_to_add = time_passed * (self.requests_per_minute / 60)
            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_refill = now
            self.total_requests += 1
            if self.tokens >= 1:
                self.tokens -= 1
                return True, "OK"
            else:
                self.rejected_requests += 1
                return (
                    False,
                    f"Rate limit exceeded. Max {self.requests_per_minute}/min, burst {self.burst_size}",
                )

    def stats(self) -> dict:
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "current_tokens": round(self.tokens, 2),
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "rejection_rate": (
                round(self.rejected_requests / self.total_requests * 100, 2)
                if self.total_requests > 0
                else 0
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for LLM API resilience."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3,
        engines: Optional[List[str]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

        tracked = engines or ["xai", "anthropic", "openai", "gemini", "kimi"]
        self.engine_stats: Dict[str, Dict] = {
            e: {"failures": 0, "successes": 0, "state": "closed"} for e in tracked
        }

    def can_execute(self, engine: str) -> tuple:
        stats = self.engine_stats.get(engine, {"failures": 0, "state": "closed"})
        if stats["state"] == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                stats["state"] = "half_open"
                self.half_open_calls = 0
                logger.info(f"Circuit breaker for {engine}: OPEN → HALF_OPEN")
            else:
                return False, f"Circuit OPEN for {engine} (cooling down)"
        if stats["state"] == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                return False, f"Circuit HALF_OPEN max calls reached for {engine}"
            self.half_open_calls += 1
        return True, "OK"

    def record_success(self, engine: str):
        stats = self.engine_stats.get(
            engine, {"failures": 0, "successes": 0, "state": "closed"}
        )
        stats["successes"] += 1
        stats["failures"] = 0
        if stats["state"] == "half_open":
            stats["state"] = "closed"
            logger.info(f"Circuit breaker for {engine}: HALF_OPEN → CLOSED")
        self.engine_stats[engine] = stats

    def record_failure(self, engine: str):
        stats = self.engine_stats.get(
            engine, {"failures": 0, "successes": 0, "state": "closed"}
        )
        stats["failures"] += 1
        self.last_failure_time = time.time()
        if stats["failures"] >= self.failure_threshold:
            stats["state"] = "open"
            logger.warning(
                f"Circuit breaker for {engine}: → OPEN (failures={stats['failures']})"
            )
        self.engine_stats[engine] = stats

    def get_stats(self) -> dict:
        return {
            "engines": self.engine_stats,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_sec": self.recovery_timeout,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Request Queue (burst handling)
# ═══════════════════════════════════════════════════════════════════════════

class RequestQueue:
    """Simple request queue for burst handling."""

    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.queue_size = 0
        self.total_queued = 0
        self.total_rejected = 0
        self.lock = asyncio.Lock()

    async def try_enqueue(self) -> tuple:
        async with self.lock:
            if self.queue_size >= self.max_queue_size:
                self.total_rejected += 1
                return False, f"Queue full ({self.max_queue_size} max)"
            self.queue_size += 1
            self.total_queued += 1
            return True, "OK"

    async def dequeue(self):
        async with self.lock:
            if self.queue_size > 0:
                self.queue_size -= 1

    def stats(self) -> dict:
        return {
            "current_size": self.queue_size,
            "max_size": self.max_queue_size,
            "total_queued": self.total_queued,
            "total_rejected": self.total_rejected,
        }
