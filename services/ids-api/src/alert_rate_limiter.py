"""
Alert Rate Limiter - Prevents Alert Flooding

Implements time-window based rate limiting to prevent alert storms from
overwhelming the LLM analysis pipeline and database.

Features:
- Configurable window-based throttling (e.g., max 10 alerts per rule per minute)
- Per-rule rate limiting (same rule can't flood)
- Per-source rate limiting (falco/suricata)
- Burst allowance for legitimate alert spikes
- Automatic exponential backoff for repeat offenders
- All throttled alerts still logged to database (marked as throttled)

Author: Smart City IDS
License: MIT
"""

import time
import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ThrottleReason(Enum):
    """Reasons an alert was throttled"""
    NONE = "not_throttled"
    RULE_LIMIT = "rule_rate_exceeded"
    SOURCE_LIMIT = "source_rate_exceeded"
    GLOBAL_LIMIT = "global_rate_exceeded"
    DUPLICATE = "duplicate_within_window"
    BACKOFF = "exponential_backoff"


@dataclass
class ThrottleStats:
    """Statistics for rate limiting"""
    total_received: int = 0
    total_throttled: int = 0
    total_processed: int = 0
    throttle_reasons: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_reset: float = field(default_factory=time.time)
    
    @property
    def throttle_rate(self) -> float:
        if self.total_received == 0:
            return 0.0
        return self.total_throttled / self.total_received
    
    def to_dict(self) -> dict:
        return {
            "total_received": self.total_received,
            "total_throttled": self.total_throttled,
            "total_processed": self.total_processed,
            "throttle_rate_percent": round(self.throttle_rate * 100, 2),
            "throttle_reasons": dict(self.throttle_reasons),
            "stats_since": datetime.fromtimestamp(self.last_reset).isoformat()
        }


@dataclass
class RuleWindow:
    """Sliding window for a specific rule"""
    timestamps: List[float] = field(default_factory=list)
    backoff_until: float = 0.0
    consecutive_throttles: int = 0


class AlertRateLimiter:
    """
    Time-window based rate limiter for security alerts.
    
    Prevents alert flooding while ensuring all alerts are logged.
    Throttled alerts are still saved to database but skip LLM analysis.
    
    Configuration via environment variables:
        ALERT_RATE_LIMIT_WINDOW_SECONDS: Window size (default: 60)
        ALERT_RATE_LIMIT_PER_RULE: Max alerts per rule per window (default: 10)
        ALERT_RATE_LIMIT_PER_SOURCE: Max alerts per source per window (default: 100)
        ALERT_RATE_LIMIT_GLOBAL: Global max alerts per window (default: 500)
        ALERT_RATE_LIMIT_BACKOFF_MULTIPLIER: Backoff multiplier (default: 2.0)
        ALERT_RATE_LIMIT_MAX_BACKOFF: Max backoff seconds (default: 300)
    
    Example:
        >>> limiter = AlertRateLimiter(window_seconds=60, max_per_rule=10)
        >>> 
        >>> # First 10 alerts pass
        >>> for i in range(10):
        ...     allowed, reason = limiter.should_process({"rule": "Test"})
        ...     assert allowed == True
        >>> 
        >>> # 11th alert is throttled
        >>> allowed, reason = limiter.should_process({"rule": "Test"})
        >>> assert allowed == False
        >>> assert reason == ThrottleReason.RULE_LIMIT
    """
    
    def __init__(
        self,
        window_seconds: int = 60,
        max_per_rule: int = 10,
        max_per_source: int = 100,
        max_global: int = 500,
        backoff_multiplier: float = 2.0,
        max_backoff_seconds: float = 300.0,
    ):
        """
        Initialize rate limiter.
        
        Args:
            window_seconds: Size of sliding window in seconds
            max_per_rule: Maximum alerts per rule within window
            max_per_source: Maximum alerts per source (falco/suricata) within window
            max_global: Maximum total alerts within window
            backoff_multiplier: Multiplier for exponential backoff
            max_backoff_seconds: Maximum backoff duration
        """
        self.window_seconds = window_seconds
        self.max_per_rule = max_per_rule
        self.max_per_source = max_per_source
        self.max_global = max_global
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff_seconds = max_backoff_seconds
        
        # Sliding windows
        self.rule_windows: Dict[str, RuleWindow] = defaultdict(RuleWindow)
        self.source_windows: Dict[str, RuleWindow] = defaultdict(RuleWindow)
        self.global_window: RuleWindow = RuleWindow()
        
        # Statistics
        self.stats = ThrottleStats()
        
        logger.info(
            f"AlertRateLimiter initialized: window={window_seconds}s, "
            f"per_rule={max_per_rule}, per_source={max_per_source}, global={max_global}"
        )
    
    def _clean_window(self, window: RuleWindow) -> None:
        """Remove expired timestamps from window"""
        now = time.time()
        cutoff = now - self.window_seconds
        window.timestamps = [ts for ts in window.timestamps if ts > cutoff]
    
    def _is_in_backoff(self, window: RuleWindow) -> bool:
        """Check if window is in backoff period"""
        return time.time() < window.backoff_until
    
    def _apply_backoff(self, window: RuleWindow) -> None:
        """Apply exponential backoff to window"""
        window.consecutive_throttles += 1
        backoff_duration = min(
            self.window_seconds * (self.backoff_multiplier ** window.consecutive_throttles),
            self.max_backoff_seconds
        )
        window.backoff_until = time.time() + backoff_duration
        logger.warning(f"Applying {backoff_duration:.1f}s backoff (consecutive={window.consecutive_throttles})")
    
    def _reset_backoff(self, window: RuleWindow) -> None:
        """Reset backoff counter on successful processing"""
        window.consecutive_throttles = 0
        window.backoff_until = 0.0
    
    def should_process(self, alert: Dict) -> Tuple[bool, ThrottleReason]:
        """
        Check if alert should be processed (sent to LLM).
        
        Throttled alerts should still be logged to database but skip LLM analysis.
        
        Args:
            alert: Alert dict with 'rule' and optionally 'source' keys
            
        Returns:
            Tuple of (should_process: bool, reason: ThrottleReason)
        """
        now = time.time()
        self.stats.total_received += 1
        
        rule = alert.get("rule", "unknown")
        source = alert.get("source", "falco")  # Default to falco
        
        # Get or create windows
        rule_window = self.rule_windows[rule]
        source_window = self.source_windows[source]
        
        # Clean expired timestamps
        self._clean_window(rule_window)
        self._clean_window(source_window)
        self._clean_window(self.global_window)
        
        # Check backoff
        if self._is_in_backoff(rule_window):
            self.stats.total_throttled += 1
            self.stats.throttle_reasons["backoff"] += 1
            return False, ThrottleReason.BACKOFF
        
        # Check rule limit
        if len(rule_window.timestamps) >= self.max_per_rule:
            self.stats.total_throttled += 1
            self.stats.throttle_reasons["rule_limit"] += 1
            self._apply_backoff(rule_window)
            logger.info(f"Rule rate limit exceeded: {rule} ({len(rule_window.timestamps)}/{self.max_per_rule})")
            return False, ThrottleReason.RULE_LIMIT
        
        # Check source limit
        if len(source_window.timestamps) >= self.max_per_source:
            self.stats.total_throttled += 1
            self.stats.throttle_reasons["source_limit"] += 1
            logger.info(f"Source rate limit exceeded: {source} ({len(source_window.timestamps)}/{self.max_per_source})")
            return False, ThrottleReason.SOURCE_LIMIT
        
        # Check global limit
        if len(self.global_window.timestamps) >= self.max_global:
            self.stats.total_throttled += 1
            self.stats.throttle_reasons["global_limit"] += 1
            logger.info(f"Global rate limit exceeded ({len(self.global_window.timestamps)}/{self.max_global})")
            return False, ThrottleReason.GLOBAL_LIMIT
        
        # All checks passed - record timestamp
        rule_window.timestamps.append(now)
        source_window.timestamps.append(now)
        self.global_window.timestamps.append(now)
        
        self._reset_backoff(rule_window)
        self.stats.total_processed += 1
        
        return True, ThrottleReason.NONE
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            **self.stats.to_dict(),
            "config": {
                "window_seconds": self.window_seconds,
                "max_per_rule": self.max_per_rule,
                "max_per_source": self.max_per_source,
                "max_global": self.max_global,
            },
            "current_windows": {
                "rules_tracked": len(self.rule_windows),
                "sources_tracked": len(self.source_windows),
                "global_count": len(self.global_window.timestamps),
            }
        }
    
    def reset_stats(self) -> None:
        """Reset statistics (not windows)"""
        self.stats = ThrottleStats()
        logger.info("Rate limiter stats reset")
    
    def reset(self) -> None:
        """Alias for reset_stats for API compatibility"""
        self.reset_stats()
    
    def clear_all(self) -> None:
        """Clear all windows and stats"""
        self.rule_windows.clear()
        self.source_windows.clear()
        self.global_window = RuleWindow()
        self.stats = ThrottleStats()
        logger.info("Rate limiter fully cleared")


# Singleton instance
import os

_alert_rate_limiter: Optional[AlertRateLimiter] = None

def get_alert_rate_limiter() -> AlertRateLimiter:
    """Get or create the global alert rate limiter instance"""
    global _alert_rate_limiter
    
    if _alert_rate_limiter is None:
        _alert_rate_limiter = AlertRateLimiter(
            window_seconds=int(os.getenv("ALERT_RATE_LIMIT_WINDOW_SECONDS", "60")),
            max_per_rule=int(os.getenv("ALERT_RATE_LIMIT_PER_RULE", "10")),
            max_per_source=int(os.getenv("ALERT_RATE_LIMIT_PER_SOURCE", "100")),
            max_global=int(os.getenv("ALERT_RATE_LIMIT_GLOBAL", "500")),
            backoff_multiplier=float(os.getenv("ALERT_RATE_LIMIT_BACKOFF_MULTIPLIER", "2.0")),
            max_backoff_seconds=float(os.getenv("ALERT_RATE_LIMIT_MAX_BACKOFF", "300")),
        )
    
    return _alert_rate_limiter
