// dashboard.usage-1.js - Usage & Quota Analytics Tab Engine
// Modularized per gemini.md Rule 2 (Strictly < 500 lines)

let usagePollTimer = null;
let usageTickTimer = null;
let currentUsageFilter = 'all';
let lastUsageData = null;

function formatNum(n) {
  if (!n || n <= 0) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function fetchUsageSnapshot() {
  try {
    const res = await fetch('/api/ui/usage');
    if (!res.ok) return;
    const data = await res.json();
    lastUsageData = data;
    renderUsageView(data);
  } catch (e) {
    console.error('[Usage Tab Error]', e);
  }
}

function startUsagePolling() {
  stopUsagePolling();
  fetchUsageSnapshot();
  usagePollTimer = setInterval(fetchUsageSnapshot, 2500);
  usageTickTimer = setInterval(tickRefillCountdowns, 1000);
}

function stopUsagePolling() {
  if (usagePollTimer) { clearInterval(usagePollTimer); usagePollTimer = null; }
  if (usageTickTimer) { clearInterval(usageTickTimer); usageTickTimer = null; }
}

function setUsageFilter(filterName) {
  currentUsageFilter = filterName;
  if (lastUsageData) renderUsageView(lastUsageData);
}

function tickRefillCountdowns() {
  const elements = document.querySelectorAll('.live-refill-tick');
  elements.forEach(el => {
    let s = parseInt(el.getAttribute('data-sec') || '0', 10);
    if (s > 0) {
      s -= 1;
      el.setAttribute('data-sec', s);
      const mins = Math.floor(s / 60);
      const secs = s % 60;
      el.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}s`;
    } else {
      el.textContent = '00:00s (Refilling...)';
    }
  });
}

function renderUsageView(data) {
  const container = document.getElementById('view-usage');
  if (!container || !data || data.status !== 'ok') return;

  const kpis = data.kpis || {};
  const servers = data.servers || [];
  const keys = data.keys || [];
  const models = data.models || [];

  // Filter servers
  const filteredServers = servers.filter(s => {
    if (currentUsageFilter === 'all') return true;
    if (currentUsageFilter === 'active') return s.enabled && !s.is_throttled;
    if (currentUsageFilter === 'exhausted') return s.is_throttled;
    if (currentUsageFilter === 'cooling') return keys.some(k => k.provider_id === s.id && k.status === 'cooldown');
    return true;
  });

  let html = `
    <!-- Usage KPI Header -->
    <div class="usage-kpi-grid">
      <div class="usage-kpi-card">
        <div class="usage-kpi-lbl">TOTAL TOKENS CONSUMED</div>
        <div class="usage-kpi-val" style="color:#58a6ff;">${kpis.total_tokens_str || '0'}</div>
        <div class="usage-kpi-sub">
          <span style="color:#7ee787;">▲ In: ${kpis.total_in_tokens_str || '0'}</span> &bull; 
          <span style="color:#d2a8ff;">▼ Out: ${kpis.total_out_tokens_str || '0'}</span>
        </div>
      </div>
      <div class="usage-kpi-card">
        <div class="usage-kpi-lbl">SERVER QUOTA HEALTH</div>
        <div class="usage-kpi-val" style="color:${kpis.throttled_servers > 0 ? '#ff7b72' : '#56d364'};">
          ${kpis.active_servers - kpis.throttled_servers}/${kpis.active_servers} Ready
        </div>
        <div class="usage-kpi-sub">
          ${kpis.throttled_servers > 0 ? `<span style="color:#ff7b72;">⚠️ ${kpis.throttled_servers} Quota Full</span>` : '<span>All Quotas Normal</span>'}
        </div>
      </div>
      <div class="usage-kpi-card">
        <div class="usage-kpi-lbl">LIFETIME REQUESTS</div>
        <div class="usage-kpi-val" style="color:#e6edf3;">${kpis.total_requests || 0}</div>
        <div class="usage-kpi-sub">Across ${kpis.total_servers || 0} configured providers</div>
      </div>
      <div class="usage-kpi-card">
        <div class="usage-kpi-lbl">KEY COOLDOWNS</div>
        <div class="usage-kpi-val" style="color:${kpis.cooling_keys_count > 0 ? '#e3b341' : '#56d364'};">
          ${kpis.cooling_keys_count} Keys
        </div>
        <div class="usage-kpi-sub">${kpis.cooling_keys_count > 0 ? 'Active 429/Error cooldown' : 'All keys available'}</div>
      </div>
    </div>

    <!-- Filter & Action Bar -->
    <div class="usage-filter-bar">
      <div class="usage-filter-group">
        <button type="button" class="btn btn-xs ${currentUsageFilter === 'all' ? 'btn-primary' : ''}" onclick="setUsageFilter('all')">All Servers (${servers.length})</button>
        <button type="button" class="btn btn-xs ${currentUsageFilter === 'active' ? 'btn-primary' : ''}" onclick="setUsageFilter('active')">🟢 Active (${servers.filter(s=>s.enabled && !s.is_throttled).length})</button>
        <button type="button" class="btn btn-xs ${currentUsageFilter === 'exhausted' ? 'btn-primary' : ''}" onclick="setUsageFilter('exhausted')">🟠 Exhausted (${kpis.throttled_servers})</button>
        <button type="button" class="btn btn-xs ${currentUsageFilter === 'cooling' ? 'btn-primary' : ''}" onclick="setUsageFilter('cooling')">🟡 Cooling Down (${kpis.cooling_keys_count})</button>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:11px; font-family:var(--mono); color:var(--text-muted);">${data.now_str || ''}</span>
        <button type="button" class="btn btn-xs" onclick="fetchUsageSnapshot()">🔄 Refresh</button>
      </div>
    </div>

    <!-- Section 1: Server Quotas Grid -->
    <div class="panel" style="margin-top:10px;">
      <div class="panel-head">
        <span>⚡ SERVER RATE LIMITS, QUOTAS &amp; REFILL CLOCKS</span>
        <span style="font-size:10px; color:var(--text-muted); font-family:var(--mono);">${filteredServers.length} Servers</span>
      </div>
      <div class="usage-servers-grid">
  `;

  if (filteredServers.length === 0) {
    html += `<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:12px; grid-column:1/-1;">No servers match the selected filter.</div>`;
  } else {
    filteredServers.forEach(s => {
      let badgeColor = '#56d364';
      let badgeText = '🟢 READY';
      if (!s.enabled) {
        badgeColor = '#8b949e'; badgeText = '⚪ DISABLED';
      } else if (s.is_throttled) {
        badgeColor = '#ff7b72'; badgeText = `🟠 EXHAUSTED (${s.refill_text || 'Active'})`;
      } else if (!s.in_pipeline) {
        badgeColor = '#79c0ff'; badgeText = '💤 STANDBY';
      }

      const rpmBarColor = (s.rpm_percent && s.rpm_percent > 85) ? '#ff7b72' : (s.rpm_percent > 60 ? '#e3b341' : '#56d364');
      const winBarColor = (s.window_percent && s.window_percent > 85) ? '#ff7b72' : (s.window_percent > 60 ? '#e3b341' : '#58a6ff');

      html += `
        <div class="usage-server-card ${s.is_throttled ? 'is-throttled' : ''}">
          <div class="usage-card-top">
            <div style="min-width:0;">
              <div style="font-weight:600; font-size:13px; color:#fff; display:flex; align-items:center; gap:6px;">
                <span class="truncate">${escapeHtml(s.name)}</span>
                <span style="font-size:9.5px; padding:1px 5px; border-radius:3px; background:#1f2837; color:#79c0ff; font-family:var(--mono);">${escapeHtml(s.type)}</span>
              </div>
              <div style="font-size:10px; color:var(--text-muted); margin-top:2px;">
                Mode: <span style="color:#d2a8ff;">${escapeHtml(s.mode)}</span> &bull; ${s.keys_count} Keys &bull; ${s.models_count} Models
              </div>
            </div>
            <div>
              <span class="usage-status-pill" style="border-color:${badgeColor}40; color:${badgeColor}; background:${badgeColor}15;">${badgeText}</span>
            </div>
          </div>

          ${s.is_throttled ? `
            <div class="usage-refill-alert">
              <span>⏳ Quota Full (${escapeHtml(s.throttle_reason)}) &bull; Refills in:</span>
              <strong class="live-refill-tick" data-sec="${s.refill_seconds}">${s.refill_text || '00:00s'}</strong>
            </div>
          ` : ''}

          <!-- RPM Meter -->
          <div class="usage-meter-block">
            <div class="usage-meter-head">
              <span>RPM (Last 60s):</span>
              <span style="font-family:var(--mono); font-weight:600;">
                ${s.rpm} ${s.rpm_limit ? `/ ${s.rpm_limit}` : `<span style="color:#56d364;">/ ∞</span>`}
              </span>
            </div>
            <div class="usage-progress-track">
              <div class="usage-progress-bar" style="width:${s.rpm_limit ? s.rpm_percent : 5}%; background:${rpmBarColor};"></div>
            </div>
          </div>

          <!-- Window Quota Meter -->
          <div class="usage-meter-block">
            <div class="usage-meter-head">
              <span>Window (${s.window_hours}h Quota):</span>
              <span style="font-family:var(--mono); font-weight:600;">
                ${s.window_reqs} ${s.window_limit ? `/ ${s.window_limit}` : `<span style="color:#58a6ff;">/ ∞</span>`}
              </span>
            </div>
            <div class="usage-progress-track">
              <div class="usage-progress-bar" style="width:${s.window_limit ? s.window_percent : 5}%; background:${winBarColor};"></div>
            </div>
          </div>

          <!-- Tokens & Latency Footer -->
          <div class="usage-card-footer">
            <div class="usage-token-chip">
              <span>Tokens:</span> <strong>${s.total_tokens_str || '0'}</strong>
              <small style="color:var(--text-muted);">(${formatNum(s.total_in_tokens)} in / ${formatNum(s.total_out_tokens)} out)</small>
            </div>
            <div style="font-size:10px; color:var(--text-muted); font-family:var(--mono);">
              Avg ${s.avg_ms || 0}ms ${s.last_tps ? `&bull; ${s.last_tps} tok/s` : ''}
            </div>
          </div>
        </div>
      `;
    });
  }

  html += `
      </div>
    </div>

    <!-- Section 2: Granular API Key Health & Cooldowns -->
    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">
        <span>🔑 API KEYS STATUS &amp; REASON MATRIX</span>
        <span style="font-size:10px; color:var(--text-muted); font-family:var(--mono);">${keys.length} Keys Configured</span>
      </div>
      <div class="table-responsive" style="max-height:280px; overflow-y:auto;">
        <table class="usage-table">
          <thead>
            <tr>
              <th>Server</th>
              <th>Key Label</th>
              <th>Masked Token</th>
              <th>Status</th>
              <th>Remaining / Reason</th>
              <th>60s Req (Tok)</th>
              <th>Total Tok</th>
              <th>Last Active</th>
            </tr>
          </thead>
          <tbody>
  `;

  if (keys.length === 0) {
    html += `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:16px;">No keys configured yet.</td></tr>`;
  } else {
    keys.forEach(k => {
      let stColor = '#56d364';
      let stLabel = 'Ready';
      if (k.status === 'cooldown') {
        stColor = '#e3b341'; stLabel = `Cooldown (${k.cooldown_remaining_s}s)`;
      } else if (k.status === 'exhausted') {
        stColor = '#ff7b72'; stLabel = 'Exhausted';
      } else if (k.status === 'error') {
        stColor = '#f85149'; stLabel = 'Auth Error';
      }

      html += `
        <tr>
          <td><strong style="color:#e6edf3;">${escapeHtml(k.provider_name)}</strong></td>
          <td><span style="font-family:var(--mono); font-size:11px;">${escapeHtml(k.key_label)}</span></td>
          <td><code style="font-size:10.5px; color:#79c0ff;">${escapeHtml(k.key_masked)}</code></td>
          <td><span class="usage-table-pill" style="color:${stColor}; background:${stColor}15; border:1px solid ${stColor}40;">${stLabel}</span></td>
          <td style="font-size:10.5px; color:${k.cooldown_reason ? '#ff7b72' : 'var(--text-muted)'};">${escapeHtml(k.cooldown_reason) || '—'}</td>
          <td style="font-family:var(--mono); font-size:11px;">${k.rpm_60s} req <small style="color:var(--text-muted);">(${formatNum(k.tokens_60s)})</small></td>
          <td style="font-family:var(--mono); font-size:11px; font-weight:600; color:#58a6ff;">${formatNum(k.total_tokens)}</td>
          <td style="font-family:var(--mono); font-size:11px; color:var(--text-muted);">${escapeHtml(k.last_used_str)}</td>
        </tr>
      `;
    });
  }

  html += `
          </tbody>
        </table>
      </div>
    </div>

    <!-- Section 3: Per-Model Token Consumption -->
    <div class="panel" style="margin-top:14px; margin-bottom:20px;">
      <div class="panel-head">
        <span>🧠 PER-MODEL TOKEN CONSUMPTION BREAKDOWN</span>
        <span style="font-size:10px; color:var(--text-muted); font-family:var(--mono);">${models.length} Models Tracked</span>
      </div>
      <div class="table-responsive" style="max-height:240px; overflow-y:auto;">
        <table class="usage-table">
          <thead>
            <tr>
              <th>Model Name</th>
              <th>Provider</th>
              <th>Requests</th>
              <th>Prompt Tokens</th>
              <th>Completion Tokens</th>
              <th>Total Tokens</th>
            </tr>
          </thead>
          <tbody>
  `;

  if (models.length === 0) {
    html += `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">No model traffic recorded yet. Make inference requests to see live data.</td></tr>`;
  } else {
    models.forEach(m => {
      html += `
        <tr>
          <td><strong style="color:#d2a8ff; font-family:var(--mono); font-size:11px;">${escapeHtml(m.model)}</strong></td>
          <td><span style="color:#e6edf3;">${escapeHtml(m.server)}</span></td>
          <td style="font-family:var(--mono);">${m.requests}</td>
          <td style="font-family:var(--mono); color:#7ee787;">${formatNum(m.in_tokens)}</td>
          <td style="font-family:var(--mono); color:#d2a8ff;">${formatNum(m.out_tokens)}</td>
          <td style="font-family:var(--mono); font-weight:700; color:#58a6ff;">${m.total_tokens_str}</td>
        </tr>
      `;
    });
  }

  html += `
          </tbody>
        </table>
      </div>
    </div>
  `;

  container.innerHTML = html;
}
