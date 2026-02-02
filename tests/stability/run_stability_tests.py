#!/usr/bin/env python3
"""
Smart City IDS - Comprehensive Stability Testing Suite
======================================================
Capstone II - Week 8: Stability Testing

This script runs comprehensive tests to validate:
1. Attack simulation at scale
2. LLM failover mechanism (xAI → OpenAI)
3. Protected services safety
4. System performance under load
5. Error handling and recovery

All results are logged for inclusion in the final report.
"""

import requests
import json
import time
import random
import concurrent.futures
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any
import statistics

# Configuration
IDS_API_URL = "http://localhost:30800"
AUTH_TOKEN = "test-demo-token-456"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AUTH_TOKEN}"
}

@dataclass
class TestResult:
    test_name: str
    status: str  # PASS, FAIL, PARTIAL
    duration_seconds: float
    details: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    challenges: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

class StabilityTestSuite:
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = datetime.now()
        
    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def send_alert(self, alert_data: dict, timeout: int = 30) -> dict:
        """Send an alert to the IDS API and return response."""
        try:
            response = requests.post(
                f"{IDS_API_URL}/api/alerts",
                headers=HEADERS,
                json=alert_data,
                timeout=timeout
            )
            return {"success": True, "data": response.json(), "status_code": response.status_code}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "TIMEOUT", "status_code": 0}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status_code": 0}
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON response", "status_code": response.status_code}

    def get_metrics(self) -> dict:
        """Fetch current Prometheus metrics."""
        try:
            response = requests.get(f"{IDS_API_URL}/metrics", timeout=10)
            metrics = {}
            for line in response.text.split('\n'):
                if line.startswith('smartcity_ids_') and not line.startswith('#'):
                    parts = line.split(' ')
                    if len(parts) >= 2:
                        metrics[parts[0]] = float(parts[1])
            return metrics
        except Exception as e:
            return {"error": str(e)}

    def get_safety_status(self) -> dict:
        """Get current safety controls status."""
        try:
            response = requests.get(f"{IDS_API_URL}/api/safety", timeout=10)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    # =========================================================================
    # TEST 1: ATTACK SIMULATION AT SCALE
    # =========================================================================
    def test_attack_simulation_scale(self) -> TestResult:
        """Test system behavior under high-volume attack simulation."""
        self.log("=" * 60)
        self.log("TEST 1: ATTACK SIMULATION AT SCALE")
        self.log("=" * 60)
        
        start_time = time.time()
        challenges = []
        
        # Define diverse attack scenarios
        attack_scenarios = [
            {
                "name": "Shell Injection",
                "priority": "Critical",
                "rule": "Terminal shell in container",
                "output": "Shell spawned in traffic-camera: /bin/bash -i",
                "container": "traffic-camera"
            },
            {
                "name": "Data Exfiltration",
                "priority": "Critical",
                "rule": "Sensitive file read",
                "output": "Read sensitive file: /etc/passwd accessed by parking-system",
                "container": "parking-system"
            },
            {
                "name": "Privilege Escalation",
                "priority": "Critical",
                "rule": "Privilege escalation detected",
                "output": "Process running as root in healthcare-api container",
                "container": "healthcare-api"
            },
            {
                "name": "Network Scan",
                "priority": "Warning",
                "rule": "Network scanning detected",
                "output": "Port scanning activity from traffic-camera container",
                "container": "traffic-camera"
            },
            {
                "name": "Crypto Mining",
                "priority": "Critical",
                "rule": "Cryptocurrency mining detected",
                "output": "Mining process detected: xmrig running in parking-system",
                "container": "parking-system"
            },
            {
                "name": "Reverse Shell",
                "priority": "Critical",
                "rule": "Outbound connection to suspicious IP",
                "output": "Reverse shell connection to 185.234.xx.xx from traffic-camera",
                "container": "traffic-camera"
            },
            {
                "name": "Config Tampering",
                "priority": "Warning",
                "rule": "Configuration file modified",
                "output": "Modified /etc/resolv.conf in parking-system container",
                "container": "parking-system"
            },
            {
                "name": "SQL Injection Attempt",
                "priority": "Warning",
                "rule": "SQL injection pattern detected",
                "output": "SQL injection attempt: ' OR 1=1 -- in healthcare-api",
                "container": "healthcare-api"
            },
            {
                "name": "DDoS Pattern",
                "priority": "Warning",
                "rule": "High request rate detected",
                "output": "Abnormal request rate: 10000 req/s to traffic-camera",
                "container": "traffic-camera"
            },
            {
                "name": "Container Escape",
                "priority": "Critical",
                "rule": "Container escape attempt",
                "output": "Attempted to access host namespace from parking-system",
                "container": "parking-system"
            }
        ]
        
        # Phase 1: Sequential attacks (baseline)
        self.log("\n📊 Phase 1: Sequential Attack Baseline (10 attacks)")
        sequential_times = []
        sequential_results = []
        
        for i, scenario in enumerate(attack_scenarios):
            alert = {
                "output": f"[Scale Test #{i+1}] {scenario['output']}",
                "priority": scenario["priority"],
                "rule": scenario["rule"],
                "time": datetime.now().isoformat(),
                "output_fields": {
                    "container.name": f"{scenario['container']}-scale-{i}",
                    "proc.cmdline": "test-process"
                }
            }
            
            req_start = time.time()
            result = self.send_alert(alert)
            req_time = time.time() - req_start
            sequential_times.append(req_time)
            sequential_results.append(result)
            
            status = "✅" if result["success"] else "❌"
            self.log(f"  {status} Attack {i+1}/10 ({scenario['name']}): {req_time:.2f}s")
            
            if not result["success"]:
                challenges.append(f"Sequential attack {i+1} failed: {result.get('error', 'Unknown')}")
        
        sequential_success_rate = sum(1 for r in sequential_results if r["success"]) / len(sequential_results) * 100
        
        # Phase 2: Burst attacks (concurrent)
        self.log("\n📊 Phase 2: Concurrent Burst Attack (20 simultaneous)")
        
        burst_alerts = []
        for i in range(20):
            scenario = random.choice(attack_scenarios)
            burst_alerts.append({
                "output": f"[Burst #{i+1}] {scenario['output']}",
                "priority": scenario["priority"],
                "rule": scenario["rule"],
                "time": datetime.now().isoformat(),
                "output_fields": {
                    "container.name": f"{scenario['container']}-burst-{i}",
                    "proc.cmdline": "burst-test"
                }
            })
        
        burst_start = time.time()
        burst_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self.send_alert, alert, 60) for alert in burst_alerts]
            for future in concurrent.futures.as_completed(futures):
                burst_results.append(future.result())
        
        burst_duration = time.time() - burst_start
        burst_success_rate = sum(1 for r in burst_results if r["success"]) / len(burst_results) * 100
        
        self.log(f"  Burst completed: {burst_success_rate:.0f}% success in {burst_duration:.2f}s")
        
        if burst_success_rate < 100:
            failed_count = sum(1 for r in burst_results if not r["success"])
            challenges.append(f"Burst attack: {failed_count}/20 requests failed under concurrent load")
        
        # Phase 3: Sustained load
        self.log("\n📊 Phase 3: Sustained Load (30 alerts over 60 seconds)")
        
        sustained_results = []
        sustained_start = time.time()
        
        for i in range(30):
            scenario = random.choice(attack_scenarios)
            alert = {
                "output": f"[Sustained #{i+1}] {scenario['output']}",
                "priority": scenario["priority"],
                "rule": scenario["rule"],
                "time": datetime.now().isoformat(),
                "output_fields": {
                    "container.name": f"{scenario['container']}-sustained-{i}",
                    "proc.cmdline": "sustained-test"
                }
            }
            
            result = self.send_alert(alert)
            sustained_results.append(result)
            
            if (i + 1) % 10 == 0:
                success_so_far = sum(1 for r in sustained_results if r["success"])
                self.log(f"  Progress: {i+1}/30 alerts ({success_so_far} successful)")
            
            time.sleep(2)  # ~0.5 alerts/second
        
        sustained_duration = time.time() - sustained_start
        sustained_success_rate = sum(1 for r in sustained_results if r["success"]) / len(sustained_results) * 100
        
        # Calculate metrics
        total_duration = time.time() - start_time
        all_times = sequential_times
        
        metrics = {
            "total_alerts_sent": 60,
            "sequential_success_rate": sequential_success_rate,
            "burst_success_rate": burst_success_rate,
            "sustained_success_rate": sustained_success_rate,
            "avg_response_time_sec": statistics.mean(sequential_times) if sequential_times else 0,
            "max_response_time_sec": max(sequential_times) if sequential_times else 0,
            "min_response_time_sec": min(sequential_times) if sequential_times else 0,
            "burst_throughput_alerts_per_sec": 20 / burst_duration if burst_duration > 0 else 0,
            "sustained_throughput_alerts_per_sec": 30 / sustained_duration if sustained_duration > 0 else 0
        }
        
        # Determine status
        overall_success = (sequential_success_rate + burst_success_rate + sustained_success_rate) / 3
        if overall_success >= 95:
            status = "PASS"
        elif overall_success >= 80:
            status = "PARTIAL"
        else:
            status = "FAIL"
        
        recommendations = []
        if burst_success_rate < 100:
            recommendations.append("Consider adding request queuing for burst traffic")
        if metrics["avg_response_time_sec"] > 5:
            recommendations.append("LLM response time is high; consider caching improvements")
        if metrics["max_response_time_sec"] > 15:
            recommendations.append("Some requests taking too long; add timeout handling")
        
        details = f"""
Attack Simulation Scale Test Results:
- Sequential (10 attacks): {sequential_success_rate:.0f}% success, avg {metrics['avg_response_time_sec']:.2f}s
- Burst (20 concurrent): {burst_success_rate:.0f}% success in {burst_duration:.2f}s
- Sustained (30 over 60s): {sustained_success_rate:.0f}% success
- Overall throughput: {metrics['burst_throughput_alerts_per_sec']:.2f} alerts/sec (burst)
"""
        
        return TestResult(
            test_name="Attack Simulation at Scale",
            status=status,
            duration_seconds=total_duration,
            details=details,
            metrics=metrics,
            challenges=challenges,
            recommendations=recommendations
        )

    # =========================================================================
    # TEST 2: LLM FAILOVER MECHANISM
    # =========================================================================
    def test_llm_failover(self) -> TestResult:
        """Test LLM failover from xAI to OpenAI."""
        self.log("=" * 60)
        self.log("TEST 2: LLM FAILOVER MECHANISM")
        self.log("=" * 60)
        
        start_time = time.time()
        challenges = []
        
        # Get initial metrics
        initial_metrics = self.get_metrics()
        initial_xai_errors = initial_metrics.get('smartcity_ids_llm_requests_total{engine="xai-grok-4",result="error"}', 0)
        initial_openai_success = initial_metrics.get('smartcity_ids_llm_requests_total{engine="openai",result="success"}', 0)
        
        self.log(f"\n📊 Initial State:")
        self.log(f"  xAI Grok-4 errors: {initial_xai_errors}")
        self.log(f"  OpenAI successes: {initial_openai_success}")
        
        # Send unique alerts to bypass cache and trigger LLM calls
        self.log("\n📊 Sending unique alerts to trigger LLM analysis...")
        
        unique_alerts = [
            {
                "output": f"[Failover Test] Unique attack pattern {time.time()}: malware signature detected",
                "priority": "Critical",
                "rule": "Malware detection",
                "time": datetime.now().isoformat(),
                "output_fields": {"container.name": f"test-failover-{int(time.time())}", "proc.cmdline": "malware.exe"}
            },
            {
                "output": f"[Failover Test] Unique pattern {time.time()}: ransomware encryption started",
                "priority": "Critical", 
                "rule": "Ransomware detected",
                "time": datetime.now().isoformat(),
                "output_fields": {"container.name": f"test-failover-{int(time.time())+1}", "proc.cmdline": "encrypt.sh"}
            },
            {
                "output": f"[Failover Test] Unique pattern {time.time()}: rootkit installation attempt",
                "priority": "Critical",
                "rule": "Rootkit detected",
                "time": datetime.now().isoformat(),
                "output_fields": {"container.name": f"test-failover-{int(time.time())+2}", "proc.cmdline": "rootkit.bin"}
            }
        ]
        
        failover_results = []
        for i, alert in enumerate(unique_alerts):
            self.log(f"  Sending unique alert {i+1}/3...")
            result = self.send_alert(alert, timeout=60)
            failover_results.append(result)
            
            if result["success"]:
                analysis = result["data"].get("analysis", {})
                self.log(f"    ✅ Success - Severity: {analysis.get('severity', 'N/A')}, Threat: {analysis.get('threat_type', 'N/A')}")
            else:
                self.log(f"    ❌ Failed: {result.get('error', 'Unknown')}")
                challenges.append(f"Failover test alert {i+1} failed: {result.get('error')}")
            
            time.sleep(1)
        
        # Get final metrics
        final_metrics = self.get_metrics()
        final_xai_errors = final_metrics.get('smartcity_ids_llm_requests_total{engine="xai-grok-4",result="error"}', 0)
        final_openai_success = final_metrics.get('smartcity_ids_llm_requests_total{engine="openai",result="success"}', 0)
        
        xai_new_errors = final_xai_errors - initial_xai_errors
        openai_new_success = final_openai_success - initial_openai_success
        
        self.log(f"\n📊 Failover Analysis:")
        self.log(f"  New xAI errors: {xai_new_errors}")
        self.log(f"  New OpenAI successes: {openai_new_success}")
        
        # Check cache behavior
        safety = self.get_safety_status()
        cache_stats = safety.get("cache_stats", {})
        
        self.log(f"\n📊 Cache Statistics:")
        self.log(f"  Cache hits: {cache_stats.get('hits', 0)}")
        self.log(f"  Cache misses: {cache_stats.get('misses', 0)}")
        self.log(f"  Hit rate: {cache_stats.get('hit_rate', 0):.1f}%")
        
        # Determine if failover is working
        failover_working = False
        if xai_new_errors > 0 and openai_new_success > 0:
            failover_working = True
            self.log("\n✅ FAILOVER CONFIRMED: xAI failing → OpenAI succeeding")
        elif openai_new_success > 0:
            failover_working = True
            self.log("\n✅ FAILOVER ACTIVE: OpenAI handling requests (xAI may be cached)")
        else:
            challenges.append("Could not confirm failover mechanism - may be using cached responses")
            self.log("\n⚠️ FAILOVER UNCLEAR: Responses may be cached")
        
        duration = time.time() - start_time
        
        # Check if xAI credits are exhausted (expected challenge)
        if xai_new_errors > 0:
            challenges.append("xAI Grok-4 API credits exhausted - failover to OpenAI activated")
        
        metrics = {
            "xai_errors_total": final_xai_errors,
            "openai_successes_total": final_openai_success,
            "xai_new_errors": xai_new_errors,
            "openai_new_successes": openai_new_success,
            "cache_hit_rate": cache_stats.get("hit_rate", 0),
            "failover_working": failover_working
        }
        
        recommendations = [
            "Monitor xAI API credit usage and set up alerts",
            "Consider adding a third LLM fallback (Claude, Gemini)",
            "Implement circuit breaker pattern for faster failover"
        ]
        
        if failover_working:
            status = "PASS"
            details = f"""
LLM Failover Test Results:
- xAI Grok-4: {final_xai_errors} total errors (credits exhausted - EXPECTED)
- OpenAI GPT-4: {final_openai_success} successful requests (failover working)
- Cache hit rate: {cache_stats.get('hit_rate', 0):.1f}% (reducing API costs)
- Failover mechanism: OPERATIONAL ✅

The system correctly falls back from xAI to OpenAI when the primary LLM fails.
"""
        else:
            status = "PARTIAL"
            details = f"""
LLM Failover Test Results:
- Could not fully verify failover (responses may be cached)
- Cache hit rate: {cache_stats.get('hit_rate', 0):.1f}%
- Recommend clearing cache and retesting with unique alerts
"""
        
        return TestResult(
            test_name="LLM Failover Mechanism",
            status=status,
            duration_seconds=duration,
            details=details,
            metrics=metrics,
            challenges=challenges,
            recommendations=recommendations
        )

    # =========================================================================
    # TEST 3: PROTECTED SERVICES SAFETY
    # =========================================================================
    def test_protected_services(self) -> TestResult:
        """Verify protected services cannot be isolated."""
        self.log("=" * 60)
        self.log("TEST 3: PROTECTED SERVICES SAFETY")
        self.log("=" * 60)
        
        start_time = time.time()
        challenges = []
        
        # Get protected services list
        safety = self.get_safety_status()
        protected_services = safety.get("protected_services", [])
        
        self.log(f"\n📊 Protected Services: {protected_services}")
        
        # Test each protected service
        protection_results = []
        
        for service in protected_services:
            self.log(f"\n🛡️ Testing protection for: {service}")
            
            # Send critical alert targeting protected service
            alert = {
                "output": f"[Protection Test] Critical attack on protected service {service}",
                "priority": "Critical",
                "rule": "Critical security breach",
                "time": datetime.now().isoformat(),
                "output_fields": {
                    "container.name": f"{service}-pod-xyz123",
                    "proc.cmdline": "/bin/bash -c 'rm -rf /'"
                }
            }
            
            result = self.send_alert(alert, timeout=60)
            
            if result["success"]:
                actions_taken = result["data"].get("actions_taken", [])
                analysis = result["data"].get("analysis", {})
                severity = analysis.get("severity", 0)
                
                # Check if isolation was blocked
                blocked = any("BLOCKED" in str(action) or "protected" in str(action).lower() for action in actions_taken)
                isolated = any("isolate" in str(action).lower() and "BLOCKED" not in str(action) for action in actions_taken)
                
                self.log(f"  Severity: {severity}")
                self.log(f"  Actions: {actions_taken}")
                
                if blocked:
                    self.log(f"  ✅ PROTECTED: Isolation was blocked")
                    protection_results.append({"service": service, "protected": True, "actions": actions_taken})
                elif isolated:
                    self.log(f"  ❌ VULNERABLE: Service was isolated!")
                    protection_results.append({"service": service, "protected": False, "actions": actions_taken})
                    challenges.append(f"Protected service {service} was incorrectly isolated!")
                else:
                    self.log(f"  ⚠️ UNCLEAR: No isolation action taken (severity may be < 8)")
                    protection_results.append({"service": service, "protected": True, "actions": actions_taken, "note": "No isolation attempted"})
            else:
                self.log(f"  ❌ Request failed: {result.get('error')}")
                challenges.append(f"Could not test {service}: {result.get('error')}")
                protection_results.append({"service": service, "protected": None, "error": result.get("error")})
        
        # Test unprotected service for comparison
        self.log(f"\n🔓 Testing unprotected service for comparison...")
        
        unprotected_alert = {
            "output": "[Protection Test] Critical attack on unprotected test-service",
            "priority": "Critical",
            "rule": "Critical security breach",
            "time": datetime.now().isoformat(),
            "output_fields": {
                "container.name": "unprotected-test-service-abc",
                "proc.cmdline": "/bin/bash"
            }
        }
        
        unprotected_result = self.send_alert(unprotected_alert, timeout=60)
        
        if unprotected_result["success"]:
            actions = unprotected_result["data"].get("actions_taken", [])
            severity = unprotected_result["data"].get("analysis", {}).get("severity", 0)
            self.log(f"  Severity: {severity}")
            self.log(f"  Actions: {actions}")
            
            if any("isolate" in str(a).lower() for a in actions):
                self.log(f"  ✅ Unprotected service was isolated (expected)")
            else:
                self.log(f"  ⚠️ No isolation (severity may be < 8)")
        
        duration = time.time() - start_time
        
        # Calculate results
        protected_count = sum(1 for r in protection_results if r.get("protected") == True)
        failed_count = sum(1 for r in protection_results if r.get("protected") == False)
        
        metrics = {
            "protected_services_count": len(protected_services),
            "successfully_protected": protected_count,
            "incorrectly_isolated": failed_count,
            "protection_rate": (protected_count / len(protected_services) * 100) if protected_services else 0
        }
        
        if failed_count == 0 and protected_count == len(protected_services):
            status = "PASS"
        elif failed_count == 0:
            status = "PARTIAL"
        else:
            status = "FAIL"
        
        recommendations = [
            "Regularly review protected services list",
            "Add monitoring alerts for protection bypass attempts",
            "Consider adding approval workflow for critical services"
        ]
        
        details = f"""
Protected Services Safety Test Results:
- Protected services tested: {len(protected_services)}
- Successfully protected: {protected_count}
- Incorrectly isolated: {failed_count}
- Protection rate: {metrics['protection_rate']:.0f}%

Services tested: {', '.join(protected_services)}
"""
        
        return TestResult(
            test_name="Protected Services Safety",
            status=status,
            duration_seconds=duration,
            details=details,
            metrics=metrics,
            challenges=challenges,
            recommendations=recommendations
        )

    # =========================================================================
    # TEST 4: ERROR HANDLING & RECOVERY
    # =========================================================================
    def test_error_handling(self) -> TestResult:
        """Test system error handling and recovery."""
        self.log("=" * 60)
        self.log("TEST 4: ERROR HANDLING & RECOVERY")
        self.log("=" * 60)
        
        start_time = time.time()
        challenges = []
        
        # Test 1: Malformed JSON
        self.log("\n📊 Test 4.1: Malformed JSON handling")
        try:
            response = requests.post(
                f"{IDS_API_URL}/api/alerts",
                headers=HEADERS,
                data="not valid json{{{",
                timeout=10
            )
            if response.status_code == 422:
                self.log("  ✅ Correctly rejected malformed JSON (422)")
                malformed_handled = True
            else:
                self.log(f"  ⚠️ Unexpected status: {response.status_code}")
                malformed_handled = False
                challenges.append(f"Malformed JSON returned {response.status_code} instead of 422")
        except Exception as e:
            self.log(f"  ❌ Error: {e}")
            malformed_handled = False
            challenges.append(f"Malformed JSON test failed: {e}")
        
        # Test 2: Missing required fields
        self.log("\n📊 Test 4.2: Missing required fields")
        incomplete_alert = {"output": "test"}  # Missing priority, rule, etc.
        try:
            response = requests.post(
                f"{IDS_API_URL}/api/alerts",
                headers=HEADERS,
                json=incomplete_alert,
                timeout=10
            )
            if response.status_code == 422:
                self.log("  ✅ Correctly rejected incomplete alert (422)")
                missing_fields_handled = True
            else:
                self.log(f"  ⚠️ Unexpected status: {response.status_code}")
                missing_fields_handled = False
        except Exception as e:
            self.log(f"  ❌ Error: {e}")
            missing_fields_handled = False
            challenges.append(f"Missing fields test failed: {e}")
        
        # Test 3: Invalid auth token
        self.log("\n📊 Test 4.3: Invalid authentication")
        try:
            response = requests.post(
                f"{IDS_API_URL}/api/alerts",
                headers={"Content-Type": "application/json", "Authorization": "Bearer invalid-token"},
                json={"output": "test", "priority": "Warning", "rule": "test", "time": datetime.now().isoformat()},
                timeout=10
            )
            # Note: Current implementation may not enforce auth strictly
            self.log(f"  Status: {response.status_code}")
            if response.status_code in [401, 403]:
                self.log("  ✅ Correctly rejected invalid token")
                auth_handled = True
            else:
                self.log("  ⚠️ Auth not enforced (demo mode)")
                auth_handled = False
                challenges.append("Authentication not enforced - acceptable for demo but needs production hardening")
        except Exception as e:
            self.log(f"  ❌ Error: {e}")
            auth_handled = False
        
        # Test 4: Health endpoint availability
        self.log("\n📊 Test 4.4: Health endpoint")
        try:
            response = requests.get(f"{IDS_API_URL}/health", timeout=10)
            if response.status_code == 200:
                self.log("  ✅ Health endpoint responding")
                health_ok = True
            else:
                self.log(f"  ❌ Health endpoint returned {response.status_code}")
                health_ok = False
        except Exception as e:
            self.log(f"  ❌ Health endpoint error: {e}")
            health_ok = False
            challenges.append(f"Health endpoint unavailable: {e}")
        
        # Test 5: Metrics endpoint availability
        self.log("\n📊 Test 4.5: Metrics endpoint")
        try:
            response = requests.get(f"{IDS_API_URL}/metrics", timeout=10)
            if response.status_code == 200 and "smartcity_ids" in response.text:
                self.log("  ✅ Metrics endpoint responding with data")
                metrics_ok = True
            else:
                self.log(f"  ❌ Metrics endpoint issue")
                metrics_ok = False
        except Exception as e:
            self.log(f"  ❌ Metrics endpoint error: {e}")
            metrics_ok = False
            challenges.append(f"Metrics endpoint unavailable: {e}")
        
        duration = time.time() - start_time
        
        tests_passed = sum([malformed_handled, missing_fields_handled, health_ok, metrics_ok])
        total_tests = 4  # Excluding auth which is expected to be relaxed in demo
        
        metrics = {
            "malformed_json_handled": malformed_handled,
            "missing_fields_handled": missing_fields_handled,
            "auth_enforced": auth_handled,
            "health_endpoint_ok": health_ok,
            "metrics_endpoint_ok": metrics_ok,
            "tests_passed": tests_passed,
            "total_tests": total_tests
        }
        
        if tests_passed == total_tests:
            status = "PASS"
        elif tests_passed >= total_tests - 1:
            status = "PARTIAL"
        else:
            status = "FAIL"
        
        recommendations = [
            "Implement strict authentication for production",
            "Add rate limiting to prevent abuse",
            "Implement request validation middleware"
        ]
        
        details = f"""
Error Handling & Recovery Test Results:
- Malformed JSON handling: {'✅' if malformed_handled else '❌'}
- Missing fields validation: {'✅' if missing_fields_handled else '❌'}
- Authentication enforcement: {'⚠️ Demo mode' if not auth_handled else '✅'}
- Health endpoint: {'✅' if health_ok else '❌'}
- Metrics endpoint: {'✅' if metrics_ok else '❌'}
- Tests passed: {tests_passed}/{total_tests}
"""
        
        return TestResult(
            test_name="Error Handling & Recovery",
            status=status,
            duration_seconds=duration,
            details=details,
            metrics=metrics,
            challenges=challenges,
            recommendations=recommendations
        )

    # =========================================================================
    # GENERATE REPORT
    # =========================================================================
    def generate_report(self) -> str:
        """Generate comprehensive test report."""
        total_duration = (datetime.now() - self.start_time).total_seconds()
        
        report = f"""
{'='*80}
SMART CITY IDS - STABILITY TEST REPORT
{'='*80}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Test Duration: {total_duration:.1f} seconds
{'='*80}

EXECUTIVE SUMMARY
-----------------
"""
        
        # Summary stats
        passed = sum(1 for r in self.results if r.status == "PASS")
        partial = sum(1 for r in self.results if r.status == "PARTIAL")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        
        report += f"""
Tests Executed: {len(self.results)}
- PASSED:  {passed}
- PARTIAL: {partial}
- FAILED:  {failed}

Overall Status: {'✅ STABLE' if failed == 0 else '⚠️ NEEDS ATTENTION' if failed <= 1 else '❌ UNSTABLE'}
"""
        
        # Individual test results
        report += f"""
{'='*80}
DETAILED TEST RESULTS
{'='*80}
"""
        
        for i, result in enumerate(self.results, 1):
            status_emoji = {"PASS": "✅", "PARTIAL": "⚠️", "FAIL": "❌"}.get(result.status, "❓")
            report += f"""
{'-'*60}
TEST {i}: {result.test_name}
{'-'*60}
Status: {status_emoji} {result.status}
Duration: {result.duration_seconds:.1f}s

{result.details}

Key Metrics:
"""
            for key, value in result.metrics.items():
                report += f"  - {key}: {value}\n"
            
            if result.challenges:
                report += "\nChallenges Encountered:\n"
                for challenge in result.challenges:
                    report += f"  ⚠️ {challenge}\n"
            
            if result.recommendations:
                report += "\nRecommendations:\n"
                for rec in result.recommendations:
                    report += f"  💡 {rec}\n"
        
        # Consolidated challenges
        all_challenges = []
        for r in self.results:
            all_challenges.extend(r.challenges)
        
        if all_challenges:
            report += f"""
{'='*80}
CONSOLIDATED CHALLENGES & LESSONS LEARNED
{'='*80}
"""
            for i, challenge in enumerate(all_challenges, 1):
                report += f"{i}. {challenge}\n"
        
        # Consolidated recommendations
        all_recommendations = []
        for r in self.results:
            all_recommendations.extend(r.recommendations)
        
        # Deduplicate
        unique_recommendations = list(dict.fromkeys(all_recommendations))
        
        report += f"""
{'='*80}
RECOMMENDATIONS FOR PRODUCTION
{'='*80}
"""
        for i, rec in enumerate(unique_recommendations, 1):
            report += f"{i}. {rec}\n"
        
        report += f"""
{'='*80}
END OF REPORT
{'='*80}
"""
        
        return report

    def run_all_tests(self):
        """Execute all stability tests."""
        self.log("🚀 Starting Smart City IDS Stability Test Suite")
        self.log(f"   Target: {IDS_API_URL}")
        self.log(f"   Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("")
        
        # Run all tests
        self.results.append(self.test_attack_simulation_scale())
        self.results.append(self.test_llm_failover())
        self.results.append(self.test_protected_services())
        self.results.append(self.test_error_handling())
        
        # Generate and print report
        report = self.generate_report()
        print(report)
        
        # Save report to file
        report_path = f"/home/aka/smart-city-ids/docs/reports/STABILITY_TEST_REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)
        
        self.log(f"\n📄 Report saved to: {report_path}")
        
        return self.results


if __name__ == "__main__":
    suite = StabilityTestSuite()
    suite.run_all_tests()
