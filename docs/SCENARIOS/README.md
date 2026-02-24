# Scenario Specs (Research-Oriented)

Use this folder to document each attack/emulation scenario as a staged, examiner-defensible spec.

## Required sections per scenario

1. **Goal**
- What the scenario demonstrates (detection, analysis, response, impact).

2. **Stages / TTPs**
- Stage-by-stage flow (initial abuse, execution, lateral movement, collection, impact).
- Include ATT&CK / ATT&CK-ICS references where applicable.

3. **Expected Telemetry**
- Suricata fields / rule names
- Falco rule names / runtime behaviors
- IDS API fields (source, rule, severity, llm_engine, actions)
- Dashboard panels/metrics expected to change

4. **Success Criteria**
- What must appear in the dashboard
- What K8s governance action should be proposed/executed (if any)
- What logs/API outputs confirm the stage

5. **Known Limitations**
- What is simulated vs protocol-semantic
- What is planned next (to avoid overclaiming)

## Starter example

- `MQTT_FLOOD_LATERAL_IMPACT.md`

