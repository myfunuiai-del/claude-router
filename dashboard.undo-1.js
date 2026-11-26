// Confirmation Modal before Deletion (100% Pure HTML Modal - Zero Browser Popups)
function openConfirmModal(titleText, bodyHtml, confirmBtnText, onConfirm) {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-modal-title');
  const body = document.getElementById('confirm-modal-body');
  const btn = document.getElementById('confirm-modal-btn');
  if (title) title.innerText = titleText;
  if (body) body.innerHTML = bodyHtml;
  if (btn) {
    btn.innerText = confirmBtnText;
    btn.onclick = () => {
      closeConfirmModal();
      onConfirm();
    };
  }
  if (modal) modal.classList.add('active');
}

function openConfirmDelete(pId) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Delete Server', `Are you sure you want to delete server <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Delete Server', () => startServerDeletion(pId));
}

function openConfirmDeleteKey(pId, index) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Revoke API Key', `Are you sure you want to revoke <strong>Key #${index+1}</strong> from <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Revoke Key', () => startKeyDeletion(pId, index));
}

function openConfirmDeleteModel(pId, modelName, fromModal=false) {
  const name = currentConfig?.providers?.[pId]?.name || pId;
  openConfirmModal('Remove Model', `Are you sure you want to remove model <strong>${modelName}</strong> from <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`, 'Remove Model', () => startModelDeletion(pId, modelName, fromModal));
}

function openConfirmDeleteTeam(teamId) {
  const name = currentConfig?.multi_agent_teams?.[teamId]?.name || teamId;
  openConfirmModal(
    'Delete Multi-Agent Team',
    `Are you sure you want to delete team <strong>${name}</strong>?<br><span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">You will have 10 seconds to undo this action.</span>`,
    'Delete Team',
    () => startTeamDeletion(teamId)
  );
}

function closeConfirmModal() {
  const modal = document.getElementById('confirm-modal');
  if (modal) modal.classList.remove('active');
}

// 10-Second Undo Deletion System (Unified for Servers, Keys, and Models)
let pendingDeletion = null;
let undoCountdownTimer = null;
let undoProgressInterval = null;

function startServerDeletion(pId) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj) return;

  const serverName = pObj.name || pId;
  const isRouted = currentConfig.routed_providers?.includes(pId);
  const routedIndex = isRouted ? currentConfig.routed_providers.indexOf(pId) : -1;
  const unroutedIndex = !isRouted ? currentConfig.unrouted_providers?.indexOf(pId) : -1;

  pendingDeletion = {
    type: 'server',
    pId: pId,
    name: serverName,
    data: JSON.parse(JSON.stringify(pObj)),
    isRouted: isRouted,
    routedIndex: routedIndex,
    unroutedIndex: unroutedIndex
  };

  delete currentConfig.providers[pId];
  if (currentConfig.routed_providers) currentConfig.routed_providers = currentConfig.routed_providers.filter(x => x !== pId);
  if (currentConfig.unrouted_providers) currentConfig.unrouted_providers = currentConfig.unrouted_providers.filter(x => x !== pId);
  renderLanes();
  renderDropdown();

  showUndoToast(`Deleted '${serverName}'`);
}

function startKeyDeletion(pId, index) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj || !pObj.keys || pObj.keys[index] === undefined) return;

  const keyVal = pObj.keys[index];
  pendingDeletion = {
    type: 'key',
    pId: pId,
    index: index,
    keyVal: keyVal
  };

  pObj.keys.splice(index, 1);
  renderLanes();

  showUndoToast(`Revoked Key #${index+1}`);
}

function startModelDeletion(pId, modelName, fromModal=false) {
  if (pendingDeletion) commitPendingDeletion();
  const pObj = currentConfig?.providers?.[pId];
  if (!pObj || !pObj.models) return;

  const prevModels = [...pObj.models];
  pendingDeletion = {
    type: 'model',
    pId: pId,
    modelName: modelName,
    fromModal: fromModal,
    prevModels: prevModels
  };

  pObj.models = pObj.models.filter(m => m !== modelName);
  renderLanes();
  if (fromModal) filterDiscoveredList();

  showUndoToast(`Removed model '${modelName}'`);
}

function startTeamDeletion(teamId) {
  if (pendingDeletion) commitPendingDeletion();
  const teamObj = currentConfig?.multi_agent_teams?.[teamId];
  if (!teamObj) return;

  const teamName = teamObj.name || teamId;
  pendingDeletion = {
    type: 'team',
    teamId: teamId,
    name: teamName,
    data: JSON.parse(JSON.stringify(teamObj))
  };

  delete currentConfig.multi_agent_teams[teamId];
  renderTeamsLane();
  showUndoToast(`Deleted team '${teamName}'`);
}

function startLocalBrainDeletion() {
  if (pendingDeletion) commitPendingDeletion();

  pendingDeletion = {
    type: 'fox_local_brain',
    name: 'Qwen2.5-0.5B Local Brain'
  };

  // Immediate UI feedback: switch badge and check status
  const badge = document.getElementById('fox-brain-badge');
  if (badge) badge.innerText = 'Online';
  const tag = document.getElementById('fox-local-engine-tag');
  if (tag) { tag.innerText = 'Removing in 10s...'; tag.style.color = '#f85149'; }
  const btn = document.getElementById('btn-start-local-download');
  if (btn) { btn.innerText = '⚡ Download & Setup Local Brain'; btn.disabled = true; }
  const btnRemove = document.getElementById('btn-remove-local-brain');
  if (btnRemove) { btnRemove.style.display = 'none'; }

  showUndoToast(`Removed 'Qwen2.5-0.5B Local Brain'`);
}

function showUndoToast(msg) {
  const toast = document.getElementById('undo-toast');
  const msgEl = document.getElementById('undo-toast-msg');
  const bar = document.getElementById('undo-progress-bar');
  if (!toast || !msgEl || !bar) return;

  msgEl.innerText = msg;
  toast.classList.remove('expiring');
  toast.classList.add('show');
  bar.style.width = '100%';

  const durationMs = 10000;
  const startTime = Date.now();

  if (undoProgressInterval) clearInterval(undoProgressInterval);
  undoProgressInterval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const remainingPct = Math.max(0, 100 - (elapsed / durationMs) * 100);
    bar.style.width = remainingPct + '%';

    if (elapsed >= 7500) {
      toast.classList.add('expiring');
    }

    if (elapsed >= durationMs) {
      clearInterval(undoProgressInterval);
      undoProgressInterval = null;
    }
  }, 100);

  if (undoCountdownTimer) clearTimeout(undoCountdownTimer);
  undoCountdownTimer = setTimeout(() => {
    commitPendingDeletion();
  }, durationMs);
}

function hideUndoToast() {
  const toast = document.getElementById('undo-toast');
  if (toast) {
    toast.classList.remove('show');
    toast.classList.remove('expiring');
  }
  if (undoProgressInterval) {
    clearInterval(undoProgressInterval);
    undoProgressInterval = null;
  }
  if (undoCountdownTimer) {
    clearTimeout(undoCountdownTimer);
    undoCountdownTimer = null;
  }
}

function triggerUndoAction() {
  if (!pendingDeletion) return;
  const item = pendingDeletion;
  pendingDeletion = null;
  hideUndoToast();

  if (item.type === 'server') {
    currentConfig.providers[item.pId] = item.data;
    const pool = item.isRouted ? currentConfig.routed_providers : currentConfig.unrouted_providers;
    if (pool) {
      const idx = item.isRouted ? item.routedIndex : item.unroutedIndex;
      idx >= 0 ? pool.splice(idx, 0, item.pId) : pool.push(item.pId);
    }
    renderLanes();
    renderDropdown();
    showToast(`↺ Restored '${item.name}'`);
    saveDomOrderAndSync();
  } else if (item.type === 'key') {
    const pObj = currentConfig?.providers?.[item.pId];
    if (pObj) {
      if (!pObj.keys) pObj.keys = [];
      pObj.keys.splice(item.index, 0, item.keyVal);
      renderLanes();
    }
    showToast(`↺ Restored Key #${item.index+1}`);
  } else if (item.type === 'model') {
    const pObj = currentConfig?.providers?.[item.pId];
    if (pObj) {
      pObj.models = item.prevModels;
      renderLanes();
      if (item.fromModal) filterDiscoveredList();
    }
    showToast(`↺ Restored '${item.modelName}'`);
  } else if (item.type === 'team') {
    if (!currentConfig.multi_agent_teams) currentConfig.multi_agent_teams = {};
    currentConfig.multi_agent_teams[item.teamId] = item.data;
    renderTeamsLane();
    showToast(`↺ Restored Team '${item.name}'`);
  } else if (item.type === 'fox_local_brain') {
    showToast(`↺ Restored 'Qwen2.5-0.5B Local Brain'`);
    if (typeof checkLocalEngineStatus === 'function') {
      checkLocalEngineStatus();
    }
  }
}

async function commitPendingDeletion() {
  if (!pendingDeletion) return;
  const item = pendingDeletion;
  pendingDeletion = null;
  hideUndoToast();

  try {
    let url, method = 'DELETE', body;
    if (item.type === 'server') {
      url = '/api/ui/providers';
      body = { provider: item.pId };
    } else if (item.type === 'key') {
      url = '/api/ui/keys';
      body = { provider: item.pId, index: item.index };
    } else if (item.type === 'model') {
      url = '/api/ui/provider-models';
      method = 'POST';
      body = { provider: item.pId, action: 'remove', model: item.modelName };
    } else if (item.type === 'team') {
      url = '/api/ui/multi-agent-teams';
      method = 'POST';
      body = { action: 'delete', id: item.teamId };
    } else if (item.type === 'fox_local_brain') {
      url = '/api/ui/fox-local/remove';
      method = 'POST';
      body = {};
    }
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    if (res.ok) {
      if (item.type === 'fox_local_brain') {
        if (typeof checkLocalEngineStatus === 'function') checkLocalEngineStatus();
        showToast('Local brain model removed successfully');
        return;
      }
      currentConfig = data.config;
      renderLanes();
      if (item.type === 'server') renderDropdown();
      if (item.type === 'model' && item.fromModal) filterDiscoveredList();
    }
  } catch (err) {
    showToast('Error completing deletion', true);
  }
}

function deleteServer(pId) {
  openConfirmDelete(pId);
}

