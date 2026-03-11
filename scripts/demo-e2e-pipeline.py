#!/usr/bin/env python3
"""
Smart City IDS - Verbose End-to-End Evaluation Script
=====================================================

This script traces the complete data flow:
IoT Device → Suricata/Falco → IDS API → LLM Analysis → Dashboard

Usage:
    python scripts/demo-e2e-pipeline.py [--duration 60] [--api-url http://localhost:8000]

Features:
- Verbose logging of each step
- Shows the exact prompt sent to LLM
- Shows the LLM response parsing
- Tracks metrics through the pipeline
- Tests each LLM provider

Data Flow:
    1. IoT devices generate traffic (traffic-camera, healthcare-api, parking-system)
    2. Suricata (network IDS) detects attacks (SQLi, DDoS, exfiltration)
    3. Falco (runtime security) detects suspicious behavior (privilege escalation)
    4. Forwarders send alerts to IDS API at POST /api/alerts/internal
    5. IDS API deduplicates alerts to reduce LLM costs
    6. IDS API sends alert to LLM for analysis
    7. LLM returns severity (1-10), threat type, confidence, recommendations
    8. IDS API applies governance rules (auto-execute vs pending approval)
    9. Kubernetes actions executed (isolate_pod, scale_up, block_ip)
    10. Results stored in database and displayed on dashboard
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
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def log_section(title: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN} {title}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.END}\n")


def log_step(step: str, detail: str = ""):
    """Print a step."""
    print(f"{Colors.GREEN}▶ {step}{Colors.END}")
    if detail:
        print(f"  {detail}")


def log_info(label: str, value: Any = None):
    """Print info."""
    if value is not None:
        print(f"  {Colors.BLUE}{label}:{Colors.END} {value}")
    else:
        print(f"  {Colors.BLUE}{label}{Colors.END}")


def log_error(msg: str):
    """Print error."""
    print(f"  {Colors.RED}✗ {msg}{Colors.END}")


def log_success(msg: str):
    """Print success."""
    print(f"  {Colors.GREEN}✓ {msg}{Colors.END}")


def log_json(data: Dict, indent: int = 4):
    """Print JSON data."""
    print(f"{Colors.YELLOW}{json.dumps(data, indent=indent, default=str)}{Colors.END}")


class IDSDemo:
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        token: Optional[str] = None,
        username: str = "admin",
        password: str = "admin",
    ):
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(timeout=30.0)
        self.start_time = time.time()
        
    async def close(self):
        await self.client.aclose()
        
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def ensure_auth(self) -> bool:
        """Login with admin/admin (or provided creds) if no token supplied."""
        if self.token:
            return True
        try:
            resp = await self.client.post(
                f"{self.api_url}/api/auth/login",
                json={"username": self.username, "password": self.password},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                if self.token:
                    log_success(f"Authenticated as {self.username}")
                    return True
            log_error(f"Login failed ({resp.status_code}) - protected checks may fail")
            return False
        except Exception as e:
            log_error(f"Login failed: {e}")
            return False
    
    async def check_health(self) -> Dict:
        """Check system health."""
        log_step("Checking System Health", f"GET {self.api_url}/health")
        try:
            resp = await self.client.get(f"{self.api_url}/health")
            data = resp.json()
            
            components = data.get('components', {})
            log_info("Kubernetes", components.get('kubernetes', 'unknown'))
            log_info("Database", components.get('database', 'unknown'))
            log_info("Falco", components.get('falco', 'unknown'))
            log_info("Suricata", components.get('suricata', 'unknown'))
            
            llm_providers = components.get('llm_providers', {})
            log_info("LLM Providers", f"{len(llm_providers)} configured")
            for name, status in llm_providers.items():
                print(f"    - {name}: {status}")
                
            return data
        except Exception as e:
            log_error(f"Health check failed: {e}")
            return {}
    
    async def check_llm_diagnostics(self) -> Dict:
        """Check LLM diagnostics."""
        log_step("Checking LLM Diagnostics", f"GET {self.api_url}/api/llm/diagnostics")
        try:
            resp = await self.client.get(f"{self.api_url}/api/llm/diagnostics")
            data = resp.json()
            
            summary = data.get('summary', {})
            log_info("Operational", summary.get('operational', 0))
            log_info("Error", summary.get('error', 0))
            log_info("Cooldown", summary.get('cooldown', 0))
            log_info("Not Configured", summary.get('not_configured', 0))
            
            providers = data.get('providers', {})
            for name, diag in providers.items():
                status = diag.get('status', 'unknown')
                configured = diag.get('configured', False)
                model = diag.get('model', 'unknown')
                print(f"    - {name}: {status} (model: {model})")
                if diag.get('last_error'):
                    print(f"      Error: {diag['last_error'][:80]}")
                    
            return data
        except Exception as e:
            log_error(f"LLM diagnostics failed: {e}")
            return {}
    
    async def test_llm_provider(self, provider: str) -> Dict:
        """Test a specific LLM provider."""
        log_step(f"Testing LLM Provider: {provider.upper()}", f"POST {self.api_url}/api/llm/test/{provider}")
        try:
            test_alert = {
                "prompt": "Analyze this security alert: suspicious outbound connection detected from container 'test-app' to IP 192.168.1.100 on port 4444"
            }
            resp = await self.client.post(
                f"{self.api_url}/api/llm/test/{provider}",
                json=test_alert,
                headers=self._headers()
            )
            data = resp.json()
            
            log_info("Status", data.get('status'))
            log_info("Provider", data.get('provider'))
            log_info("Latency", f"{data.get('latency_ms')}ms")
            log_info("Tokens", data.get('tokens'))
            log_info("Cost", f"${data.get('estimated_cost_usd', 0):.6f}")
            
            if data.get('status') == 'success':
                analysis = data.get('analysis', {})
                log_info("Severity", analysis.get('severity'))
                log_info("Threat Type", analysis.get('threat_type'))
                log_info("Summary", analysis.get('summary', '')[:100])
                log_success("Provider test successful")
            else:
                log_error(f"Provider test failed: {data.get('error')}")
                
            return data
        except Exception as e:
            log_error(f"Provider test failed: {e}")
            return {}
    
    async def check_llm_control(self) -> Dict:
        """Check LLM control center status."""
        log_step("Checking LLM Control Center", f"GET {self.api_url}/api/llm/control/status")
        try:
            resp = await self.client.get(f"{self.api_url}/api/llm/control/status")
            data = resp.json()
            
            log_info("Active Provider", data.get('active_provider') or 'AUTO')
            log_info("Effective Provider", data.get('effective_provider') or '—')
            log_info("Configured Providers", ', '.join(data.get('configured_providers', [])))
            log_info("Fallback Chain", ' → '.join(data.get('fallback_chain', [])))
            
            return data
        except Exception as e:
            log_error(f"LLM control check failed: {e}")
            return {}
    
    async def check_governance(self) -> Dict:
        """Check governance/automation status."""
        log_step("Checking Governance/Automation", f"GET {self.api_url}/api/governance/status")
        try:
            resp = await self.client.get(
                f"{self.api_url}/api/governance/status",
                headers=self._headers()
            )
            data = resp.json()
            
            log_info("Mode", data.get('mode', 'unknown'))
            metrics = data.get('metrics', {})
            log_info("Total Actions", metrics.get('total_actions_requested', 0))
            log_info("Auto Executed", metrics.get('auto_executed', 0))
            log_info("Pending Approval", metrics.get('pending_approval', 0))
            log_info("Approved", metrics.get('approved', 0))
            log_info("Rejected", metrics.get('rejected', 0))
            
            return data
        except Exception as e:
            log_error(f"Governance check failed: {e}")
            return {}
    
    async def check_metrics(self) -> Dict:
        """Check system metrics."""
        log_step("Checking System Metrics", f"GET {self.api_url}/api/metrics")
        try:
            resp = await self.client.get(f"{self.api_url}/api/metrics")
            data = resp.json()
            
            log_info("Total Alerts", data.get('total_alerts', 0))
            log_info("Critical Alerts", data.get('critical_alerts', 0))
            log_info("IoT Devices", data.get('iot_devices_active', 0))
            log_info("Uptime", f"{int(data.get('uptime_seconds', 0) // 60)}m {int(data.get('uptime_seconds', 0) % 60)}s")
            
            by_source = data.get('alerts_by_source', {})
            log_info("Alerts by Source", f"Falco: {by_source.get('falco', 0)}, Suricata: {by_source.get('suricata', 0)}")
            
            return data
        except Exception as e:
            log_error(f"Metrics check failed: {e}")
            return {}
    
    async def send_test_alert(self) -> Dict:
        """Send a test alert to the IDS API."""
        log_step("Sending Test Alert to IDS API", f"POST {self.api_url}/api/alerts")
        
        # Build a realistic Falco-style alert
        alert = {
            "rule": "Outbound Connection from Container",
            "priority": "Notice",
            "output": "14:32:10.123456789: Notice Outbound connection from container (connection=192.168.1.10:45312->192.168.1.100:4444)",
            "time": datetime.now().isoformat(),
            "output_fields": {
                "container.name": "healthcare-api-7d9f4b8c5-x2v9p",
                "container.id": "abc123def456",
                "proc.name": "python3",
                "proc.cmdline": "python3 /app/server.py",
                "fd.sip": "192.168.1.100",
                "fd.sport": "45312",
                "fd.lip": "192.168.1.10",
                "fd.lport": "4444",
                "user.name": "root"
            }
        }
        
        log_info("Alert Rule", alert['rule'])
        log_info("Priority", alert['priority'])
        log_info("Container", alert['output_fields']['container.name'])
        
        try:
            resp = await self.client.post(
                f"{self.api_url}/api/alerts",
                json=alert,
                headers=self._headers()
            )
            data = resp.json()
            
            log_info("Response Status", data.get('status'))
            log_info("Alert ID", data.get('alert_id'))
            log_info("Trace ID", data.get('trace_id'))
            log_info("LLM Engine", data.get('llm_engine'))
            log_info("Processing Time", f"{data.get('processing_time_ms')}ms")
            
            if data.get('analysis'):
                analysis = data['analysis']
                log_info("Severity", analysis.get('severity'))
                log_info("Threat Type", analysis.get('threat_type'))
                log_info("Confidence", analysis.get('confidence'))
                log_info("Summary", analysis.get('summary', '')[:150])
                
                if analysis.get('key_indicators'):
                    log_info("Key Indicators", '')
                    for indicator in analysis['key_indicators'][:3]:
                        print(f"      • {indicator}")
                
                if analysis.get('recommendations'):
                    log_info("Recommendations", '')
                    for rec in analysis['recommendations'][:3]:
                        print(f"      • {rec}")
            
            if data.get('actions_taken'):
                log_info("Actions Taken", data['actions_taken'])
            
            return data
        except Exception as e:
            log_error(f"Failed to send alert: {e}")
            return {}
    
    async def run_full_demo(self, duration: int = 60, skip_provider_tests: bool = False):
        """Run the full end-to-end evaluation flow."""
        log_section("SMART CITY IDS - VERBOSE END-TO-END EVALUATION")
        log_info("API URL", self.api_url)
        log_info("Duration", f"{duration}s")
        log_info("Start Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        await self.ensure_auth()
        
        # Step 1: Health Check
        log_section("STEP 1: SYSTEM HEALTH CHECK")
        await self.check_health()
        
        # Step 2: LLM Diagnostics
        log_section("STEP 2: LLM PROVIDER DIAGNOSTICS")
        await self.check_llm_diagnostics()
        
        # Step 3: LLM Control Center
        log_section("STEP 3: LLM CONTROL CENTER")
        await self.check_llm_control()
        
        # Step 4: Governance
        log_section("STEP 4: GOVERNANCE/AUTOMATION STATUS")
        await self.check_governance()
        
        # Step 5: Test LLM Providers
        log_section("STEP 5: TESTING LLM PROVIDERS")
        llm_diag = await self.check_llm_diagnostics()
        providers = llm_diag.get('providers', {})
        if skip_provider_tests:
            log_info("Provider Tests", "Skipped by flag (--skip-provider-tests)")
        else:
            for provider_name, diag in providers.items():
                if diag.get('configured'):
                    print()
                    await self.test_llm_provider(provider_name)
        
        # Step 6: Send Test Alert
        log_section("STEP 6: SENDING TEST ALERT")
        await self.send_test_alert()
        
        # Step 7: Check Metrics
        log_section("STEP 7: FINAL METRICS")
        await self.check_metrics()
        
        # Summary
        log_section("EVALUATION COMPLETE")
        elapsed = time.time() - self.start_time
        log_info("Total Time", f"{elapsed:.1f}s")
        log_info("Next Steps", "Run live attacks: bash scripts/run-live-attacks.sh --duration 30")


async def main():
    parser = argparse.ArgumentParser(description="Smart City IDS Verbose End-to-End Evaluation")
    parser.add_argument("--api-url", default="http://localhost:8000", help="IDS API URL")
    parser.add_argument("--token", default="", help="Auth token (if required)")
    parser.add_argument("--username", default="admin", help="Login username if --token is not provided")
    parser.add_argument("--password", default="admin", help="Login password if --token is not provided")
    parser.add_argument("--duration", type=int, default=60, help="Scenario run duration")
    parser.add_argument("--skip-provider-tests", action="store_true", help="Skip per-provider LLM test calls (faster, avoids quota/auth noise)")
    args = parser.parse_args()
    
    demo = IDSDemo(
        api_url=args.api_url,
        token=args.token or None,
        username=args.username,
        password=args.password,
    )
    try:
        await demo.run_full_demo(duration=args.duration, skip_provider_tests=args.skip_provider_tests)
    finally:
        await demo.close()


if __name__ == "__main__":
    asyncio.run(main())
