/**
 * governance.js — Governance / HITL Interface Tab
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Human-in-the-loop (HITL) governance for security automation.  Provides:
 *   • Mode controls (Manual / Assisted / Autopilot)
 *   • Pending actions queue (approve / reject workflow)
 *   • Action history audit trail
 *
 * Purpose: keep analyst accountability explicit for stakeholder demos.
 */

import { api } from '../api.js';
import { esc, shortTime, sevBadge } from '../utils.js';

/**
 * Render the governance tab: mode selector, pending queue, history.
 * @param {Object} gov       — /api/governance/status
 * @param {Object} dashboard — /api/operator/dashboard (unused but available)
 * @param {Function} refreshFn — callback to trigger a full refresh after actions
 */
export function renderGovernanceTab(gov, dashboard, refreshFn) {
  if (!gov) return;
  const gm = gov.metrics || {};

  // ── Summary stat cards ─────────────────────────────────────────────
  document.getElementById('govStats').innerHTML =
    '<div class="stat-card purple"><div class="stat-label">Mode</div><div class="stat-value" style="font-size:20px">' +
    (gov.mode === 'assisted' ? 'Assisted' : gov.mode === 'autopilot' ? 'Autopilot' : 'Manual') +
    '</div><div class="stat-sub">Threshold: severity &gt;= ' + (gov.assisted_threshold || 8) + ' requires approval</div></div>' +
    '<div class="stat-card yellow"><div class="stat-label">Pending</div><div class="stat-value">' + (gov.pending_count || 0) + '</div><div class="stat-sub">Actions awaiting decision</div></div>' +
    '<div class="stat-card green"><div class="stat-label">Approved</div><div class="stat-value">' + (gm.approved || 0) + '</div><div class="stat-sub">of ' + (gm.total_actions_requested || 0) + ' total</div></div>' +
    '<div class="stat-card red"><div class="stat-label">Rejected</div><div class="stat-value">' + (gm.rejected || 0) + '</div><div class="stat-sub">Actions blocked by analyst</div></div>';

  // Update navbar badge
  document.getElementById('pendingBadge').textContent = gov.pending_count || 0;

  // ── Mode control ───────────────────────────────────────────────────
  const modes = ['manual', 'assisted', 'autopilot'];
  const labels = ['Manual', 'Assisted', 'Autopilot'];
  let mHtml = '<div style="display:flex;gap:8px;margin-bottom:12px">';
  modes.forEach((m, idx) => {
    mHtml += '<button class="btn ' + (gov.mode === m ? 'btn-primary' : 'btn-outline') +
      '" onclick="window._setGovMode(\'' + m + '\')">' + labels[idx] + '</button>';
  });
  mHtml += '</div><div style="font-size:12px;color:var(--text3)">' +
    '<strong>Manual:</strong> All actions require analyst approval<br>' +
    '<strong>Assisted:</strong> Low-severity auto-executes; critical requires approval<br>' +
    '<strong>Autopilot:</strong> All actions auto-execute (demo mode)</div>';
  document.getElementById('govModeControl').innerHTML = mHtml;

  loadPending(refreshFn);
  loadHistory();
}

/**
 * Set governance mode and refresh.
 */
export function setGovMode(mode, refreshFn) {
  api.setGovernanceMode(mode).then(() => {
    if (typeof refreshFn === 'function') refreshFn();
  });
}

// Expose to global scope for inline onclick handlers produced by innerHTML
window._setGovMode = (mode) => {
  // refreshFn will be wired up by app.js
  api.setGovernanceMode(mode).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};

/**
 * Load and render pending actions queue.
 */
function loadPending(refreshFn) {
  api.getGovernancePending().then(data => {
    const el = document.getElementById('pendingActions');
    if (!data || !data.pending || !data.pending.length) {
      el.innerHTML = '<div style="padding:20px;color:var(--text3);text-align:center">No actions pending approval</div>';
      return;
    }
    let html = '<table><thead><tr><th>Action</th><th>Target</th><th>Severity</th><th>Reason</th><th>Actions</th></tr></thead><tbody>';
    data.pending.forEach(a => {
      html += '<tr><td>' + (a.action_type || a.action || '-') + '</td>' +
        '<td>' + (a.target || '-') + '</td>' +
        '<td><span class="badge ' + sevBadge(a.severity) + '">' + (a.severity || '-') + '</span></td>' +
        '<td style="max-width:200px">' + esc(((a.rationale || a.reason || '')).substring(0, 100)) + '</td>' +
        '<td><button class="btn btn-success btn-sm" onclick="window._approveAction(\'' + a.id + '\')">Approve</button> ' +
        '<button class="btn btn-danger btn-sm" onclick="window._rejectAction(\'' + a.id + '\')">Reject</button></td></tr>';
    });
    el.innerHTML = html + '</tbody></table>';
  });
}

/**
 * Load and render governance action history.
 */
function loadHistory() {
  api.getGovernanceHistory().then(data => {
    const el = document.getElementById('govHistory');
    if (!data || !data.history || !data.history.length) {
      el.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text3)">No action history</td></tr>';
      return;
    }
    let html = '';
    data.history.forEach(h => {
      html += '<tr><td>' + shortTime(h.timestamp) + '</td>' +
        '<td>' + (h.action_type || h.action || '-') + '</td>' +
        '<td>' + (h.target || '-') + '</td>' +
        '<td><span class="badge ' + (h.status === 'approved' || h.status === 'executed' ? 'badge-low' : h.status === 'rejected' ? 'badge-crit' : 'badge-med') + '">' + (h.status || '-') + '</span></td>' +
        '<td>' + (h.operator || '-') + '</td></tr>';
    });
    el.innerHTML = html;
  });
}

// ── Global action handlers (for inline onclick) ─────────────────────────

window._approveAction = (id) => {
  api.approveAction(id).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};

window._rejectAction = (id) => {
  api.rejectAction(id).then(() => {
    if (window._refreshAll) window._refreshAll();
  });
};
