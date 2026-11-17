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
  } catch (err) {
    showToast('Config load failure', true);
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
}

function createServerCard(id, p, isRouted, index) {
  const card = document.createElement('div');
  card.className = 'server-card';
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

  top.innerHTML = `
    <!-- Row 1: Drag handle, Priority Badge, Server Name, Protocol, and Expand Arrow -->
    <div class="server-card-header-row" onclick="toggleServerCard('${id}')">
      <div class="server-card-title-group">
        <span class="drag-handle" onclick="event.stopPropagation()" title="Touch & hold or drag to reorder">⠿</span>
        <span class="priority-badge-slot"></span>
        <span class="server-name" title="${p.name || id}">${p.name || id}</span>
        <span class="server-proto">${p.type || 'anthropic'}</span>
      </div>
      <span class="toggle-arrow">▶</span>
    </div>

    <!-- Row 2: Route Pill + Reorder/Route Buttons + Safe Delete Button -->
    <div class="server-card-controls-row">
      <div class="server-card-left-tags">
        <span style="font-size:10px; font-family:var(--mono); color:#79c0ff; background:#162438; padding:2px 6px; border-radius:4px; border:1px solid #1f4277; cursor:pointer; display:inline-flex; align-items:center; gap:3px;" title="Click to copy direct route URL" onclick="event.stopPropagation(); copyDirectRoute('${id}')">
          📋 /${id}
        </span>
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
    chip.innerHTML = `
      <span>${m}</span>
      <span class="chip-status" id="chip-status-${id}-${m}"></span>
      <span class="chip-x" title="Remove" onclick="openConfirmDeleteModel('${id}', '${m}')">✕</span>
    `;
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
    </div>
  `;
  const kList = document.createElement('div');
  kList.className = 'keys-compact-list';
  (p.keys || []).forEach((k, idx) => {
    const row = document.createElement('div');
    row.className = 'key-line';
    row.innerHTML = `
      <span style="color:#79c0ff;">#${idx+1} ${maskKey(k)}</span>
      <span class="chip-x" title="Revoke Key" onclick="openConfirmDeleteKey('${id}', ${idx})">✕</span>
    `;
    kList.appendChild(row);
  });
  if (!p.keys || p.keys.length === 0) {
    kList.innerHTML = '<span style="font-size:10px; color:var(--text-muted);">No keys</span>';
  }
  kSec.appendChild(kList);
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
setInterval(fetchStatus, 5000);

