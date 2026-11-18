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

async function fastSwitchModel(pId, modelName) {
  if (!modelName) return;
  try {
    const res = await fetch('/api/ui/provider-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, action: 'set_default', model: modelName })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Default switched: ${modelName}`);
      currentConfig = data.config;
      renderLanes();
      renderDropdown();
    }
  } catch (err) {
    showToast('Failed to switch model', true);
  }
}

async function setDefaultModel(pId, modelName) {
  try {
    // Copy model name to clipboard immediately
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(modelName);
    }
  } catch (err) {
    // Fallback if clipboard API blocked
    try {
      const ta = document.createElement('textarea');
      ta.value = modelName;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    } catch (e) {}
  }

  showToast(`Copied & Set Default: ${modelName}`);

  try {
    const res = await fetch('/api/ui/provider-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, action: 'set_default', model: modelName })
    });
    const data = await res.json();
    if (res.ok) {
      currentConfig = data.config;
      renderLanes();
      renderDropdown();
    }
  } catch (err) {
    showToast('Failed to set default model', true);
  }
}

function attachModelChipLongPress(chip, pId, modelName) {
  let pressTimer = null;
  let didLongPress = false;
  let startX = 0;
  let startY = 0;

  const cancel = () => {
    if (pressTimer) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
    chip.classList.remove('chip-pressing');
  };

  const start = (e) => {
    // If clicked on delete X, don't trigger long-press
    if (e.target.closest('.chip-x')) return;
    didLongPress = false;
    cancel();
    if (e.touches && e.touches[0]) {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }
    chip.classList.add('chip-pressing');
    pressTimer = setTimeout(() => {
      didLongPress = true;
      cancel();
      // Visual feedback
      if (navigator.vibrate) {
        try { navigator.vibrate(40); } catch(v){}
      }
      setDefaultModel(pId, modelName);
    }, 550);
  };

  chip.addEventListener('touchstart', start, { passive: true });
  chip.addEventListener('touchmove', (e) => {
    if (e.touches && e.touches[0]) {
      const dx = Math.abs(e.touches[0].clientX - startX);
      const dy = Math.abs(e.touches[0].clientY - startY);
      if (dx > 10 || dy > 10) cancel();
    }
  }, { passive: true });
  chip.addEventListener('touchend', (e) => {
    cancel();
  });
  chip.addEventListener('touchcancel', cancel);

  chip.addEventListener('mousedown', (e) => {
    if (e.button === 0) start(e);
  });
  chip.addEventListener('mousemove', (e) => {
    if (pressTimer && (Math.abs(e.movementX) > 4 || Math.abs(e.movementY) > 4)) cancel();
  });
  chip.addEventListener('mouseup', cancel);
  chip.addEventListener('mouseleave', cancel);
  chip.addEventListener('contextmenu', (e) => {
    // Suppress context menu on model chip
    e.preventDefault();
  });
}

function renderLanes() {
  const cRouted = document.getElementById('container-routed');
  const cUnrouted = document.getElementById('container-unrouted');
  if (!cRouted || !cUnrouted) return;
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
      cRouted.appendChild(createServerCard(id, providers[id], true, idx));
    });
  }

  if (unrouted.length === 0) {
    cUnrouted.innerHTML = '<div class="lane-empty">All servers are currently active in pipeline</div>';
  } else {
    unrouted.forEach((id, idx) => {
      cUnrouted.appendChild(createServerCard(id, providers[id], false, idx));
    });
  }

  setupContainerDragListeners(cRouted);
  setupContainerDragListeners(cUnrouted);
  updatePriorityBadges();
  renderTeamsLane();
}

function renderTeamsLane() {
  const cTeams = document.getElementById('container-multiagent');
  const countEl = document.getElementById('count-multiagent');
  if (!cTeams) return;
  cTeams.innerHTML = '';
  const teams = currentConfig.multi_agent_teams || {};
  const teamList = Object.values(teams);
  if (countEl) countEl.innerText = `${teamList.length} Teams`;

  if (teamList.length === 0) {
    cTeams.innerHTML = '<div class="lane-empty">No mix teams yet — tap + Add to build your first Multi-Agent orchestra</div>';
    return;
  }

  teamList.forEach(t => {
    const card = document.createElement('div');
    const isEn = t.enabled !== false;
    card.className = `server-card${isEn ? '' : ' server-off'}`;
    card.id = `team-card-${t.id}`;

    const membersHtml = (t.members || []).map((m, idx) => {
      const pObj = currentConfig.providers?.[m.provider] || {};
      const pName = pObj.name || m.provider;
      const mName = (m.model || '').split('/').pop();
      const role = m.role || `step_${idx+1}`;
      const mMode = m.mode || (idx === 0 ? 'normal' : 'agentic');
      const modeIcon = mMode === 'agentic' ? '⚡' : '💡';
      const modeColor = mMode === 'agentic' ? '#79c0ff' : '#f2cc60';
      const cached = (typeof _getCachedModelStatus === 'function') ? _getCachedModelStatus(m.provider, m.model) : null;
      const initialStatus = cached ? (cached.state === 'ok' ? '🟢' : '🔴') : '';
      const initialTitle = cached ? (cached.status || '') : '';
      return `<span class="chip" style="font-size:10px;"><strong style="color:#d2a8ff;">${role}:</strong> ${pName} (${mName}) <span class="chip-status" id="team-member-status-${t.id}-${idx}" title="${initialTitle}">${initialStatus}</span><span style="font-size:9.5px; color:${modeColor};" title="Engine Mode: ${mMode}">${modeIcon}</span></span>`;
    }).join(' ');

    card.innerHTML = `
      <div class="server-card-top" style="cursor:default;">
        <div class="server-card-header-row">
          <div class="server-card-title-group">
            <span class="prio-tag" style="background:rgba(137, 87, 229, 0.25); color:#d2a8ff; border:1px solid rgba(137, 87, 229, 0.6);">TEAM</span>
            <span class="server-name" style="color:#fff;">${t.name || t.id}</span>
            <span class="server-proto" style="background:#241b35; color:#d2a8ff; border-color:#8957e555;">${t.workflow || 'pipeline'}</span>
          </div>
          <div class="server-header-right" style="display:flex; flex-direction:column; align-items:flex-end; gap:5px;">
            <button type="button" class="power-toggle ${isEn ? 'is-on' : 'is-off'}" onclick="toggleTeamPower('${t.id}')">
              <span class="power-dot"></span>
              <span class="power-label">${isEn ? 'ON' : 'OFF'}</span>
            </button>
            <button type="button" class="btn btn-xs" id="team-test-btn-${t.id}" style="padding:1px 8px; font-size:10px;" onclick="testTeamMembers('${t.id}')">
              🧪 Test
            </button>
          </div>
        </div>
        <div class="server-card-controls-row" style="margin-top:6px;">
          <div class="server-card-left-tags" style="flex-wrap:wrap; gap:4px;">
            <span style="font-size:10px; font-family:var(--mono); color:#d2a8ff; background:#1e1430; padding:2px 6px; border-radius:4px; border:1px solid #58338f; cursor:pointer;" onclick="copyDirectRoute('multiagent')" title="Copy route">
              📋 /multiagent
            </span>
            ${membersHtml}
          </div>
          <div class="server-card-btn-group">
            <button class="btn btn-xs" onclick="openTeamModal('${t.id}')">✏️ Edit</button>
            <button class="safe-delete-btn" onclick="deleteTeam('${t.id}')">🗑️</button>
          </div>
        </div>
        <div class="ping-summary" id="team-ping-${t.id}" style="margin-top:4px;"></div>
      </div>
    `;
    cTeams.appendChild(card);
  });
}

async function testTeamMembers(tId) {
  const team = currentConfig?.multi_agent_teams?.[tId];
  if (!team) return;
  const members = team.members || [];
  if (!members.length) {
    showToast('No members configured in team', true);
    return;
  }

  const btn = document.getElementById(`team-test-btn-${tId}`);
  const summaryBox = document.getElementById(`team-ping-${tId}`);

  if (btn) {
    btn.innerText = '⏳...';
    btn.disabled = true;
  }

  members.forEach((m, idx) => {
    const el = document.getElementById(`team-member-status-${tId}-${idx}`);
    if (el) {
      el.innerHTML = '⏳';
      el.title = 'Testing member...';
    }
  });

  let completed = 0, okCount = 0;
  const updateSummary = () => {
    if (summaryBox) summaryBox.innerText = `${okCount}/${members.length} active (${completed}/${members.length} checked)`;
  };
  updateSummary();

  const pingPromises = members.map((m, idx) => {
    const pId = m.provider;
    const model = m.model;
    const el = document.getElementById(`team-member-status-${tId}-${idx}`);

    return fetch('/api/ui/test-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: pId, model: model, discover_only: false })
    }).then(res => res.json()).then(data => {
      completed++;
      const resObj = (data.models || [])[0];
      if (resObj && resObj.active) {
        okCount++;
        if (typeof _setCachedModelStatus === 'function') {
          _setCachedModelStatus(pId, model, { state: 'ok', short: resObj.short || '🟢 200', status: resObj.status || '🟢 200 OK' });
        }
        if (el) { el.innerHTML = '🟢'; el.title = resObj.status || '🟢 200 OK'; }
      } else {
        if (typeof _setCachedModelStatus === 'function') {
          _setCachedModelStatus(pId, model, { state: 'err', short: resObj?.short || '🔴 Fail', status: resObj?.status || 'Failed' });
        }
        if (el) { el.innerHTML = '🔴'; el.title = resObj?.status || 'Failed'; }
      }
      updateSummary();
    }).catch(() => {
      completed++;
      if (typeof _setCachedModelStatus === 'function') {
        _setCachedModelStatus(pId, model, { state: 'err', short: '🔴 Err', status: 'Network error / Timeout' });
      }
      if (el) { el.innerHTML = '🔴'; el.title = 'Network error / Timeout'; }
      updateSummary();
    });
  });

  try {
    await Promise.all(pingPromises);
    if (summaryBox) {
      const isAllOk = okCount === members.length;
      summaryBox.innerText = `${okCount}/${members.length} active (${isAllOk ? '🟢 Strict Ready' : '🔴 Strict Halted'})`;
      summaryBox.style.color = isAllOk ? 'var(--success-text)' : 'var(--danger-text)';
    }
    showToast(`${team.name || tId}: ${okCount}/${members.length} members active`);
  } finally {
    if (btn) {
      btn.innerText = '🧪 Test';
      btn.disabled = false;
    }
  }
}

async function toggleTeamPower(teamId) {
  try {
    const res = await fetch('/api/ui/multi-agent-teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle', id: teamId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message);
      currentConfig = data.config;
      renderTeamsLane();
    }
  } catch (e) {
    showToast('Failed to toggle team', true);
  }
}

function deleteTeam(teamId) {
  openConfirmDeleteTeam(teamId);
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
    ? `<span class="server-mode-badge is-normal" title="Normal Mode: Fast Chat + Interactive Q/A only">💬 normal</span>`
    : `<span class="server-mode-badge is-agentic" title="Agentic Mode: Full Tools, Bash &amp; File Edits">⚡ agentic</span>`;
  const hasCustomPrompt = !!(p.custom_prompt && p.custom_prompt.trim());
  const promptBadgeHtml = hasCustomPrompt
    ? `<span class="server-prompt-badge" title="Custom System Prompt Active">📝 prompt</span>`
    : '';
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
      </div>
      <div class="server-header-right" onclick="event.stopPropagation()">
        <button type="button" class="power-toggle ${isEnabled ? 'is-on' : 'is-off'}" id="power-btn-${id}" title="${isEnabled ? 'Server ON — tap to turn OFF' : 'Server OFF — tap to turn ON'}" onclick="toggleServerPower('${id}')">
          <span class="power-dot"></span>
          <span class="power-label">${isEnabled ? 'ON' : 'OFF'}</span>
        </button>
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
  (p.keys || []).forEach((k, idx) => {
    const row = document.createElement('div');
    row.className = 'key-line';
    row.innerHTML = `
      <span class="key-line-left">
        <span style="color:#79c0ff;">#${idx+1} ${maskKey(k)}</span>
        <span class="key-status" id="key-status-${id}-${idx}"></span>
      </span>
      <span class="chip-x" title="Revoke Key" onclick="openConfirmDeleteKey('${id}', ${idx})">✕</span>
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

async function addKey(e) {
  e.preventDefault();
  const pId = document.getElementById('provider-select').value;
  const input = document.getElementById('new-key-val');
  const val = input.value.trim();
  if (!val) return;
  const res = await fetch('/api/ui/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: pId, key: val })
  });
  const data = await res.json();
  if (res.ok) {
    showToast('Key added');
    input.value = '';
    currentConfig = data.config;
    renderLanes();
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

