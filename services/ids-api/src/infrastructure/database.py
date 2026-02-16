"""Async database adapter.

Wraps the existing synchronous Database class with asyncio.to_thread()
to prevent blocking the FastAPI event loop.

This is Phase 1 of the database migration:
- Phase 1 (now): async wrapper via to_thread() — fixes event loop blocking
- Phase 2 (future): full asyncpg migration for native async queries

The existing database.py + memory fallback keeps working unchanged.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

# Import the existing sync database singleton
from database import db as _sync_db

logger = logging.getLogger(__name__)


class AsyncDatabase:
    """Async adapter around the synchronous Database singleton.

    Every public method delegates to the sync db via ``asyncio.to_thread``
    so the FastAPI event loop is never blocked by psycopg2 calls.
    """

    def __init__(self, sync_db=None):
        self._db = sync_db or _sync_db

    # ── Convenience property ──────────────────────────────────────────────
    @property
    def sync(self):
        """Direct access to the underlying sync Database (for startup etc.)."""
        return self._db

    # ── Alert operations ──────────────────────────────────────────────────
    async def add_alert(self, alert_data: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_alert, alert_data)

    async def add_analysis_result(self, result: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_analysis_result, result)

    async def add_automation_action(self, action: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_automation_action, action)

    async def add_audit_log(self, log: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_audit_log, log)

    async def add_system_log(self, log: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_system_log, log)

    async def add_throttled_alert(self, alert: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_throttled_alert, alert)

    # ── Query operations ──────────────────────────────────────────────────
    async def get_alerts(self, limit: int = 10, source: str = None) -> List[dict]:
        return await asyncio.to_thread(self._db.get_alerts, limit, source)

    async def get_alert_count(self, source: str = None) -> int:
        return await asyncio.to_thread(self._db.get_alert_count, source)

    async def get_alerts_by_severity(self) -> Dict[str, int]:
        return await asyncio.to_thread(self._db.get_alerts_by_severity)

    async def get_system_logs(self, limit=50, level=None, component=None) -> list:
        return await asyncio.to_thread(self._db.get_system_logs, limit, level, component)

    async def get_throttled_alerts(self, limit=50, rule=None) -> list:
        return await asyncio.to_thread(self._db.get_throttled_alerts, limit, rule)

    async def get_throttle_stats(self) -> dict:
        return await asyncio.to_thread(self._db.get_throttle_stats)

    # ── IoT operations ────────────────────────────────────────────────────
    async def register_iot_device(self, device: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.register_iot_device, device)

    async def get_iot_devices(self) -> list:
        return await asyncio.to_thread(self._db.get_iot_devices)

    async def get_iot_device_count(self) -> int:
        return await asyncio.to_thread(self._db.get_iot_device_count)

    async def add_iot_event(self, event: dict) -> Optional[int]:
        return await asyncio.to_thread(self._db.add_iot_event, event)

    async def get_iot_events(self, limit=50, device_id=None) -> list:
        return await asyncio.to_thread(self._db.get_iot_events, limit, device_id)

    # ── Ops ───────────────────────────────────────────────────────────────
    async def apply_retention(self, **kwargs) -> dict:
        return await asyncio.to_thread(self._db.apply_retention, **kwargs)

    async def get_stats(self) -> dict:
        return await asyncio.to_thread(self._db.get_stats)

    async def get_prometheus_restore_data(self) -> dict:
        return await asyncio.to_thread(self._db.get_prometheus_restore_data)


# Module-level async singleton (mirrors the sync ``db`` in database.py)
async_db = AsyncDatabase()
