"""Production middleware — AlertCache, RateLimiter, CircuitBreaker, RequestQueue.

This module contains the four resilience / performance primitives that
protect the IDS API from overload and cascading failures.  Each class
was extracted from the original monolithic ``main.py`` during the
refactoring so they can be imported and **unit-tested independently**.

Classes:
    AlertCache      – LRU cache with TTL for SSE alert deduplication.
    RateLimiter     – Token-bucket algorithm for HTTP request throttling.
    CircuitBreaker  – Per-engine circuit breaker for LLM API resilience.
    RequestQueue    – Bounded async queue for burst absorption.

Design decisions:
    * All classes are **pure Python** (no external dependencies beyond
      ``asyncio``) so they work in both production and unit tests.
    * ``RateLimiter`` and ``RequestQueue`` use ``asyncio.Lock`` so they
      are safe for concurrent coroutine access in FastAPI.
    * ``CircuitBreaker`` tracks per-engine state in a simple dict rather
      than separate instances — this keeps the Prometheus gauge sync
      logic straightforward (see ``api._state.update_circuit_breaker_metrics``).
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
    """LRU cache with per-entry TTL for alert deduplication.

    Used by the SSE (Server-Sent Events) alert stream to avoid pushing
    duplicate alerts to the dashboard within the TTL window.

    The cache key is an MD5 hash of (rule + proc.cmdline + container.name)
    so alerts with the same fingerprint are treated as duplicates.

    Args:
        max_size:     Maximum number of cached entries (LRU eviction).
        ttl_seconds:  Time-to-live for each entry in seconds.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 60):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0    # Cache hit counter (for stats endpoint).
        self.misses = 0  # Cache miss counter.

    def _get_hash(self, alert: dict) -> str:
        """Generate an MD5 fingerprint from the alert's key fields.

        Uses rule name, process command line, and container name to
        create a stable fingerprint that groups identical alerts.

        Args:
            alert: Raw alert dict with ``rule`` and ``output_fields``.

        Returns:
            Hex MD5 digest string.
        """
        key = (
            f"{alert.get('rule', '')}:"
            f"{alert.get('output_fields', {}).get('proc.cmdline', '')}:"
            f"{alert.get('output_fields', {}).get('container.name', '')}"
        )
        return hashlib.md5(key.encode()).hexdigest()

    def get(self, alert: dict) -> Optional[dict]:
        """Look up a cached analysis result for the given alert.

        If the entry exists and is within TTL, returns the cached
        analysis and increments the hit counter.  If expired, the
        entry is removed and a miss is recorded.

        Args:
            alert: Incoming alert dict.

        Returns:
            Cached analysis dict, or ``None`` on miss/expiry.
        """
        alert_hash = self._get_hash(alert)
        if alert_hash in self.cache:
            entry = self.cache[alert_hash]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                self.hits += 1
                self.cache.move_to_end(alert_hash)  # Refresh LRU position.
                return entry["analysis"]
            else:
                del self.cache[alert_hash]  # Expired — evict.
        self.misses += 1
        return None

    def set(self, alert: dict, analysis: dict):
        """Store an analysis result in the cache.

        If the cache is full, the least-recently-used entry is evicted
        before inserting the new one.

        Args:
            alert:    Original alert dict (used to compute fingerprint).
            analysis: Analysis result to cache.
        """
        alert_hash = self._get_hash(alert)
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)  # Evict LRU (oldest) entry.
        self.cache[alert_hash] = {"analysis": analysis, "timestamp": time.time()}

    def stats(self) -> dict:
        """Return cache performance statistics.

        Returns:
            dict with hits, misses, hit_rate (%), size, max_size.
        """
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
    """Token-bucket rate limiter for HTTP API protection.

    Tokens are refilled at a constant rate (``requests_per_minute / 60``
    tokens per second).  Each ``acquire()`` call costs one token.  If
    no tokens are available the request is rejected.

    The ``burst_size`` parameter sets the maximum number of tokens
    (= maximum instantaneous burst of requests).

    Args:
        requests_per_minute: Sustained request rate.
        burst_size:          Maximum tokens / burst capacity.
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 20):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.tokens = float(burst_size)    # Start with a full bucket.
        self.last_refill = time.time()
        self.total_requests = 0
        self.rejected_requests = 0
        self.lock = asyncio.Lock()         # Protects concurrent coroutine access.

    async def acquire(self) -> tuple:
        """Try to acquire a token.

        Refills tokens based on elapsed time since the last call, then
        attempts to consume one token.

        Returns:
            (allowed: bool, reason: str)
        """
        async with self.lock:
            now = time.time()
            time_passed = now - self.last_refill
            # Refill tokens proportional to elapsed time.
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
        """Return rate limiter statistics.

        Returns:
            dict with config and runtime counters.
        """
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
    """Three-state circuit breaker model.

    State transitions::

        CLOSED  ──(failures >= threshold)──►  OPEN
        OPEN    ──(recovery_timeout elapsed)──►  HALF_OPEN
        HALF_OPEN ──(success)──►  CLOSED
        HALF_OPEN ──(failure)──►  OPEN
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-engine circuit breaker for LLM API resilience.

    When an LLM provider fails ``failure_threshold`` times consecutively,
    its circuit opens and no further requests are sent until
    ``recovery_timeout`` seconds elapse.  After the timeout the circuit
    enters the ''half-open'' state and allows up to
    ``half_open_max_calls`` probe requests.  If a probe succeeds the
    circuit closes; if it fails the circuit re-opens.

    Args:
        failure_threshold:    Consecutive failures before opening.
        recovery_timeout:     Seconds to wait before probing (half-open).
        half_open_max_calls:  Max probe requests in half-open state.
        engines:              List of engine names to track.
    """

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
        # Global state (less important now — per-engine stats are primary).
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

        # Per-engine state dict: { "xai": {"failures": 0, "successes": 0, "state": "closed"}, … }
        tracked = engines or ["xai", "anthropic", "openai", "gemini", "kimi"]
        self.engine_stats: Dict[str, Dict] = {
            e: {
                "failures": 0,
                "successes": 0,
                "state": "closed",
                "last_failure_time": 0.0,
                "half_open_calls": 0,
            }
            for e in tracked
        }

    def can_execute(self, engine: str) -> tuple:
        """Check whether a request is allowed for the given engine.

        Handles OPEN → HALF_OPEN transition when the recovery timeout
        has elapsed.

        Args:
            engine: LLM engine name.

        Returns:
            (allowed: bool, reason: str)
        """
        stats = self.engine_stats.get(
            engine,
            {
                "failures": 0,
                "successes": 0,
                "state": "closed",
                "last_failure_time": 0.0,
                "half_open_calls": 0,
            },
        )
        if stats["state"] == "open":
            # Check if recovery timeout has elapsed → transition to half-open.
            last_failure_time = float(stats.get("last_failure_time") or 0.0)
            if time.time() - last_failure_time > self.recovery_timeout:
                stats["state"] = "half_open"
                stats["half_open_calls"] = 0
                self.engine_stats[engine] = stats
                logger.info(f"Circuit breaker for {engine}: OPEN → HALF_OPEN")
            else:
                return False, f"Circuit OPEN for {engine} (cooling down)"
        if stats["state"] == "half_open":
            if int(stats.get("half_open_calls") or 0) >= self.half_open_max_calls:
                return False, f"Circuit HALF_OPEN max calls reached for {engine}"
            stats["half_open_calls"] = int(stats.get("half_open_calls") or 0) + 1
            self.engine_stats[engine] = stats
        return True, "OK"

    def record_success(self, engine: str):
        """Record a successful LLM call — resets failure count and may close circuit.

        Args:
            engine: LLM engine name.
        """
        stats = self.engine_stats.get(
            engine,
            {
                "failures": 0,
                "successes": 0,
                "state": "closed",
                "last_failure_time": 0.0,
                "half_open_calls": 0,
            },
        )
        stats["successes"] += 1
        stats["failures"] = 0  # Reset consecutive failure count.
        stats["last_failure_time"] = 0.0
        stats["half_open_calls"] = 0
        if stats["state"] in {"half_open", "open"}:
            previous_state = stats["state"]
            stats["state"] = "closed"  # Recovery succeeded → close circuit.
            logger.info(f"Circuit breaker for {engine}: {previous_state.upper()} → CLOSED")
        self.engine_stats[engine] = stats

    def record_failure(self, engine: str):
        """Record a failed LLM call — may trip the circuit to OPEN.

        Args:
            engine: LLM engine name.
        """
        stats = self.engine_stats.get(
            engine,
            {
                "failures": 0,
                "successes": 0,
                "state": "closed",
                "last_failure_time": 0.0,
                "half_open_calls": 0,
            },
        )
        stats["failures"] += 1
        stats["last_failure_time"] = time.time()
        stats["half_open_calls"] = 0
        self.last_failure_time = stats["last_failure_time"]
        if stats["state"] == "half_open" or stats["failures"] >= self.failure_threshold:
            stats["state"] = "open"  # Trip the circuit breaker.
            logger.warning(
                f"Circuit breaker for {engine}: → OPEN (failures={stats['failures']})"
            )
        self.engine_stats[engine] = stats

    def get_stats(self) -> dict:
        """Return circuit breaker state for all engines.

        Returns:
            dict with per-engine stats, failure_threshold, and recovery_timeout.
        """
        return {
            "engines": self.engine_stats,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_sec": self.recovery_timeout,
        }

    def reset(self, engine: Optional[str] = None) -> dict:
        """Reset circuit breaker state.

        The LLM UI uses "Retry All" / "Reset" actions to recover after an
        operator fixes API keys or billing. Those endpoints call ``reset()``
        when available, so the method must exist on the shared breaker.

        Args:
            engine: Optional provider name. If omitted, resets all tracked engines.

        Returns:
            Summary of reset engines and current states.
        """
        engines = [engine] if engine else list(self.engine_stats.keys())
        reset_engines = []
        for eng in engines:
            if eng not in self.engine_stats:
                continue
            self.engine_stats[eng] = {
                "failures": 0,
                "successes": 0,
                "state": "closed",
                "last_failure_time": 0.0,
                "half_open_calls": 0,
            }
            reset_engines.append(eng)

        # Reset shared timers/counters used by OPEN/HALF_OPEN transitions.
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        self.failure_count = 0
        self.success_count = 0
        self.state = CircuitState.CLOSED

        return {
            "reset_engines": reset_engines,
            "states": {k: v.get("state", "unknown") for k, v in self.engine_stats.items()},
        }


# ═══════════════════════════════════════════════════════════════════════════
# Request Queue (burst handling)
# ═══════════════════════════════════════════════════════════════════════════

class RequestQueue:
    """Bounded async request queue for burst absorption.

    When the system receives a burst of alerts that exceeds the LLM
    processing capacity, the queue buffers up to ``max_queue_size``
    requests.  Additional requests are rejected with a 429 status.

    Unlike a real ``asyncio.Queue``, this is a simple counter — the
    actual alert processing happens inline.  The counter just tracks
    how many concurrent requests are ''in-flight'' so the API can
    reject new ones when overloaded.

    Args:
        max_queue_size: Maximum concurrent in-flight requests.
    """

    def __init__(self, max_queue_size: int = 100):
        self.max_queue_size = max_queue_size
        self.queue_size = 0         # Current in-flight count.
        self.total_queued = 0       # Lifetime accepted count.
        self.total_rejected = 0     # Lifetime rejected count.
        self.lock = asyncio.Lock()  # Protects concurrent coroutine access.

    async def try_enqueue(self) -> tuple:
        """Try to reserve a slot in the queue.

        Returns:
            (ok: bool, reason: str)
        """
        async with self.lock:
            if self.queue_size >= self.max_queue_size:
                self.total_rejected += 1
                return False, f"Queue full ({self.max_queue_size} max)"
            self.queue_size += 1
            self.total_queued += 1
            return True, "OK"

    async def dequeue(self):
        """Release a slot after processing completes."""
        async with self.lock:
            if self.queue_size > 0:
                self.queue_size -= 1

    def stats(self) -> dict:
        """Return queue statistics.

        Returns:
            dict with current_size, max_size, total_queued, total_rejected.
        """
        return {
            "current_size": self.queue_size,
            "max_size": self.max_queue_size,
            "total_queued": self.total_queued,
            "total_rejected": self.total_rejected,
        }
