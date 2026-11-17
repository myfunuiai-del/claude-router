let activeMainTab = 'console';
let livePaused = false;
let livePollTimer = null;

function _escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function switchMainTab(tab) {
  activeMainTab = tab === 'live' ? 'live' : 'console';
  const vConsole = document.getElementById('view-console');
  const vLive = document.getElementById('view-live');
  const bConsole = document.getElementById('tab-btn-console');
  const bLive = document.getElementById('tab-btn-live');

  if (vConsole) vConsole.style.display = activeMainTab === 'console' ? '' : 'none';
  if (vLive) vLive.style.display = activeMainTab === 'live' ? '' : 'none';
  if (bConsole) bConsole.classList.toggle('active', activeMainTab === 'console');
  if (bLive) bLive.classList.toggle('active', activeMainTab === 'live');

  _restartLivePolling();
  if (activeMainTab === 'live') {
    fetchLiveSnapshot();
  }
}

function toggleLivePause() {
  livePaused = !livePaused;
  const btn = document.getElementById('live-pause-btn');
  const dot = document.getElementById('live-tab-dot');
  if (btn) btn.innerText = livePaused ? '▶ Resume' : '⏸ Pause';
  if (dot) dot.classList.toggle('is-paused', livePaused);
  if (!livePaused && activeMainTab === 'live') {
    fetchLiveSnapshot();
  }
}

function _restartLivePolling() {
  if (livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
  const intervalMs = activeMainTab === 'live' ? 1500 : 6000;
  livePollTimer = setInterval(() => {
    if (!livePaused) fetchLiveSnapshot();
  }, intervalMs);
}

async function fetchLiveSnapshot() {
  try {
    const res = await fetch('/api/ui/live');
    if (!res.ok) return;
    const data = await res.json();
    renderLiveSnapshot(data);
  } catch (err) {
    // Ignore transient poll errors
  }
}

function renderLiveSnapshot(data) {
  const issues = data.issues || [];
  const inFlight = data.in_flight || [];
  const servers = data.servers || [];
  const feed = data.feed || [];
  const cooldowns = data.cooldowns || [];

  // Update tab badge & dot even while on Console tab
  const badge = document.getElementById('tab-issue-badge');
  if (badge) {
    if (issues.length > 0) {
      badge.style.display = 'inline-block';
      badge.innerText = String(issues.length);
    } else {
      badge.style.display = 'none';
    }
  }
  const tabDot = document.getElementById('live-tab-dot');
  if (tabDot && !livePaused) {
    tabDot.classList.toggle('is-busy', inFlight.length > 0);
  }

  if (activeMainTab !== 'live') return;

  // Clock
  const clockEl = document.getElementById('live-clock');
  if (clockEl) clockEl.innerText = data.now_str || '--:--:--';

  // 1. Now Running / In-Flight
  const nowStatus = document.getElementById('live-now-status');
  const inFlightBox = document.getElementById('live-inflight-box');
  if (nowStatus && inFlightBox) {
    if (inFlight.length > 0) {
      nowStatus.innerHTML = `<span class="live-pulse-dot is-busy"></span><span>⚡ Active Now (${inFlight.length} running)</span>`;
      inFlightBox.innerHTML = inFlight.map(item => `
        <div class="inflight-row">
          <span>⚡ <strong>${_escHtml(item.provider_name)}</strong> • ${_escHtml(item.model)} • ${_escHtml(item.key_label)}</span>
          <span>${_escHtml(item.stage)} • ${(item.elapsed_ms / 1000).toFixed(1)}s</span>
        </div>
      `).join('');
    } else {
      const last = feed[0];
      nowStatus.innerHTML = `<span class="live-pulse-dot${livePaused ? ' is-paused' : ''}"></span><span>${livePaused ? '⏸ Live Paused' : '● Live — Idle'}</span>`;
      if (last && last.status === 'ok') {
        inFlightBox.innerHTML = `<div class="inflight-idle">Last passed: <span style="color:#79c0ff;">${_escHtml(last.passed_by)}</span> (${last.latency_ms}ms at ${_escHtml(last.time)})</div>`;
      } else {
        inFlightBox.innerHTML = `<div class="inflight-idle">Waiting for agent requests on http://127.0.0.1:8999 ...</div>`;
      }
    }
  }

  // 2. Per-Server Live Usage Cards
  const srvMeta = document.getElementById('live-servers-meta');
  const srvGrid = document.getElementById('live-servers-grid');
  if (srvMeta) {
    const activeOn = servers.filter(s => s.enabled).length;
    srvMeta.innerText = `${activeOn}/${servers.length} ON`;
  }
  if (srvGrid) {
    if (!servers.length) {
      srvGrid.innerHTML = '<div class="live-empty">No servers configured</div>';
    } else {
      srvGrid.innerHTML = servers.map(s => {
        const rate = s.success_rate === null ? 100 : s.success_rate;
        const barColor = s.success_rate === null ? '#30363d' : (rate >= 80 ? '#3fb950' : rate >= 40 ? '#d29922' : '#f85149');
        const stateTag = !s.enabled
          ? '<span class="prio-tag prio-off">OFF</span>'
          : (s.in_pipeline ? '<span class="prio-tag prio-1">ON</span>' : '<span class="prio-tag prio-standby">STANDBY</span>');
        const cardCls = `live-srv-card${!s.enabled ? ' is-off' : ''}${s.last_status === 'err' ? ' has-err' : ''}`;
        return `
          <div class="${cardCls}">
            <div class="live-srv-head">
              <span class="live-srv-name" title="${_escHtml(s.name)}">${_escHtml(s.name)}</span>
              ${stateTag}
            </div>
            <div class="live-srv-stats">
              <span>✅ ${s.ok} &nbsp;❌ ${s.err}${s.recoveries ? ` &nbsp;🛡 ${s.recoveries}` : ''}</span>
              <span>${s.avg_ms ? `${s.avg_ms}ms` : '—'}</span>
            </div>
            <div class="live-rate-bar"><div class="live-rate-fill" style="width:${rate}%; background:${barColor};"></div></div>
            <div class="live-srv-sub">${_escHtml(s.last_model || '—')} ${s.last_key ? `• ${_escHtml(s.last_key)}` : ''} • ${_escHtml(s.last_used_str)}</div>
            ${s.last_error ? `<div class="live-srv-err" title="${_escHtml(s.last_error)}">⚠ ${_escHtml(s.last_error)}</div>` : ''}
          </div>
        `;
      }).join('');
    }
  }

  // 3. Live Cooldowns & Issues
  const cdBox = document.getElementById('live-cooldowns-box');
  const clearCdBtn = document.getElementById('live-clear-cd-btn');
  if (clearCdBtn) clearCdBtn.style.display = cooldowns.length > 0 ? '' : 'none';
  if (cdBox) {
    cdBox.innerHTML = cooldowns.map(c => {
      const scope = c.scope && c.scope !== '*' ? ` [${c.scope}]` : '';
      return `<span class="cooldown-chip">❄️ ${_escHtml(c.provider)} ${_escHtml(c.key)}${_escHtml(scope)} • HTTP ${c.code} • ${c.remaining_s}s left</span>`;
    }).join('');
  }

  const issuesEl = document.getElementById('live-issues-list');
  if (issuesEl) {
    if (!issues.length) {
      issuesEl.innerHTML = '<div class="live-empty">🟢 No issues recorded — all requests clean</div>';
    } else {
      issuesEl.innerHTML = issues.map(it => `
        <div class="live-row is-issue">
          <div class="live-row-top">
            <span>
              <span class="live-code-badge err">${it.code ? `HTTP ${it.code}` : 'NET ERR'}</span>
              <strong style="color:var(--text-heading); margin-left:4px;">${_escHtml(it.provider_name)}</strong>
              <span style="color:var(--text-muted);"> • ${_escHtml(it.key_label)} • ${_escHtml(it.model)}</span>
            </span>
            <span style="color:var(--text-muted);">${_escHtml(it.time)}</span>
          </div>
          <div class="live-row-reason">কারণ: ${_escHtml(it.reason)}</div>
          ${it.detail ? `<div class="live-row-detail">${_escHtml(it.detail)}</div>` : ''}
        </div>
      `).join('');
    }
  }

  // 4. Live Request Feed (Winner + 5-Stage Recovery Details)
  const feedMeta = document.getElementById('live-feed-meta');
  const feedEl = document.getElementById('live-feed-list');
  if (feedMeta) feedMeta.innerText = `${feed.length} recent`;
  if (feedEl) {
    if (!feed.length) {
      feedEl.innerHTML = '<div class="live-empty">No completed requests yet — send a prompt to see live routing &amp; recovery</div>';
    } else {
      feedEl.innerHTML = feed.map(f => {
        const isOk = f.status === 'ok';
        const hasRec = !!(f.recovery_stage && f.recovery_stage.length > 0);
        const rowCls = !isOk ? 'live-row is-issue' : (hasRec ? 'live-row is-recovered' : 'live-row is-ok');
        const badgeHtml = isOk
          ? `<span class="live-code-badge ok">200 OK</span>`
          : `<span class="live-code-badge err">${f.code || 'ERR'} FAIL</span>`;
        const recHtml = hasRec
          ? `<div class="live-recovery-pill">🛡️ ${_escHtml(f.recovery_stage)} ➔ Passed by ${_escHtml(f.provider_name)} (${_escHtml(f.key_label)})</div>`
          : '';
        return `
          <div class="${rowCls}">
            <div class="live-row-top">
              <span>${badgeHtml} <span style="color:var(--text-muted); margin-left:4px;">${_escHtml(f.path)}</span></span>
              <span style="color:var(--text-muted);">${f.latency_ms}ms • ${_escHtml(f.time)}</span>
            </div>
            <div class="live-winner-line">${isOk ? '✅ Passed by:' : '❌ Failed:'} ${_escHtml(f.passed_by)}</div>
            ${recHtml}
          </div>
        `;
      }).join('');
    }
  }
}

async function clearLiveData(mode) {
  const actionMap = {
    cooldowns: 'clear_cooldowns',
    issues: 'clear_issues',
    all: 'clear_all'
  };
  const action = actionMap[mode] || 'clear_all';
  try {
    const res = await fetch('/api/ui/live-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || 'Cleared');
      fetchLiveSnapshot();
    }
  } catch (err) {
    showToast('Failed to clear live data', true);
  }
}

// Start lightweight polling immediately (6s on Console tab for issue badge, 1.5s when Live tab active)
_restartLivePolling();
fetchLiveSnapshot();
