let currentConfig = null;

function showToast(msg, isErr=false) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.innerText = msg;
  t.style.borderColor = isErr ? 'var(--danger)' : 'var(--brand)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

function maskKey(k) {
  if (!k || k.length <= 12) return k;
  return k.substring(0, 7) + '...' + k.substring(k.length - 4);
}

async function fetchStatus() {
  try {
    const res = await fetch('/status');
    if (res.ok) {
      const s = await res.json();
      const elServer = document.getElementById('active-server');
      const elModel = document.getElementById('active-model');
      const elAccount = document.getElementById('active-account');
      const elUpdated = document.getElementById('active-updated');
      if (elServer) elServer.innerText = s.server || 'None';
      if (elModel) elModel.innerText = s.model || 'None';
      if (elAccount) elAccount.innerText = s.account || '';
      if (elUpdated) elUpdated.innerText = s.last_updated?.split(' ')[1] || 'Live';
      const elMeterWrap = document.getElementById('active-meter-wrap');
      const elMeter = document.getElementById('active-speed-meter');
      if (elMeterWrap && elMeter) {
        const inT = s.input_tokens || 0;
        const outT = s.output_tokens || 0;
        const tps = s.tok_per_sec || 0;
        const ms = s.latency_ms || 0;
        if (inT > 0 || outT > 0 || ms > 0) {
          const parts = [];
          if (inT || outT) parts.push(`${inT}→${outT} tok`);
          if (tps > 0) parts.push(`⚡ ${tps} tok/s`);
          if (ms > 0) parts.push(`${(ms / 1000).toFixed(1)}s`);
          elMeter.innerText = parts.join(' • ');
          elMeterWrap.style.display = '';
        } else {
          elMeterWrap.style.display = 'none';
        }
      }
      if (typeof fetchLiveSnapshot === 'function') fetchLiveSnapshot(true);
      if (typeof syncMobileDashboardUI === 'function') syncMobileDashboardUI();
    }
  } catch(e) {}
}

async function loadConfig() {
  try {
    const res = await fetch('/api/ui/config');
    if (!res.ok) throw new Error();
    currentConfig = await res.json();
    
    // Ensure routed_providers and unrouted_providers exist
    if (!currentConfig.routed_providers) currentConfig.routed_providers = [];
    if (!currentConfig.unrouted_providers) {
      const all = Object.keys(currentConfig.providers || {});
      currentConfig.unrouted_providers = all.filter(k => !currentConfig.routed_providers.includes(k));
    }

    renderLanes();
    renderDropdown();
    renderRecoveryToggle();
    renderSignatureToggle();
    if (typeof syncMobileDashboardUI === 'function') syncMobileDashboardUI();
  } catch (err) {
    showToast('Config load failure', true);
  }
}

function renderRecoveryToggle() {
  const btn = document.getElementById('recovery-toggle-btn');
  if (!btn || !currentConfig) return;
  const isOn = currentConfig.auto_recovery !== false;
  btn.classList.toggle('is-on', isOn);
  btn.classList.toggle('is-off', !isOn);
  const lbl = btn.querySelector('.power-label');
  if (lbl) lbl.innerText = isOn ? 'Recovery: ON' : 'Recovery: OFF';
  btn.title = isOn
    ? 'Auto History Recovery ON — tap to turn OFF'
    : 'Auto History Recovery OFF — tap to turn ON';
}

function renderSignatureToggle() {
  const btn = document.getElementById('signature-toggle-btn');
  if (!btn || !currentConfig) return;
  const isOn = currentConfig.show_model_signature !== false;
  btn.classList.toggle('is-on', isOn);
  btn.classList.toggle('is-off', !isOn);
  const lbl = btn.querySelector('.power-label');
  if (lbl) lbl.innerText = isOn ? 'Tag with response: ON' : 'Tag with response: OFF';
  btn.title = isOn
    ? 'Tag with response ON — tap to turn OFF'
    : 'Tag with response OFF — tap to turn ON';
}

async function toggleModelSignature() {
  if (!currentConfig) return;
  const nextVal = (currentConfig.show_model_signature === false);
  try {
    const res = await fetch('/api/ui/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ show_model_signature: nextVal })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Settings update failed', true);
      return;
    }
    currentConfig = data.config;
    renderSignatureToggle();
    showToast(data.message || `Tag with response: ${nextVal ? 'ON' : 'OFF'}`);
  } catch (err) {
    showToast('Failed to update Tag with response setting', true);
  }
}

async function toggleAutoRecovery() {
  if (!currentConfig) return;
  const nextVal = (currentConfig.auto_recovery === false);
  try {
    const res = await fetch('/api/ui/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_recovery: nextVal })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Settings update failed', true);
      return;
    }
    currentConfig = data.config;
    renderRecoveryToggle();
    showToast(data.message || `Auto-Recovery: ${nextVal ? 'ON' : 'OFF'}`);
  } catch (err) {
    showToast('Failed to update Auto-Recovery', true);
  }
}

function renderAutoStartToggle() {
  const drw = document.getElementById('drawer-switch-autostart');
  if (!drw || !currentConfig) return;
  const isOn = currentConfig.auto_start !== false;
  drw.classList.toggle('is-on', isOn);
}

async function toggleAutoStart() {
  if (!currentConfig) return;
  const nextVal = (currentConfig.auto_start === false);
  try {
    const res = await fetch('/api/ui/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_start: nextVal })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Settings update failed', true);
      return;
    }
    currentConfig = data.config;
    renderAutoStartToggle();
    showToast(data.message || `Auto-Start on Launch: ${nextVal ? 'ON' : 'OFF'}`);
  } catch (err) {
    showToast('Failed to update Auto-Start setting', true);
  }
}

function closeUpdateModal() {
  const modal = document.getElementById('update-modal');
  if (modal) modal.style.display = 'none';
}

let commitHistoryPage = 1;
let commitHistoryLoading = false;
let commitHistoryHasMore = true;

function setupCommitInfiniteScroll() {
  const container = document.getElementById('commit-scroll-container');
  if (!container) return;
  container.onscroll = () => {
    if (commitHistoryLoading || !commitHistoryHasMore) return;
    if (container.scrollTop + container.clientHeight >= container.scrollHeight - 30) {
      loadNextCommitsPage();
    }
  };
}

async function loadNextCommitsPage() {
  if (commitHistoryLoading || !commitHistoryHasMore) return;
  commitHistoryLoading = true;
  const listEl = document.getElementById('commit-history-list');
  const spinner = document.getElementById('commit-loading-indicator');
  if (spinner) spinner.style.display = 'block';

  try {
    const res = await fetch(`/api/ui/commits?page=${commitHistoryPage}&per_page=8`);
    const data = await res.json();
    if (!res.ok || data.status !== 'ok' || !data.commits || data.commits.length === 0) {
      commitHistoryHasMore = false;
      if (spinner) {
        spinner.textContent = 'End of commit history';
        spinner.style.color = '#8b949e';
      }
      return;
    }

    commitHistoryPage++;
    if (spinner) spinner.style.display = 'none';

    data.commits.forEach(c => {
      const item = document.createElement('div');
      item.style.cssText = 'padding:7px 0; border-bottom:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:flex-start; gap:8px; font-size:11.5px;';
      const dateText = c.date ? new Date(c.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
      item.innerHTML = `
        <div style="flex:1; min-width:0;">
          <div style="color:#e6edf3; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${c.title || ''}">${c.title || 'Commit'}</div>
          <div style="color:#8b949e; font-size:10px; margin-top:1px;">by ${c.author || 'dev'} ${dateText ? '• ' + dateText : ''}</div>
        </div>
        <a href="${c.url}" target="_blank" rel="noopener noreferrer" style="font-family:monospace; font-size:10.5px; color:#58a6ff; text-decoration:none; padding:2px 5px; border-radius:4px; background:rgba(56,139,253,0.1); border:1px solid rgba(56,139,253,0.25); flex-shrink:0;">
          ${c.sha}
        </a>
      `;
      if (listEl) listEl.appendChild(item);
    });
  } catch (err) {
    if (spinner) {
      spinner.textContent = 'Could not load older commits';
      spinner.style.color = '#f85149';
    }
  } finally {
    commitHistoryLoading = false;
  }
}

async function checkAppUpdate(showModal = false) {
  const modal = document.getElementById('update-modal');
  const body = document.getElementById('update-modal-body');
  const acts = document.getElementById('update-modal-actions');
  const tag = document.getElementById('drawer-version-tag');

  if (showModal && modal) {
    modal.style.display = 'flex';
    if (body) body.innerHTML = '<div style="padding:14px 0;text-align:center;color:#8b949e;">📡 Connecting to GitHub to check updates...</div>';
    if (acts) acts.innerHTML = '<button type="button" class="btn btn-xs" onclick="closeUpdateModal()">Cancel</button>';
  }

  try {
    const res = await fetch('/api/ui/version-check');
    const data = await res.json();
    if (!res.ok || data.status !== 'ok') {
      if (showModal && body) {
        body.innerHTML = `<div style="color:#f85149;">❌ Failed to check updates: ${data.message || 'Unknown error'}</div>`;
      }
      return;
    }

    if (tag && data.current_version) {
      tag.textContent = data.current_version;
    }

    if (showModal && body && acts) {
      commitHistoryPage = 1;
      commitHistoryLoading = false;
      commitHistoryHasMore = true;

      const commitCardHtml = `
        <div style="margin-top:12px; background:#0d1117; border:1px solid #30363d; border-radius:8px; overflow:hidden;">
          <div style="padding:7px 10px; background:#161b22; border-bottom:1px solid #30363d; font-size:11px; font-weight:700; color:#8b949e; letter-spacing:0.3px; display:flex; justify-content:space-between; align-items:center;">
            <span>📜 RECENT UPDATES & COMMITS</span>
            <span style="font-size:10px; color:#58a6ff;">Scroll for more ↓</span>
          </div>
          <div id="commit-scroll-container" style="max-height:165px; overflow-y:auto; padding:0 10px;">
            <div id="commit-history-list"></div>
            <div id="commit-loading-indicator" style="padding:8px 0; text-align:center; font-size:11px; color:#58a6ff;">Loading commits...</div>
          </div>
        </div>
      `;

      if (data.update_available) {
        body.innerHTML = `
          <div style="background:rgba(56,139,253,0.1); border:1px solid rgba(56,139,253,0.3); border-radius:8px; padding:12px;">
            <div style="font-size:14px; font-weight:700; color:#58a6ff; margin-bottom:4px;">✨ New Version Available!</div>
            <div style="font-size:12px; color:#c9d1d9;">Installed: <code>${data.current_version}</code> ➔ Latest: <b style="color:#3fb950;">${data.latest_version}</b></div>
            ${data.latest_commit ? `<div style="font-size:11.5px; color:#8b949e; margin-top:5px;">Latest Commit: <code>${data.latest_commit}</code></div>` : ''}
          </div>
          ${commitCardHtml}
          <p style="font-size:11.5px; color:#8b949e; margin:10px 0 0;">Updating will pull the latest code, keep your keys/configs untouched, and reload C-Router.</p>
        `;
        acts.innerHTML = `
          <button type="button" class="btn btn-xs" onclick="closeUpdateModal()">Later</button>
          <button type="button" class="btn btn-xs btn-primary" onclick="triggerUpdateApply(false)" style="background:#238636; border-color:#2ea043; font-weight:700;">⚡ Update Now</button>
        `;
      } else {
        body.innerHTML = `
          <div style="background:rgba(35,134,54,0.1); border:1px solid rgba(46,160,67,0.3); border-radius:8px; padding:12px;">
            <div style="font-size:13.5px; font-weight:700; color:#3fb950; margin-bottom:4px;">✅ You are up to date!</div>
            <div style="font-size:12px; color:#c9d1d9;">Current Version: <b>${data.current_version}</b></div>
            ${data.latest_commit ? `<div style="font-size:11px; color:#8b949e; margin-top:4px;">Latest Commit: <code>${data.latest_commit}</code></div>` : ''}
          </div>
          ${commitCardHtml}
          <p style="font-size:11.5px; color:#8b949e; margin:10px 0 0;">You already have the newest version of C-Router. You can still reinstall/force-update anytime to refresh files.</p>
        `;
        acts.innerHTML = `
          <button type="button" class="btn btn-xs" onclick="closeUpdateModal()">Done</button>
          <button type="button" class="btn btn-xs" onclick="triggerUpdateApply(true)" title="Force sync latest files from GitHub" style="border-color:#388bfd; color:#58a6ff; background:rgba(56,139,253,0.1);">🔄 Force Update / Refresh</button>
        `;
      }

      setupCommitInfiniteScroll();
      loadNextCommitsPage();
    }
  } catch (err) {
    if (showModal && body) {
      body.innerHTML = `<div style="color:#f85149;">❌ Network error checking updates: ${err.message}</div>`;
    }
  }
}

async function triggerUpdateApply(force = false) {
  const body = document.getElementById('update-modal-body');
  const acts = document.getElementById('update-modal-actions');
  if (body) {
    body.innerHTML = '<div style="padding:14px 0;text-align:center;color:#58a6ff;"><div style="font-size:24px;margin-bottom:6px;">⚡</div>Downloading and applying update from GitHub...<br><span style="font-size:11px;color:#8b949e;">Your keys and configs are preserved safely.</span></div>';
  }
  if (acts) acts.innerHTML = '';

  try {
    const res = await fetch('/api/ui/update-apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force })
    });
    const data = await res.json();
    if (!res.ok || data.status !== 'ok') {
      if (body) body.innerHTML = `<div style="color:#f85149;">❌ Update failed: ${data.message || 'Unknown error'}</div>`;
      if (acts) acts.innerHTML = '<button type="button" class="btn btn-xs" onclick="closeUpdateModal()">Close</button>';
      return;
    }

    if (body) {
      body.innerHTML = '<div style="padding:14px 0;text-align:center;color:#3fb950;"><div style="font-size:28px;margin-bottom:6px;">🎉</div><b>Update applied successfully!</b><br><span style="font-size:12px;color:#c9d1d9;">Restarting C-Router gateway... reloading page in 2s.</span></div>';
    }
    setTimeout(() => {
      window.location.reload();
    }, 2500);
  } catch (err) {
    if (body) body.innerHTML = `<div style="color:#f85149;">❌ Error applying update: ${err.message}</div>`;
    if (acts) acts.innerHTML = '<button type="button" class="btn btn-xs" onclick="closeUpdateModal()">Close</button>';
  }
}

function openUninstallModal() {
  const modal = document.getElementById('uninstall-modal');
  const step1 = document.getElementById('uninstall-step-1');
  const step2 = document.getElementById('uninstall-step-2');
  const btn = document.getElementById('confirm-uninstall-btn');
  if (!modal) return;
  if (step1) step1.style.display = 'block';
  if (step2) step2.style.display = 'none';
  if (btn) {
    btn.disabled = false;
    btn.textContent = '🗑️ Yes, Permanently Uninstall';
  }
  modal.style.display = 'flex';
}

function closeUninstallModal() {
  const modal = document.getElementById('uninstall-modal');
  if (modal) modal.style.display = 'none';
}

function advanceUninstallStep() {
  const step1 = document.getElementById('uninstall-step-1');
  const step2 = document.getElementById('uninstall-step-2');
  if (step1) step1.style.display = 'none';
  if (step2) step2.style.display = 'block';
}

async function confirmFullUninstall() {
  const btn = document.getElementById('confirm-uninstall-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Uninstalling...';
  }
  try {
    const res = await fetch('/api/ui/uninstall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Uninstall failed', true);
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🗑️ Yes, Permanently Uninstall';
      }
      return;
    }
    closeUninstallModal();
    document.body.innerHTML = '<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;padding:24px;text-align:center;"><div style="font-size:36px;margin-bottom:12px;">✅</div><h2 style="margin:0 0 8px;color:#f0f6fc;">C-Router Uninstalled</h2><p style="margin:0;color:#8b949e;font-size:14px;max-width:340px;line-height:1.5;">Proxy stopped, Auto-Start removed, and all C-Router files have been deleted. You can close this tab.</p></div>';
  } catch (err) {
    showToast('Failed to trigger uninstall', true);
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🗑️ Yes, Permanently Uninstall';
    }
  }
}

function renderDropdown() {
  const sel = document.getElementById('provider-select');
  if (!sel) return;
  sel.innerHTML = '';
  if (!currentConfig?.providers) return;
  for (const [id, p] of Object.entries(currentConfig.providers)) {
    const opt = document.createElement('option');
    opt.value = id;
    opt.innerText = p.name || id;
    sel.appendChild(opt);
  }
}

function renderLanes() {
  const cRouted = document.getElementById('container-routed');
  const cUnrouted = document.getElementById('container-unrouted');
  if (!cRouted || !cUnrouted) return;

  // Preserve expanded server cards across re-renders
  const expandedIds = new Set(
    Array.from(document.querySelectorAll('.server-card.expanded')).map(c => c.dataset.providerId)
  );

  cRouted.innerHTML = '';
  cUnrouted.innerHTML = '';

  const providers = currentConfig.providers || {};
  const allKeys = Object.keys(providers);

  let routed = currentConfig.routed_providers || [];
  let unrouted = currentConfig.unrouted_providers || [];

  // Clean missing or duplicated keys
  routed = routed.filter(k => providers[k]);
  unrouted = unrouted.filter(k => providers[k] && !routed.includes(k));

  // Any missing providers go to unrouted
  allKeys.forEach(k => {
    if (!routed.includes(k) && !unrouted.includes(k)) unrouted.push(k);
  });

  if (routed.length === 0) {
    cRouted.innerHTML = '<div class="lane-empty">Drag servers here or tap ⚡ to activate failover pipeline</div>';
  } else {
    routed.forEach((id, idx) => {
      const card = createServerCard(id, providers[id], true, idx);
      if (expandedIds.has(id)) card.classList.add('expanded');
      cRouted.appendChild(card);
    });
  }

  if (unrouted.length === 0) {
    cUnrouted.innerHTML = '<div class="lane-empty">All servers are currently active in pipeline</div>';
  } else {
    unrouted.forEach((id, idx) => {
      const card = createServerCard(id, providers[id], false, idx);
      if (expandedIds.has(id)) card.classList.add('expanded');
      cUnrouted.appendChild(card);
    });
  }

  setupContainerDragListeners(cRouted);
  setupContainerDragListeners(cUnrouted);
  updatePriorityBadges();
  if (typeof renderTeamsLane === 'function') renderTeamsLane();
}

async function toggleServerMode(pId) {
  try {
    const res = await fetch('/api/ui/provider-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId })
    });
    const data = await res.json();
    if (res.ok) {
      currentConfig = data.config;
      renderLanes();
      showToast(data.message || `Mode updated for ${pId}`);
    } else {
      showToast(data.message || 'Mode switch failed', true);
    }
  } catch (e) {
    showToast(`Failed to switch mode: ${e.message}`, true);
  }
}

function createServerCard(id, p, isRouted, index) {
  const isEnabled = p.enabled !== false;
  const card = document.createElement('div');
  card.className = `server-card${isEnabled ? '' : ' server-off'}`;
  card.id = `server-card-${id}`;
  card.dataset.providerId = id;
  card.draggable = true;

  // Mouse HTML5 Drag Events
  card.ondragstart = (e) => {
    card.classList.add('is-dragging');
    e.dataTransfer.setData('text/plain', id);
    e.dataTransfer.effectAllowed = 'move';
  };
  card.ondragend = () => {
    card.classList.remove('is-dragging');
    saveDomOrderAndSync();
  };

  // Header Line (2-Row Mobile-First Layout)
  const top = document.createElement('div');
  top.className = 'server-card-top';
  const sMode = (p.mode || 'agentic').toLowerCase();
  const modeBadgeHtml = sMode === 'normal'
    ? `<span class="server-mode-badge is-normal" style="cursor:pointer;" title="Normal Mode (Saves tokens): Tap to switch to ⚡ Agentic" onclick="event.stopPropagation(); toggleServerMode('${id}')">💬 normal</span>`
    : `<span class="server-mode-badge is-agentic" style="cursor:pointer;" title="Agentic Mode (Full tools): Tap to switch to 💡 Normal" onclick="event.stopPropagation(); toggleServerMode('${id}')">⚡ agentic</span>`;
  const hasCustomPrompt = !!(p.custom_prompt && p.custom_prompt.trim());
  const promptBadgeHtml = hasCustomPrompt
    ? `<span class="server-prompt-badge" title="Custom System Prompt Active">📝 prompt</span>`
    : '';
  const rl = p.rate_limit || {};
  let rateBadgeHtml = '';
  if (rl.rpm || rl.max_requests) {
    const parts = [];
    if (rl.rpm) parts.push(`${rl.rpm} RPM`);
    if (rl.max_requests) parts.push(`${rl.max_requests}/${rl.window_hours || 1}h`);
    rateBadgeHtml = `<span class="quota-badge" id="quota-badge-${id}" style="font-size:9.5px; font-family:var(--mono); color:#d2a8ff; background:#1b152b; padding:1px 5px; border-radius:3px; border:1px solid #58338f;" title="Configured Quota: ${parts.join(' • ')}">⚡ ${parts.join(' | ')}</span>`;
  }
  const allModels = p.models || [];
  const defModel = p.default_model || allModels[0] || '';
  const fastSwitchHtml = allModels.length > 0
    ? `<select class="fast-model-select" title="Fast switch default model" onclick="event.stopPropagation()" onchange="fastSwitchModel('${id}', this.value)">${allModels.map(m => `<option value="${m.replace(/"/g, '&quot;')}" ${m === defModel ? 'selected' : ''}>${m}</option>`).join('')}</select>`
    : '';

  top.innerHTML = `
    <!-- Row 1: Drag handle, Priority Badge, Server Name, Protocol, Mode, ON/OFF Toggle, and Expand Arrow -->
    <div class="server-card-header-row" onclick="toggleServerCard('${id}')">
      <div class="server-card-title-group">
        <span class="drag-handle" onclick="event.stopPropagation()" title="Touch & hold or drag to reorder">⠿</span>
        <span class="priority-badge-slot"></span>
        <span class="server-name" title="${p.name || id}">${p.name || id}</span>
        <span class="server-proto">${p.type || 'anthropic'}</span>
        ${modeBadgeHtml}
        ${promptBadgeHtml}
        ${rateBadgeHtml}
      </div>
      <div class="server-header-right" onclick="event.stopPropagation()">
        <button type="button" class="power-toggle ${isEnabled ? 'is-on' : 'is-off'}" id="power-btn-${id}" title="${isEnabled ? 'Server ON — tap to turn OFF' : 'Server OFF — tap to turn ON'}" onclick="toggleServerPower('${id}')">
          <span class="power-dot"></span>
          <span class="power-label">${isEnabled ? 'ON' : 'OFF'}</span>
        </button>
        <button type="button" class="mobile-card-sheet-btn" title="Quick Actions" onclick="openServerBottomSheet('${id}')">⋯</button>
        <span class="toggle-arrow" onclick="toggleServerCard('${id}')">▶</span>
      </div>
    </div>

    <!-- Row 2: Route Pill + Fast Model Switcher + Reorder/Route Buttons + Safe Delete Button -->
    <div class="server-card-controls-row">
      <div class="server-card-left-tags">
        <span style="font-size:10px; font-family:var(--mono); color:#79c0ff; background:#162438; padding:2px 6px; border-radius:4px; border:1px solid #1f4277; cursor:pointer; display:inline-flex; align-items:center; gap:3px;" title="Click to copy direct route URL" onclick="event.stopPropagation(); copyDirectRoute('${id}')">
          📋 /${id}
        </span>
        ${fastSwitchHtml}
      </div>
      <div class="server-card-btn-group" onclick="event.stopPropagation()">
        <button class="btn-reorder btn-up" title="Move Up (Higher Priority)" onclick="moveCardUp('${id}')">▲</button>
        <button class="btn-reorder btn-down" title="Move Down (Lower Priority)" onclick="moveCardDown('${id}')">▼</button>
        <button class="btn btn-xs btn-lane-toggle" onclick="moveLaneQuick('${id}')">
          ${isRouted ? '💤 Standby' : '⚡ Route'}
        </button>
        <button class="btn btn-xs" title="Edit Server" onclick="openServerModal('${id}')">✏️ Edit</button>
        <button class="safe-delete-btn" title="Delete Server" onclick="openConfirmDelete('${id}')">🗑️</button>
      </div>
    </div>
  `;
  card.appendChild(top);

  // Collapsible Body
  const body = document.createElement('div');
  body.className = 'server-card-body';
  body.onclick = (e) => e.stopPropagation();

  // Models Section
  const mSec = document.createElement('div');
  mSec.innerHTML = `
    <div class="section-label">
      <span>MODELS (${(p.models || []).length})</span>
      <div style="display:flex; gap:4px;">
        <button class="btn btn-xs" onclick="openModelsSelector('${id}')">Select</button>
        <button class="btn btn-xs" id="ping-btn-${id}" onclick="testModels('${id}')">Ping</button>
      </div>
    </div>
  `;
  const chips = document.createElement('div');
  chips.className = 'chips-box';
  (p.models || []).forEach(m => {
    const isDef = m === p.default_model;
    const chip = document.createElement('span');
    chip.className = `chip ${isDef ? 'is-def' : ''}`;
    chip.title = 'Hold to copy & set as default';
    chip.innerHTML = `
      <span class="chip-label">${m}</span>
      <span class="chip-status" id="chip-status-${id}-${m}"></span>
      <span class="chip-x" title="Remove" onclick="openConfirmDeleteModel('${id}', '${m}')">✕</span>
    `;
    attachModelChipLongPress(chip, id, m);
    chips.appendChild(chip);
  });
  mSec.appendChild(chips);

  const pingBox = document.createElement('div');
  pingBox.id = `ping-${id}`;
  pingBox.className = 'ping-summary';
  mSec.appendChild(pingBox);
  body.appendChild(mSec);

  // Keys Section
  const kSec = document.createElement('div');
  kSec.innerHTML = `
    <div class="section-label">
      <span>KEYS (${(p.keys || []).length})</span>
      <div style="display:flex; gap:4px;">
        <button class="btn btn-xs" id="key-ping-btn-${id}" onclick="testKeys('${id}')">Test</button>
      </div>
    </div>
  `;
  const kList = document.createElement('div');
  kList.className = 'keys-compact-list';
  kList.style.cssText = 'max-height: 235px; overflow-y: auto; padding-right: 3px; scrollbar-width: thin;';
  (p.keys || []).forEach((k, idx) => {
    const row = document.createElement('div');
    row.className = 'key-line';
    row.style.cssText = 'display:flex; flex-direction:column; gap:6px; padding:7px 9px; align-items:stretch;';
    const keyName = (p.key_names && p.key_names[k]) ? p.key_names[k] : '';
    const nameBadge = keyName
      ? `<span style="color:#ffd166; font-weight:600; font-size:11px; background:rgba(255,209,102,0.1); border:1px solid rgba(255,209,102,0.28); padding:1px 6px; border-radius:4px;">🏷️ ${keyName.replace(/</g,'&lt;')}</span>`
      : '';
    const btnStyle = 'cursor:pointer; padding:2px 6px; border-radius:4px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); font-size:10.5px; display:inline-flex; align-items:center; gap:3px;';
    row.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; flex-wrap:wrap;">
        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; min-width:0;">
          <span style="color:#8b949e; font-size:10px; font-weight:600;">#${idx+1}</span>
          ${nameBadge}
          <span id="key-val-${id}-${idx}" style="color:#79c0ff; font-family:monospace; font-size:10.5px; word-break:break-all;" data-masked="1">${maskKey(k)}</span>
        </div>
        <span class="key-status" id="key-status-${id}-${idx}"></span>
      </div>
      <div style="display:flex; align-items:center; justify-content:space-between; gap:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.05);">
        <div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
          <span style="${btnStyle} color:#79c0ff;" title="Show/Hide Key" onclick="event.stopPropagation(); toggleShowKey('${id}', ${idx})">👁️ Show</span>
          <span style="${btnStyle} color:#79c0ff;" title="Copy Key" onclick="event.stopPropagation(); copySingleKey('${id}', ${idx})">📋 Copy</span>
          <span style="${btnStyle} color:#56d364;" title="Test Key" onclick="event.stopPropagation(); testSingleKey('${id}', ${idx})">⚡ Test</span>
          <span style="${btnStyle} color:#ffd166;" title="Rename Key" onclick="event.stopPropagation(); openRenameKeyModal('${id}', ${idx})">✏️ Name</span>
        </div>
        <div style="display:flex; align-items:center; gap:4px; flex-shrink:0;">
          ${idx > 0 ? `<span style="${btnStyle} color:#8b949e;" title="Move Up" onclick="event.stopPropagation(); moveKeyPriority('${id}', ${idx}, 'up')">▲</span>` : ''}
          ${idx < (p.keys.length - 1) ? `<span style="${btnStyle} color:#8b949e;" title="Move Down" onclick="event.stopPropagation(); moveKeyPriority('${id}', ${idx}, 'down')">▼</span>` : ''}
          <span style="${btnStyle} color:#f85149; border-color:rgba(248,81,73,0.25);" title="Revoke Key" onclick="event.stopPropagation(); openConfirmDeleteKey('${id}', ${idx})">✕</span>
        </div>
      </div>
    `;
    kList.appendChild(row);
  });
  if (!p.keys || p.keys.length === 0) {
    kList.innerHTML = '<span style="font-size:10px; color:var(--text-muted);">No keys</span>';
  }
  kSec.appendChild(kList);

  const keyPingBox = document.createElement('div');
  keyPingBox.id = `key-ping-${id}`;
  keyPingBox.className = 'ping-summary';
  kSec.appendChild(keyPingBox);
  body.appendChild(kSec);

  card.appendChild(body);

  // Attach Touch Drag & Drop handler to the drag handle
  const handle = top.querySelector('.drag-handle');
  if (handle) setupCardTouchDrag(handle, card);

  return card;
}

function copyDirectRoute(id) {
  const url = `${window.location.origin}/${id}`;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => {
      showToast(`Copied route URL: /${id}`);
    }).catch(() => {
      showToast(`Direct Route: /${id}`);
    });
  } else {
    showToast(`Direct Route: /${id}`);
  }
}

async function toggleServerPower(id) {
  if (!currentConfig?.providers?.[id]) return;
  const p = currentConfig.providers[id];
  const nextEnabled = (p.enabled === false);

  try {
    const res = await fetch('/api/ui/provider-toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: id, enabled: nextEnabled })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Toggle failed', true);
      return;
    }
    currentConfig = data.config;

    const card = document.getElementById(`server-card-${id}`);
    const btn = document.getElementById(`power-btn-${id}`);
    if (card) card.classList.toggle('server-off', !nextEnabled);
    if (btn) {
      btn.classList.toggle('is-on', nextEnabled);
      btn.classList.toggle('is-off', !nextEnabled);
      btn.title = nextEnabled ? 'Server ON — tap to turn OFF' : 'Server OFF — tap to turn ON';
      const lbl = btn.querySelector('.power-label');
      if (lbl) lbl.innerText = nextEnabled ? 'ON' : 'OFF';
    }
    updatePriorityBadges();
    showToast(data.message || `${p.name || id}: ${nextEnabled ? 'ON' : 'OFF'}`);
  } catch (err) {
    showToast('Failed to toggle server', true);
  }
}

function toggleServerCard(id) {
  const card = document.getElementById(`server-card-${id}`);
  if (!card) return;
  const isExpanded = card.classList.contains('expanded');
  document.querySelectorAll('.server-card.expanded').forEach(c => c.classList.remove('expanded'));
  if (!isExpanded) card.classList.add('expanded');
}

// Collapse expanded server card only when clicking outside all cards & modals
document.addEventListener('click', (e) => {
  if (e.target.closest('.server-card') || e.target.closest('.modal-overlay') || e.target.closest('.modal') || e.target.closest('.bottom-sheet') || e.target.closest('#toast')) {
    return;
  }
  document.querySelectorAll('.server-card.expanded').forEach(c => c.classList.remove('expanded'));
});

async function addKey(e) {
  e.preventDefault();
  const pId = document.getElementById('provider-select').value;
  const input = document.getElementById('new-key-val');
  const nameInput = document.getElementById('new-key-name');
  const val = input.value.trim();
  const keyName = nameInput ? nameInput.value.trim() : '';
  if (!val) return;
  const res = await fetch('/api/ui/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, key: val, name: keyName })
  });
  const data = await res.json();
  if (res.ok) {
    showToast(keyName ? `Key '${keyName}' added` : 'Key added');
    input.value = '';
    if (nameInput) nameInput.value = '';
    currentConfig = data.config;
    renderLanes();
  } else {
    showToast(data.message || 'Failed to add key', true);
  }
}

function toggleShowKey(pId, idx) {
  const el = document.getElementById(`key-val-${pId}-${idx}`);
  const k = currentConfig?.providers?.[pId]?.keys?.[idx];
  if (!el || !k) return;
  if (el.getAttribute('data-masked') === '1') {
    el.innerText = k;
    el.setAttribute('data-masked', '0');
  } else {
    el.innerText = maskKey(k);
    el.setAttribute('data-masked', '1');
  }
}

function copySingleKey(pId, idx) {
  const k = currentConfig?.providers?.[pId]?.keys?.[idx];
  if (!k) return;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(k).then(() => showToast('API Key copied!')).catch(() => showToast('Copy failed', true));
  } else {
    showToast('Clipboard not available', true);
  }
}

async function moveKeyPriority(pId, idx, direction) {
  try {
    const res = await fetch('/api/ui/keys/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, index: idx, direction })
    });
    const data = await res.json();
    if (res.ok) {
      currentConfig = data.config;
      renderLanes();
      showToast('Key priority updated');
    }
  } catch (e) {
    showToast('Failed to reorder key', true);
  }
}

async function testSingleKey(pId, idx) {
  const statusEl = document.getElementById(`key-status-${pId}-${idx}`);
  if (statusEl) {
    statusEl.innerHTML = '<span style="color:#79c0ff; font-size:10px;">⏳ Testing...</span>';
  }
  try {
    const res = await fetch('/api/ui/keys/test-single', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, index: idx })
    });
    const data = await res.json();
    if (statusEl) {
      if (data.alive) {
        statusEl.innerHTML = `<span style="color:#56d364; font-size:10px;">✅ ${data.latency_ms}ms</span>`;
      } else {
        statusEl.innerHTML = `<span style="color:#f85149; font-size:10px;">❌ ${data.message}</span>`;
      }
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = '<span style="color:#f85149; font-size:10px;">❌ Error</span>';
  }
}

function openRenameKeyModal(pId, idx) {
  const p = currentConfig?.providers?.[pId];
  const k = p?.keys?.[idx];
  if (!k) return;
  const curName = (p.key_names && p.key_names[k]) ? p.key_names[k] : '';
  if (typeof openConfirmModal === 'function') {
    openConfirmModal(
      'Rename API Key',
      `<div style="margin-bottom:8px; font-size:11.5px; color:#8b949e;">Key #${idx+1}: <code>${maskKey(k)}</code></div>
       <input type="text" id="rename-key-input" value="${curName.replace(/"/g, '&quot;')}" placeholder="Enter key name (e.g. Personal, Work)" style="width:100%; padding:8px 10px; border-radius:6px; background:#0d1117; border:1px solid #30363d; color:#e6edf3; font-size:12px;" />`,
      'Save Name',
      async () => {
        const newName = document.getElementById('rename-key-input')?.value?.trim() || '';
        const res = await fetch('/api/ui/keys/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: pId, index: idx, name: newName })
        });
        const data = await res.json();
        if (res.ok) {
          currentConfig = data.config;
          renderLanes();
          showToast(newName ? `Renamed to '${newName}'` : 'Key name cleared');
        }
      }
    );
    setTimeout(() => document.getElementById('rename-key-input')?.focus(), 100);
  }
}

async function executeDeleteKey(pId, index) {
  const res = await fetch('/api/ui/keys', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, index })
  });
  const data = await res.json();
  if (res.ok) {
    showToast('Key deleted');
    currentConfig = data.config;
    renderLanes();
  }
}

function deleteKey(pId, index) {
  openConfirmDeleteKey(pId, index);
}

loadConfig();
fetchStatus();
setInterval(() => {
  if (!document.hidden && (typeof activeMainTab === 'undefined' || activeMainTab === 'console')) {
    fetchStatus();
  }
}, 5000);
