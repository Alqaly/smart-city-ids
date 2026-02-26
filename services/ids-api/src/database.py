"""Database module for persistent alert storage.

Uses PostgreSQL for storing alerts, IoT events, and metrics.
Falls back to in-memory storage if database is unavailable.
"""

import os
import logging
import contextlib
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time
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
    import psycopg2.pool
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available, using in-memory storage")

# Connection pool size — small pool is enough for this workload
_DB_MIN_CONN = 2
_DB_MAX_CONN = 8


class Database:
    """PostgreSQL database handler with connection pool and fallback to memory.

    Uses a ThreadedConnectionPool so concurrent FastAPI handler threads get
    their own connection without blocking each other.  Each query checks out
    a connection, runs, and returns it to the pool in a finally block.
    """

    def __init__(self):
        self._pool: Optional["psycopg2.pool.ThreadedConnectionPool"] = None
        self.use_memory = not PSYCOPG2_AVAILABLE
        self._db_reconnect_interval_s = max(2, int(os.environ.get("DB_RECONNECT_INTERVAL_SECONDS", "10")))
        self._db_monitor_started = False
        self._db_last_mode = "memory" if self.use_memory else "postgresql"
        self._memory_alerts: List[Dict[str, Any]] = []
        self._memory_iot_events: List[Dict[str, Any]] = []
        self._memory_iot_devices: Dict[str, Dict[str, Any]] = {}
        self._memory_analysis_results: List[Dict[str, Any]] = []
        self._memory_automation_actions: List[Dict[str, Any]] = []
        self._memory_audit_logs: List[Dict[str, Any]] = []
        self._memory_system_logs: List[Dict[str, Any]] = []
        self._memory_throttled_alerts: List[Dict[str, Any]] = []
        self._memory_llm_api_calls: List[Dict[str, Any]] = []
        self._memory_llm_provider_health: Dict[str, Dict[str, Any]] = {}

        if PSYCOPG2_AVAILABLE:
            self._connect()
            self._start_db_reconnect_monitor()

    def _connect(self):
        """Create the connection pool and initialise tables."""
        try:
            if self._pool is not None:
                try:
                    self._pool.closeall()
                except Exception:
                    pass
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=_DB_MIN_CONN,
                maxconn=_DB_MAX_CONN,
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=5,
            )
            # Init tables using one pooled connection
            conn = self._pool.getconn()
            try:
                conn.autocommit = True
            finally:
                self._pool.putconn(conn)
            self.use_memory = False
            self._init_tables()
            self._log_db_mode_transition()
            logger.info(f"✅ PostgreSQL pool ready ({_DB_MIN_CONN}-{_DB_MAX_CONN} conns) at {DB_HOST}:{DB_PORT}/{DB_NAME}")
        except Exception as e:
            logger.warning(f"⚠️ Could not connect to PostgreSQL: {e}. Using in-memory storage.")
            self.use_memory = True
            self._log_db_mode_transition()

    def _log_db_mode_transition(self):
        """Log only on storage mode transitions to reduce noise."""
        mode = "memory" if self.use_memory else "postgresql"
        if mode != self._db_last_mode:
            if mode == "postgresql":
                logger.warning("✅ Database recovered: switched from memory-fallback to PostgreSQL")
            else:
                logger.warning("⚠️ Database unavailable: switched to memory-fallback")
            self._db_last_mode = mode

    def _start_db_reconnect_monitor(self):
        """Background monitor that retries PostgreSQL and auto-recovers from fallback.

        This prevents the demo/user-facing dashboard from appearing to "lose"
        history permanently after an IDS API restart race. If PostgreSQL is not
        reachable at startup, the API may enter memory-fallback mode, but this
        monitor keeps retrying and switches back automatically when DB recovers.
        """
        if self._db_monitor_started:
            return
        self._db_monitor_started = True

        def _loop():
            while True:
                try:
                    if self.use_memory:
                        # In fallback mode, keep trying to restore PostgreSQL.
                        self._connect()
                    else:
                        # In DB mode, verify liveness and reconnect if pool dies.
                        self._ensure_connection()
                    self._log_db_mode_transition()
                except Exception as e:
                    logger.debug(f"DB reconnect monitor iteration failed: {e}")
                time.sleep(self._db_reconnect_interval_s)

        t = threading.Thread(target=_loop, name="db-reconnect-monitor", daemon=True)
        t.start()

    # ── Connection helpers ────────────────────────────────────────────

    def _get_conn(self):
        """Check out a connection from the pool, reconnecting if needed."""
        if self._pool is None or self._pool.closed:
            self._connect()
        try:
            conn = self._pool.getconn()
            conn.autocommit = True
            return conn
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise

    def _put_conn(self, conn):
        """Return a connection to the pool."""
        if self._pool and not self._pool.closed:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.warning(f"Failed to return connection to pool: {e}")

    def _ensure_connection(self):
        """Check pool is live; try to reconnect once if not.  Returns bool."""
        if self.use_memory:
            return False
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                self._put_conn(conn)
            return True
        except Exception as e:
            logger.warning(f"Database pool check failed: {e} — attempting reconnect")
            self.use_memory = True
            self._log_db_mode_transition()
            self._connect()
            return not self.use_memory

    # Legacy single-conn attribute kept for backward compat (some code uses self.conn)
    @property
    def conn(self):
        """Return a pooled connection.  Callers that used self.conn directly
        should migrate to the _get_conn()/_put_conn() pattern, but this
        shim prevents AttributeError in legacy code paths."""
        if self.use_memory or self._pool is None:
            return None
        try:
            return self._get_conn()
        except Exception:
            return None

    @conn.setter
    def conn(self, value):
        # Accept but ignore direct assignments (legacy __init__ pattern)
        pass

    @contextlib.contextmanager
    def _cursor(self, cursor_factory=None):
        """Context manager: check out a pooled connection, yield a cursor, return connection.

        Usage (replaces all `with self._cursor() as cur:` patterns)::

            with self._cursor() as cur:
                cur.execute(...)
        """
        if self.use_memory or self._pool is None:
            raise RuntimeError("Database not available")
        conn = self._get_conn()
        try:
            kwargs = {"cursor_factory": cursor_factory} if cursor_factory else {}
            with conn.cursor(**kwargs) as cur:
                yield cur
        finally:
            self._put_conn(conn)

    def _init_tables(self):
        """Create tables if they don't exist. Handles schema migration from older versions."""
        with self._cursor() as cur:
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
            
            # System config table (for LLM priority and cost ceilings)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key VARCHAR(255) PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # LLM API call log (cost/tokens observability, persistent across restarts)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_api_calls (
                    id SERIAL PRIMARY KEY,
                    provider_name VARCHAR(50) NOT NULL,
                    purpose VARCHAR(50),
                    model VARCHAR(255),
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    success BOOLEAN DEFAULT TRUE,
                    latency_ms INTEGER,
                    error_message TEXT,
                    meta JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Provider health snapshot (optional periodic monitoring)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_provider_health (
                    provider_name VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(50) NOT NULL,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details JSONB
                )
            """)
            
            # Initialize default LLM priority if not exists
            cur.execute("""
                INSERT INTO system_config (key, value)
                VALUES ('llm_priority', '["kimi", "gemini", "openai", "anthropic", "xai"]')
                ON CONFLICT (key) DO NOTHING
            """)
            
            # Initialize default cost ceiling if not exists
            cur.execute("""
                INSERT INTO system_config (key, value)
                VALUES ('llm_cost_ceiling', '{"max_daily_usd": 10.0, "current_daily_usd": 0.0, "last_reset": null}')
                ON CONFLICT (key) DO NOTHING
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_api_calls(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_provider_created ON llm_api_calls(provider_name, created_at)")
            
            logger.info("✅ Database tables initialized")
    
    # ============== SYSTEM CONFIG ==============
    
    def get_system_config(self, key: str, default: Any = None) -> Any:
        """Get a system configuration value."""
        if self.use_memory or not self._ensure_connection():
            # Fallback to memory
            if not hasattr(self, '_memory_system_config'):
                self._memory_system_config = {
                    'llm_priority': ["kimi", "gemini", "openai", "anthropic", "xai"],
                    'llm_cost_ceiling': {"max_daily_usd": 10.0, "current_daily_usd": 0.0, "last_reset": None}
                }
            return self._memory_system_config.get(key, default)

        try:
            with self._cursor() as cur:
                cur.execute("SELECT value FROM system_config WHERE key = %s", (key,))
                row = cur.fetchone()
                if row:
                    return row[0]
                return default
        except Exception as e:
            logger.error(f"Error getting system config {key}: {e}")
            return default

    def set_system_config(self, key: str, value: Any) -> bool:
        """Set a system configuration value."""
        if self.use_memory or not self._ensure_connection():
            # Fallback to memory
            if not hasattr(self, '_memory_system_config'):
                self._memory_system_config = {
                    'llm_priority': ["kimi", "gemini", "openai", "anthropic", "xai"],
                    'llm_cost_ceiling': {"max_daily_usd": 10.0, "current_daily_usd": 0.0, "last_reset": None}
                }
            self._memory_system_config[key] = value
            return True

        try:
            with self._cursor() as cur:
                cur.execute("""
                    INSERT INTO system_config (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """, (key, json.dumps(value)))
                return True
        except Exception as e:
            logger.error(f"Error setting system config {key}: {e}")
            return False

    # ============== ALERTS ==============
    
    def add_alert(self, alert: Dict[str, Any]) -> int:
        """Add an alert to the database."""
        if self.use_memory or not self._ensure_connection():
            alert["id"] = len(self._memory_alerts) + 1
            self._memory_alerts.append(alert)
            return alert["id"]

        try:
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor(RealDictCursor) as cur:
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
            with self._cursor(RealDictCursor) as cur:
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
            with self._cursor() as cur:
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
            with self._cursor(RealDictCursor) as cur:
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

    def get_latest_analysis_models(self, alert_ids: List[int]) -> Dict[int, str]:
        """Return latest recorded analysis model/provider for each alert id."""
        ids = [int(i) for i in (alert_ids or []) if str(i).isdigit()]
        if not ids:
            return {}

        if self.use_memory or not self._ensure_connection():
            out: Dict[int, str] = {}
            for row in sorted(self._memory_analysis_results, key=lambda r: int(r.get("id", 0) or 0), reverse=True):
                aid = int(row.get("alert_id") or 0)
                if aid in ids and aid not in out and row.get("model"):
                    out[aid] = str(row.get("model"))
            return out

        try:
            with self._cursor(RealDictCursor) as cur:
                cur.execute("""
                    SELECT DISTINCT ON (alert_id) alert_id, model
                    FROM analysis_results
                    WHERE alert_id = ANY(%s)
                    ORDER BY alert_id, id DESC
                """, (ids,))
                rows = cur.fetchall() or []
                return {int(r["alert_id"]): str(r["model"]) for r in rows if r.get("model")}
        except Exception as e:
            logger.error(f"Error getting latest analysis models: {e}")
            return {}
    
    def get_alert_count(self, source: Optional[str] = None) -> int:
        """Get total alert count."""
        if self.use_memory or not self._ensure_connection():
            if source:
                return len([a for a in self._memory_alerts if a.get("source") == source])
            return len(self._memory_alerts)
        
        try:
            with self._cursor() as cur:
                if source:
                    cur.execute("SELECT COUNT(*) FROM alerts WHERE source = %s", (source,))
                else:
                    cur.execute("SELECT COUNT(*) FROM alerts")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting alert count: {e}")
            return len(self._memory_alerts)

    def get_alert_by_id(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """Get a single alert by its database ID.

        Args:
            alert_id: Integer primary key of the alert row.

        Returns:
            Alert dict if found, None otherwise.
        """
        if self.use_memory or not self._ensure_connection():
            for a in self._memory_alerts:
                if a.get("id") == alert_id:
                    return a
            return None

        try:
            with self._cursor(RealDictCursor) as cur:
                cur.execute("SELECT * FROM alerts WHERE id = %s", (alert_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting alert {alert_id}: {e}")
            return None

    def update_alert_analysis(self, alert_id: int, analysis: dict, severity: int,
                               summary: str, threat_type: str) -> bool:
        """Update the LLM analysis fields of an existing alert.

        Used by the re-analyze feature to overwrite a previous analysis
        with a fresh one from a different (or the same) LLM engine.

        Args:
            alert_id:    Database row ID.
            analysis:    Full LLM analysis dict (stored as JSONB).
            severity:    Updated severity score (1-10).
            summary:     Updated summary text.
            threat_type: Updated threat classification.

        Returns:
            True if the update succeeded, False otherwise.
        """
        if self.use_memory or not self._ensure_connection():
            for a in self._memory_alerts:
                if a.get("id") == alert_id:
                    a["analysis"] = analysis
                    a["severity"] = severity
                    a["summary"] = summary
                    a["threat_type"] = threat_type
                    return True
            return False

        try:
            with self._cursor() as cur:
                cur.execute("""
                    UPDATE alerts
                    SET analysis = %s, severity = %s, summary = %s, threat_type = %s
                    WHERE id = %s
                """, (json.dumps(analysis), severity, summary, threat_type, alert_id))
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating alert {alert_id}: {e}")
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False
    
    def get_alerts_by_severity(self) -> Dict[str, int]:
        """Get alert counts grouped by severity."""
        if self.use_memory or not self._ensure_connection():
            counts = {}
            for a in self._memory_alerts:
                sev = str(a.get("severity", 0))
                counts[sev] = counts.get(sev, 0) + 1
            return counts
        
        try:
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor(RealDictCursor) as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
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
            with self._cursor(RealDictCursor) as cur:
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
            with self._cursor() as cur:
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
            with self._cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM iot_events")
                return cur.fetchone()[0]
        except:
            return 0

    def get_prometheus_restore_data(self) -> Dict[str, Any]:
        """Get detailed metrics to restore Prometheus counters on startup.
        
        This ensures Grafana shows historical data even after pod restarts.
        """
        # Cache to avoid expensive aggregation + noisy logs during dashboard polling.
        # /api/metrics is polled frequently; this should not hit PostgreSQL every time.
        cache_ttl = 300  # seconds
        now = time.time() if 'time' in globals() else __import__('time').time()
        if getattr(self, "_prom_restore_cache", None) is not None and getattr(self, "_prom_restore_cache_ts", 0):
            age = now - float(getattr(self, "_prom_restore_cache_ts", 0))
            if age < cache_ttl:
                return self._prom_restore_cache

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

            data_out = {
                "alerts_by_source_priority": alerts_by_source_priority,
                "alerts_by_severity": alerts_by_severity,
                "alerts_by_threat_type": alerts_by_threat_type,
                "total_processed": total_processed,
                "actions_executed": actions_executed,
                "critical_alerts": critical_alerts,
                "iot_events_by_type": iot_events_by_type,
            }
            self._prom_restore_cache = data_out
            self._prom_restore_cache_ts = now
            return data_out
        
        try:
            data = {}
            with self._cursor() as cur:
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
                
                # Keep this at debug to avoid spam (dashboard polls /api/metrics).
                logger.debug(
                    f"📊 Prometheus restore data: {data['total_processed']} alerts, "
                    f"{len(data['actions_executed'])} action types, "
                    f"{data['critical_alerts']} critical"
                )
            self._prom_restore_cache = data
            self._prom_restore_cache_ts = now
            return data
        except Exception as e:
            logger.error(f"Error getting Prometheus restore data: {e}")
            return {"alerts_by_source_priority": {}, "alerts_by_severity": {}, 
                    "alerts_by_threat_type": {}, "total_processed": 0, "actions_executed": {}}

    # ─────────────────────────────────────────────────────────────────────
    # LLM usage logging (DB-backed) — powers /api/metrics/llm-usage
    # ─────────────────────────────────────────────────────────────────────

    def log_llm_api_call(
        self,
        provider_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        purpose: Optional[str] = None,
        model: Optional[str] = None,
        success: bool = True,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        provider = (provider_name or "").strip().lower()
        if not provider:
            return

        row = {
            "provider_name": provider,
            "purpose": (purpose or None),
            "model": (model or None),
            "prompt_tokens": max(0, int(prompt_tokens or 0)),
            "completion_tokens": max(0, int(completion_tokens or 0)),
            "success": bool(success),
            "latency_ms": int(latency_ms) if latency_ms is not None else None,
            "error_message": error_message,
            "meta": meta or {},
            "created_at": created_at or datetime.utcnow(),
        }

        if self.use_memory or not self._ensure_connection():
            self._memory_llm_api_calls.append(row)
            return

        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_api_calls
                        (provider_name, purpose, model, prompt_tokens, completion_tokens, success, latency_ms, error_message, meta, created_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["provider_name"],
                        row["purpose"],
                        row["model"],
                        row["prompt_tokens"],
                        row["completion_tokens"],
                        row["success"],
                        row["latency_ms"],
                        row["error_message"],
                        json.dumps(row["meta"]),
                        row["created_at"],
                    ),
                )
        except Exception as e:
            logger.debug(f"Failed to log LLM API call (non-fatal): {e}")

    def upsert_llm_provider_health(
        self,
        provider_name: str,
        status: str,
        *,
        checked_at: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        provider = (provider_name or "").strip().lower()
        if not provider:
            return

        row = {
            "provider_name": provider,
            "status": (status or "unknown").strip().lower() or "unknown",
            "checked_at": checked_at or datetime.utcnow(),
            "details": details or {},
        }

        if self.use_memory or not self._ensure_connection():
            self._memory_llm_provider_health[provider] = row
            return

        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_provider_health (provider_name, status, checked_at, details)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (provider_name)
                    DO UPDATE SET status=EXCLUDED.status, checked_at=EXCLUDED.checked_at, details=EXCLUDED.details
                    """,
                    (row["provider_name"], row["status"], row["checked_at"], json.dumps(row["details"])),
                )
        except Exception as e:
            logger.debug(f"Failed to upsert provider health (non-fatal): {e}")

    def get_llm_usage_window(self, start_utc: datetime, end_utc: datetime) -> Dict[str, Any]:
        start_utc = start_utc or datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        end_utc = end_utc or datetime.utcnow()
        if end_utc < start_utc:
            start_utc, end_utc = end_utc, start_utc

        if self.use_memory or not self._ensure_connection():
            rows = [
                r for r in self._memory_llm_api_calls
                if (r.get("created_at") or datetime.utcnow()) >= start_utc and (r.get("created_at") or datetime.utcnow()) <= end_utc
            ]
            by_provider: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                p = (r.get("provider_name") or "unknown").strip().lower() or "unknown"
                agg = by_provider.setdefault(p, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
                agg["calls"] += 1
                agg["prompt_tokens"] += int(r.get("prompt_tokens") or 0)
                agg["completion_tokens"] += int(r.get("completion_tokens") or 0)

            providers_out = []
            for p, agg in sorted(by_provider.items()):
                providers_out.append({
                    "provider": p,
                    "calls": int(agg["calls"]),
                    "prompt_tokens": int(agg["prompt_tokens"]),
                    "completion_tokens": int(agg["completion_tokens"]),
                })

            totals = {
                "calls": sum(p["calls"] for p in providers_out),
                "prompt_tokens": sum(p["prompt_tokens"] for p in providers_out),
                "completion_tokens": sum(p["completion_tokens"] for p in providers_out),
            }
            totals["tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
            return {"start_utc": start_utc.isoformat() + "Z", "end_utc": end_utc.isoformat() + "Z", "totals": totals, "providers": providers_out}

        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT provider_name,
                           COUNT(*) AS calls,
                           COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                           COALESCE(SUM(completion_tokens), 0) AS completion_tokens
                    FROM llm_api_calls
                    WHERE created_at >= %s AND created_at <= %s
                    GROUP BY provider_name
                    ORDER BY provider_name
                    """,
                    (start_utc, end_utc),
                )
                rows = cur.fetchall()
        except Exception as e:
            logger.debug(f"Failed to read llm_api_calls (non-fatal): {e}")
            return {"start_utc": start_utc.isoformat() + "Z", "end_utc": end_utc.isoformat() + "Z", "totals": {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "tokens": 0}, "providers": []}

        providers_out = []
        for provider_name, calls, prompt_tokens, completion_tokens in rows:
            providers_out.append({
                "provider": (provider_name or "unknown"),
                "calls": int(calls or 0),
                "prompt_tokens": int(prompt_tokens or 0),
                "completion_tokens": int(completion_tokens or 0),
            })

        totals = {
            "calls": sum(p["calls"] for p in providers_out),
            "prompt_tokens": sum(p["prompt_tokens"] for p in providers_out),
            "completion_tokens": sum(p["completion_tokens"] for p in providers_out),
        }
        totals["tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
        return {"start_utc": start_utc.isoformat() + "Z", "end_utc": end_utc.isoformat() + "Z", "totals": totals, "providers": providers_out}

    def get_llm_usage_today(self) -> Dict[str, Any]:
        now = datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_llm_usage_window(start, now)


# Global database instance
db = Database()
