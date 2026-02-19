"""
Alert Deduplicator for Smart City IDS

Implements fingerprint-based caching to reduce duplicate LLM calls.
Expected savings: 40-60% reduction in LLM calls during alert bursts.

Cost impact:
- Without dedup: $50-100/day in LLM costs (50k+ alerts/day)
- With dedup: $15-40/day in LLM costs (40-60% reduction)
- Annual savings: $5,000-30,000

Author: Smart City IDS
License: MIT
"""

import hashlib
import json
import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class AlertDeduplicator:
    """
    Fingerprint-based alert deduplicator with severity-aware TTL caching.
    
    Detects and caches analysis of duplicate security alerts to prevent
    redundant LLM calls during alert storms (common in DDoS/brute-force).
    
    Severity-aware TTL: High-severity alerts get shorter TTLs so they are
    re-analyzed more frequently, while low-severity alerts cache longer.
      - Critical (sev >= 8): TTL = base / 3  (e.g. 20s for 60s base)
      - High     (sev >= 6): TTL = base / 2  (e.g. 30s for 60s base)
      - Medium   (sev >= 4): TTL = base      (e.g. 60s)
      - Low      (sev < 4):  TTL = base * 2  (e.g. 120s)
    
    Attributes:
        ttl_seconds (int): Base cache TTL in seconds (default 60)
        max_cache_size (int): Maximum fingerprints to cache (default 10000)
        hits (int): Number of deduplicated alerts
        misses (int): Number of new alerts analyzed
        evictions (int): Number of cache evictions
    """
    
    def __init__(self, ttl_seconds: int = 60, max_cache_size: int = 10000):
        """
        Initialize alert deduplicator.
        
        Args:
            ttl_seconds: Base time-to-live for fingerprint cache (default 60s).
                         Actual TTL varies by severity (see class docstring).
            max_cache_size: Maximum fingerprints to keep in memory
        """
        self.ttl = ttl_seconds
        self.max_cache_size = max_cache_size
        self.cache: Dict[str, Dict] = {}  # fingerprint -> {timestamp, analysis, count, effective_ttl}
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.dedup_count: Dict[str, int] = defaultdict(int)
        
    def get_fingerprint(self, alert: Dict) -> str:
        """
        Generate unique fingerprint for alert.
        
        Fingerprint is based on alert rule + container + process to identify
        identical or very similar security alerts.
        
        Args:
            alert: Alert dict from Falco/Suricata
            
        Returns:
            SHA256 hex digest (64 chars)
            
        Examples:
            >>> alert1 = {
            ...     "rule": "Unauthorized Process",
            ...     "output_fields": {"container.name": "web-01", "proc.cmdline": "/bin/bash"}
            ... }
            >>> alert2 = {
            ...     "rule": "Unauthorized Process",
            ...     "output_fields": {"container.name": "web-01", "proc.cmdline": "/bin/bash"}
            ... }
            >>> dedup = AlertDeduplicator()
            >>> dedup.get_fingerprint(alert1) == dedup.get_fingerprint(alert2)
            True
        """
        # Extract key fields for fingerprinting
        rule = alert.get("rule", "unknown")
        output_fields = alert.get("output_fields", {})
        container_name = output_fields.get("container.name", "")
        proc_cmdline = output_fields.get("proc.cmdline", "")
        proc_exe = output_fields.get("proc.exe", "")
        
        # Create composite key
        key = f"{rule}:{container_name}:{proc_cmdline}:{proc_exe}"
        
        # Hash to fixed-length fingerprint
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _severity_ttl(self, severity: int) -> int:
        """
        Compute effective TTL based on alert severity.
        
        High-severity alerts expire faster so they get re-analyzed more
        frequently, while low-severity alerts stay cached longer.
        
        Args:
            severity: Alert severity (1-10)
            
        Returns:
            Effective TTL in seconds
        """
        if severity >= 8:
            return max(10, self.ttl // 3)   # Critical: ~20s for 60s base
        elif severity >= 6:
            return max(15, self.ttl // 2)   # High: ~30s for 60s base
        elif severity >= 4:
            return self.ttl                  # Medium: base TTL
        else:
            return self.ttl * 2              # Low: 2x base
    
    def should_analyze(self, alert: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Check if alert should be analyzed or if cached result can be used.
        Uses severity-aware TTL: cached high-severity alerts expire faster.
        
        Args:
            alert: Alert dict from Falco/Suricata
            
        Returns:
            Tuple of (should_analyze: bool, cached_analysis: dict or None)
                - (True, None) if alert is new and needs analysis
                - (False, cached_analysis) if cached result is available
        """
        fp = self.get_fingerprint(alert)
        now = time.time()
        
        # Check if fingerprint exists and is not expired
        if fp in self.cache:
            entry = self.cache[fp]
            age = now - entry["timestamp"]
            
            # Use the severity-aware TTL from the cached analysis
            effective_ttl = entry.get("effective_ttl", self.ttl)
            
            if age < effective_ttl:
                # Cache hit: return cached analysis
                self.hits += 1
                entry["hit_count"] = entry.get("hit_count", 1) + 1
                self.dedup_count[fp] += 1
                
                cached_sev = entry.get("analysis", {}).get("severity", "?")
                logger.info(
                    f"Alert dedup HIT (fp={fp[:8]}…, age={age:.1f}s/{effective_ttl}s, "
                    f"sev={cached_sev}, hits={self.hits}, count={entry['hit_count']})"
                )
                
                return False, entry.get("analysis")
            else:
                # Cache expired: remove and process as new
                del self.cache[fp]
                self.misses += 1
                logger.info(f"Cache expired for fp={fp[:8]}… (age={age:.1f}s, ttl={effective_ttl}s)")
                return True, None
        
        # Cache miss: need to analyze
        self.misses += 1
        logger.info(f"Alert dedup MISS (fp={fp[:8]}…, total_misses={self.misses})")
        return True, None
    
    def cache_analysis(self, alert: Dict, analysis: Dict) -> None:
        """
        Store analysis result in cache for future deduplication.
        Uses severity-aware TTL: high-severity results expire faster.
        
        Args:
            alert: Original alert dict
            analysis: LLM analysis result dict
            
        Side effects:
            - Updates cache with new fingerprint/analysis pair
            - Evicts old entries if cache exceeds max_cache_size
            - Computes effective TTL from analysis severity
        """
        fp = self.get_fingerprint(alert)
        
        # Evict oldest entries if cache is full
        if len(self.cache) >= self.max_cache_size:
            oldest_fp = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_fp]
            self.evictions += 1
            logger.warning(
                f"Cache eviction: removed oldest entry (fp={oldest_fp[:8]}…, "
                f"total_evictions={self.evictions})"
            )
        
        # Compute severity-aware TTL
        severity = analysis.get("severity", 5) if isinstance(analysis, dict) else 5
        effective_ttl = self._severity_ttl(severity)
        
        # Store new analysis with effective TTL
        self.cache[fp] = {
            "timestamp": time.time(),
            "analysis": analysis,
            "alert": alert,
            "hit_count": 1,
            "effective_ttl": effective_ttl,
        }
        
        logger.debug(
            f"Cached analysis for fp={fp[:8]}… "
            f"(sev={severity}, ttl={effective_ttl}s, cache_size={len(self.cache)})"
        )
    
    def get_stats(self) -> Dict:
        """
        Get deduplication statistics.
        
        Returns:
            dict with keys:
                - hits: Number of cache hits
                - misses: Number of cache misses
                - cache_size: Current cache size
                - hit_rate: Percentage of hits (hits / (hits + misses))
                - ttl_seconds: Cache TTL
                - max_cache_size: Maximum cache capacity
                - evictions: Number of evictions
                - top_duplicates: Most frequently duplicated alerts
                
        Examples:
            >>> dedup = AlertDeduplicator()
            >>> stats = dedup.get_stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.1%}")
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        # Get top duplicated alerts
        top_dupes = sorted(
            self.dedup_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_alerts": total,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_size": len(self.cache),
            "max_cache_size": self.max_cache_size,
            "cache_utilization_percent": round(len(self.cache) / self.max_cache_size * 100, 2),
            "ttl_seconds": self.ttl,
            "severity_ttl": {
                "critical_gte8": self._severity_ttl(8),
                "high_gte6": self._severity_ttl(6),
                "medium_gte4": self._severity_ttl(4),
                "low_lt4": self._severity_ttl(1),
            },
            "evictions": self.evictions,
            "top_duplicates": [
                {
                    "fingerprint": fp[:16] + "...",
                    "duplicate_count": count
                }
                for fp, count in top_dupes
            ]
        }
    
    def clear_cache(self) -> None:
        """
        Clear all cached entries.
        
        Useful for testing or periodic cleanup.
        """
        self.cache.clear()
        self.dedup_count.clear()
        logger.info("Alert deduplicator cache cleared")
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        expired_fps = [
            fp for fp, entry in self.cache.items()
            if now - entry["timestamp"] >= self.ttl
        ]
        
        for fp in expired_fps:
            del self.cache[fp]
        
        if expired_fps:
            logger.info(f"Cleaned up {len(expired_fps)} expired cache entries")
        
        return len(expired_fps)


class AlertBatcher:
    """
    Group similar alerts for batch LLM analysis.
    
    Reduces LLM calls by combining similar threat-type alerts.
    Example: 10 identical DDoS alerts → 1 batch LLM call
    
    Expected savings: 30-50% reduction in LLM calls
    
    Attributes:
        batch_size (int): Number of alerts before forced batch processing
        batch_timeout (int): Max seconds to wait for batch to fill
        batches: Dict of threat_type -> list of alerts
    """
    
    def __init__(self, batch_size: int = 10, batch_timeout: int = 5):
        """
        Initialize alert batcher.
        
        Args:
            batch_size: Min alerts to trigger batch processing (default 10)
            batch_timeout: Max seconds to wait before processing (default 5)
        """
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.batches: Dict[str, list] = defaultdict(list)
        self.batch_timestamps: Dict[str, float] = {}
        self.total_batched = 0
    
    def classify_threat(self, alert: Dict) -> str:
        """
        Classify alert to threat type for batching.
        
        Args:
            alert: Alert from Falco/Suricata
            
        Returns:
            Threat type string (e.g., "DDoS", "PrivilegeEscalation")
        """
        rule = alert.get("rule", "").lower()
        
        # Simple rule-based classification
        if any(x in rule for x in ["dos", "ddos", "flood", "brute force"]):
            return "DDoS"
        elif any(x in rule for x in ["privilege", "escalation", "sudo"]):
            return "PrivilegeEscalation"
        elif any(x in rule for x in ["injection", "sql", "xss"]):
            return "Injection"
        elif any(x in rule for x in ["data exfil", "data loss", "exfiltration"]):
            return "DataExfiltration"
        elif any(x in rule for x in ["malware", "trojan", "ransomware"]):
            return "Malware"
        else:
            return "Other"
    
    def add_alert(self, alert: Dict) -> Tuple[bool, Optional[str]]:
        """
        Add alert to batcher.
        
        Args:
            alert: Alert dict
            
        Returns:
            Tuple of (should_batch_now: bool, threat_type: str)
        """
        threat_type = self.classify_threat(alert)
        
        # Initialize batch timestamp on first alert
        if threat_type not in self.batch_timestamps:
            self.batch_timestamps[threat_type] = time.time()
        
        self.batches[threat_type].append(alert)
        
        # Check if batch is ready
        batch = self.batches[threat_type]
        age = time.time() - self.batch_timestamps[threat_type]
        
        should_batch = (
            len(batch) >= self.batch_size or
            age >= self.batch_timeout
        )
        
        return should_batch, threat_type
    
    def get_batch(self, threat_type: str) -> Optional[list]:
        """
        Retrieve and clear batch for given threat type.
        
        Args:
            threat_type: Threat type string
            
        Returns:
            List of alerts or None if empty
        """
        if threat_type in self.batches and self.batches[threat_type]:
            batch = self.batches[threat_type]
            del self.batches[threat_type]
            del self.batch_timestamps[threat_type]
            self.total_batched += len(batch)
            return batch
        return None
    
    def get_stats(self) -> Dict:
        """Get batching statistics."""
        total_queued = sum(len(b) for b in self.batches.values())
        return {
            "total_batched": self.total_batched,
            "queued_alerts": total_queued,
            "active_batches": len(self.batches),
            "threat_types": list(self.batches.keys())
        }
