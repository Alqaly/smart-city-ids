/**
 * threats.js — Threats / Metrics / Hunt utility tabs
 */

import { api } from '../api.js';
import { esc, shortTime } from '../utils.js';

export function renderThreatsTab(alertBundle) {
  const alerts = (alertBundle && alertBundle.alerts) ? alertBundle.alerts : [];
  const mitreEl = document.getElementById('threatMitreHeatmap');
  const svcEl = document.getElementById('threatServiceMatrix');
  const tlEl = document.getElementById('threatTimeline');
  if (!mitreEl || !svcEl || !tlEl) return;

  if (!alerts.length) {
    mitreEl.innerHTML = '<div style="color:var(--text3)">No threat data yet.</div>';
    svcEl.innerHTML = '<div style="color:var(--text3)">No service mapping yet.</div>';
    tlEl.innerHTML = '<div style="color:var(--text3)">No timeline yet.</div>';
    return;
  }

  const mitreCounts = {};
  const svcCounts = {};
  alerts.forEach(a => {
    const an = a.analysis || {};
    const m = an.mitre_technique || a.output_fields?.technique_id || 'unknown';
    mitreCounts[m] = (mitreCounts[m] || 0) + 1;
    const svc = (a.raw_alert && a.raw_alert.output_fields && a.raw_alert.output_fields['container.name']) ||
      (a.output_fields && a.output_fields['container.name']) ||
      a.source || 'unknown';
    svcCounts[svc] = (svcCounts[svc] || 0) + 1;
  });

  const maxMitre = Math.max(...Object.values(mitreCounts), 1);
  mitreEl.innerHTML = Object.entries(mitreCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k, v]) => {
      const pct = Math.round((v / maxMitre) * 100);
      return '<div style="margin-bottom:8px">' +
        '<div style="display:flex;justify-content:space-between;font-size:12px"><span>' + esc(k) + '</span><strong>' + v + '</strong></div>' +
        '<div class="progress"><div class="progress-fill" style="width:' + pct + '%;background:var(--red)"></div></div>' +
      '</div>';
    }).join('');

  const maxSvc = Math.max(...Object.values(svcCounts), 1);
  svcEl.innerHTML = Object.entries(svcCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k, v]) => {
      const pct = Math.round((v / maxSvc) * 100);
      return '<div style="margin-bottom:8px">' +
        '<div style="display:flex;justify-content:space-between;font-size:12px"><span>' + esc(k) + '</span><strong>' + v + '</strong></div>' +
        '<div class="progress"><div class="progress-fill" style="width:' + pct + '%;background:var(--accent)"></div></div>' +
      '</div>';
    }).join('');

  tlEl.innerHTML = '<div class="feed">' + alerts.slice(0, 20).map(a =>
    '<div class="feed-item"><span class="feed-time">' + shortTime(a.timestamp) + '</span><span class="feed-msg"><strong>' + esc(a.rule || '-') + '</strong> — ' + esc(a.threat_type || (a.analysis && a.analysis.threat_type) || '-') + '</span></div>'
  ).join('') + '</div>';
}

export function renderMetricsTab(metrics, pipeline, llmDiag) {
  const mttrEl = document.getElementById('metricsMttr');
  const latEl = document.getElementById('metricsLatency');
  const tplEl = document.getElementById('metricsTemplates');
  if (!mttrEl || !latEl || !tplEl) return;

  const total = (metrics && metrics.total_alerts) || 0;
  const crit = (metrics && metrics.critical_alerts) || 0;
  const mttrProxy = total > 0 ? Math.max(1, Math.round((crit / total) * 120)) : 0;
  mttrEl.innerHTML =
    '<div style="font-size:36px;font-weight:700;color:var(--accent)">' + mttrProxy + 's</div>' +
    '<div style="font-size:12px;color:var(--text3)">Proxy MTTR from critical-alert ratio</div>';

  const llmStage = (pipeline && pipeline.stages || []).find(s => s.id === 'llm');
  const p95 = llmStage ? llmStage.p95_latency_ms : 0;
  latEl.innerHTML =
    '<div style="font-size:36px;font-weight:700;color:var(--orange)">' + p95 + 'ms</div>' +
    '<div style="font-size:12px;color:var(--text3)">LLM pipeline p95 latency</div>';

  tplEl.innerHTML =
    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px">' +
    '<div class="provider-card"><div class="provider-icon">DB</div><div class="provider-info"><div class="provider-name">postgres-dashboard-otlp-v1.json</div><div class="provider-detail">DB health + query latency</div></div></div>' +
    '<div class="provider-card"><div class="provider-icon">K8S</div><div class="provider-info"><div class="provider-name">k8s-status-v1.json</div><div class="provider-detail">Pods/services/readiness</div></div></div>' +
    '<div class="provider-card"><div class="provider-icon">IDS</div><div class="provider-info"><div class="provider-name">ids-metrics-v1.json</div><div class="provider-detail">Alerts, LLM, governance</div></div></div>' +
    '</div>';
}

export function initHunt() {
  const out = document.getElementById('huntOutput');
  if (!out) return;
  out.innerHTML = 'Ready. Use presets to pivot the incident grid and threat tab.';
}

window._huntPreset = (preset) => {
  const out = document.getElementById('huntOutput');
  if (!out) return;
  if (preset === 'healthcare') {
    const search = document.getElementById('incidentSearch');
    if (search) {
      search.value = 'healthcare';
      search.dispatchEvent(new Event('input'));
    }
    out.innerHTML = 'Applied hunt preset: healthcare incidents.';
  } else if (preset === 'mitre') {
    const tabBtn = document.querySelector('.tab-btn[data-tab="threats"]');
    if (tabBtn) tabBtn.click();
    out.innerHTML = 'Switched to Threats tab for MITRE coverage.';
  } else {
    out.innerHTML = 'Preset not recognized.';
  }
};
