"""Database module for persistent alert storage.

Uses PostgreSQL for storing alerts, IoT events, and metrics.
Falls back to in-memory storage if database is unavailable.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smartcity_ids")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Try to import psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available, using in-memory storage")


class Database:
    """PostgreSQL database handler with fallback to memory."""
    
    def __init__(self):
        self.conn = None
        self.use_memory = not PSYCOPG2_AVAILABLE
        self._memory_alerts: List[Dict[str, Any]] = []
        self._memory_iot_events: List[Dict[str, Any]] = []
        self._memory_iot_devices: Dict[str, Dict[str, Any]] = {}
        
        if PSYCOPG2_AVAILABLE:
            self._connect()
    
    def _connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=5
            )
            self.conn.autocommit = True
            self._init_tables()
            self.use_memory = False
            logger.info(f"✅ Connected to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
        except Exception as e:
            logger.warning(f"⚠️ Could not connect to PostgreSQL: {e}. Using in-memory storage.")
            self.use_memory = True
    
    def _ensure_connection(self):
        """Ensure database connection is active."""
        if self.use_memory:
            return False
        try:
            if self.conn is None or self.conn.closed:
                self._connect()
            # Test connection
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Database connection lost: {e}")
            self._connect()
            return not self.use_memory
    
    def _init_tables(self):
        """Create tables if they don't exist."""
        with self.conn.cursor() as cur:
            # Alerts table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    source VARCHAR(50) NOT NULL,
                    rule VARCHAR(255),
                    priority VARCHAR(50),
                    severity INTEGER,
                    summary TEXT,
                    threat_type VARCHAR(100),
                    recommendations JSONB,
                    automated_actions JSONB,
                    raw_alert JSONB,
                    analysis JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # IoT devices table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS iot_devices (
                    device_id VARCHAR(64) PRIMARY KEY,
                    device_type VARCHAR(50),
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_count INTEGER DEFAULT 0,
                    metadata JSONB
                )
            """)
            
            # IoT events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS iot_events (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR(64) REFERENCES iot_devices(device_id),
                    device_type VARCHAR(50),
                    event_type VARCHAR(50),
                    value JSONB,
                    timestamp TIMESTAMP,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB
                )
            """)
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_iot_events_device ON iot_events(device_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_iot_events_type ON iot_events(event_type)")
            
            logger.info("✅ Database tables initialized")
    
    # ============== ALERTS ==============
    
    def add_alert(self, alert: Dict[str, Any]) -> int:
        """Add an alert to the database."""
        if self.use_memory or not self._ensure_connection():
            alert["id"] = len(self._memory_alerts) + 1
            self._memory_alerts.append(alert)
            return alert["id"]
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO alerts (source, rule, priority, severity, summary, 
                                       threat_type, recommendations, automated_actions,
                                       raw_alert, analysis, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    alert.get("source", "unknown"),
                    alert.get("rule"),
                    alert.get("priority"),
                    alert.get("severity"),
                    alert.get("summary"),
                    alert.get("threat_type"),
                    json.dumps(alert.get("recommendations", [])),
                    json.dumps(alert.get("automated_actions", [])),
                    json.dumps(alert.get("raw_alert", {})),
                    json.dumps(alert.get("analysis", {})),
                    alert.get("timestamp", datetime.now())
                ))
                alert_id = cur.fetchone()[0]
                return alert_id
        except Exception as e:
            logger.error(f"Error adding alert to database: {e}")
            # Fallback to memory
            alert["id"] = len(self._memory_alerts) + 1
            self._memory_alerts.append(alert)
            return alert["id"]
    
    def get_alerts(self, limit: int = 100, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get alerts from database."""
        if self.use_memory or not self._ensure_connection():
            filtered = self._memory_alerts
            if source:
                filtered = [a for a in filtered if a.get("source") == source]
            return list(reversed(filtered[-limit:]))
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                if source:
                    cur.execute("""
                        SELECT * FROM alerts WHERE source = %s 
                        ORDER BY id DESC LIMIT %s
                    """, (source, limit))
                else:
                    cur.execute("""
                        SELECT * FROM alerts ORDER BY id DESC LIMIT %s
                    """, (limit,))
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return list(reversed(self._memory_alerts[-limit:]))
    
    def get_alert_count(self, source: Optional[str] = None) -> int:
        """Get total alert count."""
        if self.use_memory or not self._ensure_connection():
            if source:
                return len([a for a in self._memory_alerts if a.get("source") == source])
            return len(self._memory_alerts)
        
        try:
            with self.conn.cursor() as cur:
                if source:
                    cur.execute("SELECT COUNT(*) FROM alerts WHERE source = %s", (source,))
                else:
                    cur.execute("SELECT COUNT(*) FROM alerts")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting alert count: {e}")
            return len(self._memory_alerts)
    
    def get_alerts_by_severity(self) -> Dict[str, int]:
        """Get alert counts grouped by severity."""
        if self.use_memory or not self._ensure_connection():
            counts = {}
            for a in self._memory_alerts:
                sev = str(a.get("severity", 0))
                counts[sev] = counts.get(sev, 0) + 1
            return counts
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT severity, COUNT(*) FROM alerts 
                    GROUP BY severity ORDER BY severity
                """)
                return {str(row[0]): row[1] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"Error getting severity stats: {e}")
            return {}
    
    # ============== IOT DEVICES ==============
    
    def register_iot_device(self, device_id: str, device_type: str, metadata: Dict = None) -> bool:
        """Register or update an IoT device."""
        now = datetime.now()
        
        if self.use_memory or not self._ensure_connection():
            if device_id not in self._memory_iot_devices:
                self._memory_iot_devices[device_id] = {
                    "device_id": device_id,
                    "device_type": device_type,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "event_count": 0,
                    "metadata": metadata or {}
                }
                return True  # New device
            else:
                self._memory_iot_devices[device_id]["last_seen"] = now.isoformat()
                self._memory_iot_devices[device_id]["event_count"] += 1
                return False  # Existing device
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO iot_devices (device_id, device_type, metadata)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE SET
                        last_seen = CURRENT_TIMESTAMP,
                        event_count = iot_devices.event_count + 1
                    RETURNING (xmax = 0) as is_new
                """, (device_id, device_type, json.dumps(metadata or {})))
                is_new = cur.fetchone()[0]
                return is_new
        except Exception as e:
            logger.error(f"Error registering IoT device: {e}")
            return False
    
    def get_iot_devices(self) -> List[Dict[str, Any]]:
        """Get all registered IoT devices."""
        if self.use_memory or not self._ensure_connection():
            return list(self._memory_iot_devices.values())
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM iot_devices ORDER BY last_seen DESC")
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting IoT devices: {e}")
            return list(self._memory_iot_devices.values())
    
    def get_iot_device_count(self) -> int:
        """Get number of registered IoT devices."""
        if self.use_memory or not self._ensure_connection():
            return len(self._memory_iot_devices)
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM iot_devices")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting IoT device count: {e}")
            return len(self._memory_iot_devices)
    
    # ============== IOT EVENTS ==============
    
    def add_iot_event(self, event: Dict[str, Any]) -> int:
        """Add an IoT event to the database."""
        if self.use_memory or not self._ensure_connection():
            event["id"] = len(self._memory_iot_events) + 1
            self._memory_iot_events.append(event)
            return event["id"]
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO iot_events (device_id, device_type, event_type, 
                                           value, timestamp, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    event.get("device_id"),
                    event.get("device_type"),
                    event.get("event_type"),
                    json.dumps(event.get("value", {})),
                    event.get("timestamp", datetime.now()),
                    json.dumps(event.get("metadata", {}))
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding IoT event: {e}")
            event["id"] = len(self._memory_iot_events) + 1
            self._memory_iot_events.append(event)
            return event["id"]
    
    def get_iot_events(self, limit: int = 100, device_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get IoT events from database."""
        if self.use_memory or not self._ensure_connection():
            filtered = self._memory_iot_events
            if device_id:
                filtered = [e for e in filtered if e.get("device_id") == device_id]
            return list(reversed(filtered[-limit:]))
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                if device_id:
                    cur.execute("""
                        SELECT * FROM iot_events WHERE device_id = %s 
                        ORDER BY id DESC LIMIT %s
                    """, (device_id, limit))
                else:
                    cur.execute("""
                        SELECT * FROM iot_events ORDER BY id DESC LIMIT %s
                    """, (limit,))
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting IoT events: {e}")
            return list(reversed(self._memory_iot_events[-limit:]))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {
            "storage_type": "memory" if self.use_memory else "postgresql",
            "total_alerts": self.get_alert_count(),
            "alerts_by_source": {
                "falco": self.get_alert_count("falco"),
                "suricata": self.get_alert_count("suricata")
            },
            "iot_devices": self.get_iot_device_count(),
            "iot_events": len(self._memory_iot_events) if self.use_memory else self._get_iot_event_count()
        }
        return stats
    
    def _get_iot_event_count(self) -> int:
        """Get IoT event count from database."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM iot_events")
                return cur.fetchone()[0]
        except:
            return 0

    def get_prometheus_restore_data(self) -> Dict[str, Any]:
        """Get detailed metrics to restore Prometheus counters on startup.
        
        This ensures Grafana shows historical data even after pod restarts.
        """
        if self.use_memory or not self._ensure_connection():
            return {"alerts_by_source_priority": {}, "alerts_by_severity": {}, 
                    "alerts_by_threat_type": {}, "total_processed": 0, "actions_executed": {}}
        
        try:
            data = {}
            with self.conn.cursor() as cur:
                # Alerts by source and priority
                cur.execute("""
                    SELECT source, priority, COUNT(*) 
                    FROM alerts GROUP BY source, priority
                """)
                data["alerts_by_source_priority"] = {
                    f"{row[0]}:{row[1]}": row[2] for row in cur.fetchall()
                }
                
                # Alerts by severity
                cur.execute("""
                    SELECT severity, COUNT(*) FROM alerts 
                    WHERE severity IS NOT NULL GROUP BY severity
                """)
                data["alerts_by_severity"] = {str(row[0]): row[1] for row in cur.fetchall()}
                
                # Alerts by threat type
                cur.execute("""
                    SELECT threat_type, COUNT(*) FROM alerts 
                    WHERE threat_type IS NOT NULL GROUP BY threat_type
                """)
                data["alerts_by_threat_type"] = {row[0]: row[1] for row in cur.fetchall()}
                
                # Total processed (successful)
                cur.execute("SELECT COUNT(*) FROM alerts WHERE severity IS NOT NULL")
                data["total_processed"] = cur.fetchone()[0]
                
                # Actions executed (from automated_actions column)
                cur.execute("""
                    SELECT jsonb_array_elements_text(automated_actions) as action, COUNT(*)
                    FROM alerts 
                    WHERE automated_actions IS NOT NULL AND automated_actions != 'null'::jsonb
                    GROUP BY action
                """)
                data["actions_executed"] = {row[0]: row[1] for row in cur.fetchall()}
                
                # Critical alerts count (severity >= 8)
                cur.execute("SELECT COUNT(*) FROM alerts WHERE severity >= 8")
                data["critical_alerts"] = cur.fetchone()[0]
                
                # IoT events by type
                cur.execute("""
                    SELECT device_id, event_type, COUNT(*) FROM iot_events 
                    GROUP BY device_id, event_type
                """)
                data["iot_events_by_type"] = {
                    f"{row[0]}:{row[1]}": row[2] for row in cur.fetchall()
                }
                
                logger.info(f"📊 Prometheus restore data: {data['total_processed']} alerts, "
                           f"{len(data['actions_executed'])} action types, "
                           f"{data['critical_alerts']} critical")
                
            return data
        except Exception as e:
            logger.error(f"Error getting Prometheus restore data: {e}")
            return {"alerts_by_source_priority": {}, "alerts_by_severity": {}, 
                    "alerts_by_threat_type": {}, "total_processed": 0, "actions_executed": {}}


# Global database instance
db = Database()
