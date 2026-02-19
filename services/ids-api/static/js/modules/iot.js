/**
 * iot.js — IoT Devices Tab + WebSocket MQTT Bridge Stream
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Two responsibilities:
 *   1. IoT Devices tab: fleet stats, protocol emulator cards (ONVIF,
 *      MQTT/CoAP, FHIR R4, Modbus/OPC-UA, DALI-2/TALQ), and fleet table.
 *   2. IoT WebSocket stream: connects to iot-stream-bridge (NodePort 30810)
 *      for real-time MQTT traffic visualisation.
 *
 * Each protocol emulator's telemetry card includes device-specific detail
 * (e.g. ANPR plates for traffic cameras, AQI per station for env sensors).
 */

import { store } from '../state.js';
import { api } from '../api.js';
import { esc } from '../utils.js';


// ══════════════════════════════════════════════════════════════════════════
// IoT Devices Tab
// ══════════════════════════════════════════════════════════════════════════

/**
 * Fetch metrics, device list and telemetry, then render all IoT sub-panels.
 */
export function loadIoT() {
  Promise.all([
    api.getMetrics(),
    api.getIoTDevices(),
    api.getIoTTelemetry(),
  ]).then(([m, deviceData, telem]) => {
    telem = telem || {};
    const devices = (deviceData && deviceData.devices) ? deviceData.devices : [];
    const totalPods = (deviceData && deviceData.total) || devices.length || 0;
    const runningPods = devices.filter(d => !!d.connected).length;
    const typeSet = {};
    devices.forEach(d => { typeSet[d.device_type || 'unknown'] = 1; });
    const healthPct = totalPods > 0 ? Math.round((runningPods / totalPods) * 100) : 0;

    // Count protocols online
    let protos = 0;
    ['traffic-camera', 'parking-system', 'healthcare-api', 'env-sensor', 'street-lighting']
      .forEach(k => { if (telem[k] && telem[k].online) protos++; });

    // ── Summary stat cards ───────────────────────────────────────────
    document.getElementById('iotStats').innerHTML =
      '<div class="stat-card green"><div class="stat-label">Active Devices</div><div class="stat-value">' + runningPods + '</div><div class="stat-sub">Running in cluster</div></div>' +
      '<div class="stat-card blue"><div class="stat-label">Total Pods</div><div class="stat-value">' + totalPods + '</div><div class="stat-sub">IoT workloads deployed</div></div>' +
      '<div class="stat-card purple"><div class="stat-label">Protocol Emulators</div><div class="stat-value">' + protos + '/5</div><div class="stat-sub">ONVIF, MQTT, FHIR, Modbus, DALI</div></div>' +
      '<div class="stat-card ' + (healthPct >= 90 ? 'green' : healthPct >= 50 ? 'yellow' : 'red') + '"><div class="stat-label">Fleet Health</div><div class="stat-value">' + healthPct + '%</div><div class="stat-sub">' + runningPods + '/' + totalPods + ' pods running</div></div>';

    // ── Traffic Camera ONVIF ─────────────────────────────────────────
    renderTrafficCamera(telem);
    // ── Parking System MQTT/CoAP ─────────────────────────────────────
    renderParking(telem);
    // ── Healthcare FHIR R4 ───────────────────────────────────────────
    renderHealthcare(telem);
    // ── Environmental Sensor Modbus/OPC UA ────────────────────────────
    renderEnvSensor(telem);
    // ── Street Lighting DALI-2/TALQ ──────────────────────────────────
    renderStreetLighting(telem);

    // ── Fleet table ──────────────────────────────────────────────────
    let ih = '';
    if (devices.length > 0) {
      devices.forEach(d => {
        const dotCls = d.connected ? 'dot-green' : 'dot-red';
        const rate = (typeof d.current_rate === 'number') ? d.current_rate.toFixed(1) : '0.0';
        ih += '<tr><td>' + esc(d.device || d.device_id || '-') + '</td>' +
          '<td><span class="badge badge-info">' + esc(d.device_type || '-') + '</span></td>' +
          '<td><span class="dot ' + dotCls + '"></span>' + esc(d.status || '-') +
          ' <span style="font-size:11px;color:var(--text3)">(' + rate + '/min)</span></td>' +
          '<td>' + esc(d.namespace || 'smart-city') + '</td>' +
          '<td>' + esc(d.ip || '-') + '</td></tr>';
      });
    } else {
      ih = '<tr><td colspan="5" style="text-align:center;color:var(--text3)">No IoT devices found</td></tr>';
    }
    document.getElementById('iotTable').innerHTML = ih;
  });
}

// ── Protocol Emulator Card Renderers ─────────────────────────────────────

function renderTrafficCamera(telem) {
  const tc = telem['traffic-camera'] || {};
  document.getElementById('tc-status').innerHTML = tc.online
    ? '<span class="dot dot-green"></span>Online'
    : '<span class="dot dot-red"></span>Offline';
  document.getElementById('tc-status').className = tc.online ? 'badge badge-low' : 'badge badge-crit';

  if (tc.online && tc.telemetry) {
    const t = tc.telemetry, st = tc.stats || {};
    document.getElementById('tc-detail').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;text-align:left">' +
      '<div style="color:var(--text3)">Device ID</div><div><strong>' + esc(t.device_id || '-') + '</strong></div>' +
      '<div style="color:var(--text3)">Resolution</div><div>' + esc(t.codec || 'H.264') + ' @ ' + esc(t.current_fps || '-') + ' fps</div>' +
      '<div style="color:var(--text3)">Bitrate</div><div>' + (t.bitrate_kbps || 0) + ' kbps</div>' +
      '<div style="color:var(--text3)">CMOS Temp</div><div>' + (t.cmos_temperature_c || '-') + '&deg;C</div>' +
      '<div style="color:var(--text3)">Day/Night</div><div>' + esc(t.day_night_mode || '-') + '</div>' +
      '<div style="color:var(--text3)">Frames</div><div>' + (st.frames_processed || t.frame_counter || 0).toLocaleString() + '</div>' +
      '<div style="color:var(--text3)">Plates Detected</div><div><strong style="color:var(--accent)">' + (st.plates_detected || 0) + '</strong></div>' +
      '<div style="color:var(--text3)">Vehicles</div><div>' + (st.vehicles_total || 0).toLocaleString() + '</div>' +
      '<div style="color:var(--text3)">Firmware</div><div style="font-family:monospace">' + esc(st.firmware || '-') + '</div>' +
      '<div style="color:var(--text3)">ONVIF Ver</div><div>' + esc(st.protocol_version || '-') + '</div>' +
      '</div>';
    // ANPR telemetry panel
    const lp = t.last_plate;
    if (lp) {
      document.getElementById('tc-telemetry').innerHTML =
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">' +
        '<div style="background:var(--bg);border-radius:6px;padding:12px;border:1px solid var(--border)">' +
        '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">Last Plate</div>' +
        '<div style="font-size:22px;font-weight:700;font-family:monospace;color:var(--accent)">' + esc(lp.plate_number || '-') + '</div>' +
        '<div style="font-size:11px;color:var(--text2);margin-top:4px">' + esc(lp.vehicle_class || '-') + ' &bull; ' + esc(lp.direction || '-') + ' &bull; Lane ' + esc(lp.lane || '-') + '</div>' +
        '</div>' +
        '<div style="background:var(--bg);border-radius:6px;padding:12px;border:1px solid var(--border)">' +
        '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">Speed</div>' +
        '<div style="font-size:22px;font-weight:700">' + (lp.speed_kmh || 0).toFixed(1) + ' <span style="font-size:12px;color:var(--text3)">km/h</span></div>' +
        '<div style="font-size:11px;color:var(--text2);margin-top:4px">Confidence: ' + (lp.confidence * 100 || 0).toFixed(1) + '%</div>' +
        '</div>' +
        '<div style="background:var(--bg);border-radius:6px;padding:12px;border:1px solid var(--border)">' +
        '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">Camera Feed</div>' +
        '<div style="font-size:14px;font-weight:600">' + esc(t.codec || 'H.264') + '</div>' +
        '<div style="font-size:11px;color:var(--text2);margin-top:4px">Input: ' + (t.input_voltage_v || 0).toFixed(2) + 'V &bull; IR: ' + esc(t.ir_status || '-') + '</div>' +
        '</div></div>';
    }
  } else {
    document.getElementById('tc-detail').innerHTML = '<div style="color:var(--text3);text-align:center;padding:12px">Service offline or unreachable</div>';
    document.getElementById('tc-telemetry').innerHTML = '<div style="color:var(--text3);text-align:center">No ONVIF telemetry available</div>';
  }
}

function renderParking(telem) {
  const pk = telem['parking-system'] || {};
  document.getElementById('pk-status').innerHTML = pk.online
    ? '<span class="dot dot-green"></span>Online'
    : '<span class="dot dot-red"></span>Offline';
  document.getElementById('pk-status').className = pk.online ? 'badge badge-low' : 'badge badge-crit';

  if (pk.online && pk.stats) {
    const ps = pk.stats, gw = pk.gateway || {};
    document.getElementById('pk-detail').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;text-align:left">' +
      '<div style="color:var(--text3)">Gateway ID</div><div><strong>' + esc(gw.gateway_id || '-') + '</strong></div>' +
      '<div style="color:var(--text3)">Sensors</div><div>' + esc(gw.sensors_online || ps.sensors_total - ps.sensors_faulted || 0) + ' / ' + esc(ps.sensors_total || 0) + ' online</div>' +
      '<div style="color:var(--text3)">Occupancy</div><div><strong style="color:var(--yellow)">' + (ps.occupancy_rate || 0).toFixed(1) + '%</strong></div>' +
      '<div style="color:var(--text3)">Capacity</div><div>' + (ps.total_occupied || 0) + ' / ' + (ps.total_capacity || 0) + ' spaces</div>' +
      '<div style="color:var(--text3)">MQTT Broker</div><div style="font-family:monospace;font-size:11px">' + esc(gw.broker || '-') + '</div>' +
      '<div style="color:var(--text3)">Uplink</div><div style="font-size:11px">' + esc(gw.uplink || '-') + '</div>' +
      '<div style="color:var(--text3)">Battery Avg</div><div>' + (ps.avg_battery_pct || 0).toFixed(1) + '%</div>' +
      '<div style="color:var(--text3)">Faulted</div><div style="color:var(--red)">' + (ps.sensors_faulted || 0) + ' sensors</div>' +
      '</div>';

    // Parking lot detail cards
    const lots = pk.lots;
    if (lots && lots.parking_lots) {
      let lh = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px">';
      Object.keys(lots.parking_lots).forEach(lid => {
        const lot = lots.parking_lots[lid];
        const occPct = lot.occupancy_pct || 0;
        const barColor = occPct > 85 ? 'var(--red)' : occPct > 60 ? 'var(--yellow)' : 'var(--green)';
        lh += '<div style="background:var(--bg);border-radius:6px;padding:14px;border:1px solid var(--border)">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">' +
          '<strong>' + esc(lot.name || lid) + '</strong>' +
          '<span class="badge" style="background:rgba(234,179,8,.12);color:var(--yellow)">' + esc(lot.zone || '-') + '</span></div>' +
          '<div style="font-size:24px;font-weight:700;margin-bottom:4px">' + occPct.toFixed(0) + '% <span style="font-size:12px;color:var(--text3);font-weight:400">occupied</span></div>' +
          '<div class="progress" style="margin-bottom:8px"><div class="progress-fill" style="width:' + occPct + '%;background:' + barColor + '"></div></div>' +
          '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px;color:var(--text2)">' +
          '<div>Occupied: <strong>' + (lot.occupied || 0) + '</strong></div>' +
          '<div>Vacant: <strong>' + (lot.vacant || 0) + '</strong></div>' +
          '<div>Capacity: ' + (lot.capacity || 0) + '</div>' +
          '<div>Battery: ' + (lot.avg_battery_pct || 0).toFixed(0) + '%</div>' +
          '<div>Type: ' + esc(lot.sensor_type || '-') + '</div>' +
          '<div>Faulted: <span style="color:var(--red)">' + (lot.faulted_sensors || 0) + '</span></div>' +
          '</div></div>';
      });
      lh += '</div>';
      document.getElementById('pk-lots').innerHTML = lh;
    }
  } else {
    document.getElementById('pk-detail').innerHTML = '<div style="color:var(--text3);text-align:center;padding:12px">Service offline or unreachable</div>';
    document.getElementById('pk-lots').innerHTML = '<div style="color:var(--text3);text-align:center">No parking data available</div>';
  }
}

function renderHealthcare(telem) {
  const hc = telem['healthcare-api'] || {};
  document.getElementById('hc-status').innerHTML = hc.online
    ? '<span class="dot dot-green"></span>Online'
    : '<span class="dot dot-red"></span>Offline';
  document.getElementById('hc-status').className = hc.online ? 'badge badge-low' : 'badge badge-crit';

  if (hc.online && hc.stats) {
    const hs = hc.stats;
    document.getElementById('hc-detail').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;text-align:left">' +
      '<div style="color:var(--text3)">FHIR Version</div><div><strong>' + esc(hs.fhir_version || '-') + '</strong></div>' +
      '<div style="color:var(--text3)">Active Devices</div><div>' + (hs.active_devices || 0) + '</div>' +
      '<div style="color:var(--text3)">Patients</div><div>' + (hs.active_patients || 0) + '</div>' +
      '<div style="color:var(--text3)">Observations</div><div><strong style="color:var(--accent)">' + (hs.observations_total || 0).toLocaleString() + '</strong></div>' +
      '<div style="color:var(--text3)">Medications</div><div>' + (hs.medications_active || 0) + ' active</div>' +
      '<div style="color:var(--text3)">Active Alarms</div><div style="color:' + (hs.active_alarms > 0 ? 'var(--red)' : 'var(--green)') + '">' + (hs.active_alarms || 0) + '</div>' +
      '<div style="color:var(--text3)">Protocol</div><div style="font-size:11px">' + esc(hs.protocol || '-') + '</div>' +
      '</div>';

    // Medical devices telemetry table
    const devs = (hc.telemetry && hc.telemetry.devices) ? hc.telemetry.devices : [];
    if (devs.length > 0) {
      let dh = '<table style="width:100%;font-size:12px"><thead><tr><th>Device</th><th>Type</th><th>Patient</th><th>Location</th><th>Readings</th><th>Battery</th><th>Alarm</th></tr></thead><tbody>';
      devs.forEach(d => {
        let readingStr = '';
        if (d.readings) {
          readingStr = Object.keys(d.readings).map(k =>
            '<span style="color:var(--text2)">' + esc(k) + ':</span> <strong>' + esc(String(d.readings[k])) + '</strong>'
          ).join(' &bull; ');
        }
        const alarmBadge = d.alarm_active
          ? '<span class="badge badge-crit">' + esc(d.alarm_type || 'ALARM') + '</span>'
          : '<span class="badge badge-low">OK</span>';
        const battColor = d.battery_pct > 50 ? 'var(--green)' : d.battery_pct > 20 ? 'var(--yellow)' : 'var(--red)';
        dh += '<tr><td style="font-family:monospace">' + esc(d.device_id || '-') + '</td>' +
          '<td><span class="badge badge-purple" style="font-size:10px">' + esc(d.type || '-') + '</span><br><span style="font-size:10px;color:var(--text3)">' + esc(d.ieee_standard || '') + '</span></td>' +
          '<td>' + esc(d.patient || '-') + '</td>' +
          '<td>' + esc(d.location || '-') + '</td>' +
          '<td>' + readingStr + '</td>' +
          '<td><span style="color:' + battColor + '">' + (d.battery_pct || 0).toFixed(0) + '%</span></td>' +
          '<td>' + alarmBadge + '</td></tr>';
      });
      dh += '</tbody></table>';
      document.getElementById('hc-telemetry').innerHTML = dh;
    }
  } else {
    document.getElementById('hc-detail').innerHTML = '<div style="color:var(--text3);text-align:center;padding:12px">Service offline or unreachable</div>';
    document.getElementById('hc-telemetry').innerHTML = '<div style="color:var(--text3);text-align:center">No FHIR telemetry available</div>';
  }
}

function renderEnvSensor(telem) {
  const ev = telem['env-sensor'] || {};
  document.getElementById('ev-status').innerHTML = ev.online
    ? '<span class="dot dot-green"></span>Online'
    : '<span class="dot dot-red"></span>Offline';
  document.getElementById('ev-status').className = ev.online ? 'badge badge-low' : 'badge badge-crit';

  if (ev.online && ev.stats) {
    const es = ev.stats;
    document.getElementById('ev-detail').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;text-align:left">' +
      '<div style="color:var(--text3)">Stations</div><div><strong>' + (es.stations_online || 0) + ' / ' + (es.stations_total || 0) + '</strong> online</div>' +
      '<div style="color:var(--text3)">Sensor Channels</div><div>' + (es.total_sensor_channels || 0) + '</div>' +
      '<div style="color:var(--text3)">City AQI</div><div><strong style="color:' + (es.avg_aqi <= 50 ? 'var(--green)' : es.avg_aqi <= 100 ? 'var(--yellow)' : 'var(--red)') + '">' +
      (es.avg_aqi || 0) + '</strong> ' + esc(es.aqi_category || '') + '</div>' +
      '<div style="color:var(--text3)">Faulted</div><div style="color:' + (es.stations_faulted > 0 ? 'var(--red)' : 'var(--green)') + '">' +
      (es.stations_faulted || 0) + ' stations</div>' +
      '<div style="color:var(--text3)">Registers/Stn</div><div>' + (es.sensors_per_station || 0) + '</div>' +
      '<div style="color:var(--text3)">Protocol</div><div style="font-size:11px">' + esc(es.protocol || '-') + '</div>' +
      '</div>';

    // AQI station cards
    const aqi = ev.aqi;
    if (aqi && aqi.stations) {
      let ah = '<div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">' +
        '<div style="background:var(--bg);border-radius:8px;padding:16px 24px;border:1px solid var(--border);text-align:center">' +
        '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px">City AQI</div>' +
        '<div style="font-size:36px;font-weight:700;color:' + (aqi.city_aqi <= 50 ? 'var(--green)' : aqi.city_aqi <= 100 ? 'var(--yellow)' : 'var(--red)') + '">' +
        (aqi.city_aqi || 0) + '</div>' +
        '<div style="font-size:11px;color:var(--text2)">' + esc(aqi.category || '') + '</div></div>' +
        '<div style="flex:1;display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px">';
      Object.keys(aqi.stations).forEach(sid => {
        const s = aqi.stations[sid];
        const col = s.aqi <= 50 ? 'var(--green)' : s.aqi <= 100 ? 'var(--yellow)' : s.aqi <= 150 ? 'var(--orange)' : 'var(--red)';
        ah += '<div style="background:var(--bg);border-radius:6px;padding:8px 12px;border:1px solid var(--border)">' +
          '<div style="font-size:10px;color:var(--text3)">' + esc(sid) + '</div>' +
          '<div style="font-size:20px;font-weight:700;color:' + col + '">' + s.aqi + '</div>' +
          '<div style="font-size:10px;color:var(--text2)">' + esc(s.category || '') + '</div></div>';
      });
      ah += '</div></div>';
      document.getElementById('ev-aqi').innerHTML = ah;
    }
  } else {
    document.getElementById('ev-detail').innerHTML = '<div style="color:var(--text3);text-align:center;padding:12px">Service offline</div>';
    document.getElementById('ev-aqi').innerHTML = '<div style="color:var(--text3);text-align:center">No environmental data</div>';
  }
}

function renderStreetLighting(telem) {
  const sl = telem['street-lighting'] || {};
  document.getElementById('sl-status').innerHTML = sl.online
    ? '<span class="dot dot-green"></span>Online'
    : '<span class="dot dot-red"></span>Offline';
  document.getElementById('sl-status').className = sl.online ? 'badge badge-low' : 'badge badge-crit';

  if (sl.online && sl.stats) {
    const ss = sl.stats;
    document.getElementById('sl-detail').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;text-align:left">' +
      '<div style="color:var(--text3)">Luminaires</div><div><strong>' + (ss.luminaires_on || 0) + ' / ' + (ss.luminaires_total || 0) + '</strong> on</div>' +
      '<div style="color:var(--text3)">Total Power</div><div>' + (ss.total_power_w || 0).toFixed(0) + ' W</div>' +
      '<div style="color:var(--text3)">Avg Dimming</div><div>' + (ss.avg_dim_pct || 0).toFixed(0) + '%</div>' +
      '<div style="color:var(--text3)">Faults</div><div style="color:' + (ss.luminaires_fault > 0 ? 'var(--red)' : 'var(--green)') + '">' +
      (ss.luminaires_fault || 0) + '</div>' +
      '<div style="color:var(--text3)">Energy</div><div>' + (ss.energy_total_kwh || 0).toFixed(2) + ' kWh</div>' +
      '<div style="color:var(--text3)">Pro Protocol</div><div style="font-size:11px">' + esc(ss.protocol || '-') + '</div>' +
      '</div>';

    // Zone breakdown
    if (ss.zones) {
      let zh = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px">';
      Object.keys(ss.zones).forEach(zn => {
        const z = ss.zones[zn];
        const dimColor = z.avg_dim_pct > 70 ? 'var(--yellow)' : z.avg_dim_pct > 30 ? 'var(--accent)' : 'var(--text3)';
        zh += '<div style="background:var(--bg);border-radius:6px;padding:10px 12px;border:1px solid var(--border)">' +
          '<div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.3px">' + esc(zn) + '</div>' +
          '<div style="font-size:18px;font-weight:700;color:' + dimColor + '">' + (z.avg_dim_pct || 0).toFixed(0) + '%</div>' +
          '<div style="font-size:10px;color:var(--text2)">' + (z.on || 0) + '/' + z.count + ' on &bull; ' + (z.power_w || 0).toFixed(0) + 'W</div></div>';
      });
      zh += '</div>';
      document.getElementById('sl-zones').innerHTML = zh;
    }
  } else {
    document.getElementById('sl-detail').innerHTML = '<div style="color:var(--text3);text-align:center;padding:12px">Service offline</div>';
    document.getElementById('sl-zones').innerHTML = '<div style="color:var(--text3);text-align:center">No lighting data</div>';
  }
}

// ══════════════════════════════════════════════════════════════════════════
// IoT Event Feed (polling-based — replaces broken WebSocket bridge)
// ══════════════════════════════════════════════════════════════════════════
//
// The iot-stream-bridge (NodePort 30810) is not deployed in most setups,
// so the old WebSocket approach just showed "Bridge unavailable" forever.
// This replacement polls /api/iot/events every 10 seconds and renders
// real device events that are already collected by the backend.

let iotFeedTimer = null;
let lastEventCount = 0;

/**
 * Start the IoT Event Feed — polls /api/iot/events every 10 seconds.
 */
export function connectIoTStream() {
  const dot = document.getElementById('iotStreamDot');
  const status = document.getElementById('iotStreamStatus');
  const log = document.getElementById('iotStreamLog');

  dot.className = 'dot dot-green';
  status.textContent = 'Polling IoT events';
  log.innerHTML = '';

  fetchIoTEvents(); // immediate first fetch
  iotFeedTimer = setInterval(fetchIoTEvents, 10000);
}

function fetchIoTEvents() {
  api.getIoTEvents(30).then(data => {
    if (!data || !data.events) return;
    const events = data.events;
    const dot = document.getElementById('iotStreamDot');
    const status = document.getElementById('iotStreamStatus');
    const log = document.getElementById('iotStreamLog');
    const countEl = document.getElementById('iotStreamCount');

    if (events.length === 0) {
      dot.className = 'dot dot-yellow';
      status.textContent = 'No events yet — waiting for IoT traffic';
      return;
    }

    dot.className = 'dot dot-green';
    status.textContent = 'Live — ' + data.total + ' total events';
    store.setState({ iotStreamCount: data.total });
    countEl.textContent = data.total;

    // Only re-render if count changed
    if (data.total === lastEventCount) return;
    lastEventCount = data.total;

    // Render most recent events (newest first)
    const lines = events.slice().reverse().map(ev => {
      const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : '--:--:--';
      const device = ev.device_id || ev.device || 'unknown';
      const evType = ev.event_type || ev.type || 'data';
      const ns = ev.namespace || 'smart-city';
      const detail = ev.value || ev.message || JSON.stringify(ev.data || '').slice(0, 60);
      return '[' + ts + '] ' + device + ' (' + ns + ') ' + evType + ' → ' + detail;
    });

    log.textContent = lines.join('\n');
  }).catch(() => {
    // silently retry on next interval
  });
}

/** Stop the IoT Event Feed (called on logout). */
export function disconnectIoTStream() {
  if (iotFeedTimer) { clearInterval(iotFeedTimer); iotFeedTimer = null; }
}

/** Toggle IoT event feed panel visibility. */
export function toggleIoTStream() {
  const state = store.getState();
  const open = !state.ui.iotStreamOpen;
  store.setState({ ui: { ...state.ui, iotStreamOpen: open } });
  document.getElementById('iotStreamBody').style.display = open ? 'block' : 'none';
  document.getElementById('iotStreamToggleBtn').textContent = open ? '\u25BC' : '\u25B2';
}

/** Clear the IoT event feed log. */
export function clearIoTStream() {
  document.getElementById('iotStreamLog').textContent = 'IoT event feed cleared.';
  store.setState({ iotStreamCount: 0 });
  document.getElementById('iotStreamCount').textContent = '0';
  lastEventCount = 0;
}
