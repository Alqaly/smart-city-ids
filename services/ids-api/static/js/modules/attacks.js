/**
 * attacks.js — Attack Simulation Engine Tab
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * 12 predefined MITRE ATT&CK for ICS scenarios + custom alert injection.
 *
 * Design decision (addressing feedback):
 *   ATTACK_SCENARIOS are kept client-side.  They are:
 *     • Static metadata (never changes at runtime)
 *     • Needed only for the rendering layer
 *     • The backend validates alert payloads independently
 *   Moving them to a backend endpoint would add a round-trip on tab switch
 *   without any security or maintenance benefit.  The actual alert injection
 *   goes through /api/alerts/internal which validates server-side.
 */

import { store } from '../state.js';
import { api } from '../api.js';
import { $, esc, sevBadge, severityToPriority } from '../utils.js';

// ══════════════════════════════════════════════════════════════════════════
// Scenario Registry — 12 MITRE ATT&CK for ICS attack templates
// ══════════════════════════════════════════════════════════════════════════

const ALL_PODS = ['traffic-camera', 'parking-system', 'healthcare-api', 'env-sensor', 'street-lighting'];
function randomPod(exclude) {
  const pool = exclude ? ALL_PODS.filter(p => p !== exclude) : ALL_PODS;
  return pool[Math.floor(Math.random() * pool.length)];
}

export const ATTACK_SCENARIOS = [
  // ── Initial Access ──
  { id: 0, name: 'DDoS Traffic Cameras', cat: 'Denial of Service', source: 'suricata', threat: 'DDoS / Volumetric Flood', pod: 'traffic-camera', sev: 9, color: '#ef4444', duration: 15000, icon: '\uD83C\uDF10', particles: 50, mitre: 'T0866', mitreName: 'Exploitation of Remote Services', description: 'SYN flood targeting ONVIF Profile S camera endpoints. Saturates RTSP/HTTP ports to blind surveillance.' },
  { id: 1, name: 'Shell Healthcare Pod', cat: 'Execution', source: 'falco', threat: 'Privilege Escalation', pod: 'healthcare-api', sev: 8, color: '#f97316', duration: 12000, icon: '\uD83D\uDC1A', particles: 30, mitre: 'T0807', mitreName: 'Command-Line Interface', description: 'Reverse shell spawned inside HL7 FHIR R4 container. Attacker gains CLI access to patient data endpoints.' },
  { id: 2, name: 'Port Scan Parking', cat: 'Discovery', source: 'suricata', threat: 'Reconnaissance', pod: 'parking-system', sev: 6, color: '#eab308', duration: 10000, icon: '\uD83D\uDD0D', particles: 20, mitre: 'T0846', mitreName: 'Remote System Discovery', description: 'Sequential SYN scan of MQTT broker (1883) and CoAP (5683) ports on parking sensor network.' },
  { id: 3, name: 'Exfil Smart Lights', cat: 'Exfiltration', source: 'falco', threat: 'Data Exfiltration', pod: 'street-lighting', sev: 7, color: '#00d4ff', duration: 18000, icon: '\uD83D\uDCE4', particles: 40, mitre: 'T0882', mitreName: 'Theft of Operational Information', description: 'DALI-2 luminaire schedule data exfiltrated via DNS tunneling. Contains zone dimming profiles and energy usage.' },
  // ── New scenarios for 5 emulators ──
  { id: 4, name: 'Modbus Register Overwrite', cat: 'Impair Process', source: 'falco', threat: 'Sensor Manipulation', pod: 'env-sensor', sev: 9, color: '#a855f7', duration: 14000, icon: '\u2699\uFE0F', particles: 45, mitre: 'T0836', mitreName: 'Modify Parameter', description: 'Unauthorized write to Modbus holding registers 40001-40016 (PM2.5/O3 values). Falsifies EPA AQI readings to hide pollution event.' },
  { id: 5, name: 'OPC UA Node Injection', cat: 'Impair Process', source: 'falco', threat: 'Protocol Abuse', pod: 'env-sensor', sev: 8, color: '#ec4899', duration: 13000, icon: '\uD83C\uDFED', particles: 35, mitre: 'T0855', mitreName: 'Unauthorized Command Message', description: 'Rogue OPC UA client injects fabricated temperature nodes into environmental monitoring namespace.' },
  { id: 6, name: 'ONVIF Camera Hijack', cat: 'Lateral Movement', source: 'falco', threat: 'Device Takeover', pod: 'traffic-camera', sev: 9, color: '#dc2626', duration: 16000, icon: '\uD83C\uDFA5', particles: 50, mitre: 'T0867', mitreName: 'Lateral Tool Transfer', description: 'Attacker exploits WS-Discovery to pivot between ONVIF cameras. PTZ controls seized, ANPR feed redirected.' },
  { id: 7, name: 'FHIR Patient Data Tamper', cat: 'Impact', source: 'falco', threat: 'Data Integrity', pod: 'healthcare-api', sev: 10, color: '#b91c1c', duration: 20000, icon: '\u2620\uFE0F', particles: 55, mitre: 'T0831', mitreName: 'Manipulation of Control', description: 'Medication dosage modified in FHIR MedicationRequest resources. LOINC vitals observations altered to hide critical patient state.' },
  { id: 8, name: 'MQTT Broker Poisoning', cat: 'Impact', source: 'suricata', threat: 'Message Injection', pod: 'parking-system', sev: 8, color: '#059669', duration: 12000, icon: '\uD83D\uDC8A', particles: 35, mitre: 'T0830', mitreName: 'Man in the Middle', description: 'Rogue MQTT messages published to parking/+/status topics. SenML payloads report all bays as vacant causing traffic chaos.' },
  { id: 9, name: 'TALQ Gateway Spoof', cat: 'Evasion', source: 'suricata', threat: 'Identity Spoofing', pod: 'street-lighting', sev: 7, color: '#6366f1', duration: 11000, icon: '\uD83D\uDCA1', particles: 25, mitre: 'T0856', mitreName: 'Spoof Reporting Message', description: 'Fake TALQ v2.4 gateway sends spoofed outdoor-light-point state reports. Hides luminaire failures across 3 zones.' },
  { id: 10, name: 'Ransomware IoT Fleet', cat: 'Impact', source: 'falco', threat: 'Ransomware', pod: 'traffic-camera', sev: 10, color: '#991b1b', duration: 22000, icon: '\uD83D\uDD12', particles: 60, mitre: 'T0828', mitreName: 'Loss of Productivity and Revenue', description: 'Simulated ransomware encrypts ONVIF config, Modbus maps, and DALI scene files across the entire IoT fleet.' },
  { id: 11, name: 'Credential Harvest RPi', cat: 'Collection', source: 'falco', threat: 'Credential Theft', pod: 'traffic-camera', sev: 7, color: '#d97706', duration: 10000, icon: '\uD83D\uDD11', particles: 20, mitre: 'T0859', mitreName: 'Valid Accounts', description: 'Attacker harvests API keys from Raspberry Pi motion sensor config. Uses stolen creds to inject false alerts via /api/iot/sensor.' },
];

// ══════════════════════════════════════════════════════════════════════════
// Tab Renderer
// ══════════════════════════════════════════════════════════════════════════

function attackSeverityClass(sev) {
  return sev >= 8 ? 'badge-crit' : sev >= 6 ? 'badge-high' : 'badge-med';
}

/**
 * Render the attack simulation tab: stats, category filter, scenario grid, MITRE table.
 */
export function renderAttackTab() {
  const state = store.getState();
  const categories = [...new Set(ATTACK_SCENARIOS.map(a => a.cat))];
  const targets = [...new Set(ATTACK_SCENARIOS.map(a => a.pod))];
  const mitres = [...new Set(ATTACK_SCENARIOS.map(a => a.mitre))];

  const atkScEl = $('atkScenarioCount');
  if (atkScEl) atkScEl.textContent = ATTACK_SCENARIOS.length + ' + Custom';
  const atkMiEl = $('atkMitreCount');
  if (atkMiEl) atkMiEl.textContent = mitres.length;
  const atkTgEl = $('atkTargetCount');
  if (atkTgEl) atkTgEl.textContent = targets.length + '/5';
  const atkRnEl = $('atkRunCount');
  if (atkRnEl) atkRnEl.textContent = state.attackRunCount;

  // ── Category filter chips ──────────────────────────────────────────
  const activeCategory = state.activeCategory;
  let chips = '<button class="btn btn-sm ' + (activeCategory === 'all' ? 'btn-primary' : 'btn-outline') +
    '" onclick="window._filterAttacks(\'all\')">All (' + ATTACK_SCENARIOS.length + ')</button>';
  categories.forEach(cat => {
    const count = ATTACK_SCENARIOS.filter(a => a.cat === cat).length;
    chips += '<button class="btn btn-sm ' + (activeCategory === cat ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterAttacks(\'' + cat + '\')">' + cat + ' (' + count + ')</button>';
  });
  const catFilterEl = $('attackCategoryFilter');
  if (catFilterEl) catFilterEl.innerHTML = chips;

  // ── Scenario cards ─────────────────────────────────────────────────
  const filtered = activeCategory === 'all' ? ATTACK_SCENARIOS : ATTACK_SCENARIOS.filter(a => a.cat === activeCategory);
  let html = '';
  filtered.forEach(attack => {
    html += '<div class="attack-card" onclick="window._launchAttack(' + attack.id + ')" style="border-left:3px solid ' + attack.color + '">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
      '<span style="font-size:18px">' + attack.icon + '</span>' +
      '<div><h4 style="margin:0;color:' + attack.color + ';font-size:13px">' + attack.name + '</h4>' +
      '<span style="font-size:10px;color:var(--text3);font-family:monospace">' + attack.mitre + '</span></div>' +
      '</div>' +
      '<p style="font-size:11px;color:var(--text3);margin-bottom:8px;line-height:1.5">' + attack.description + '</p>' +
      '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px">' +
      '<span class="badge ' + attackSeverityClass(attack.sev) + '">' + attack.sev + '/10</span>' +
      '<span class="badge badge-info">' + attack.source.toUpperCase() + '</span>' +
      '<span style="color:var(--text3)">Any IoT device</span>' +
      '</div></div>';
  });
  // Custom alert card
  html += '<div class="attack-card" onclick="window._showCustomModal()" style="border-left:3px solid var(--accent2)">' +
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-size:18px">\u2699\uFE0F</span><h4 style="margin:0;font-size:13px">Custom Alert</h4></div>' +
    '<p style="font-size:11px;color:var(--text3);margin-bottom:8px;line-height:1.5">Create a custom Falco/Suricata payload and inject into the real IDS analysis pipeline.</p>' +
    '<div style="font-size:11px"><span class="badge badge-purple">Custom</span></div></div>';
  const gridEl = $('attackGrid');
  if (gridEl) gridEl.innerHTML = html;

  // ── MITRE ATT&CK table ─────────────────────────────────────────────
  const mitreMap = {};
  ATTACK_SCENARIOS.forEach(a => {
    if (!mitreMap[a.mitre]) mitreMap[a.mitre] = { id: a.mitre, name: a.mitreName, tactic: a.cat, scenarios: [] };
    mitreMap[a.mitre].scenarios.push(a.name);
  });
  let mitreHtml = '';
  Object.values(mitreMap).forEach(m => {
    mitreHtml += '<tr><td style="font-family:monospace;color:var(--accent)">' + m.id + '</td>' +
      '<td>' + m.name + '</td>' +
      '<td><span class="badge badge-info">' + m.tactic + '</span></td>' +
      '<td style="font-size:11px">' + m.scenarios.join(', ') + '</td></tr>';
  });
  const mitreEl = $('mitreTable');
  if (mitreEl) mitreEl.innerHTML = mitreHtml;
}

// ══════════════════════════════════════════════════════════════════════════
// Attack Execution Engine
// ══════════════════════════════════════════════════════════════════════════

/**
 * Launch a predefined attack scenario.
 */
export function launchAttack(attackId, refreshFn) {
  const state = store.getState();
  if (state.currentAttack) return;
  const attack = ATTACK_SCENARIOS.find(a => a.id === attackId);
  if (!attack) return;

  store.setState({
    currentAttack: attack,
    attackTimerMs: 0,
    attackRunCount: state.attackRunCount + 1,
  });
  const runCountEl = $('atkRunCount');
  if (runCountEl) runCountEl.textContent = state.attackRunCount + 1;
  const atkStatusEl = $('attackStatus');
  if (atkStatusEl) {
    atkStatusEl.textContent = 'Attacking: ' + attack.name;
    atkStatusEl.className = 'pill pill-err';
  }
  const progressFill = $('attackProgressFill');
  if (progressFill) {
    progressFill.style.background = 'var(--red)';
    progressFill.style.width = '0%';
  }
  const timerEl = $('attackTimer');
  if (timerEl) timerEl.textContent = '00:00';

  addLog('[' + new Date().toLocaleTimeString() + '] \u2501\u2501\u2501 ATTACK START: ' + attack.name + ' (' + attack.mitre + ' | ' + attack.source.toUpperCase() + ' | Sev ' + attack.sev + '/10) \u2501\u2501\u2501');
  addLog('[' + new Date().toLocaleTimeString() + '] Target: ' + attack.pod + ' | Threat: ' + attack.threat);
  addLog('[' + new Date().toLocaleTimeString() + '] ' + attack.description);

  triggerRealAttack(attack, refreshFn);

  const attackInterval = setInterval(() => {
    const s = store.getState();
    const newMs = s.attackTimerMs + 100;
    store.setState({ attackTimerMs: newMs });
    const progress = Math.min(100, (newMs / attack.duration) * 100);
    const pf = $('attackProgressFill');
    if (pf) pf.style.width = progress + '%';
    const tm = $('attackTimer');
    if (tm) tm.textContent = new Date(newMs).toISOString().substr(14, 5);
    if (Math.random() < 0.3) createAttackParticle(attack);
    if (newMs >= attack.duration) {
      clearInterval(attackInterval);
      attackComplete();
    }
  }, 100);
}

function triggerRealAttack(attack, refreshFn) {
  const ts = new Date().toISOString();
  const traceId = 'attack-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
  // Randomize target pod across all IoT services
  const targetPod = ALL_PODS[Math.floor(Math.random() * ALL_PODS.length)];
  const payload = {
    output: attack.source.toUpperCase() + ' Attack: ' + attack.name + ' on ' + targetPod + ' [' + attack.mitre + ']',
    priority: severityToPriority(attack.sev),
    rule: attack.name,
    time: ts,
    output_fields: {
      'container.name': targetPod,
      'alert.signature': attack.name,
      'threat.type': attack.threat,
      'mitre.technique': attack.mitre,
      'mitre.name': attack.mitreName,
      'attack.category': attack.cat,
      'trace.id': traceId,
    },
  };

  api.injectAlert(payload)
    .then(data => {
      addLog('[' + new Date().toLocaleTimeString() + '] \u2705 Attack injected \u2192 Trace: ' + (data.trace_id || traceId) + ' \u2192 Severity ' + (data.severity || '-'));
      if (data.actions_taken && data.actions_taken.length) {
        addLog('[' + new Date().toLocaleTimeString() + '] \u26A1 Automated Actions: ' + data.actions_taken.join(', '));
      }
      if (typeof refreshFn === 'function') setTimeout(refreshFn, 1500);
    })
    .catch(e => {
      addLog('[' + new Date().toLocaleTimeString() + '] \u274C Attack API error: ' + e.message);
    });
}

function createAttackParticle(attack) {
  const vis = $('attackFlowVis');
  if (!vis) return;
  const particle = document.createElement('div');
  particle.style.cssText = 'position:absolute;left:0;top:' + (Math.random() * 180) + 'px;width:4px;height:4px;background:' + attack.color + ';border-radius:50%;opacity:.8;animation:attackFlow 2s linear forwards;font-size:10px';
  particle.textContent = attack.icon;
  vis.appendChild(particle);
  const state = store.getState();
  store.setState({ attackFlowEvents: state.attackFlowEvents + 1 });
  const flowCountEl = $('attackFlowCount');
  if (flowCountEl) flowCountEl.textContent = (state.attackFlowEvents + 1) + ' events';
  setTimeout(() => { particle.remove(); }, 2000);
}

function attackComplete() {
  const statusEl = $('attackStatus');
  if (statusEl) {
    statusEl.textContent = 'Complete';
    statusEl.className = 'pill pill-success';
  }
  const pf = $('attackProgressFill');
  if (pf) pf.style.background = 'var(--green)';
  const attack = store.getState().currentAttack;
  addLog('[' + new Date().toLocaleTimeString() + '] \u2705 Attack simulation complete — ' + attack.name + ' (' + attack.mitre + ')');
  setTimeout(() => {
    const s = $('attackStatus');
    if (s) { s.textContent = 'Idle'; s.className = 'pill pill-ok'; }
    const p = $('attackProgressFill');
    if (p) { p.style.width = '0%'; p.style.background = 'var(--red)'; }
    const t = $('attackTimer');
    if (t) t.textContent = '00:00';
    store.setState({ currentAttack: null });
  }, 3000);
}

// ══════════════════════════════════════════════════════════════════════════
// Custom Alert Injection Modal
// ══════════════════════════════════════════════════════════════════════════

export function showCustomModal() {
  const podOpts = ALL_PODS.map(p => '<option value="' + p + '">' + p + '</option>').join('');
  const mc = $('modalContent'); if (!mc) return;
  mc.innerHTML =
    '<h2 style="margin-bottom:4px">Custom Alert Injection</h2>' +
    '<p style="font-size:12px;color:var(--text3);margin-bottom:16px">Inject a custom security event into the IDS pipeline. It will flow through dedup, LLM analysis, governance, and K8s automation.</p>' +
    '<label style="font-size:12px;color:var(--text2)">Rule Name</label>' +
    '<input id="customRule" value="Custom Security Rule" style="width:100%;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);margin-bottom:12px">' +
    '<label style="font-size:12px;color:var(--text2)">Alert Description</label>' +
    '<textarea id="customOutput" style="width:100%;min-height:60px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:8px;margin-bottom:12px">Suspicious process execution detected in smart-city IoT container — unauthorized binary spawned with network access</textarea>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">' +
    '<div><label style="font-size:12px;color:var(--text2)">Source</label>' +
    '<select id="customSource" style="width:100%;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text)"><option value="falco">Falco</option><option value="suricata">Suricata</option></select></div>' +
    '<div><label style="font-size:12px;color:var(--text2)">Priority</label>' +
    '<select id="customPriority" style="width:100%;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text)"><option value="Critical">Critical</option><option value="Warning" selected>Warning</option><option value="Notice">Notice</option></select></div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">' +
    '<div><label style="font-size:12px;color:var(--text2)">Target Pod</label>' +
    '<select id="customContainer" style="width:100%;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text)">' + podOpts + '</select></div>' +
    '<div><label style="font-size:12px;color:var(--text2)">MITRE Technique</label>' +
    '<input id="customMitre" placeholder="e.g. T0836" style="width:100%;padding:8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text)"></div>' +
    '</div>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn btn-outline" onclick="window._closeModal()">Cancel</button><button class="btn btn-primary" onclick="window._sendCustom()">Inject Alert</button></div>';
  const modalOv = $('modalOverlay');
  if (modalOv) modalOv.classList.add('open');
}

export function sendCustom(refreshFn) {
  const ts = new Date().toISOString();
  const mitre = ($('customMitre') || {}).value || '';
  const payload = {
    output: ($('customOutput') || {}).value || '',
    priority: ($('customPriority') || {}).value || 'Warning',
    rule: ($('customRule') || {}).value || 'Custom',
    time: ts,
    output_fields: {
      'container.name': ($('customContainer') || {}).value || 'unknown',
      'proc.cmdline': 'custom-injection',
      'mitre.technique': mitre,
    },
  };
  closeModal();

  const state = store.getState();
  store.setState({ attackRunCount: state.attackRunCount + 1 });
  const rc = $('atkRunCount'); if (rc) rc.textContent = state.attackRunCount + 1;

  addLog('\u2501'.repeat(64));
  addLog('  CUSTOM ALERT INJECTION' + (mitre ? ' [' + mitre + ']' : ''));
  addLog('\u2501'.repeat(64));
  addLog('');
  addLog('  \u25ba STEP 1: Custom payload');
  addLog('  \u2502 Rule:      ' + payload.rule);
  addLog('  \u2502 Priority:  ' + payload.priority);
  addLog('  \u2502 Output:    ' + payload.output);
  addLog('  \u2502 Container: ' + (payload.output_fields['container.name'] || '-'));
  addLog('');
  addLog('  \u25ba STEP 2: Sending to IDS API \u2192 LLM analysis...');

  const sendTime = performance.now();
  api.injectAlert(payload)
    .then(d => {
      const elapsed = Math.round(performance.now() - sendTime);
      const a = d.analysis || {};
      const sev = d.severity || a.severity || '-';
      const eng = d.llm_engine || a.llm_engine || 'unknown';
      addLog('');
      addLog('  \u25ba STEP 3: LLM Analysis Complete (' + elapsed + 'ms)');
      addLog('  \u250c\u2500 LLM Response \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500');
      addLog('  \u2502 Engine:      ' + eng);
      addLog('  \u2502 Severity:    ' + sev + '/10  \u2502  Threat: ' + (d.threat_type || a.threat_type || '-'));
      addLog('  \u2502 Confidence:  ' + (typeof a.confidence === 'number' ? Math.round(a.confidence * 100) + '%' : (a.confidence || '-')));
      addLog('  \u2502 Summary:     ' + (d.summary || a.summary || '-'));
      if (a.reasoning) addLog('  \u2502 Reasoning:   ' + a.reasoning);
      if (a.business_impact) addLog('  \u2502 Impact:      ' + a.business_impact);
      if (a.recommendations && a.recommendations.length) {
        addLog('  \u2502 Recommendations:');
        a.recommendations.forEach((r, i) => { addLog('  \u2502   ' + (i + 1) + '. ' + r); });
      }
      addLog('  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500');
      addLog('');
      addLog('  \u25ba STEP 4: Actions: ' + ((d.actions_taken && d.actions_taken.length) ? d.actions_taken.join(', ') : 'none'));
      addLog('');
      addLog('  \u2705 Pipeline complete');
      addLog('');
    })
    .catch(e => { addLog('  \u274c ERROR: ' + e.message + '\n'); });

  if (typeof refreshFn === 'function') {
    setTimeout(refreshFn, 2000);
    setTimeout(refreshFn, 5000);
  }
}

function closeModal() {
  const m = $('modalOverlay');
  if (m) m.classList.remove('open');
}

export function clearAttackLog() {
  const el = $('attackLog');
  if (el) el.textContent = '';
}

function addLog(msg) {
  const el = $('attackLog');
  if (!el) return;
  const t = new Date().toLocaleTimeString();
  const isIndent = msg.startsWith('  ') || msg.startsWith('\u2501') || msg === '' || msg.startsWith('\n');
  const prefix = isIndent ? '           ' : '[' + t + '] ';
  el.textContent += prefix + msg + '\n';
  el.scrollTop = el.scrollHeight;
}

// ── Global bindings for inline onclick ───────────────────────────────────

window._launchAttack = (id) => launchAttack(id, window._refreshAll);
window._filterAttacks = (cat) => {
  store.setState({ activeCategory: cat });
  renderAttackTab();
};
window._showCustomModal = showCustomModal;
window._sendCustom = () => sendCustom(window._refreshAll);
window._closeModal = closeModal;
window._clearAttackLog = clearAttackLog;
