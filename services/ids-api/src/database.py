"""Database module for persistent alert storage.

Uses PostgreSQL for storing alerts, IoT events, and metrics.
Falls back to in-memory storage if database is unavailable.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
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
        self._memory_analysis_results: List[Dict[str, Any]] = []
        self._memory_automation_actions: List[Dict[str, Any]] = []
        self._memory_audit_logs: List[Dict[str, Any]] = []
        self._memory_system_logs: List[Dict[str, Any]] = []
        self._memory_throttled_alerts: List[Dict[str, Any]] = []
        
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
        """Create tables if they don't exist. Handles schema migration from older versions."""
        with self.conn.cursor() as cur:
            # ── Schema migration: detect old schema and drop stale tables ──
            # Old schema had 'created_at' instead of 'timestamp', 'encrypted_alert_data' etc.
            # Since this is a demo, safe to drop and recreate with correct schema.
            try:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'alerts' AND table_schema = 'public'
                """)
                existing_cols = {row[0] for row in cur.fetchall()}
                if existing_cols and 'timestamp' not in existing_cols:
                    logger.warning("⚠️ Detected old alerts schema (missing 'timestamp' column) — migrating...")
                    # Drop dependent tables first (foreign keys)
                    for tbl in ['throttled_alerts', 'system_logs', 'iot_events', 'iot_devices',
                                'audit_logs', 'automation_actions', 'analysis_results', 'alerts']:
                        cur.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
                    logger.info("✅ Old tables dropped — recreating with current schema")
            except Exception as e:
                logger.warning(f"Schema migration check failed (non-fatal): {e}")

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

            # Analysis results table (LLM outputs, auditability)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id SERIAL PRIMARY KEY,
                    alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
                    model VARCHAR(255),
                    analysis JSONB,
                    analysis_time_ms INTEGER,
                    confidence_score NUMERIC,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Automation actions table (operational audit trail)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS automation_actions (
                    id SERIAL PRIMARY KEY,
                    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
                    action_type VARCHAR(255),
                    target_resource VARCHAR(255),
                    target_namespace VARCHAR(255),
                    status VARCHAR(50),
                    error_message TEXT,
                    execution_time_ms INTEGER,
                    mode VARCHAR(50),
                    triggered_by VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # Audit logs table (governance decisions)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    action VARCHAR(255) NOT NULL,
                    resource_type VARCHAR(255),
                    resource_id VARCHAR(255),
                    details JSONB,
                    status VARCHAR(50),
                    error_message TEXT,
                    actor VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            
            # System logs table (for debugging and audit)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id SERIAL PRIMARY KEY,
                    level VARCHAR(20) NOT NULL,
                    component VARCHAR(100),
                    message TEXT,
                    details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Throttled alerts table (alerts that were rate-limited)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS throttled_alerts (
                    id SERIAL PRIMARY KEY,
                    source VARCHAR(50),
                    rule VARCHAR(255),
                    priority VARCHAR(50),
                    throttle_reason VARCHAR(100),
                    raw_alert JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_iot_events_device ON iot_events(device_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_iot_events_type ON iot_events(event_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_analysis_alert_id ON analysis_results(alert_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_alert_id ON automation_actions(alert_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON automation_actions(action_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON automation_actions(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_created ON system_logs(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_throttled_rule ON throttled_alerts(rule)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_throttled_created ON throttled_alerts(created_at)")
            
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
                    INSERT INTO alerts (source, rule, priority, severity, summary, threat_type,
                                        recommendations, automated_actions, raw_alert, analysis, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    alert.get("source"),
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
                logger.info(f"✅ Alert stored in PostgreSQL: id={alert_id}")
                return alert_id
        except Exception as e:
            logger.error(f"Error adding alert to PostgreSQL: {e}")
            # Fallback to memory
            alert["id"] = len(self._memory_alerts) + 1
            self._memory_alerts.append(alert)
            return alert["id"]

    def add_analysis_result(self, alert_id: int, result: Dict[str, Any]) -> int:
        """Add LLM analysis result for an alert."""
        record = {
            "alert_id": alert_id,
            "model": result.get("model"),
            "analysis": result.get("analysis"),
            "analysis_time_ms": result.get("analysis_time_ms"),
            "confidence_score": result.get("confidence_score"),
            "analyzed_at": result.get("analyzed_at", datetime.now())
        }

        if self.use_memory or not self._ensure_connection():
            record["id"] = len(self._memory_analysis_results) + 1
            self._memory_analysis_results.append(record)
            return record["id"]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO analysis_results (alert_id, model, analysis, analysis_time_ms,
                                                  confidence_score, analyzed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    record["alert_id"],
                    record["model"],
                    json.dumps(record["analysis"] or {}),
                    record["analysis_time_ms"],
                    record["confidence_score"],
                    record["analyzed_at"]
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding analysis result: {e}")
            record["id"] = len(self._memory_analysis_results) + 1
            self._memory_analysis_results.append(record)
            return record["id"]

    def add_automation_action(self, action: Dict[str, Any]) -> int:
        """Record an automation action for auditability."""
        if self.use_memory or not self._ensure_connection():
            action["id"] = len(self._memory_automation_actions) + 1
            self._memory_automation_actions.append(action)
            return action["id"]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO automation_actions (
                        alert_id, action_type, target_resource, target_namespace, status,
                        error_message, execution_time_ms, mode, triggered_by, created_at, completed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    action.get("alert_id"),
                    action.get("action_type"),
                    action.get("target_resource"),
                    action.get("target_namespace"),
                    action.get("status"),
                    action.get("error_message"),
                    action.get("execution_time_ms"),
                    action.get("mode"),
                    action.get("triggered_by"),
                    action.get("created_at", datetime.now()),
                    action.get("completed_at")
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding automation action: {e}")
            action["id"] = len(self._memory_automation_actions) + 1
            self._memory_automation_actions.append(action)
            return action["id"]

    def add_audit_log(self, log_entry: Dict[str, Any]) -> int:
        """Record an audit log entry for governance decisions."""
        if self.use_memory or not self._ensure_connection():
            log_entry["id"] = len(self._memory_audit_logs) + 1
            self._memory_audit_logs.append(log_entry)
            return log_entry["id"]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO audit_logs (action, resource_type, resource_id, details,
                                           status, error_message, actor, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    log_entry.get("action"),
                    log_entry.get("resource_type"),
                    log_entry.get("resource_id"),
                    json.dumps(log_entry.get("details", {})),
                    log_entry.get("status"),
                    log_entry.get("error_message"),
                    log_entry.get("actor"),
                    log_entry.get("created_at", datetime.now())
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding audit log: {e}")
            log_entry["id"] = len(self._memory_audit_logs) + 1
            self._memory_audit_logs.append(log_entry)
            return log_entry["id"]

    def add_system_log(self, level: str, component: str, message: str, details: Dict = None) -> int:
        """Add a system log entry for debugging and audit."""
        log_entry = {
            "level": level,
            "component": component,
            "message": message,
            "details": details or {},
            "created_at": datetime.now()
        }
        
        if self.use_memory or not self._ensure_connection():
            log_entry["id"] = len(self._memory_system_logs) + 1
            self._memory_system_logs.append(log_entry)
            return log_entry["id"]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO system_logs (level, component, message, details, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    log_entry["level"],
                    log_entry["component"],
                    log_entry["message"],
                    json.dumps(log_entry["details"]),
                    log_entry["created_at"]
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding system log: {e}")
            log_entry["id"] = len(self._memory_system_logs) + 1
            self._memory_system_logs.append(log_entry)
            return log_entry["id"]

    def add_throttled_alert(self, alert: Dict[str, Any], throttle_reason: str) -> int:
        """Record an alert that was throttled (rate-limited)."""
        record = {
            "source": alert.get("source", "unknown"),
            "rule": alert.get("rule"),
            "priority": alert.get("priority"),
            "throttle_reason": throttle_reason,
            "raw_alert": alert,
            "created_at": datetime.now()
        }
        
        if self.use_memory or not self._ensure_connection():
            record["id"] = len(self._memory_throttled_alerts) + 1
            self._memory_throttled_alerts.append(record)
            return record["id"]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO throttled_alerts (source, rule, priority, throttle_reason, raw_alert, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    record["source"],
                    record["rule"],
                    record["priority"],
                    record["throttle_reason"],
                    json.dumps(record["raw_alert"]),
                    record["created_at"]
                ))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error adding throttled alert: {e}")
            record["id"] = len(self._memory_throttled_alerts) + 1
            self._memory_throttled_alerts.append(record)
            return record["id"]

    def get_system_logs(self, limit: int = 100, level: str = None, component: str = None) -> List[Dict]:
        """Get system logs with optional filtering."""
        if self.use_memory or not self._ensure_connection():
            logs = self._memory_system_logs
            if level:
                logs = [l for l in logs if l.get("level") == level]
            if component:
                logs = [l for l in logs if l.get("component") == component]
            return list(reversed(logs[-limit:]))
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM system_logs WHERE 1=1"
                params = []
                if level:
                    query += " AND level = %s"
                    params.append(level)
                if component:
                    query += " AND component = %s"
                    params.append(component)
                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(query, params)
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting system logs: {e}")
            return []

    def get_throttled_alerts(self, limit: int = 100, rule: str = None) -> List[Dict]:
        """Get throttled alerts with optional filtering."""
        if self.use_memory or not self._ensure_connection():
            alerts = self._memory_throttled_alerts
            if rule:
                alerts = [a for a in alerts if a.get("rule") == rule]
            return list(reversed(alerts[-limit:]))
        
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                if rule:
                    cur.execute("""
                        SELECT * FROM throttled_alerts WHERE rule = %s
                        ORDER BY created_at DESC LIMIT %s
                    """, (rule, limit))
                else:
                    cur.execute("""
                        SELECT * FROM throttled_alerts
                        ORDER BY created_at DESC LIMIT %s
                    """, (limit,))
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting throttled alerts: {e}")
            return []

    def get_throttle_stats(self) -> Dict:
        """Get statistics about throttled alerts."""
        if self.use_memory or not self._ensure_connection():
            return {
                "total_throttled": len(self._memory_throttled_alerts),
                "by_reason": {},
                "by_rule": {}
            }
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM throttled_alerts")
                total = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT throttle_reason, COUNT(*) FROM throttled_alerts
                    GROUP BY throttle_reason
                """)
                by_reason = {row[0]: row[1] for row in cur.fetchall()}
                
                cur.execute("""
                    SELECT rule, COUNT(*) FROM throttled_alerts
                    GROUP BY rule ORDER BY COUNT(*) DESC LIMIT 10
                """)
                by_rule = {row[0]: row[1] for row in cur.fetchall()}
                
                return {
                    "total_throttled": total,
                    "by_reason": by_reason,
                    "by_rule": by_rule
                }
        except Exception as e:
            logger.error(f"Error getting throttle stats: {e}")
            return {"total_throttled": 0, "by_reason": {}, "by_rule": {}}
    
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

    def apply_retention(self, alerts_days: int = 30, iot_days: int = 30,
                        automation_days: int = 180, audit_days: int = 180) -> Dict[str, int]:
        """Apply simple retention policy and return delete counts."""
        def _as_datetime(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return datetime.now()
            return datetime.now()

        cutoffs = {
            "alerts": datetime.now() - timedelta(days=alerts_days),
            "iot_events": datetime.now() - timedelta(days=iot_days),
            "automation_actions": datetime.now() - timedelta(days=automation_days),
            "audit_logs": datetime.now() - timedelta(days=audit_days),
        }
        deleted = {"alerts": 0, "iot_events": 0, "automation_actions": 0, "audit_logs": 0}

        if self.use_memory or not self._ensure_connection():
            before = len(self._memory_alerts)
            self._memory_alerts = [a for a in self._memory_alerts if _as_datetime(a.get("timestamp", datetime.now())) >= cutoffs["alerts"]]
            deleted["alerts"] = before - len(self._memory_alerts)

            before = len(self._memory_iot_events)
            self._memory_iot_events = [e for e in self._memory_iot_events if _as_datetime(e.get("timestamp", datetime.now())) >= cutoffs["iot_events"]]
            deleted["iot_events"] = before - len(self._memory_iot_events)

            before = len(self._memory_automation_actions)
            self._memory_automation_actions = [a for a in self._memory_automation_actions if _as_datetime(a.get("created_at", datetime.now())) >= cutoffs["automation_actions"]]
            deleted["automation_actions"] = before - len(self._memory_automation_actions)

            before = len(self._memory_audit_logs)
            self._memory_audit_logs = [a for a in self._memory_audit_logs if _as_datetime(a.get("created_at", datetime.now())) >= cutoffs["audit_logs"]]
            deleted["audit_logs"] = before - len(self._memory_audit_logs)
            return deleted

        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM alerts WHERE timestamp < %s", (cutoffs["alerts"],))
                deleted["alerts"] = cur.rowcount
                cur.execute("DELETE FROM iot_events WHERE timestamp < %s", (cutoffs["iot_events"],))
                deleted["iot_events"] = cur.rowcount
                cur.execute("DELETE FROM automation_actions WHERE created_at < %s", (cutoffs["automation_actions"],))
                deleted["automation_actions"] = cur.rowcount
                cur.execute("DELETE FROM audit_logs WHERE created_at < %s", (cutoffs["audit_logs"],))
                deleted["audit_logs"] = cur.rowcount
            return deleted
        except Exception as e:
            logger.error(f"Error applying retention policy: {e}")
            return deleted

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
            alerts_by_source_priority = {}
            alerts_by_severity = {}
            alerts_by_threat_type = {}
            actions_executed = {}
            iot_events_by_type = {}

            for alert in self._memory_alerts:
                key = f"{alert.get('source')}:{alert.get('priority')}"
                alerts_by_source_priority[key] = alerts_by_source_priority.get(key, 0) + 1
                sev = str(alert.get("severity"))
                alerts_by_severity[sev] = alerts_by_severity.get(sev, 0) + 1
                threat = alert.get("threat_type")
                if threat:
                    alerts_by_threat_type[threat] = alerts_by_threat_type.get(threat, 0) + 1

            for action in self._memory_automation_actions:
                action_type = action.get("action_type")
                if action_type:
                    actions_executed[action_type] = actions_executed.get(action_type, 0) + 1

            for event in self._memory_iot_events:
                key = f"{event.get('device_id')}:{event.get('event_type')}"
                iot_events_by_type[key] = iot_events_by_type.get(key, 0) + 1

            total_processed = sum(alerts_by_severity.values())
            critical_alerts = sum(
                count for sev, count in alerts_by_severity.items() if sev and sev.isdigit() and int(sev) >= 8
            )

            return {
                "alerts_by_source_priority": alerts_by_source_priority,
                "alerts_by_severity": alerts_by_severity,
                "alerts_by_threat_type": alerts_by_threat_type,
                "total_processed": total_processed,
                "actions_executed": actions_executed,
                "critical_alerts": critical_alerts,
                "iot_events_by_type": iot_events_by_type,
            }
        
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
                
                # Actions executed (from automation_actions table)
                cur.execute("""
                    SELECT action_type, COUNT(*)
                    FROM automation_actions
                    WHERE action_type IS NOT NULL
                    GROUP BY action_type
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
