#!/usr/bin/env python3
"""
Suricata Eve JSON → IDS API Alert Forwarder

Converts Suricata network IDS alerts (Eve JSON format) to IDS API Alert format.
Listens on UDP:514, parses Eve JSON, and forwards to IDS API /api/alerts endpoint.

Eve JSON format:
  {
    "timestamp": "2026-01-10T12:00:00.000Z",
    "event_type": "alert",
    "alert": {"signature": "...", "signature_id": 1, "category": "..."},
    "src_ip": "10.0.0.1",
    "dest_ip": "10.0.0.2",
    "src_port": 12345,
    "dest_port": 80,
    "proto": "tcp"
  }

IDS API Alert format (expected by /api/alerts):
  {
    "output": "Suricata alert: ...",
    "priority": "High",
    "rule": "Rule name",
    "time": "2026-01-10T12:00:00Z",
    "output_fields": {
      "container.name": "suricata",
      "src_ip": "10.0.0.1",
      "dest_ip": "10.0.0.2",
      "alert.signature": "..."
    }
  }
"""

import json
import logging
import socket
import sys
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ============================================================================
# Configuration
# ============================================================================

IDS_API_URL = "http://ids-api:8000/api/alerts"  # K8s service DNS
IDS_API_TOKEN = "suricata-forwarder-token"  # Bearer token for IDS API
LISTEN_PORT = 514
LISTEN_HOST = "0.0.0.0"
SYSLOG_BUFFER = 4096

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

class SuricataAlert(BaseModel):
    """Suricata Eve JSON alert"""
    timestamp: str
    event_type: str
    alert: Dict[str, Any]
    src_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    src_port: Optional[int] = None
    dest_port: Optional[int] = None
    proto: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow additional Eve JSON fields


class IDSAlert(BaseModel):
    """IDS API Alert format (matches main.py AlertIn)"""
    output: str = Field(..., min_length=1, max_length=2048)
    rule: str = Field(..., min_length=1, max_length=512)
    priority: str = Field(..., pattern="^(Emergency|Alert|Critical|Error|Warning|Notice|Informational|Debug)$")
    time: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    output_fields: Dict[str, str] = Field(default_factory=dict)


# ============================================================================
# FastAPI Application (for health checks)
# ============================================================================

app = FastAPI(title="Suricata Forwarder", version="1.0.0")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "suricata-forwarder",
        "alerts_forwarded": alerts_forwarded_count
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return {
        "suricata_alerts_received": alerts_received_count,
        "suricata_alerts_forwarded": alerts_forwarded_count,
        "suricata_forward_failures": forward_failures_count
    }


# ============================================================================
# Metrics
# ============================================================================

alerts_received_count = 0
alerts_forwarded_count = 0
forward_failures_count = 0


def increment_received():
    global alerts_received_count
    alerts_received_count += 1


def increment_forwarded():
    global alerts_forwarded_count
    alerts_forwarded_count += 1


def increment_failed():
    global forward_failures_count
    forward_failures_count += 1


# ============================================================================
# Conversion Logic
# ============================================================================

def priority_to_syslog(eve_priority: Optional[int]) -> str:
    """
    Convert Suricata alert priority (1-4) to syslog severity.
    
    Suricata priorities:
      1 = High       → Critical
      2 = Medium     → Error
      3 = Low        → Warning
      4 = Very Low   → Notice
    """
    priority_map = {
        1: "Critical",
        2: "Error",
        3: "Warning",
        4: "Notice"
    }
    return priority_map.get(eve_priority, "Warning")


def convert_eve_to_alert(eve_json: Dict[str, Any]) -> Optional[IDSAlert]:
    """
    Convert Suricata Eve JSON to IDS API Alert format.
    
    Returns:
        IDSAlert if conversion successful, None otherwise.
    """
    try:
        # Extract fields
        timestamp = eve_json.get("timestamp", datetime.utcnow().isoformat() + "Z")
        alert_data = eve_json.get("alert", {})
        signature = alert_data.get("signature", "Unknown Suricata Alert")
        signature_id = alert_data.get("signature_id", 0)
        category = alert_data.get("category", "Unknown")
        
        # Severity mapping
        priority_num = alert_data.get("severity", 3)
        priority_str = priority_to_syslog(priority_num)
        
        # Network fields
        src_ip = eve_json.get("src_ip", "unknown")
        dest_ip = eve_json.get("dest_ip", "unknown")
        src_port = eve_json.get("src_port", "")
        dest_port = eve_json.get("dest_port", "")
        proto = eve_json.get("proto", "unknown").upper()
        
        # Build output message
        output = (
            f"Suricata Network Alert: {signature} "
            f"({src_ip}:{src_port} → {dest_ip}:{dest_port}/{proto}) "
            f"[SigID: {signature_id}, Category: {category}]"
        )
        
        # Build output_fields (must be Dict[str, str])
        output_fields = {
            "container.name": "suricata",
            "alert.signature": signature,
            "alert.signature_id": str(signature_id),
            "alert.category": category,
            "src_ip": src_ip,
            "src_port": str(src_port),
            "dest_ip": dest_ip,
            "dest_port": str(dest_port),
            "proto": proto,
            "event_type": eve_json.get("event_type", "unknown")
        }
        
        # Create alert
        alert = IDSAlert(
            output=output,
            rule=signature,
            priority=priority_str,
            time=timestamp,
            output_fields=output_fields
        )
        
        return alert
        
    except Exception as e:
        logger.error(f"Error converting Eve JSON to Alert: {e}")
        return None


# ============================================================================
# UDP Syslog Listener
# ============================================================================

async def forward_to_ids_api(alert: IDSAlert) -> bool:
    """
    Forward alert to IDS API /api/alerts endpoint.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {IDS_API_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                IDS_API_URL,
                json=alert.dict(),
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Forwarded Suricata alert: {alert.rule}")
                increment_forwarded()
                return True
            else:
                logger.error(f"❌ IDS API returned {response.status_code}: {response.text}")
                increment_failed()
                return False
                
    except Exception as e:
        logger.error(f"❌ Error forwarding to IDS API: {e}")
        increment_failed()
        return False


async def udp_listener():
    """
    Listen for Suricata Eve JSON alerts on UDP:514.
    Parse and forward to IDS API.
    """
    logger.info(f"🚀 Suricata Forwarder starting...")
    logger.info(f"📡 Listening on {LISTEN_HOST}:{LISTEN_PORT}/UDP")
    logger.info(f"📤 Forwarding to {IDS_API_URL}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LISTEN_HOST, LISTEN_PORT))
    
    try:
        while True:
            # Receive UDP syslog message
            data, addr = sock.recvfrom(SYSLOG_BUFFER)
            
            try:
                # Parse syslog (strip leading timestamp/priority if present)
                message = data.decode("utf-8", errors="ignore").strip()
                
                # Extract JSON payload
                # Syslog format: <PRI>TAG: JSON
                # Try to find JSON start
                json_start = message.find("{")
                if json_start == -1:
                    logger.warning(f"No JSON in syslog message: {message[:100]}")
                    continue
                
                json_str = message[json_start:]
                eve_json = json.loads(json_str)
                
                increment_received()
                logger.info(f"📥 Received Eve JSON: {eve_json.get('alert', {}).get('signature', 'Unknown')}")
                
                # Convert to IDS API format
                alert = convert_eve_to_alert(eve_json)
                if not alert:
                    logger.warning("Failed to convert Eve JSON")
                    continue
                
                # Forward to IDS API
                await forward_to_ids_api(alert)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in syslog: {e}")
            except Exception as e:
                logger.error(f"Error processing syslog: {e}")
                
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        sock.close()


# ============================================================================
# CLI Test Mode
# ============================================================================

async def test_conversion():
    """Test Eve JSON conversion without network."""
    sample_eve = {
        "timestamp": "2026-01-10T12:00:00.000Z",
        "event_type": "alert",
        "alert": {
            "signature": "Possible SQL Injection Attack",
            "signature_id": 2000000,
            "category": "Web Application Attack",
            "severity": 1
        },
        "src_ip": "192.168.1.100",
        "dest_ip": "10.0.0.5",
        "src_port": 54321,
        "dest_port": 80,
        "proto": "tcp"
    }
    
    logger.info("🧪 Testing Eve JSON conversion...")
    alert = convert_eve_to_alert(sample_eve)
    
    if alert:
        logger.info("✅ Conversion successful!")
        logger.info(f"Output: {alert.output}")
        logger.info(f"Priority: {alert.priority}")
        logger.info(f"Rule: {alert.rule}")
        return alert
    else:
        logger.error("❌ Conversion failed")
        return None


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode
        logger.info("Running in TEST mode...")
        asyncio.run(test_conversion())
    else:
        # Production mode: Run FastAPI + UDP listener
        logger.info("Running in PRODUCTION mode...")
        
        # Start UDP listener in background
        import threading
        listener_thread = threading.Thread(target=lambda: asyncio.run(udp_listener()), daemon=True)
        listener_thread.start()
        
        # Start FastAPI server for health checks
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8100,  # Health/metrics on 8100
            log_level="info"
        )
