/**
 * kubernetes.js — Kubernetes Cluster Tab
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Renders the K8s cluster view: component status cards (K8s, DB, Falco,
 * Suricata) plus pod and service roster tables.
 *
 * Note on static pod/service data:
 *   The pod and service tables are intentionally static (matching the
 *   deployed k8s-manifests).  A future enhancement could query the K8s
 *   API directly, but for this reference deployment the hardcoded roster is correct and
 *   avoids an extra API endpoint and RBAC grants.
 */

import { api } from '../api.js';
import { $ } from '../utils.js';

/**
 * Load cluster health then render all K8s sub-panels.
 */
export function loadK8s() {
  api.getHealth().then(h => {
    const c = (h && h.components) ? h.components : {};
    const k8sStatsEl = $('k8sStats');
    if (k8sStatsEl) k8sStatsEl.innerHTML =
      '<div class="stat-card green"><div class="stat-label">Kubernetes</div><div class="stat-value">' +
      (c.kubernetes === 'connected' ? 'Connected' : 'Offline') +
      '</div><div class="stat-sub">Cluster API</div></div>' +
      '<div class="stat-card blue"><div class="stat-label">Database</div><div class="stat-value">' +
      (c.database === 'memory-fallback' ? 'In-Memory' : (c.database || '--')) +
      '</div><div class="stat-sub">' +
      (c.database === 'memory-fallback' ? 'PostgreSQL offline — volatile storage' : 'PostgreSQL persistent storage') +
      '</div></div>' +
      '<div class="stat-card purple"><div class="stat-label">Falco</div><div class="stat-value">' +
      (c.falco || '--') + '</div><div class="stat-sub">Runtime detection</div></div>' +
      '<div class="stat-card orange"><div class="stat-label">Suricata</div><div class="stat-value">' +
      (c.suricata || '--') + '</div><div class="stat-sub">Network detection</div></div>';
    renderK8sTables();
  });
}

/**
 * Render the pod roster and service endpoint tables.
 * Static data — matches deployed k8s-manifests.
 */
function renderK8sTables() {
  const pods = [
    ['ids-api (x2)',           'Running', '0', 'smart-city'],
    ['postgres',               'Running', '0', 'smart-city'],
    ['traffic-camera (x2)',    'Running', '0', 'smart-city'],
    ['healthcare-api (x2)',    'Running', '0', 'smart-city'],
    ['parking-system (x2)',    'Running', '0', 'smart-city'],
    ['mqtt-broker',            'Running', '0', 'smart-city'],
    ['iot-devices-enhanced (x10)', 'Running', '0', 'smart-city'],
    ['iot-simulator-high (x4)',    'Running', '0', 'smart-city'],
    ['iot-simulator-medium (x5)',  'Running', '0', 'smart-city'],
    ['iot-simulator-burst',        'Running', '0', 'smart-city'],
    ['falco',                  'Running', '0', 'falco-system'],
    ['falco-forwarder',        'Running', '0', 'falco-system'],
    ['falco-metacollector',    'Running', '0', 'falco-system'],
    ['prometheus',             'Running', '0', 'monitoring'],
    ['grafana',                'Running', '0', 'monitoring'],
    ['suricata',               'Running', '0', 'monitoring'],
    ['suricata-forwarder',     'Running', '0', 'monitoring'],
  ];
  let ph = '';
  pods.forEach(p => {
    ph += '<tr><td>' + p[0] + '</td><td><span class="dot dot-green"></span>' +
      p[1] + '</td><td>' + p[2] + '</td><td>' + p[3] + '</td></tr>';
  });
  const podsEl = $('podsTable');
  if (podsEl) podsEl.innerHTML = ph;

  // Explanation blurb
  const explEl = $('k8sExplain');
  if (explEl) {
    explEl.innerHTML =
      '<strong>Pods</strong> are running container instances (the actual processes). ' +
      '<strong>Services</strong> are stable network endpoints that route traffic to ' +
      'pods — pods restart/move, but the service name and port stay the same.';
  }

  const svcs = [
    ['ids-api-service',      'NodePort',   '8000:30800', 'smart-city'],
    ['postgres',             'ClusterIP',  '5432',       'smart-city'],
    ['traffic-camera-service', 'ClusterIP', '80',        'smart-city'],
    ['healthcare-api-service', 'ClusterIP', '80',        'smart-city'],
    ['parking-system-service', 'ClusterIP', '80',        'smart-city'],
    ['mqtt-broker',          'ClusterIP',  '1883',       'smart-city'],
    ['falco-forwarder',      'ClusterIP',  '8080',       'falco-system'],
    ['prometheus',           'NodePort',   '9090:31106', 'monitoring'],
    ['grafana',              'NodePort',   '3000:30300', 'monitoring'],
    ['suricata',             'ClusterIP',  '514/UDP',    'monitoring'],
    ['suricata-forwarder',   'ClusterIP',  '514/UDP, 8100', 'monitoring'],
  ];
  let sh = '';
  svcs.forEach(s => {
    sh += '<tr><td>' + s[0] + '</td><td><span class="badge badge-info">' + s[1] +
      '</span></td><td>' + s[2] + '</td><td>' + s[3] + '</td></tr>';
  });
  const svcsEl = $('servicesTable');
  if (svcsEl) svcsEl.innerHTML = sh;
}
