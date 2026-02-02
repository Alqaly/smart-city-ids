# Security Model & Attack Justification

**Version:** 1.0  
**Status:** Capstone II Integration  
**Last Updated:** 2026-02-02

---

## Academic Disclaimer

> **"All traffic and attacks are emulated but statistically grounded, reproducible, and mapped to real-world threat behaviors. The objective is not to mirror a specific city, but to evaluate system behavior under realistic operational stress."**

---

## Attack Classification

### What This Project Does NOT Do

- We do **not** simulate zero-day exploits
- We do **not** attack real systems
- We do **not** claim to detect novel threats

### What This Project DOES Do

We simulate **observable attacker behaviors** that runtime IDS systems (Falco, Suricata) are designed to detect.

> **"We do not simulate zero-day exploits. We simulate observable attacker behaviors that runtime IDS systems are designed to detect."**

---

## MITRE ATT&CK Mapping

All attack simulations are mapped to the MITRE ATT&CK framework for traceability:

| Attack Simulation | What It Represents | MITRE ID | MITRE Technique | Detection Source |
|-------------------|-------------------|----------|-----------------|------------------|
| Privileged shell spawn | Container escape attempt | **T1611** | Escape to Host | Falco |
| Shell in container | Command execution | **T1059.004** | Unix Shell | Falco |
| Unexpected outbound traffic | Data exfiltration | **T1041** | Exfiltration Over C2 Channel | Suricata |
| Excessive connection flood | DDoS attack | **T1498** | Network Denial of Service | Suricata |
| Sensitive file read | Credential access | **T1552.001** | Credentials In Files | Falco |
| Binary download/exec | Malware execution | **T1105** | Ingress Tool Transfer | Falco |
| Netcat listener | Reverse shell | **T1059.004** | Unix Shell | Falco |
| Process in /tmp | Suspicious execution location | **T1036.005** | Match Legitimate Name or Location | Falco |
| Kernel module load | Rootkit installation | **T1547.006** | Kernel Modules and Extensions | Falco |
| Cron modification | Persistence | **T1053.003** | Cron | Falco |

---

## Detection Chain

### How Attacks Flow Through the System

```
Attack Simulator → Container Runtime → Falco/Suricata → Forwarder → IDS API → LLM Analysis → Automated Response
```

### Traceability Per Attack

| Step | Observable Evidence |
|------|---------------------|
| 1. Attack injected | Attack simulator log timestamp |
| 2. Syscall detected | Falco rule name + output |
| 3. Alert forwarded | Forwarder log + HTTP POST |
| 4. Alert stored | PostgreSQL `alerts` table |
| 5. LLM analyzed | `llm_analysis_duration_seconds` metric |
| 6. Action taken | `automated_actions_total{action}` metric |

---

## Falco Rules Triggered

The following Falco rules are intentionally triggered by our attack simulations:

| Falco Rule | Triggered By | Severity |
|------------|--------------|----------|
| `Terminal shell in container` | Shell spawn attacks | Warning |
| `Read sensitive file untrusted` | Credential access attempts | Critical |
| `Contact K8S API Server From Container` | Container escape attempts | Critical |
| `Drop and execute new binary in container` | Malware execution | Critical |
| `Netcat Remote Code Execution in Container` | Reverse shell attempts | Critical |
| `Modify binary dirs` | Persistence attempts | Warning |
| `Write below etc` | Configuration tampering | Warning |

---

## Suricata Rules Triggered

| Suricata Rule Category | Triggered By | Severity |
|------------------------|--------------|----------|
| `ET SCAN` | Port scanning | Medium |
| `ET DOS` | DDoS flood attacks | High |
| `ET POLICY` | Suspicious outbound connections | Medium |
| `ET TROJAN` | Known malware patterns | Critical |

---

## Attack Simulator Scripts

### Available Attack Simulations

| Script | Purpose | MITRE Techniques |
|--------|---------|------------------|
| `attack-simulator/ddos_simulator.py` | Connection flooding | T1498 |
| `attack-simulator/privilege_escalation.py` | Container escape | T1611, T1059 |
| `attack-simulator/data_exfiltration.py` | Outbound data theft | T1041 |
| `attack-simulator/phase4-smart-city-attacks.py` | Combined attack scenarios | Multiple |

### Attack Injection Protocol

1. **Baseline Period**: Run system without attacks for 5 minutes
2. **Attack Window**: Inject specific attack for 2 minutes
3. **Recovery Period**: Stop attack, observe system recovery
4. **Measurement**: Compare metrics across all three periods

---

## Falsifiability Tests

### How to Prove Attacks Are Not Random

**Test 1: Correlation with Injection**
```bash
# Inject attack at known time
python attack-simulator/privilege_escalation.py

# Query alert timestamps
psql -c "SELECT created_at, severity FROM alerts WHERE created_at > NOW() - INTERVAL '5 minutes'"

# Expect: Alert timestamps cluster around injection time
```

**Test 2: Alert Disappearance**
```bash
# Stop all attack simulators
pkill -f attack-simulator

# Wait 2 minutes, query alerts
psql -c "SELECT COUNT(*) FROM alerts WHERE created_at > NOW() - INTERVAL '1 minute'"

# Expect: Near-zero new alerts (only noise from failure injection)
```

**Test 3: Severity Correlation**
```bash
# Inject low-severity attack (port scan)
# Expect: Alerts with severity 3-5

# Inject high-severity attack (shell spawn)
# Expect: Alerts with severity 8-10
```

---

## Examiner FAQ

**Q: How do you know the IDS isn't just triggering randomly?**  
A: Because alert rate, severity, and mitigation actions correlate with injected attack windows and disappear when the injection stops. This is falsifiable and testable.

**Q: Are these real attacks?**  
A: No. These are emulated behaviors that trigger real detection rules. The behaviors are mapped to MITRE ATT&CK techniques that represent documented attacker TTPs.

**Q: Why not use real attack traffic?**  
A: 1) Ethical constraints prevent attacking real systems. 2) Reproducibility requires controlled injection. 3) MITRE-mapped emulation is accepted methodology in security research.

**Q: How do you know Falco/Suricata rules are correct?**  
A: Falco and Suricata rule sets are maintained by security communities (Falco Project, Emerging Threats) and map to known CVEs and attack techniques. We use unmodified rule sets.

---

## Metrics for Attack Verification

### Key Prometheus Queries

```promql
# Alert rate during attack window
rate(alerts_total[5m])

# Severity distribution during attack
histogram_quantile(0.95, security_alert_severity_bucket)

# Automated actions triggered
increase(automated_actions_total[5m])

# LLM latency under load
histogram_quantile(0.95, llm_analysis_duration_seconds_bucket)
```

### Expected Observations

| Metric | Baseline | During Attack | Recovery |
|--------|----------|---------------|----------|
| `alerts_total` rate | <1/min | 10-50/min | <1/min |
| `severity` p95 | 3-4 | 7-9 | 3-4 |
| `automated_actions_total` | 0 | 1-5 | 0 |
| `llm_analysis_duration` | <2s | 2-5s | <2s |

---

## References

- MITRE ATT&CK Framework: https://attack.mitre.org/
- Falco Rules Repository: https://github.com/falcosecurity/rules
- Emerging Threats Suricata Rules: https://rules.emergingthreats.net/
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
