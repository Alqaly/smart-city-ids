-- Migration 001: Unified runtime schema (alerts, analysis, automation, audit, IoT)
-- Created: 2026-02-03
-- Description: Aligns migration schema with runtime database.py

BEGIN;

-- Core alerts table
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
);

CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_threat_type ON alerts(threat_type);

-- Analysis results (LLM outputs)
CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
    model VARCHAR(255),
    analysis JSONB,
    analysis_time_ms INTEGER,
    confidence_score NUMERIC,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_alert_id ON analysis_results(alert_id);

-- Automation actions (operational audit trail)
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
);

CREATE INDEX IF NOT EXISTS idx_actions_alert_id ON automation_actions(alert_id);
CREATE INDEX IF NOT EXISTS idx_actions_type ON automation_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_actions_status ON automation_actions(status);

-- Audit logs (governance decisions)
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
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at);

-- IoT devices table
CREATE TABLE IF NOT EXISTS iot_devices (
    device_id VARCHAR(64) PRIMARY KEY,
    device_type VARCHAR(50),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_count INTEGER DEFAULT 0,
    metadata JSONB
);

-- IoT events table
CREATE TABLE IF NOT EXISTS iot_events (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(64) REFERENCES iot_devices(device_id),
    device_type VARCHAR(50),
    event_type VARCHAR(50),
    value JSONB,
    timestamp TIMESTAMP,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_iot_events_device ON iot_events(device_id);
CREATE INDEX IF NOT EXISTS idx_iot_events_type ON iot_events(event_type);
CREATE INDEX IF NOT EXISTS idx_iot_events_timestamp ON iot_events(timestamp);

COMMIT;
