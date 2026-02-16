"""Async database adapter — Phase 1 of the database migration.

Problem:
    The original ``database.py`` at project root uses synchronous
    ``psycopg2`` calls.  Running those directly inside FastAPI's async
    handlers blocks the event loop and causes request latency spikes.

Solution (Phase 1 — current):
    Wrap every sync method with ``asyncio.to_thread()`` so the blocking
    I/O runs in a thread-pool while the event loop stays responsive.
    This is a zero-change approach — the existing ``Database`` class
    (including its PostgreSQL-with-memory-fallback logic) works unchanged.

Future (Phase 2):
    Replace ``psycopg2`` with ``asyncpg`` for native async queries,
    eliminating the thread-pool overhead entirely.

Architecture::

    FastAPI handler
        └── await async_db.add_alert(data)
                └── asyncio.to_thread(_sync_db.add_alert, data)
                        └── psycopg2 cursor.execute(...)

Usage:
    from infrastructure.database import async_db
    await async_db.add_alert({...})
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

# Import the existing sync database singleton from the project-root module.
from database import db as _sync_db

logger = logging.getLogger(__name__)


class AsyncDatabase:
    """Async adapter around the synchronous ``Database`` singleton.

    Every public method delegates to the sync ``db`` via
    ``asyncio.to_thread()`` so the FastAPI event loop is never blocked
    by ``psycopg2`` calls.

    Args:
        sync_db: Optional override for the sync database instance
                 (used in tests to inject a mock).
    """

    def __init__(self, sync_db=None):
        self._db = sync_db or _sync_db

    # ── Convenience property ──────────────────────────────────────────────
    @property
    def sync(self):
        """Direct access to the underlying sync Database.

        Used during application startup for schema migrations and
        Prometheus metric restoration that don't need async wrappers.
        """
        return self._db

    # ── Alert CRUD operations ─────────────────────────────────────────────

    async def add_alert(self, alert_data: dict) -> Optional[int]:
        """Insert a new security alert and return its ID."""
        return await asyncio.to_thread(self._db.add_alert, alert_data)

    async def add_analysis_result(self, result: dict) -> Optional[int]:
        """Insert an LLM analysis result linked to an alert."""
        return await asyncio.to_thread(self._db.add_analysis_result, result)

    async def add_automation_action(self, action: dict) -> Optional[int]:
        """Insert a record of an automated K8s action taken."""
        return await asyncio.to_thread(self._db.add_automation_action, action)

    async def add_audit_log(self, log: dict) -> Optional[int]:
        """Insert a governance audit log entry."""
        return await asyncio.to_thread(self._db.add_audit_log, log)

    async def add_system_log(self, log: dict) -> Optional[int]:
        """Insert a system-level log entry (startup, errors, etc.)."""
        return await asyncio.to_thread(self._db.add_system_log, log)

    async def add_throttled_alert(self, alert: dict) -> Optional[int]:
        """Insert a throttled alert record (alert was rate-limited)."""
        return await asyncio.to_thread(self._db.add_throttled_alert, alert)

    # ── Query operations ──────────────────────────────────────────────────

    async def get_alerts(self, limit: int = 10, source: str = None) -> List[dict]:
        """Retrieve recent alerts, optionally filtered by source."""
        return await asyncio.to_thread(self._db.get_alerts, limit, source)

    async def get_alert_count(self, source: str = None) -> int:
        """Count total alerts, optionally filtered by source."""
        return await asyncio.to_thread(self._db.get_alert_count, source)

    async def get_alerts_by_severity(self) -> Dict[str, int]:
        """Get alert count grouped by severity level."""
        return await asyncio.to_thread(self._db.get_alerts_by_severity)

    async def get_system_logs(self, limit=50, level=None, component=None) -> list:
        """Retrieve system logs with optional level/component filters."""
        return await asyncio.to_thread(self._db.get_system_logs, limit, level, component)

    async def get_throttled_alerts(self, limit=50, rule=None) -> list:
        """Retrieve throttled alert records."""
        return await asyncio.to_thread(self._db.get_throttled_alerts, limit, rule)

    async def get_throttle_stats(self) -> dict:
        """Get aggregated throttle statistics."""
        return await asyncio.to_thread(self._db.get_throttle_stats)

    # ── IoT device & event operations ─────────────────────────────────────

    async def register_iot_device(self, device: dict) -> Optional[int]:
        """Register or update an IoT device record."""
        return await asyncio.to_thread(self._db.register_iot_device, device)

    async def get_iot_devices(self) -> list:
        """List all registered IoT devices."""
        return await asyncio.to_thread(self._db.get_iot_devices)

    async def get_iot_device_count(self) -> int:
        """Count registered IoT devices."""
        return await asyncio.to_thread(self._db.get_iot_device_count)

    async def add_iot_event(self, event: dict) -> Optional[int]:
        """Insert an IoT sensor event."""
        return await asyncio.to_thread(self._db.add_iot_event, event)

    async def get_iot_events(self, limit=50, device_id=None) -> list:
        """Retrieve IoT events with optional device_id filter."""
        return await asyncio.to_thread(self._db.get_iot_events, limit, device_id)

    # ── Ops / maintenance ─────────────────────────────────────────────────

    async def apply_retention(self, **kwargs) -> dict:
        """Apply data retention policy (delete old records)."""
        return await asyncio.to_thread(self._db.apply_retention, **kwargs)

    async def get_stats(self) -> dict:
        """Get database storage statistics (row counts, storage type)."""
        return await asyncio.to_thread(self._db.get_stats)

    async def get_prometheus_restore_data(self) -> dict:
        """Get histogram data for restoring Prometheus counters after restart."""
        return await asyncio.to_thread(self._db.get_prometheus_restore_data)


# Module-level async singleton — mirrors the sync ``db`` in database.py.
# Imported as: ``from infrastructure.database import async_db``
async_db = AsyncDatabase()
