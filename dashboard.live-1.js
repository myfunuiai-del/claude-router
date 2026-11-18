let activeMainTab = 'console';
let livePaused = false;
let livePollTimer = null;
let liveFetchInProgress = false;
let liveAbortCtrl = null;
let lastRenderedSeq = -1;
let lastInFlightSig = '';
let lastCooldownSig = '';
let lastTopFeedId = 0;
let lastTopIssueId = 0;

function _escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _shouldPollLive() {
  return activeMainTab === 'live' && !livePaused && !document.hidden;
}

function stopLivePolling() {
  if (livePollTimer) {
    clearTimeout(livePollTimer);
    livePollTimer = null;
  }
  if (liveAbortCtrl) {
    try { liveAbortCtrl.abort(); } catch (e) {}
    liveAbortCtrl = null;
  }
  liveFetchInProgress = false;
  const dot = document.getElementById('live-tab-dot');
  if (dot) {
    dot.classList.remove('is-busy');
    dot.classList.toggle('is-paused', true);
  }
}

function scheduleNextLivePoll() {
  if (livePollTimer) {
    clearTimeout(livePollTimer);
    livePollTimer = null;
  }
  if (!_shouldPollLive()) return;
  livePollTimer = setTimeout(() => {
    livePollTimer = null;
    if (_shouldPollLive()) {
      fetchLiveSnapshot();
    }
  }, 1500);
}

function startLivePolling() {
  if (!_shouldPollLive()) {
    stopLivePolling();
    return;
  }
  const dot = document.getElementById('live-tab-dot');
  if (dot) dot.classList.remove('is-paused');
  fetchLiveSnapshot(true);
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

  if (activeMainTab === 'live') {
    lastRenderedSeq = -1;
    lastInFlightSig = '';
    lastCooldownSig = '';
    startLivePolling();
  } else {
    stopLivePolling();
  }
}

function toggleLivePause() {
  livePaused = !livePaused;
  const btn = document.getElementById('live-pause-btn');
  if (btn) btn.innerText = livePaused ? '▶ Resume' : '⏸ Pause';
  if (livePaused) {
    stopLivePolling();
    const nowStatus = document.getElementById('live-now-status');
    if (nowStatus) nowStatus.innerHTML = '<span class="live-pulse-dot is-paused"></span><span>⏸ Live Paused</span>';
  } else {
    startLivePolling();
  }
}

async function fetchLiveSnapshot(forceRender = false) {
  if (!_shouldPollLive() && !forceRender) {
    stopLivePolling();
    return;
  }
  if (liveFetchInProgress) return;
  liveFetchInProgress = true;
  liveAbortCtrl = new AbortController();

  try {
    const res = await fetch('/api/ui/live', { signal: liveAbortCtrl.signal });
    if (!res.ok) return;
    const data = await res.json();
    if (activeMainTab === 'live') {
      renderLiveSnapshot(data, forceRender);
    }
  } catch (err) {
    // Ignore abort/transient errors
  } finally {
    liveFetchInProgress = false;
    liveAbortCtrl = null;
    if (_shouldPollLive()) {
      scheduleNextLivePoll();
    }
  }
}

function renderLiveSnapshot(data, forceRender = false) {
  if (activeMainTab !== 'live') return;

  const issues = data.issues || [];
  const inFlight = data.in_flight || [];
  const servers = data.servers || [];
  const feed = data.feed || [];
  const cooldowns = data.cooldowns || [];
  const seq = typeof data.seq === 'number' ? data.seq : -1;

  // Update badge & dot
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
    tabDot.classList.remove('is-paused');
    tabDot.classList.toggle('is-busy', inFlight.length > 0);
  }

  // Clock
  const clockEl = document.getElementById('live-clock');
  if (clockEl) clockEl.textContent = `LIVE ${data.now_str || '--:--:--'}`;

  // 1. Now Running / In-Flight (only update DOM when changed)
  const inFlightSig = JSON.stringify(inFlight.map(i => [i.id, i.provider, i.model, i.key_label, i.stage, Math.floor((i.elapsed_ms || 0) / 1000)]))
    + '|' + (feed[0]?.id || 0) + '|' + livePaused;
  if (forceRender || inFlightSig !== lastInFlightSig) {
    lastInFlightSig = inFlightSig;
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
          inFlightBox.innerHTML = '<div class="inflight-idle">Waiting for agent requests on http://127.0.0.1:8999 ...</div>';
        }
      }
    }
  }

  // 2. Cooldowns (only update DOM when changed)
  const cdSig = JSON.stringify(cooldowns);
  if (forceRender || cdSig !== lastCooldownSig) {
    lastCooldownSig = cdSig;
    const cdBox = document.getElementById('live-cooldowns-box');
    const clearCdBtn = document.getElementById('live-clear-cd-btn');
    if (clearCdBtn) clearCdBtn.style.display = cooldowns.length > 0 ? '' : 'none';
    if (cdBox) {
      cdBox.innerHTML = cooldowns.map(c => {
        const scope = c.scope && c.scope !== '*' ? ` [${c.scope}]` : '';
        return `<span class="cooldown-chip">❄️ ${_escHtml(c.provider)} ${_escHtml(c.key)}${_escHtml(scope)} • HTTP ${c.code} • ${c.remaining_s}s left</span>`;
      }).join('');
    }
  }

  // 3. Heavy lists (Servers, Issues, Feed) — ONLY rebuild DOM when seq actually changed!
  if (!forceRender && seq === lastRenderedSeq) return;
  lastRenderedSeq = seq;

  const srvMeta = document.getElementById('live-servers-meta');
  const srvGrid = document.getElementById('live-servers-grid');
  if (srvMeta) {
    const activeOn = servers.filter(s => s.enabled).length;
    srvMeta.textContent = `${activeOn}/${servers.length} ON`;
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

  const prevTopIssueId = lastTopIssueId;
  const issuesEl = document.getElementById('live-issues-list');
  if (issuesEl) {
    if (!issues.length) {
      issuesEl.innerHTML = '<div class="live-empty">🟢 No issues recorded — all requests clean</div>';
      lastTopIssueId = 0;
    } else {
      issuesEl.innerHTML = issues.map(it => {
        const isNew = prevTopIssueId > 0 && it.id > prevTopIssueId;
        return `
        <div class="live-row is-issue${isNew ? ' is-new' : ''}">
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
      `;
      }).join('');
      lastTopIssueId = issues[0].id || lastTopIssueId;
    }
  }

  const prevTopFeedId = lastTopFeedId;
  const feedMeta = document.getElementById('live-feed-meta');
  const feedEl = document.getElementById('live-feed-list');
  if (feedMeta) feedMeta.textContent = `${feed.length} recent`;
  if (feedEl) {
    if (!feed.length) {
      feedEl.innerHTML = '<div class="live-empty">No completed requests yet — send a prompt to see live routing &amp; recovery</div>';
      lastTopFeedId = 0;
    } else {
      feedEl.innerHTML = feed.map(f => {
        const isOk = f.status === 'ok';
        const hasRec = !!(f.recovery_stage && f.recovery_stage.length > 0);
        const isNew = prevTopFeedId > 0 && f.id > prevTopFeedId;
        const rowCls = (!isOk ? 'live-row is-issue' : (hasRec ? 'live-row is-recovered' : 'live-row is-ok')) + (isNew ? ' is-new' : '');
        const badgeHtml = isOk
          ? '<span class="live-code-badge ok">200 OK</span>'
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
      lastTopFeedId = feed[0].id || lastTopFeedId;
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
      lastRenderedSeq = -1;
      lastCooldownSig = '';
      if (activeMainTab === 'live') fetchLiveSnapshot(true);
    }
  } catch (err) {
    showToast('Failed to clear live data', true);
  }
}

// Strictly stop Live polling whenever page is hidden, closed, or switched away
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopLivePolling();
  } else if (_shouldPollLive()) {
    startLivePolling();
  }
});

window.addEventListener('pagehide', stopLivePolling);
window.addEventListener('beforeunload', stopLivePolling);

// Initial state: Live polling is STOPPED until user explicitly opens the Live tab
stopLivePolling();
