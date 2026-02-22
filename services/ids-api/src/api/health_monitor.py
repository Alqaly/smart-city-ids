"""
Enhanced Health Monitoring API for LLM providers and system components.
Provides aggregated health scores, historical metrics, and resilience tracking.
"""

from __future__ import annotations

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@dataclass
class HealthSnapshot:
    """A point-in-time health snapshot for a provider or component."""
    timestamp: float
    status: str  # healthy, degraded, unhealthy, unknown
    latency_ms: Optional[float] = None
    error_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderHealthHistory:
    """Historical health data for a single provider."""
    provider: str
    snapshots: deque = field(default_factory=lambda: deque(maxlen=1000))
    total_checks: int = 0
    healthy_checks: int = 0
    degraded_checks: int = 0
    unhealthy_checks: int = 0
    
    @property
    def uptime_percentage(self) -> float:
        if self.total_checks == 0:
            return 100.0
        return (self.healthy_checks / self.total_checks) * 100
    
    @property
    def current_status(self) -> str:
        if not self.snapshots:
            return "unknown"
        return self.snapshots[-1].status
    
    @property
    def avg_latency_ms(self) -> Optional[float]:
        latencies = [s.latency_ms for s in self.snapshots if s.latency_ms is not None]
        if not latencies:
            return None
        return sum(latencies) / len(latencies)
    
    @property
    def p95_latency_ms(self) -> Optional[float]:
        latencies = sorted([s.latency_ms for s in self.snapshots if s.latency_ms is not None])
        if not latencies:
            return None
        idx = int(len(latencies) * 0.95)
        return latencies[min(idx, len(latencies) - 1)]


class HealthMonitor:
    """
    Centralized health monitoring for all system components.
    
    Features:
    - Tracks health history for each LLM provider
    - Calculates aggregate health scores
    - Detects degradation trends
    - Provides resilience metrics
    """
    
    def __init__(self, max_history_per_provider: int = 1000):
        self.provider_histories: Dict[str, ProviderHealthHistory] = {}
        self.system_health_history: deque = deque(maxlen=500)
        self.sse_connection_history: deque = deque(maxlen=500)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
        
        # Thresholds for health classification
        self.thresholds = {
            "latency_p95_ms": 5000,  # 5s p95 is degraded
            "latency_p95_critical_ms": 10000,  # 10s is unhealthy
            "error_rate_threshold": 0.1,  # 10% error rate is degraded
            "error_rate_critical": 0.25,  # 25% error rate is unhealthy
        }
    
    async def record_provider_check(
        self,
        provider: str,
        success: bool,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Record a health check result for a provider."""
        async with self._lock:
            if provider not in self.provider_histories:
                self.provider_histories[provider] = ProviderHealthHistory(provider=provider)
            
            history = self.provider_histories[provider]
            history.total_checks += 1
            
            # Determine status based on success and latency
            if not success:
                status = "unhealthy"
                history.unhealthy_checks += 1
            elif latency_ms and latency_ms > self.thresholds["latency_p95_critical_ms"]:
                status = "degraded"
                history.degraded_checks += 1
            elif latency_ms and latency_ms > self.thresholds["latency_p95_ms"]:
                status = "degraded"
                history.degraded_checks += 1
            else:
                status = "healthy"
                history.healthy_checks += 1
            
            snapshot = HealthSnapshot(
                timestamp=time.time(),
                status=status,
                latency_ms=latency_ms,
                metadata=metadata or {}
            )
            history.snapshots.append(snapshot)
            self.last_update = time.time()
    
    async def record_sse_event(self, event_type: str, metadata: Optional[Dict] = None):
        """Record an SSE connection event."""
        self.sse_connection_history.append({
            "timestamp": time.time(),
            "type": event_type,
            "metadata": metadata or {}
        })
    
    def get_provider_health(self, provider: str) -> Optional[Dict]:
        """Get current health status for a provider."""
        history = self.provider_histories.get(provider)
        if not history:
            return None
        
        recent_snapshots = list(history.snapshots)[-50:]  # Last 50 checks
        recent_errors = sum(1 for s in recent_snapshots if s.status == "unhealthy")
        recent_error_rate = recent_errors / len(recent_snapshots) if recent_snapshots else 0
        
        # Calculate trend (improving, stable, degrading)
        trend = "stable"
        if len(recent_snapshots) >= 10:
            first_half = sum(1 for s in recent_snapshots[:25] if s.status == "healthy")
            second_half = sum(1 for s in recent_snapshots[-25:] if s.status == "healthy")
            if second_half > first_half + 3:
                trend = "improving"
            elif second_half < first_half - 3:
                trend = "degrading"
        
        return {
            "provider": provider,
            "current_status": history.current_status,
            "uptime_percentage": round(history.uptime_percentage, 2),
            "total_checks": history.total_checks,
            "recent_error_rate": round(recent_error_rate * 100, 2),
            "avg_latency_ms": round(history.avg_latency_ms, 2) if history.avg_latency_ms else None,
            "p95_latency_ms": round(history.p95_latency_ms, 2) if history.p95_latency_ms else None,
            "trend": trend,
            "last_check_ago_seconds": int(time.time() - history.snapshots[-1].timestamp) if history.snapshots else None,
        }
    
    def get_all_providers_health(self) -> List[Dict]:
        """Get health status for all providers."""
        return [
            self.get_provider_health(provider)
            for provider in self.provider_histories.keys()
        ]
    
    def get_system_health_score(self) -> Dict:
        """Calculate overall system health score (0-100)."""
        if not self.provider_histories:
            return {"score": 100, "status": "healthy", "factors": {}}
        
        total_weight = 0
        weighted_score = 0
        factors = {}
        
        for provider, history in self.provider_histories.items():
            # Weight by recent activity
            weight = min(history.total_checks, 100) / 100
            total_weight += weight
            
            # Calculate individual provider score
            if history.current_status == "healthy":
                score = 100
            elif history.current_status == "degraded":
                score = 60
            else:
                score = 20
            
            weighted_score += score * weight
            factors[provider] = {
                "score": score,
                "weight": round(weight, 2),
                "status": history.current_status
            }
        
        final_score = int(weighted_score / total_weight) if total_weight > 0 else 100
        
        status = "healthy"
        if final_score < 40:
            status = "critical"
        elif final_score < 70:
            status = "degraded"
        
        return {
            "score": final_score,
            "status": status,
            "factors": factors,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_sse_health(self) -> Dict:
        """Get SSE connection health metrics."""
        if not self.sse_connection_history:
            return {"status": "unknown", "events_count": 0}
        
        recent_events = [
            e for e in self.sse_connection_history
            if time.time() - e["timestamp"] < 3600  # Last hour
        ]
        
        connection_events = [e for e in recent_events if e["type"] in ("connected", "disconnected", "error")]
        
        return {
            "status": "connected" if connection_events and connection_events[-1]["type"] == "connected" else "disconnected",
            "events_last_hour": len(recent_events),
            "connections_last_hour": len(connection_events),
            "last_event_ago_seconds": int(time.time() - self.sse_connection_history[-1]["timestamp"]) if self.sse_connection_history else None,
        }
    
    def get_resilience_metrics(self) -> Dict:
        """Calculate resilience metrics for the system."""
        all_health = self.get_all_providers_health()
        
        if not all_health:
            return {"resilience_score": 0, "redundancy_level": "none"}
        
        healthy_count = sum(1 for h in all_health if h["current_status"] == "healthy")
        total_count = len(all_health)
        
        # Resilience score based on redundancy
        if total_count == 0:
            resilience_score = 0
        elif healthy_count >= 3:
            resilience_score = 100  # High redundancy
        elif healthy_count == 2:
            resilience_score = 70   # Some redundancy
        elif healthy_count == 1:
            resilience_score = 30   # Single point of failure
        else:
            resilience_score = 0    # No providers available
        
        redundancy_level = "critical"
        if healthy_count >= 4:
            redundancy_level = "excellent"
        elif healthy_count == 3:
            redundancy_level = "good"
        elif healthy_count == 2:
            redundancy_level = "fair"
        elif healthy_count == 1:
            redundancy_level = "poor"
        
        return {
            "resilience_score": resilience_score,
            "redundancy_level": redundancy_level,
            "healthy_providers": healthy_count,
            "total_providers": total_count,
            "failover_readiness": healthy_count >= 2,
        }


# Global health monitor instance
health_monitor = HealthMonitor()


@router.get("/api/health/enhanced")
async def get_enhanced_health():
    """
    Get comprehensive health status for all providers and system components.
    
    Returns:
        {
            "system_score": 0-100,
            "system_status": "healthy|degraded|critical",
            "providers": [...],
            "resilience": {...},
            "sse": {...}
        }
    """
    return {
        "system_score": health_monitor.get_system_health_score(),
        "providers": health_monitor.get_all_providers_health(),
        "resilience": health_monitor.get_resilience_metrics(),
        "sse": health_monitor.get_sse_health(),
    }


@router.get("/api/health/providers/{provider}")
async def get_provider_detailed_health(provider: str):
    """Get detailed health history for a specific provider."""
    health = health_monitor.get_provider_health(provider)
    if not health:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    
    history = health_monitor.provider_histories.get(provider)
    if history:
        # Include recent snapshots
        recent_snapshots = [
            {
                "timestamp": datetime.fromtimestamp(s.timestamp).isoformat(),
                "status": s.status,
                "latency_ms": s.latency_ms,
            }
            for s in list(history.snapshots)[-50:]
        ]
        health["recent_snapshots"] = recent_snapshots
    
    return health


@router.post("/api/health/providers/{provider}/check")
async def record_provider_health_check(
    provider: str,
    success: bool,
    latency_ms: Optional[float] = None,
    error: Optional[str] = None
):
    """Record a health check result (used by background health checks)."""
    await health_monitor.record_provider_check(provider, success, latency_ms, error)
    return {"status": "recorded"}


@router.get("/api/health/resilience")
async def get_resilience_status():
    """Get system resilience metrics and failover readiness."""
    return health_monitor.get_resilience_metrics()
