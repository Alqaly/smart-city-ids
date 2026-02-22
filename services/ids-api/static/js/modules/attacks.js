/**
 * attacks.js — Attack Simulation Engine Tab (v2)
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Comprehensive attack simulation with 67 scenarios + 5 multi-stage campaigns
 * across 8 MITRE ATT&CK categories — dynamically loaded from the backend
 * registry at GET /api/attacks/registry.
 *
 * Architecture:
 *   1. On first load, fetches the full registry from GET /api/attacks/registry
 *   2. Renders category filters, scenario cards, campaign cards, and MITRE table
 *   3. Attack injection sends payloads to POST /api/alerts/internal
 *   4. Campaign execution chains multiple scenarios with stage progression
 *   5. IoT fleet scaling controls integrated with GET/POST /api/iot/scale
 *
 * Categories: Network(15), Application(12), Auth(8), Data(8), Container(8),
 *             Lateral(6), IoT Protocol(10), Campaigns(5)
 */

import { store } from '../state.js';
import { api } from '../api.js';
import { $, esc, sevBadge, severityToPriority } from '../utils.js';

// ══════════════════════════════════════════════════════════════════════════
// Registry cache — loaded from backend on first tab switch
// ══════════════════════════════════════════════════════════════════════════

let _registry = null;
let _registryLoading = false;

const CATEGORY_ICONS = {
  network: '🌐', application: '💉', authentication: '🔑', data: '📤',
  container: '🐛', lateral: '🔀', iot_protocol: '📡', campaign: '⚔️',
};
const CATEGORY_COLORS = {
  network: '#3b82f6', application: '#ef4444', authentication: '#f59e0b',
  data: '#06b6d4', container: '#a855f7', lateral: '#ec4899',
  iot_protocol: '#10b981', campaign: '#dc2626',
};

const ALL_PODS = ['traffic-camera', 'parking-system', 'healthcare-api', 'env-sensor', 'street-lighting'];

/**
 * Fetch the full attack registry from the backend (67 scenarios + 5 campaigns).
 */
async function loadRegistry() {
  if (_registry) return _registry;
  if (_registryLoading) {
    // Wait for in-flight request
    await new Promise(r => { const iv = setInterval(() => { if (!_registryLoading) { clearInterval(iv); r(); } }, 50); });
    return _registry;
  }
  _registryLoading = true;
  try {
    const data = await api.getAttackRegistry();
    if (data && data.scenarios) {
      _registry = data;
      _registryLoading = false;
      return _registry;
    }
  } catch (e) {
    console.warn('[attacks] Registry fetch failed, using fallback:', e);
  }
  _registryLoading = false;
  _registry = _getFallbackRegistry();
  return _registry;
}

/** Minimal fallback if backend registry isn't available yet. */
function _getFallbackRegistry() {
  return {
    scenarios: {},
    campaigns: {},
    categories: {},
    total_scenarios: 0,
    total_campaigns: 0,
  };
}

// ══════════════════════════════════════════════════════════════════════════
// Tab Renderer
// ══════════════════════════════════════════════════════════════════════════

function attackSeverityClass(sev) {
  return sev >= 8 ? 'badge-crit' : sev >= 6 ? 'badge-high' : sev >= 4 ? 'badge-med' : 'badge-low';
}

function sourceColor(source) {
  return source === 'falco' ? '#f97316' : '#3b82f6';
}

/**
 * Render the attack simulation tab — stats, filters, scenario grid, campaigns, MITRE table, scaling.
 */
export async function renderAttackTab() {
  const registry = await loadRegistry();
  if (!registry) return;

  const state = store.getState();
  const scenarios = registry.scenarios || {};
  const campaigns = registry.campaigns || {};
  const categories = registry.categories || {};
  const scenarioList = Object.values(scenarios);
  const campaignList = Object.values(campaigns);

  const catKeys = Object.keys(categories);
  if (campaignList.length > 0 && !catKeys.includes('campaign')) catKeys.push('campaign');

  const mitreSet = new Set(scenarioList.map(s => s.mitre_id));
  const targetSet = new Set(scenarioList.map(s => s.target));

  // ── Stats ──────────────────────────────────────────────────────
  const atkScEl = $('atkScenarioCount');
  if (atkScEl) atkScEl.textContent = scenarioList.length + ' + ' + campaignList.length + ' campaigns';
  const atkMiEl = $('atkMitreCount');
  if (atkMiEl) atkMiEl.textContent = mitreSet.size;
  const atkTgEl = $('atkTargetCount');
  if (atkTgEl) atkTgEl.textContent = targetSet.size + '/5';
  const atkRnEl = $('atkRunCount');
  if (atkRnEl) atkRnEl.textContent = state.attackRunCount;
  const atkCatEl = $('atkCategoryCount');
  if (atkCatEl) atkCatEl.textContent = catKeys.length;

  // ── Category filter chips ──────────────────────────────────────
  const activeCategory = state.activeCategory || 'all';
  const totalItems = scenarioList.length + campaignList.length;
  let chips = '<button class="btn btn-sm ' + (activeCategory === 'all' ? 'btn-primary' : 'btn-outline') +
    '" onclick="window._filterAttacks(\'all\')">All (' + totalItems + ')</button>';

  catKeys.forEach(catKey => {
    const cat = categories[catKey] || { name: catKey };
    const icon = CATEGORY_ICONS[catKey] || '📌';
    const count = catKey === 'campaign'
      ? campaignList.length
      : scenarioList.filter(s => s.category === catKey).length;
    if (count === 0) return;
    chips += '<button class="btn btn-sm ' + (activeCategory === catKey ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterAttacks(\'' + catKey + '\')" style="' +
      (activeCategory === catKey ? 'background:' + (CATEGORY_COLORS[catKey] || 'var(--accent)') : '') +
      '">' + icon + ' ' + esc(cat.name || catKey) + ' (' + count + ')</button>';
  });
  const catFilterEl = $('attackCategoryFilter');
  if (catFilterEl) catFilterEl.innerHTML = chips;

  // ── Phase filter chips ─────────────────────────────────────────
  const phaseEl = $('attackPhaseFilter');
  if (phaseEl) {
    const activePhase = state.activePhase || 'all';
    phaseEl.innerHTML =
      '<button class="btn btn-sm ' + (activePhase === 'all' ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterPhase(\'all\')">All Phases</button>' +
      '<button class="btn btn-sm ' + (activePhase === '1' ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterPhase(\'1\')">Phase 1 · 20 Core</button>' +
      '<button class="btn btn-sm ' + (activePhase === '2' ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterPhase(\'2\')">Phase 2 · 45 Extended</button>' +
      '<button class="btn btn-sm ' + (activePhase === '3' ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._filterPhase(\'3\')">Phase 3 · All ' + scenarioList.length + '</button>';
  }

  // ── Filter scenarios ───────────────────────────────────────────
  let filtered = [];
  if (activeCategory === 'all') {
    filtered = scenarioList;
  } else if (activeCategory === 'campaign') {
    filtered = [];  // campaigns rendered separately
  } else {
    filtered = scenarioList.filter(s => s.category === activeCategory);
  }

  // Phase filtering
  const activePhase = state.activePhase || 'all';
  if (activePhase !== 'all') {
    const phaseIds = _getPhaseIds(activePhase);
    filtered = filtered.filter(s => phaseIds.includes(s.id));
  }

  // ── Scenario cards ─────────────────────────────────────────────
  let html = '';
  filtered.forEach(attack => {
    const color = CATEGORY_COLORS[attack.category] || '#888';
    const icon = CATEGORY_ICONS[attack.category] || '📌';
    html += '<div class="attack-card" onclick="window._launchAttack(\'' + attack.id + '\')" style="border-left:3px solid ' + color + '">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
      '<span style="font-size:16px">' + icon + '</span>' +
      '<div style="flex:1"><h4 style="margin:0;color:' + color + ';font-size:12px;font-weight:700">' + esc(attack.name) + '</h4>' +
      '<span style="font-size:10px;color:var(--text3);font-family:monospace">' + esc(attack.id) + ' · ' + esc(attack.mitre_id) + '</span></div>' +
      '</div>' +
      '<p style="font-size:10px;color:var(--text3);margin-bottom:8px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">' + esc(attack.description) + '</p>' +
      '<div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;font-size:10px">' +
      '<span class="badge ' + attackSeverityClass(attack.severity) + '">' + attack.severity + '/10</span>' +
      '<span class="badge" style="background:rgba(255,255,255,0.05);color:' + sourceColor(attack.source) + '">' + (attack.source || '').toUpperCase() + '</span>' +
      '<span style="color:var(--text3)">' + esc(attack.target) + '</span>' +
      '<span style="color:var(--text3);margin-left:auto;font-family:monospace;font-size:9px">' + esc(attack.tactic) + '</span>' +
      '</div></div>';
  });

  // ── Campaign cards (if campaign category selected or showing all) ──
  if (activeCategory === 'all' || activeCategory === 'campaign') {
    campaignList.forEach(c => {
      html += '<div class="attack-card" onclick="window._launchCampaign(\'' + c.id + '\')" style="border-left:3px solid #dc2626;background:rgba(220,38,38,0.05)">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
        '<span style="font-size:16px">⚔️</span>' +
        '<div style="flex:1"><h4 style="margin:0;color:#dc2626;font-size:12px;font-weight:700">' + esc(c.name) + '</h4>' +
        '<span style="font-size:10px;color:var(--text3);font-family:monospace">' + esc(c.id) + ' · ' + c.stage_count + ' stages · ~' + c.duration_minutes + ' min</span></div>' +
        '</div>' +
        '<p style="font-size:10px;color:var(--text3);margin-bottom:8px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">' + esc(c.description) + '</p>' +
        '<div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;font-size:10px">' +
        '<span class="badge badge-crit">' + c.severity + '/10</span>' +
        '<span class="badge" style="background:rgba(220,38,38,0.12);color:#dc2626">CAMPAIGN</span>' +
        '<span style="color:var(--text3);font-family:monospace;font-size:9px">' + esc(c.techniques.join(' → ')) + '</span>' +
        '</div>' +
        '<div style="margin-top:6px;font-size:10px;color:var(--text3)">' +
        c.stage_names.map((sn, i) => '<span style="margin-right:6px">' + (i + 1) + '. ' + esc(sn) + '</span>').join('') +
        '</div></div>';
    });
  }

  // Custom alert card — always last
  html += '<div class="attack-card" onclick="window._showCustomModal()" style="border-left:3px solid var(--accent2)">' +
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-size:16px">⚙️</span><h4 style="margin:0;font-size:12px;font-weight:700">Custom Alert</h4></div>' +
    '<p style="font-size:10px;color:var(--text3);margin-bottom:8px;line-height:1.5">Create a custom Falco/Suricata payload and inject into the real IDS analysis pipeline.</p>' +
    '<div style="font-size:10px"><span class="badge badge-purple">Custom</span></div></div>';

  const gridEl = $('attackGrid');
  if (gridEl) gridEl.innerHTML = html;

  // ── MITRE ATT&CK coverage table ───────────────────────────────
  const mitreMap = {};
  scenarioList.forEach(s => {
    if (!mitreMap[s.mitre_id]) mitreMap[s.mitre_id] = { id: s.mitre_id, name: s.mitre_name, tactic: s.tactic, scenarios: [], categories: new Set() };
    mitreMap[s.mitre_id].scenarios.push(s.id + ' ' + s.name);
    mitreMap[s.mitre_id].categories.add(s.category);
  });
  let mitreHtml = '';
  Object.values(mitreMap).sort((a, b) => a.id.localeCompare(b.id)).forEach(m => {
    const catBadges = [...m.categories].map(c =>
      '<span class="badge" style="background:' + (CATEGORY_COLORS[c] || '#888') + '20;color:' + (CATEGORY_COLORS[c] || '#888') + ';font-size:9px;margin-right:2px">' + (CATEGORY_ICONS[c] || '') + '</span>'
    ).join('');
    mitreHtml += '<tr><td style="font-family:monospace;color:var(--accent);font-size:11px">' + m.id + '</td>' +
      '<td style="font-size:11px">' + esc(m.name) + '</td>' +
      '<td>' + catBadges + '<span class="badge badge-info" style="font-size:9px">' + esc(m.tactic) + '</span></td>' +
      '<td style="font-size:10px;max-width:300px;overflow:hidden;text-overflow:ellipsis">' + m.scenarios.join(', ') + '</td></tr>';
  });
  const mitreEl = $('mitreTable');
  if (mitreEl) mitreEl.innerHTML = mitreHtml;

  // ── IoT Fleet Scale Panel ──────────────────────────────────────
  loadIoTScale();
}


// ══════════════════════════════════════════════════════════════════════════
// IoT Fleet Scaling (inside Attack Simulation tab)
// ══════════════════════════════════════════════════════════════════════════

async function loadIoTScale() {
  const scaleEl = $('iotScalePanel');
  if (!scaleEl) return;

  try {
    const data = await api.getIoTScale();
    if (!data || data.error) {
      scaleEl.innerHTML = '<div style="color:var(--text3);text-align:center;padding:8px">K8s cluster not available — IoT scaling disabled</div>';
      return;
    }
    const services = data.services || {};
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px">';
    Object.entries(services).forEach(([svc, info]) => {
      const ready = info.ready || 0;
      const desired = info.replicas || 0;
      const color = ready >= desired ? 'var(--green)' : ready > 0 ? 'var(--yellow)' : 'var(--red)';
      html += '<div style="background:var(--bg);border-radius:6px;padding:10px;border:1px solid var(--border)">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
        '<span style="font-size:11px;font-weight:600">' + esc(svc) + '</span>' +
        '<span style="font-size:11px;color:' + color + '">' + ready + '/' + desired + '</span>' +
        '</div>' +
        '<div style="display:flex;gap:4px">' +
        '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(1,\'' + svc + '\')" style="font-size:10px;padding:2px 6px">1</button>' +
        '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(3,\'' + svc + '\')" style="font-size:10px;padding:2px 6px">3</button>' +
        '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(5,\'' + svc + '\')" style="font-size:10px;padding:2px 6px">5</button>' +
        '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(10,\'' + svc + '\')" style="font-size:10px;padding:2px 6px">10</button>' +
        '</div></div>';
    });
    html += '</div>';
    html += '<div style="margin-top:8px;display:flex;gap:6px;align-items:center">' +
      '<span style="font-size:11px;color:var(--text3)">Scale all:</span>' +
      '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(1)" style="font-size:10px">1</button>' +
      '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(3)" style="font-size:10px">3</button>' +
      '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(5)" style="font-size:10px">5</button>' +
      '<button class="btn btn-sm btn-outline" onclick="window._scaleIoT(10)" style="font-size:10px">10</button>' +
      '<span style="margin-left:auto;font-size:11px;color:var(--text3)">Total: ' + (data.total_replicas || 0) + ' replicas, ' + (data.total_ready || 0) + ' ready</span>' +
      '</div>';
    scaleEl.innerHTML = html;
  } catch (e) {
    scaleEl.innerHTML = '<div style="color:var(--text3);text-align:center;padding:8px">Scale info unavailable</div>';
  }
}


// ══════════════════════════════════════════════════════════════════════════
// Attack Execution Engine
// ══════════════════════════════════════════════════════════════════════════

/**
 * Launch a predefined attack scenario by ID (e.g., 'N1').
 */
export function launchAttack(attackId, refreshFn) {
  const state = store.getState();
  if (state.currentAttack) return;

  const registry = _registry;
  if (!registry || !registry.scenarios) return;

  const attack = registry.scenarios[attackId];
  if (!attack) return;

  const color = CATEGORY_COLORS[attack.category] || '#888';
  const icon = CATEGORY_ICONS[attack.category] || '📌';
  const duration = 8000 + (attack.severity * 1000);

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
    progressFill.style.background = color;
    progressFill.style.width = '0%';
  }
  const timerEl = $('attackTimer');
  if (timerEl) timerEl.textContent = '00:00';

  addLog('');
  addLog('━'.repeat(64));
  addLog('  ' + icon + ' ATTACK: ' + attack.name + ' [' + attack.id + ']');
  addLog('━'.repeat(64));
  addLog('  MITRE: ' + attack.mitre_id + ' (' + attack.mitre_name + ')');
  addLog('  Target: ' + attack.target + '  |  Source: ' + (attack.source || '').toUpperCase() + '  |  Severity: ' + attack.severity + '/10');
  addLog('  Tactic: ' + attack.tactic + '  |  Kill Chain: ' + attack.kill_chain);
  addLog('  ' + attack.description);
  addLog('');
  addLog('  ► Sending alert to IDS pipeline...');

  triggerRealAttack(attack, refreshFn);

  const attackInterval = setInterval(() => {
    const s = store.getState();
    const newMs = s.attackTimerMs + 100;
    store.setState({ attackTimerMs: newMs });
    const progress = Math.min(100, (newMs / duration) * 100);
    const pf = $('attackProgressFill');
    if (pf) pf.style.width = progress + '%';
    const tm = $('attackTimer');
    if (tm) tm.textContent = new Date(newMs).toISOString().substr(14, 5);
    if (Math.random() < 0.25) createAttackParticle(color, icon);
    if (newMs >= duration) {
      clearInterval(attackInterval);
      attackComplete();
    }
  }, 100);
}

function triggerRealAttack(attack, refreshFn) {
  const ts = new Date().toISOString();
  const traceId = 'attack-' + attack.id + '-' + Date.now();
  const targetPod = attack.target;
  const payload = {
    output: (attack.source || 'falco').toUpperCase() + ' Attack: ' + attack.name + ' on ' + targetPod + ' [' + attack.mitre_id + ']',
    priority: severityToPriority(attack.severity),
    rule: attack.rule || attack.name,
    time: ts,
    output_fields: {
      'container.name': targetPod,
      'alert.signature': attack.name,
      'threat.type': attack.tactic,
      'mitre.technique': attack.mitre_id,
      'mitre.name': attack.mitre_name,
      'attack.id': attack.id,
      'attack.category': attack.category,
      'attack_phase': (attack.tactic || '').toLowerCase().replace(/ /g, '_'),
      'technique_id': attack.mitre_id,
      'kill_chain_stage': attack.kill_chain,
      'event_volume': attack.volume || 'low',
      'trace.id': traceId,
    },
  };

  const sendTime = performance.now();
  api.injectAlert(payload)
    .then(data => {
      const elapsed = Math.round(performance.now() - sendTime);
      const a = data.analysis || {};
      const sev = data.severity || a.severity || '-';
      const eng = data.llm_engine || a.llm_engine || 'unknown';

      addLog('');
      addLog('  ► IDS Response (' + elapsed + 'ms)');
      addLog('  ┌─ LLM Analysis ──────────────────────────────────────────');
      addLog('  │ Engine:      ' + eng);
      addLog('  │ Severity:    ' + sev + '/10  │  Threat: ' + (data.threat_type || a.threat_type || '-'));
      addLog('  │ Confidence:  ' + (typeof a.confidence === 'number' ? Math.round(a.confidence * 100) + '%' : (a.confidence || '-')));
      addLog('  │ Summary:     ' + (data.summary || a.summary || '-'));
      if (a.reasoning) addLog('  │ Reasoning:   ' + a.reasoning);
      if (a.business_impact) addLog('  │ Impact:      ' + a.business_impact);
      if (a.recommendations && a.recommendations.length) {
        addLog('  │ Recommendations:');
        a.recommendations.forEach((r, i) => { addLog('  │   ' + (i + 1) + '. ' + r); });
      }
      addLog('  └──────────────────────────────────────────────────────────');
      if (data.actions_taken && data.actions_taken.length) {
        addLog('  ⚡ Automated Actions: ' + data.actions_taken.join(', '));
      }
      addLog('');

      const sevEl = $('atkLastSev');
      if (sevEl) sevEl.textContent = sev;
      const actEl = $('atkLastAction');
      if (actEl && data.actions_taken && data.actions_taken.length) actEl.textContent = data.actions_taken[0];

      if (typeof refreshFn === 'function') setTimeout(refreshFn, 1500);
    })
    .catch(e => {
      addLog('  ✗ Attack API error: ' + e.message);
    });
}


/**
 * Launch a multi-stage campaign by campaign ID (e.g., 'M1').
 */
export async function launchCampaign(campaignId, refreshFn) {
  const state = store.getState();
  if (state.currentAttack) return;

  const registry = _registry;
  if (!registry || !registry.campaigns) return;

  const campaign = registry.campaigns[campaignId];
  if (!campaign) return;

  store.setState({
    currentAttack: { ...campaign, isCampaign: true },
    attackTimerMs: 0,
    attackRunCount: state.attackRunCount + 1,
  });

  const runCountEl = $('atkRunCount');
  if (runCountEl) runCountEl.textContent = state.attackRunCount + 1;
  const atkStatusEl = $('attackStatus');
  if (atkStatusEl) {
    atkStatusEl.textContent = 'Campaign: ' + campaign.name;
    atkStatusEl.className = 'pill pill-err';
  }

  addLog('');
  addLog('╔' + '═'.repeat(62) + '╗');
  addLog('║  ⚔️  CAMPAIGN: ' + campaign.name.padEnd(45) + '║');
  addLog('╚' + '═'.repeat(62) + '╝');
  addLog('  ' + campaign.description);
  addLog('  Stages: ' + campaign.stage_count + '  |  Duration: ~' + campaign.duration_minutes + ' min');
  addLog('  Kill Chain: ' + campaign.techniques.join(' → '));
  addLog('');

  // Execute stages sequentially
  for (let i = 0; i < campaign.stages.length; i++) {
    const stageId = campaign.stages[i];
    const stageName = campaign.stage_names[i];
    const scenario = registry.scenarios[stageId];

    addLog('  ▶ Stage ' + (i + 1) + '/' + campaign.stages.length + ': ' + stageName);

    if (!scenario) {
      addLog('    ⚠ Scenario ' + stageId + ' not found, skipping');
      continue;
    }

    const ts = new Date().toISOString();
    const payload = {
      output: scenario.source.toUpperCase() + ' Campaign ' + campaign.name + ' Stage ' + (i + 1) + ': ' +
        scenario.name + ' on ' + scenario.target + ' [' + scenario.mitre_id + ']',
      priority: severityToPriority(scenario.severity),
      rule: scenario.rule || scenario.name,
      time: ts,
      output_fields: {
        'container.name': scenario.target,
        'mitre.technique': scenario.mitre_id,
        'mitre.name': scenario.mitre_name,
        'attack.id': stageId,
        'attack.category': scenario.category,
        'campaign.id': campaignId,
        'campaign.name': campaign.name,
        'campaign.stage': i + 1,
        'campaign.total_stages': campaign.stages.length,
        'attack_phase': (scenario.tactic || '').toLowerCase().replace(/ /g, '_'),
        'technique_id': scenario.mitre_id,
        'kill_chain_stage': scenario.kill_chain,
        'event_volume': scenario.volume || 'low',
      },
    };

    try {
      const sendTime = performance.now();
      const data = await api.injectAlert(payload);
      const elapsed = Math.round(performance.now() - sendTime);
      const a = data.analysis || {};
      addLog('    ✓ Stage ' + (i + 1) + ' complete (' + elapsed + 'ms) — Severity: ' + (a.severity || data.severity || '?') + '/10, Engine: ' + (data.llm_engine || 'local'));
      if (data.actions_taken && data.actions_taken.length) {
        addLog('    ⚡ Actions: ' + data.actions_taken.join(', '));
      }
    } catch (e) {
      addLog('    ✗ Stage ' + (i + 1) + ' error: ' + e.message);
    }

    // Inter-stage delay
    if (i < campaign.stages.length - 1) {
      const stageDelay = Math.min(3000, (campaign.duration_minutes * 60000) / campaign.stages.length);
      addLog('    ⏳ Next stage in ' + (stageDelay / 1000).toFixed(0) + 's...');
      await new Promise(r => setTimeout(r, stageDelay));
    }

    // Update progress
    const progress = ((i + 1) / campaign.stages.length) * 100;
    const pf = $('attackProgressFill');
    if (pf) {
      pf.style.width = progress + '%';
      pf.style.background = '#dc2626';
    }
  }

  addLog('');
  addLog('  ✅ Campaign "' + campaign.name + '" complete (' + campaign.stages.length + ' stages executed)');
  addLog('');

  attackComplete();
  if (typeof refreshFn === 'function') {
    setTimeout(refreshFn, 2000);
    setTimeout(refreshFn, 5000);
  }
}


function createAttackParticle(color, icon) {
  const vis = $('attackFlowVis');
  if (!vis) return;
  const particle = document.createElement('div');
  particle.style.cssText = 'position:absolute;left:0;top:' + (Math.random() * 180) + 'px;width:4px;height:4px;background:' + color + ';border-radius:50%;opacity:.8;animation:attackFlow 2s linear forwards;font-size:10px';
  particle.textContent = icon;
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
  if (attack) {
    addLog('  ✅ ' + (attack.isCampaign ? 'Campaign' : 'Attack') + ' simulation complete — ' + attack.name);
  }
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
// Phase ID lists (mirrors attack_runner.py)
// ══════════════════════════════════════════════════════════════════════════

function _getPhaseIds(phase) {
  const p1 = ['N1','N2','N6','N13','A1','A3','A4','A7','A12','S1','S3','S4','C1','C2','C3','C5','I1','I5','I9','I8'];
  const p2extra = ['N4','N7','N10','A2','A5','A6','A9','A11','D1','D3','D4','D5','L1','L3','L5','L6','I2','I3','I4','I7','I10','S6','S7','S8','C4'];
  if (phase === '1') return p1;
  if (phase === '2') return [...p1, ...p2extra];
  return Object.keys(_registry ? _registry.scenarios : {});
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

  addLog('');
  addLog('━'.repeat(64));
  addLog('  CUSTOM ALERT INJECTION' + (mitre ? ' [' + mitre + ']' : ''));
  addLog('━'.repeat(64));
  addLog('');
  addLog('  ► STEP 1: Custom payload');
  addLog('  │ Rule:      ' + payload.rule);
  addLog('  │ Priority:  ' + payload.priority);
  addLog('  │ Output:    ' + payload.output);
  addLog('  │ Container: ' + (payload.output_fields['container.name'] || '-'));
  addLog('');
  addLog('  ► STEP 2: Sending to IDS API → LLM analysis...');

  const sendTime = performance.now();
  api.injectAlert(payload)
    .then(d => {
      const elapsed = Math.round(performance.now() - sendTime);
      const a = d.analysis || {};
      const sev = d.severity || a.severity || '-';
      const eng = d.llm_engine || a.llm_engine || 'unknown';
      addLog('');
      addLog('  ► STEP 3: LLM Analysis Complete (' + elapsed + 'ms)');
      addLog('  ┌─ LLM Response ──────────────────────────────────────────');
      addLog('  │ Engine:      ' + eng);
      addLog('  │ Severity:    ' + sev + '/10  │  Threat: ' + (d.threat_type || a.threat_type || '-'));
      addLog('  │ Confidence:  ' + (typeof a.confidence === 'number' ? Math.round(a.confidence * 100) + '%' : (a.confidence || '-')));
      addLog('  │ Summary:     ' + (d.summary || a.summary || '-'));
      if (a.reasoning) addLog('  │ Reasoning:   ' + a.reasoning);
      if (a.business_impact) addLog('  │ Impact:      ' + a.business_impact);
      if (a.recommendations && a.recommendations.length) {
        addLog('  │ Recommendations:');
        a.recommendations.forEach((r, i) => { addLog('  │   ' + (i + 1) + '. ' + r); });
      }
      addLog('  └──────────────────────────────────────────────────────────');
      addLog('');
      addLog('  ► STEP 4: Actions: ' + ((d.actions_taken && d.actions_taken.length) ? d.actions_taken.join(', ') : 'none'));
      addLog('');
      addLog('  ✅ Pipeline complete');
      addLog('');

      const sevEl = $('atkLastSev');
      if (sevEl) sevEl.textContent = sev;
    })
    .catch(e => { addLog('  ✗ ERROR: ' + e.message + '\n'); });

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
  const isIndent = msg.startsWith('  ') || msg.startsWith('━') || msg.startsWith('╔') || msg.startsWith('╚') || msg === '' || msg.startsWith('\n');
  const prefix = isIndent ? '           ' : '[' + t + '] ';
  el.textContent += prefix + msg + '\n';
  el.scrollTop = el.scrollHeight;
}

// ── Global bindings for inline onclick ───────────────────────────────────

window._launchAttack = (id) => launchAttack(id, window._refreshAll);
window._launchCampaign = (id) => launchCampaign(id, window._refreshAll);
window._filterAttacks = (cat) => {
  store.setState({ activeCategory: cat });
  renderAttackTab();
};
window._filterPhase = (phase) => {
  store.setState({ activePhase: phase });
  renderAttackTab();
};
window._showCustomModal = showCustomModal;
window._sendCustom = () => sendCustom(window._refreshAll);
window._closeModal = closeModal;
window._clearAttackLog = clearAttackLog;
window._scaleIoT = (replicas, service) => {
  api.setIoTScale(replicas, service).then(() => {
    addLog('[' + new Date().toLocaleTimeString() + '] Scaled ' + (service || 'all services') + ' to ' + replicas + ' replicas');
    loadIoTScale();
  });
};
