#!/usr/bin/env python3
"""
Smart City IDS — Demo Attack Runner
====================================
Sends realistic attack alerts directly to the IDS API so they appear
on the Operator Dashboard (LLM analysis, governance, severity, etc.).

Also optionally triggers REAL Falco events by exec-ing commands in pods.

Usage (demo-safe, sends alerts to IDS directly):
    python demo_attack_runner.py                       # Run all 10 scenarios sequentially
    python demo_attack_runner.py --scenario shell      # Run a single scenario
    python demo_attack_runner.py --list                # List available scenarios
    python demo_attack_runner.py --count 5             # Run 5 random scenarios
    python demo_attack_runner.py --rapid               # Rapid-fire 20 alerts in 30s (stress test)
    python demo_attack_runner.py --live                # Also exec real commands in k8s pods (Falco)

Environment:
    IDS_API_URL   — IDS API base URL (default: http://localhost:8000)
    IDS_NODE_PORT — If set, use NodePort URL (http://localhost:<port>)
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── Configuration ───────────────────────────────────────────────────────────

IDS_API_URL = os.getenv("IDS_API_URL", "http://localhost:8000")
IDS_NODE_PORT = os.getenv("IDS_NODE_PORT", "30800")
KUBECONFIG = os.getenv("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")

# Smart City IoT pods (containers that exist in the cluster)
IOT_PODS = [
    "traffic-camera-north", "traffic-camera-south",
    "air-quality-downtown", "air-quality-industrial",
    "smart-light-main-st", "smart-light-park",
    "power-grid-monitor", "water-system-monitor",
    "healthcare-api", "iot-device-enhanced",
]

# ── Attack Scenario Definitions ─────────────────────────────────────────────

SCENARIOS = {
    "shell": {
        "name": "Terminal Shell in Container",
        "category": "Runtime",
        "description": "Attacker spawned an interactive bash shell inside a traffic camera pod",
        "priority": "Critical",
        "rule": "Terminal shell in container",
        "make_output": lambda c: f"Terminal shell in container: bash was spawned in {c} (user=root proc.cmdline=bash parent=runc)",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "proc.cmdline": "bash",
            "user.name": "root",
            "evt.type": "execve",
            "proc.pname": "runc",
        },
        "live_cmd": "bash -c 'echo pwned'",
    },
    "sensitive_read": {
        "name": "Sensitive File Read (/etc/shadow)",
        "category": "File Access",
        "description": "Process read the shadow password file inside an IoT container — credential theft attempt",
        "priority": "Warning",
        "rule": "Read sensitive file untrusted",
        "make_output": lambda c: f"Sensitive file opened for reading: /etc/shadow by process cat in container {c} (user=www-data)",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "proc.cmdline": "cat /etc/shadow",
            "fd.name": "/etc/shadow",
            "user.name": "www-data",
        },
        "live_cmd": "cat /etc/shadow 2>/dev/null || true",
    },
    "outbound": {
        "name": "Unexpected Outbound Connection",
        "category": "Network",
        "description": "IoT sensor made an outbound HTTPS connection to a suspicious external IP",
        "priority": "Notice",
        "rule": "Unexpected outbound connection destination",
        "make_output": lambda c: f"Unexpected outbound connection from {c} to 185.192.69.10:443 (proc=curl user=root)",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "fd.sip": "185.192.69.10",
            "fd.sport": "443",
            "proc.cmdline": "curl https://185.192.69.10/c2",
            "user.name": "root",
        },
        "live_cmd": "curl -s --max-time 2 http://1.1.1.1 >/dev/null 2>&1 || true",
    },
    "port_scan": {
        "name": "Network Port Scan",
        "category": "Recon",
        "description": "Suricata detected a horizontal port scan from an IoT device targeting internal cluster services",
        "priority": "Warning",
        "rule": "ET SCAN Potential VNC Scan 5900-5920",
        "make_output": lambda c: f"Suricata Network Alert: ET SCAN Potential VNC Scan 5900-5920 (10.42.1.5 → 10.42.0.8:5900/TCP) [SigID: 2002911] container={c}",
        "output_fields_fn": lambda c: {
            "container.name": "suricata",
            "alert.signature": "ET SCAN Potential VNC Scan",
            "src_ip": "10.42.1.5",
            "dest_ip": "10.42.0.8",
            "dest_port": "5900",
            "proto": "TCP",
        },
        "live_cmd": None,
    },
    "dns_exfil": {
        "name": "DNS Data Exfiltration",
        "category": "Exfiltration",
        "description": "Suricata detected DNS-based data exfiltration — encoded patient records sent via DNS queries",
        "priority": "Critical",
        "rule": "ET POLICY Possible Data Exfiltration via DNS",
        "make_output": lambda c: f"Suricata Network Alert: ET POLICY Data Exfiltration via DNS (10.42.1.5 → 203.0.113.50:53/UDP) [SigID: 2027863] container={c}",
        "output_fields_fn": lambda c: {
            "container.name": "suricata",
            "alert.signature": "ET POLICY Data Exfiltration via DNS",
            "src_ip": "10.42.1.5",
            "dest_ip": "203.0.113.50",
            "dest_port": "53",
            "proto": "UDP",
        },
        "live_cmd": None,
    },
    "ddos": {
        "name": "DDoS / NTP Amplification",
        "category": "DoS",
        "description": "Large-scale NTP amplification DDoS targeting the smart city traffic management endpoints",
        "priority": "Critical",
        "rule": "ET DOS Possible NTP DDoS Amplification",
        "make_output": lambda c: f"Suricata Network Alert: ET DOS NTP DDoS Amplification (10.0.0.99 → 10.42.0.8:80/UDP) [SigID: 2016150] container={c}",
        "output_fields_fn": lambda c: {
            "container.name": "suricata",
            "alert.signature": "ET DOS NTP DDoS Amplification",
            "src_ip": "10.0.0.99",
            "dest_ip": "10.42.0.8",
            "dest_port": "80",
            "proto": "UDP",
        },
        "live_cmd": None,
    },
    "privesc": {
        "name": "Privilege Escalation (sudo)",
        "category": "PrivEsc",
        "description": "www-data user attempted privilege escalation via sudo inside the power grid monitoring pod",
        "priority": "Critical",
        "rule": "Launch Privileged Container",
        "make_output": lambda c: f"Container privilege escalation: setuid binary in {c} (user=www-data proc.cmdline=sudo su)",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "proc.cmdline": "sudo su",
            "user.name": "www-data",
            "evt.type": "execve",
        },
        "live_cmd": "sudo id 2>/dev/null || true",
    },
    "cryptominer": {
        "name": "Crypto Mining Detected",
        "category": "Cryptojacking",
        "description": "XMRig cryptominer binary executed inside an air quality sensor — resource hijacking",
        "priority": "Critical",
        "rule": "Detect crypto miners using the Stratum protocol",
        "make_output": lambda c: f"Crypto miner detected: xmrig binary started in {c} (user=root cmdline=./xmrig --donate-level 1 -o pool.minexmr.com:4444)",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "proc.cmdline": "./xmrig --donate-level 1 -o pool.minexmr.com:4444",
            "user.name": "root",
            "proc.name": "xmrig",
        },
        "live_cmd": None,
    },
    "sqli": {
        "name": "SQL Injection Attempt",
        "category": "WebApp",
        "description": "SQL injection payload detected in HTTP request to the healthcare API — database compromise attempt",
        "priority": "Critical",
        "rule": "ET WEB_SERVER SQL Injection Attempt",
        "make_output": lambda c: f"Suricata Network Alert: ET WEB_SERVER SQL Injection (10.42.1.5 → healthcare-api:5000) payload={{patient_id: \"1' OR '1'='1\"}} container={c}",
        "output_fields_fn": lambda c: {
            "container.name": "suricata",
            "alert.signature": "ET WEB_SERVER SQL Injection Attempt",
            "src_ip": "10.42.1.5",
            "dest_ip": "10.42.0.20",
            "dest_port": "5000",
            "proto": "TCP",
            "http.uri": "/api/patients?id=1' OR '1'='1",
        },
        "live_cmd": None,
    },
    "lateral": {
        "name": "Lateral Movement (Service Discovery)",
        "category": "Lateral",
        "description": "Compromised IoT pod performing DNS discovery of internal services — lateral movement preparation",
        "priority": "Warning",
        "rule": "Contact K8S API Server From Container",
        "make_output": lambda c: f"K8s service discovery from {c}: nslookup kubernetes.default.svc (user=root) — potential lateral movement",
        "output_fields_fn": lambda c: {
            "container.name": c,
            "proc.cmdline": "nslookup kubernetes.default.svc.cluster.local",
            "user.name": "root",
            "evt.type": "connect",
        },
        "live_cmd": "nslookup kubernetes.default.svc.cluster.local 2>/dev/null || true",
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def pick_container(scenario_id: str) -> str:
    """Pick a realistic container name for the scenario."""
    mapping = {
        "shell": ["traffic-camera-north", "traffic-camera-south"],
        "sensitive_read": ["air-quality-downtown", "healthcare-api"],
        "outbound": ["smart-light-main-st", "smart-light-park"],
        "port_scan": ["iot-device-enhanced"],
        "dns_exfil": ["healthcare-api"],
        "ddos": ["traffic-camera-north"],
        "privesc": ["power-grid-monitor", "water-system-monitor"],
        "cryptominer": ["air-quality-industrial", "air-quality-downtown"],
        "sqli": ["healthcare-api"],
        "lateral": ["iot-device-enhanced", "smart-light-main-st"],
    }
    candidates = mapping.get(scenario_id, IOT_PODS)
    return random.choice(candidates)


def build_alert(scenario_id: str) -> dict:
    """Build an alert payload from a scenario definition."""
    sc = SCENARIOS[scenario_id]
    container = pick_container(scenario_id)
    return {
        "output": sc["make_output"](container),
        "priority": sc["priority"],
        "rule": sc["rule"],
        "time": datetime.now(timezone.utc).isoformat(),
        "output_fields": sc["output_fields_fn"](container),
    }


def send_alert(alert: dict, base_url: str) -> dict:
    """Send alert to /api/alerts/internal (no-auth cluster endpoint)."""
    url = f"{base_url}/api/alerts/internal"
    try:
        resp = requests.post(url, json=alert, timeout=15)
        return resp.json()
    except requests.exceptions.ConnectionError:
        # Try NodePort fallback on multiple IPs
        for host in ["localhost", "127.0.0.1"]:
            node_url = f"http://{host}:{IDS_NODE_PORT}"
            try:
                resp = requests.post(f"{node_url}/api/alerts/internal", json=alert, timeout=15)
                return resp.json()
            except Exception:
                continue
        return {"error": "All connection attempts failed"}
    except Exception as e:
        return {"error": str(e)}


def exec_in_pod(cmd: str):
    """Exec a command in a random smart-city pod to trigger real Falco events."""
    try:
        # Find a suitable pod
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", "smart-city",
             "--field-selector=status.phase=Running",
             "-o", "jsonpath={.items[*].metadata.name}"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "KUBECONFIG": KUBECONFIG},
        )
        pods = [p for p in result.stdout.split() if any(x in p for x in ["traffic-camera", "air-quality", "smart-light", "iot-device"])]
        if not pods:
            return
        pod = random.choice(pods)
        subprocess.run(
            ["kubectl", "exec", "-n", "smart-city", pod, "--", "sh", "-c", cmd],
            capture_output=True, timeout=10,
            env={**os.environ, "KUBECONFIG": KUBECONFIG},
        )
    except Exception:
        pass  # Best-effort


# ── Formatters ───────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def header(text):
    print(f"\n{BOLD}{CYAN}{'═' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 72}{RESET}\n")

def scenario_banner(idx, total, sc_id, sc):
    prio_color = RED if sc["priority"] == "Critical" else YELLOW if sc["priority"] == "Warning" else GREEN
    print(f"  {BOLD}[{idx}/{total}]{RESET} {prio_color}[{sc['priority']}]{RESET} {sc['name']}")
    print(f"       {sc['description']}")
    print(f"       Category: {sc['category']}  |  Rule: {sc['rule']}")

def result_line(resp):
    err = resp.get("error")
    if err:
        print(f"       {RED}✗ Error: {err}{RESET}")
    else:
        analysis = resp.get("analysis", {}) or {}
        sev = analysis.get("severity", resp.get("severity", "-"))
        engine = resp.get("llm_engine", resp.get("engine", "unknown"))
        status = resp.get("status", "unknown")
        threat = analysis.get("threat_type", resp.get("threat_type", "-"))
        summary = analysis.get("summary", "")[:80]
        sev_color = RED if isinstance(sev, int) and sev >= 8 else YELLOW if isinstance(sev, int) and sev >= 5 else GREEN
        print(f"       {GREEN}✓{RESET} Status: {status} | Severity: {sev_color}{sev}{RESET} | Threat: {threat}")
        if summary:
            print(f"         {summary}...")


# ── Main Runners ─────────────────────────────────────────────────────────────

def run_scenario(sc_id: str, base_url: str, live: bool = False, idx: int = 1, total: int = 1):
    sc = SCENARIOS[sc_id]
    scenario_banner(idx, total, sc_id, sc)

    alert = build_alert(sc_id)
    resp = send_alert(alert, base_url)
    result_line(resp)

    if live and sc.get("live_cmd"):
        print(f"       🔧 Executing in cluster pod: {sc['live_cmd'][:60]}...")
        exec_in_pod(sc["live_cmd"])

    print()
    return resp


def run_all(base_url: str, live: bool = False, delay: float = 3.0):
    header("SMART CITY IDS — FULL ATTACK DEMO")
    print(f"  Target:     {base_url}")
    print(f"  Scenarios:  {len(SCENARIOS)}")
    print(f"  Live exec:  {'YES — real Falco triggers' if live else 'No — alerts sent via API only'}")
    print(f"  Delay:      {delay}s between attacks")
    print()

    results = []
    ids = list(SCENARIOS.keys())
    for i, sc_id in enumerate(ids, 1):
        r = run_scenario(sc_id, base_url, live, i, len(ids))
        results.append((sc_id, r))
        if i < len(ids):
            time.sleep(delay)

    # Summary
    header("ATTACK DEMO COMPLETE — SUMMARY")
    ok = sum(1 for _, r in results if r.get("status") in ("processed", "success") and not r.get("error"))
    print(f"  Total:   {len(results)}")
    print(f"  Success: {GREEN}{ok}{RESET}")
    print(f"  Failed:  {RED}{len(results) - ok}{RESET}")
    print()
    print(f"  {BOLD}→ Open the Operator Dashboard to see all alerts:{RESET}")
    print(f"    http://localhost:{IDS_NODE_PORT}/ui")
    print(f"    http://localhost:{IDS_NODE_PORT}/ui")
    print()


def run_rapid(base_url: str, count: int = 20, delay: float = 1.5):
    header("RAPID-FIRE STRESS TEST")
    print(f"  Sending {count} random alerts, {delay}s apart\n")
    ids = list(SCENARIOS.keys())
    for i in range(1, count + 1):
        sc_id = random.choice(ids)
        run_scenario(sc_id, base_url, False, i, count)
        time.sleep(delay)
    print(f"\n  {BOLD}Done!{RESET} Check dashboard → http://localhost:{IDS_NODE_PORT}/ui\n")


def run_count(base_url: str, count: int, live: bool = False, delay: float = 3.0):
    header(f"RUNNING {count} RANDOM SCENARIOS")
    ids = list(SCENARIOS.keys())
    selected = [random.choice(ids) for _ in range(count)]
    for i, sc_id in enumerate(selected, 1):
        run_scenario(sc_id, base_url, live, i, count)
        if i < count:
            time.sleep(delay)
    print(f"\n  {BOLD}Done!{RESET} Check dashboard → http://localhost:{IDS_NODE_PORT}/ui\n")


def list_scenarios():
    header("AVAILABLE ATTACK SCENARIOS")
    for sc_id, sc in SCENARIOS.items():
        prio_color = RED if sc["priority"] == "Critical" else YELLOW if sc["priority"] == "Warning" else GREEN
        live = "✓" if sc.get("live_cmd") else "✗"
        print(f"  {BOLD}{sc_id:16s}{RESET}  {prio_color}[{sc['priority']:8s}]{RESET}  {sc['name']}")
        print(f"                    {sc['description']}")
        print(f"                    Live exec: {live}  |  Category: {sc['category']}")
        print()


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smart City IDS — Demo Attack Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo_attack_runner.py                   # All 10 scenarios
  python demo_attack_runner.py --scenario shell  # Single scenario
  python demo_attack_runner.py --list            # Show all scenarios
  python demo_attack_runner.py --count 5         # 5 random attacks
  python demo_attack_runner.py --rapid           # Stress test (20 fast)
  python demo_attack_runner.py --live            # Also trigger real Falco events
  python demo_attack_runner.py --url http://172.20.10.2:30800  # Custom URL
        """,
    )
    parser.add_argument("--url", default=IDS_API_URL, help=f"IDS API URL (default: {IDS_API_URL})")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), help="Run a single scenario")
    parser.add_argument("--list", action="store_true", help="List all available scenarios")
    parser.add_argument("--count", type=int, help="Run N random scenarios")
    parser.add_argument("--rapid", action="store_true", help="Rapid-fire stress test (20 alerts)")
    parser.add_argument("--live", action="store_true", help="Also exec real commands in pods (Falco triggers)")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between attacks (default: 3)")

    args = parser.parse_args()

    if args.list:
        list_scenarios()
    elif args.scenario:
        header(f"SINGLE SCENARIO: {args.scenario}")
        run_scenario(args.scenario, args.url, args.live)
    elif args.rapid:
        run_rapid(args.url)
    elif args.count:
        run_count(args.url, args.count, args.live, args.delay)
    else:
        run_all(args.url, args.live, args.delay)
