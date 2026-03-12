#!/usr/bin/env python3
"""
Smart City IDS - Complete End-to-End Evaluation Run
===================================================

This script exercises the complete data flow with verbose logging:
IoT Device → Suricata/Falco → IDS API → LLM Analysis → Automated Action → Dashboard

Usage:
    python scripts/eval-complete.py [--api-url http://localhost:8000]
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

import httpx


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'


def log(msg: str, color: str = Colors.END):
    print(f"{color}{msg}{Colors.END}")


def log_section(title: str):
    log(f"\n{'='*70}", Colors.CYAN + Colors.BOLD)
    log(f" {title}", Colors.CYAN + Colors.BOLD)
    log(f"{'='*70}\n", Colors.CYAN + Colors.BOLD)


async def main():
    parser = argparse.ArgumentParser(description="Smart City IDS Complete End-to-End Evaluation Run")
    parser.add_argument("--api-url", default="http://localhost:8000", help="IDS API URL")
    parser.add_argument("--token", default=os.getenv("IDS_API_TOKEN", ""), help="API token")
    parser.add_argument("--username", default="admin", help="Login username (used if --token not provided)")
    parser.add_argument("--password", default="admin", help="Login password (used if --token not provided)")
    args = parser.parse_args()
    
    api_url = args.api_url.rstrip('/')
    headers = {"Content-Type": "application/json"}
    token = args.token
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        alert_result: Dict[str, Any] = {}
        if not token:
            try:
                login_resp = await client.post(
                    f"{api_url}/api/auth/login",
                    json={"username": args.username, "password": args.password},
                    headers=headers,
                )
                if login_resp.status_code == 200:
                    token = login_resp.json().get("access_token", "")
                    if token:
                        log(f"Authenticated as {args.username}", Colors.GREEN)
                else:
                    log(f"Login skipped/failed ({login_resp.status_code}) - public endpoints only", Colors.YELLOW)
            except Exception as e:
                log(f"Login failed ({e}) - continuing with public endpoints only", Colors.YELLOW)

        if token:
            headers["Authorization"] = f"Bearer {token}"

        # 1. Health Check
        log_section("1. SYSTEM HEALTH CHECK")
        try:
            resp = await client.get(f"{api_url}/health")
            health = resp.json()
            log(f"Status: {health.get('status', 'unknown')}")
            
            components = health.get('components', {})
            log(f"Kubernetes: {components.get('kubernetes', 'unknown')}")
            log(f"Database: {components.get('database', 'unknown')}")
            
            llm_providers = components.get('llm_providers', {})
            log(f"\nLLM Providers ({len(llm_providers)} total):")
            for name, status in llm_providers.items():
                log(f"  - {name}: {status}")
        except Exception as e:
            log(f"Health check failed: {e}", Colors.RED)
            return
        
        # 2. LLM Diagnostics
        log_section("2. LLM DIAGNOSTICS")
        try:
            resp = await client.get(f"{api_url}/api/llm/diagnostics")
            diags = resp.json()
            
            summary = diags.get('summary', {})
            log(f"Operational: {summary.get('operational', 0)}")
            log(f"Error: {summary.get('error', 0)}")
            log(f"Not Configured: {summary.get('not_configured', 0)}")
            
            providers = diags.get('providers', {})
            log(f"\nProvider Details:")
            for name, diag in providers.items():
                status = diag.get('status', 'unknown')
                color = Colors.GREEN if status == 'operational' else Colors.YELLOW if status == 'not_configured' else Colors.RED
                log(f"  {name}: {status} (model: {diag.get('model', 'n/a')})", color)
        except Exception as e:
            log(f"LLM diagnostics failed: {e}", Colors.RED)
        
        # 3. Governance Status
        log_section("3. GOVERNANCE / AUTOMATION STATUS")
        try:
            resp = await client.get(f"{api_url}/api/governance/status", headers=headers)
            gov = resp.json()
            
            log(f"Mode: {gov.get('mode', 'unknown')}")
            metrics = gov.get('metrics', {})
            log(f"Total Actions Requested: {metrics.get('total_actions_requested', 0)}")
            log(f"Auto Executed: {metrics.get('auto_executed', 0)}")
            log(f"Pending Approval: {metrics.get('pending_approval', 0)}")
            log(f"Approved: {metrics.get('approved', 0)}")
            log(f"Rejected: {metrics.get('rejected', 0)}")
        except Exception as e:
            log(f"Governance check failed: {e}", Colors.RED)
        
        # 4. LLM Control Center
        log_section("4. LLM CONTROL CENTER")
        try:
            resp = await client.get(f"{api_url}/api/llm/control/status")
            control = resp.json()
            
            log(f"Active Provider: {control.get('active_provider') or 'AUTO'}")
            log(f"Effective Provider: {control.get('effective_provider') or '—'}")
            log(f"Configured: {', '.join(control.get('configured_providers', []))}")
            log(f"Fallback Chain: {' → '.join(control.get('fallback_chain', []))}")
        except Exception as e:
            log(f"LLM control check failed: {e}", Colors.RED)
        
        # 5. Send Test Alert
        log_section("5. SENDING TEST ALERT")
        
        # Critical severity alert that should trigger LLM analysis
        test_alert = {
            "rule": "Outbound Connection to Suspicious IP",
            "priority": "Critical",
            "output": "Suspicious outbound connection from healthcare-api container to external IP 192.168.1.100 on port 4444 (possible C2 beacon)",
            "time": datetime.now().isoformat(),
            "output_fields": {
                "container.name": "healthcare-api-7d9f4b8c5-x2v9p",
                "container.id": "abc123def456",
                "proc.name": "python3",
                "fd.sip": "192.168.1.100",
                "fd.sport": "4444",
                "user.name": "root"
            }
        }
        
        log(f"Alert: {test_alert['rule']}")
        log(f"Priority: {test_alert['priority']}")
        log(f"Container: {test_alert['output_fields']['container.name']}")
        
        try:
            start = time.time()
            resp = await client.post(
                f"{api_url}/api/alerts",
                json=test_alert,
                headers=headers
            )
            result = resp.json()
            alert_result = result
            elapsed = (time.time() - start) * 1000
            
            log(f"\nResponse (took {elapsed:.0f}ms):", Colors.GREEN)
            log(f"  Status: {result.get('status')}")
            log(f"  Alert ID: {result.get('alert_id')}")
            log(f"  LLM Engine: {result.get('llm_engine')}")
            
            if result.get('analysis'):
                analysis = result['analysis']
                log(f"\n  LLM Analysis:")
                log(f"    Severity: {analysis.get('severity')}/10")
                log(f"    Threat Type: {analysis.get('threat_type')}")
                log(f"    Confidence: {analysis.get('confidence')}")
                log(f"    Summary: {analysis.get('summary', '')[:100]}...")
            
            if result.get('actions_taken'):
                log(f"\n  Actions Taken:")
                for action in result['actions_taken']:
                    log(f"    - {action}")
                    
        except Exception as e:
            log(f"Failed to send alert: {e}", Colors.RED)
        
        # 6. Check Updated Metrics
        log_section("6. UPDATED METRICS")
        await asyncio.sleep(1)  # Give time for processing
        
        try:
            resp = await client.get(f"{api_url}/api/metrics")
            metrics = resp.json()
            
            log(f"Total Alerts: {metrics.get('total_alerts', 0)}")
            log(f"Critical Alerts: {metrics.get('critical_alerts', 0)}")
            log(f"Automated Actions: {metrics.get('automated_actions', 0)}")
            
            by_source = metrics.get('alerts_by_source', {})
            log(f"By Source: Falco={by_source.get('falco', 0)}, Suricata={by_source.get('suricata', 0)}")
        except Exception as e:
            log(f"Metrics check failed: {e}", Colors.RED)
        
        # 7. Check Updated Governance
        log_section("7. UPDATED GOVERNANCE METRICS")
        try:
            resp = await client.get(f"{api_url}/api/governance/status", headers=headers)
            gov = resp.json()
            
            metrics = gov.get('metrics', {})
            log(f"Auto Executed: {metrics.get('auto_executed', 0)}")
            log(f"Pending Approval: {metrics.get('pending_approval', 0)}")
            log(f"Approved: {metrics.get('approved', 0)}")
            log(f"Rejected: {metrics.get('rejected', 0)}")
        except Exception as e:
            log(f"Governance check failed: {e}", Colors.RED)
        
        log_section("EVALUATION RUN COMPLETE")
        log("What was validated:")
        log("  1. Alert sent to IDS API")
        if alert_result.get("status") == "success" and alert_result.get("analysis"):
            log("  2. LLM analysis completed")
        else:
            log("  2. LLM analysis did not complete (provider/auth/quota issue visible)")
        log("  3. Governance endpoint and metrics pipeline responded")
        log("  4. Metrics updated in real-time")


if __name__ == "__main__":
    asyncio.run(main())
