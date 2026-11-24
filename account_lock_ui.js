/* ==============================================================
   Account Model Lock, Binding & Model Redirection UI Component
   - Exact Antigravity Chat Models from Screen
   - Supports: 1-to-1 profile exclusivity, Model Deletion via Native Modal & 10s Undo Toast
   - Supports: Redirection Profiles (Only shows models present in account profiles)
   ============================================================== */
let accountLockState = { enabled: false, accounts: [], redirections: [] };
let availableAccounts = [];
let currentLiveEmail = '';
let activePickingAccId = null;
let editingAccId = null;

// Authentic base models catalog for Account Model Binding
const EXACT_ANTIGEM_MODELS = [
  "Gemini 3.8 Flash",
  "Gemini 4 Neon",
  "Gemini 4 Neon (XHigh)",
  "Gemini 4 Hydrogen",
  "Gemini 4 Hydrogen (XHigh)",
  "Orchestrator (Neon)",
  "Claude Sonnet 4.6",
  "Claude Opus 4.6",
  "GPT-OSS 120B",
  "Gemini 4 Argon",
  "Orchestrator (Argon)"
];

let allKnownModels = [...EXACT_ANTIGEM_MODELS];

// Undo state specific to Account Model Binding
let accModelPendingDeletion = null;

let busyLockDismissedByUser = false;

async function fetchAccountLock() {
  try {
    const res = await fetch('/api/ui/account-lock');
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === 'ok') {
      accountLockState = data.state || { enabled: false, accounts: [], redirections: [] };
      availableAccounts = data.available_accounts || [];
      currentLiveEmail = data.current_email || '';
      renderAccountLockUI();
      updateRedirectionBadge();
      handleBusyLockPopup(data.busy_info);
    }
  } catch (e) {
    console.error('Failed to load account lock status:', e);
  }
}

function handleBusyLockPopup(busyInfo) {
  const modal = document.getElementById('busy-lock-popup-modal');
  const modelSpan = document.getElementById('busy-lock-model-name');
  if (!modal) return;

  if (busyInfo && busyInfo.busy && !busyLockDismissedByUser) {
    if (modelSpan) modelSpan.textContent = busyInfo.model || 'New Model';
    modal.style.display = 'flex';
  } else if (!busyInfo || !busyInfo.busy) {
    busyLockDismissedByUser = false;
    modal.style.display = 'none';
  }
}

function closeBusyLockModal() {
  const modal = document.getElementById('busy-lock-popup-modal');
  if (modal) modal.style.display = 'none';
  busyLockDismissedByUser = true;
}

async function triggerForceSwitchFromDashboard() {
  try {
    const res = await fetch('/api/ui/account-lock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'force_switch' })
    });
    if (res.ok) {
      closeBusyLockModal();
      if (typeof showToast === 'function') {
        showToast('⚡ Force Switch sent! Swapping account now...');
      }
      setTimeout(fetchAccountLock, 800);
    }
  } catch (e) {
    alert('Failed to send force switch: ' + e);
  }
}

function renderAccountLockUI() {
  const btn = document.getElementById('account-lock-toggle-btn');
  const label = document.getElementById('account-lock-toggle-label');
  const container = document.getElementById('account-lock-items');
  if (!btn || !container) return;

  const isEnabled = accountLockState.enabled === true;
  btn.className = `power-toggle ${isEnabled ? 'is-on' : 'is-off'}`;
  label.textContent = isEnabled ? 'ON' : 'OFF';

  let accs = accountLockState.accounts || [];
  if (accs.length === 0 && availableAccounts.length > 0) {
    accs = availableAccounts.map((email, idx) => ({
      id: 'acc_' + (idx + 1),
      name: idx === 0 ? 'Work Pro' : 'Personal Account',
      email: email,
      models: idx === 0 ? ['Gemini 3.8 Flash'] : []
    }));
    accountLockState.accounts = accs;
  }

  container.innerHTML = accs.map(acc => {
    const isLive = acc.email.toLowerCase() === currentLiveEmail.toLowerCase();
    const hasName = Boolean(acc.name && acc.name.trim());
    const isEditing = editingAccId === acc.id || !hasName;
    const models = acc.models || [];

    const nameSectionHtml = isEditing ? `
      <div style="display:flex; align-items:center; gap:6px;">
        <input type="text" id="input-name-${acc.id}" 
               value="${(acc.name || '').replace(/"/g, '&quot;')}" 
               placeholder="Enter profile name..." 
               style="background:#0d1117; border:1px solid #388bfd; color:#e6edf3; border-radius:4px; padding:3px 8px; font-size:12px; font-weight:600; min-width:140px; max-width:200px;" 
               onkeydown="if(event.key==='Enter') saveAccountName('${acc.id}')" />
        <button class="btn btn-xs btn-success" onclick="saveAccountName('${acc.id}')" style="padding:2px 8px; font-size:11px;">Save</button>
      </div>
    ` : `
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:13px; font-weight:700; color:#e6edf3;">${acc.name}</span>
        <button class="btn btn-xs" onclick="startEditingName('${acc.id}')" style="padding:1px 6px; font-size:10px; color:#8b949e; border-color:#30363d;" title="Edit Name">✏️ Edit</button>
      </div>
    `;

    const modelsChips = models.length > 0 
      ? models.map(m => `<span style="background:#162438; color:#79c0ff; border:1px solid #1f4277; border-radius:12px; padding:2px 8px; font-size:11px; font-family:var(--mono);">${m}</span>`).join(' ')
      : '<span style="color:var(--text-muted); font-size:11px; font-style:italic;">No models selected</span>';

    return `
      <div class="account-card" style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px; display:flex; flex-direction:column; gap:10px;">
        
        <!-- Row 1: Profile Name on left, Active Now Badge on right -->
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:11px; color:var(--text-muted); font-weight:600; text-transform:uppercase;">NAME:</span>
            ${nameSectionHtml}
          </div>
          ${isLive ? '<span style="background:#238636; color:#fff; font-size:9px; padding:2px 7px; border-radius:10px; font-weight:700; letter-spacing:0.5px;">ACTIVE NOW</span>' : ''}
        </div>

        <!-- Row 2: Gmail Address -->
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:11px; color:var(--text-muted); font-weight:600; text-transform:uppercase;">GMAIL:</span>
          <span style="font-family:var(--mono); font-size:12px; color:#58a6ff;">${acc.email}</span>
        </div>

        <!-- Row 3: Active Models header on left + Model Selection button on right, Chips below -->
        <div style="border-top:1px solid #21262d; padding-top:8px; display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
            <span style="font-size:11px; color:var(--text-muted);">Active Models:</span>
            <button class="btn btn-xs btn-primary" onclick="openAccountModelPicker('${acc.id}')" style="display:flex; align-items:center; gap:5px; padding:4px 10px; font-size:11px; border-radius:5px; background:#1f6feb; border-color:#388bfd;">
              <span>🤖 Model Selection</span>
              <span style="background:#0d1117; border-radius:10px; padding:0 6px; font-size:10px; font-weight:600;">${models.length}</span>
            </button>
          </div>
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            ${modelsChips}
          </div>
        </div>

      </div>
    `;
  }).join('');
}

function startEditingName(accId) {
  editingAccId = accId;
  renderAccountLockUI();
  setTimeout(() => {
    const inp = document.getElementById(`input-name-${accId}`);
    if (inp) { inp.focus(); inp.select(); }
  }, 50);
}

async function saveAccountName(accId) {
  const inp = document.getElementById(`input-name-${accId}`);
  if (!inp) return;
  const newName = inp.value.trim();
  const acc = (accountLockState.accounts || []).find(a => a.id === accId);
  if (acc) {
    acc.name = newName;
    editingAccId = null;
    await saveAccountState();
  }
}

async function toggleAccountLock() {
  const nextVal = !accountLockState.enabled;
  try {
    const res = await fetch('/api/ui/account-lock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'toggle', enabled: nextVal })
    });
    if (res.ok) {
      const data = await res.json();
      accountLockState = data.state;
      currentLiveEmail = data.current_email;
      availableAccounts = data.available_accounts;
      renderAccountLockUI();
      updateRedirectionBadge();
      if (typeof showToast === 'function') {
        showToast(`Account Lock turned ${nextVal ? 'ON' : 'OFF'}`);
      }
    }
  } catch (e) {
    alert('Failed to toggle Account Lock: ' + e);
  }
}

async function saveAccountState() {
  try {
    const res = await fetch('/api/ui/account-lock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        action: 'save', 
        accounts: accountLockState.accounts, 
        enabled: accountLockState.enabled,
        redirections: accountLockState.redirections || [],
        redirections_enabled: accountLockState.redirections_enabled !== false,
        custom_models: accountLockState.custom_models || []
      })
    });
    if (res.ok) {
      const data = await res.json();
      accountLockState = data.state;
      renderAccountLockUI();
      updateRedirectionBadge();
    }
  } catch (e) {
    console.error('Error saving account state:', e);
  }
}

/* ---------------- Model Picker Modal, Swap & Delete Logic ---------------- */
function openAccountModelPicker(accId) {
  activePickingAccId = accId;
  const acc = (accountLockState.accounts || []).find(a => a.id === accId);
  if (!acc) return;

  const modal = document.getElementById('account-model-modal');
  const title = document.getElementById('acc-model-modal-title');
  const body = document.getElementById('acc-model-modal-body');
  if (!modal || !title || !body) return;

  title.innerText = `Select Models for: ${acc.name || acc.email}`;
  renderModelPickerList(acc);
  modal.style.display = 'flex';
}

function closeAccountModelPicker() {
  const modal = document.getElementById('account-model-modal');
  if (modal) modal.style.display = 'none';
  activePickingAccId = null;
}

function getAssignedAccountForModel(modelName, excludeAccId) {
  const accs = accountLockState.accounts || [];
  for (const a of accs) {
    if (a.id !== excludeAccId && (a.models || []).includes(modelName)) {
      return a;
    }
  }
  return null;
}

function renderModelPickerList(acc) {
  const body = document.getElementById('acc-model-modal-body');
  if (!body) return;

  const currentModels = acc.models || [];
  const listToRender = Array.from(new Set([...allKnownModels, ...currentModels]));

  body.innerHTML = `
    <div style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">
      Select models for <strong>${acc.name || acc.email}</strong>. (A model can only belong to one profile):
    </div>
    <div style="max-height:280px; overflow-y:auto; display:flex; flex-direction:column; gap:6px; padding-right:4px;">
      ${listToRender.map(m => {
        const isChecked = currentModels.includes(m);
        const otherAcc = getAssignedAccountForModel(m, acc.id);
        
        return `
          <div style="display:flex; justify-content:space-between; align-items:center; background:#161b22; border:1px solid #30363d; border-radius:6px; padding:7px 10px; gap:8px;">
            <label style="display:flex; align-items:center; gap:8px; cursor:pointer; flex:1; min-width:0; margin:0;">
              <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="handleModelCheck('${escapeHtml(m)}', this.checked)" style="cursor:pointer;" />
              <span style="font-size:12px; font-weight:600; color:#e6edf3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(m)}</span>
            </label>
            <div style="display:flex; align-items:center; gap:6px; flex-shrink:0;">
              ${otherAcc ? `
                <span style="font-size:10px; color:#d29922; background:#382405; padding:1px 6px; border-radius:4px;" title="Assigned to ${otherAcc.name || otherAcc.email}">In ${escapeHtml(otherAcc.name || otherAcc.email)}</span>
                <button type="button" class="btn btn-xs" onclick="swapModelToCurrentAcc('${escapeHtml(m)}', '${otherAcc.id}')" style="padding:1px 7px; font-size:10px; background:#1f6feb; border-color:#388bfd; color:#fff;" title="Swap model to this profile">⇄ Swap</button>
              ` : ''}
              <button type="button" class="btn btn-xs" onclick="openConfirmDeleteAccModel('${escapeHtml(m)}')" style="padding:1px 6px; font-size:11px; background:transparent; border:1px solid #da3633; color:#f85149; border-radius:4px;" title="Remove Model">🗑️</button>
            </div>
          </div>
        `;
      }).join('')}
    </div>
    
    <!-- Add extra / custom model input -->
    <div style="margin-top:10px; display:flex; gap:6px;">
      <input type="text" id="acc-custom-model-input" placeholder="Type extra model name to add..." style="flex:1; background:#0d1117; border:1px solid #30363d; color:#e6edf3; border-radius:4px; padding:4px 8px; font-size:12px;" onkeydown="if(event.key==='Enter') addCustomModelToAcc()" />
      <button class="btn btn-xs btn-primary" onclick="addCustomModelToAcc()">+ Add</button>
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function handleModelCheck(modelName, isChecked) {
  if (!activePickingAccId) return;
  const acc = (accountLockState.accounts || []).find(a => a.id === activePickingAccId);
  if (!acc) return;
  if (!acc.models) acc.models = [];

  if (isChecked) {
    const otherAcc = getAssignedAccountForModel(modelName, acc.id);
    if (otherAcc) {
      if (typeof openConfirmModal === 'function') {
        openConfirmModal(
          'SWAP MODEL PROFILE',
          `Model <strong>${modelName}</strong> is currently assigned to <strong>${otherAcc.name || otherAcc.email}</strong>.<br><br>Do you want to SWAP it to <strong>${acc.name || acc.email}</strong>?`,
          'Swap Model',
          () => swapModelToCurrentAcc(modelName, otherAcc.id)
        );
      } else {
        const confirmSwap = confirm(`"${modelName}" is currently assigned to "${otherAcc.name || otherAcc.email}".\nDo you want to SWAP it to this profile?`);
        if (confirmSwap) swapModelToCurrentAcc(modelName, otherAcc.id);
      }
      return;
    }
    if (!acc.models.includes(modelName)) acc.models.push(modelName);
  } else {
    acc.models = acc.models.filter(m => m !== modelName);
  }
  saveAccountState();
  renderModelPickerList(acc);
}

function swapModelToCurrentAcc(modelName, fromAccId) {
  if (!activePickingAccId) return;
  const currentAcc = (accountLockState.accounts || []).find(a => a.id === activePickingAccId);
  const fromAcc = (accountLockState.accounts || []).find(a => a.id === fromAccId);
  if (!currentAcc || !fromAcc) return;

  fromAcc.models = (fromAcc.models || []).filter(m => m !== modelName);
  if (!currentAcc.models) currentAcc.models = [];
  if (!currentAcc.models.includes(modelName)) currentAcc.models.push(modelName);

  saveAccountState();
  renderModelPickerList(currentAcc);
  if (typeof showToast === 'function') {
    showToast(`Swapped "${modelName}" to ${currentAcc.name || currentAcc.email}`);
  }
}

function addCustomModelToAcc() {
  const inp = document.getElementById('acc-custom-model-input');
  if (!inp || !inp.value.trim() || !activePickingAccId) return;
  const m = inp.value.trim();
  
  if (!allKnownModels.includes(m)) {
    allKnownModels.push(m);
  }
  handleModelCheck(m, true);
  inp.value = '';
}

/* ---------------- Exact Matching "REMOVE MODEL" Modal + 10s Undo System ---------------- */
function openConfirmDeleteAccModel(modelName) {
  const currentAcc = (accountLockState.accounts || []).find(a => a.id === activePickingAccId);
  const profileName = currentAcc ? (currentAcc.name || currentAcc.email) : 'Account Lock';

  const bodyHtml = `
    Are you sure you want to remove model <strong>${modelName}</strong> from <strong>${profileName}</strong>?<br>
    <span style="color:var(--text-muted); font-size:11px; margin-top:6px; display:inline-block;">You will have 10 seconds to undo this action.</span>
  `;

  if (typeof openConfirmModal === 'function') {
    openConfirmModal('REMOVE MODEL', bodyHtml, 'Remove Model', () => startAccModelDeletion(modelName));
    const cfmModal = document.getElementById('confirm-modal');
    if (cfmModal) cfmModal.style.setProperty('z-index', '100001', 'important');
  } else {
    const confirmed = confirm(`Are you sure you want to remove model "${modelName}" from "${profileName}"?\nYou will have 10 seconds to undo this action.`);
    if (confirmed) startAccModelDeletion(modelName);
  }
}

function startAccModelDeletion(modelName) {
  if (typeof commitPendingDeletion === 'function' && window.pendingDeletion) {
    commitPendingDeletion();
  }

  const deletedFromAccs = [];
  for (const acc of (accountLockState.accounts || [])) {
    if (acc.models && acc.models.includes(modelName)) {
      deletedFromAccs.push(acc.id);
      acc.models = acc.models.filter(m => m !== modelName);
    }
  }

  allKnownModels = allKnownModels.filter(m => m !== modelName);

  saveAccountState();
  if (activePickingAccId) {
    const acc = (accountLockState.accounts || []).find(a => a.id === activePickingAccId);
    if (acc) renderModelPickerList(acc);
  }

  accModelPendingDeletion = {
    modelName: modelName,
    deletedFromAccs: deletedFromAccs
  };

  if (typeof showUndoToast === 'function') {
    window.pendingDeletion = {
      type: 'acc_model_lock',
      restore: () => undoAccModelDeletion()
    };
    showUndoToast(`Removed model '${modelName}'`);
  } else {
    if (typeof showToast === 'function') {
      showToast(`Removed model '${modelName}'`);
    }
  }
}

function undoAccModelDeletion() {
  if (!accModelPendingDeletion) return;
  const { modelName, deletedFromAccs } = accModelPendingDeletion;

  if (!allKnownModels.includes(modelName)) {
    allKnownModels.push(modelName);
  }

  for (const accId of deletedFromAccs) {
    const acc = (accountLockState.accounts || []).find(a => a.id === accId);
    if (acc) {
      if (!acc.models) acc.models = [];
      if (!acc.models.includes(modelName)) acc.models.push(modelName);
    }
  }

  saveAccountState();

  if (activePickingAccId) {
    const acc = (accountLockState.accounts || []).find(a => a.id === activePickingAccId);
    if (acc) renderModelPickerList(acc);
  }

  accModelPendingDeletion = null;
  window.pendingDeletion = null;

  if (typeof showToast === 'function') {
    showToast(`Restored "${modelName}"`);
  }
}

if (typeof window.triggerUndoAction === 'function') {
  const origTriggerUndo = window.triggerUndoAction;
  window.triggerUndoAction = function() {
    if (window.pendingDeletion && window.pendingDeletion.type === 'acc_model_lock') {
      window.pendingDeletion.restore();
      const toast = document.getElementById('undo-toast');
      if (toast) {
        toast.classList.remove('show');
        toast.classList.remove('expiring');
      }
      return;
    }
    origTriggerUndo.apply(this, arguments);
  };
}

/* ==============================================================
   Redirection Profiles Logic
   - Combines Account Profile Models + Custom Redirection Models
   - Custom Models DO NOT affect account profiles
   ============================================================== */
function getAllAssignedModels() {
  const models = new Set();
  for (const acc of (accountLockState.accounts || [])) {
    for (const m of (acc.models || [])) {
      if (m && m.trim()) models.add(m.trim());
    }
  }
  // Include custom redirection models (UI-only, no effect on accounts)
  for (const cm of (accountLockState.custom_models || [])) {
    if (cm && cm.trim()) models.add(cm.trim());
  }
  return Array.from(models);
}

function toggleCustomModelInput() {
  const row = document.getElementById('custom-model-input-row');
  if (!row) return;
  const isHidden = row.style.display === 'none' || !row.style.display;
  row.style.display = isHidden ? 'flex' : 'none';
  if (isHidden) {
    const input = document.getElementById('custom-model-input-text');
    if (input) input.focus();
  }
}

async function addCustomModelOnly() {
  const input = document.getElementById('custom-model-input-text');
  if (!input) return;
  const val = input.value.trim();
  if (!val) {
    alert('Please enter a model name');
    return;
  }
  if (!accountLockState.custom_models) {
    accountLockState.custom_models = [];
  }
  if (!accountLockState.custom_models.includes(val)) {
    accountLockState.custom_models.push(val);
    await saveAccountState();
    renderRedirectionModalContent();
    const fromSelect = document.getElementById('redir-from-select');
    if (fromSelect) fromSelect.value = val;
    input.value = '';
    if (typeof showToast === 'function') {
      showToast(`Model added to redirection options: ${val}`);
    }
  } else {
    alert('Model is already in options.');
  }
}

function updateRedirectionBadge() {
  const badge = document.getElementById('redirection-count-badge');
  if (!badge) return;
  const list = accountLockState.redirections || [];
  if (list.length > 0) {
    badge.innerText = list.length;
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

function openRedirectionModal() {
  const modal = document.getElementById('redirection-profiles-modal');
  if (!modal) return;
  renderRedirectionModalContent();
  modal.style.display = 'flex';
}

function closeRedirectionModal() {
  const modal = document.getElementById('redirection-profiles-modal');
  if (modal) modal.style.display = 'none';
}

// Dedicated standalone model list ONLY for Redirection dropdowns (independent of Account Profile models)
const REDIRECTION_MODELS = [
  "Gemini 4 Neon (Low)",
  "Gemini 4 Neon (Medium)",
  "Gemini 4 Neon (High)",
  "Gemini 4 Neon (XHigh)",
  "Gemini 4 Hydrogen (Low)",
  "Gemini 4 Hydrogen (Medium)",
  "Gemini 4 Hydrogen (High)",
  "Gemini 4 Hydrogen (XHigh)",
  "Gemini 4 Argon (Low)",
  "Gemini 4 Argon (Medium)",
  "Gemini 4 Argon (High)",
  "Orchestrator (Neon)",
  "Orchestrator (Argon)",
  "Gemini 3.8 Flash (Low)",
  "Gemini 3.8 Flash (Medium)",
  "Gemini 3.8 Flash (High)",
  "Claude Sonnet 4.6 (Low)",
  "Claude Sonnet 4.6 (Medium)",
  "Claude Sonnet 4.6 (High)",
  "Claude Opus 4.6 (Low)",
  "Claude Opus 4.6 (Medium)",
  "Claude Opus 4.6 (High)",
  "GPT-OSS 120B (Medium)"
];

async function toggleMasterRedirection() {
  accountLockState.redirections_enabled = accountLockState.redirections_enabled === false ? true : false;
  await saveAccountState();
  renderRedirectionModalContent();
  if (typeof showToast === 'function') {
    showToast(`Model Redirection turned ${accountLockState.redirections_enabled ? 'ON' : 'OFF'}`);
  }
}

function renderRedirectionModalContent() {
  const listContainer = document.getElementById('redirection-profiles-list');
  const fromSelect = document.getElementById('redir-from-select');
  const toSelect = document.getElementById('redir-to-select');
  const masterBtn = document.getElementById('redirection-master-toggle-btn');
  const masterLabel = document.getElementById('redirection-master-toggle-label');
  if (!listContainer || !fromSelect || !toSelect) return;

  const isMasterOn = accountLockState.redirections_enabled !== false;
  if (masterBtn && masterLabel) {
    masterBtn.className = `power-toggle ${isMasterOn ? 'is-on' : 'is-off'}`;
    masterLabel.textContent = isMasterOn ? 'ON' : 'OFF';
  }

  const redirections = accountLockState.redirections || [];

  // Populate 'When Model Is Selected' from editable REDIRECTION_MODELS + custom_models - hidden_models
  const effectiveModels = getEffectiveRedirModels();
  const prevVal = fromSelect.value;
  const modelOptionsHtml = effectiveModels.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  fromSelect.innerHTML = modelOptionsHtml;
  if (prevVal && effectiveModels.includes(prevVal)) {
    fromSelect.value = prevVal;
  } else if (effectiveModels.includes("GPT-OSS 120B (Medium)")) {
    fromSelect.value = "GPT-OSS 120B (Medium)";
  }

  // Populate 'Switch To Account Profile' from configured Google Accounts
  const accounts = accountLockState.accounts || [];
  if (accounts.length > 0) {
    toSelect.innerHTML = accounts.map(acc => {
      const label = acc.name ? `${acc.name} (${acc.email})` : acc.email;
      return `<option value="${escapeHtml(acc.email)}">${escapeHtml(label)}</option>`;
    }).join('');
  } else {
    toSelect.innerHTML = '<option value="">No accounts configured</option>';
  }

  // Render Existing Redirection Profiles List
  if (redirections.length === 0) {
    listContainer.innerHTML = `
      <div style="background:#161b22; border:1px dashed #30363d; border-radius:6px; padding:16px; text-align:center; color:var(--text-muted); font-size:12px;">
        No model-to-account rules created yet.<br>Select a model and target account profile below.
      </div>
    `;
    return;
  }

  listContainer.innerHTML = redirections.map((r, idx) => {
    const isEnabled = r.enabled !== false;
    const targetEmail = r.to_account || '';
    const matchedAcc = accounts.find(a => (a.email || '').toLowerCase() === targetEmail.toLowerCase());
    const targetDisplay = targetEmail
      ? `👤 ${matchedAcc && matchedAcc.name ? matchedAcc.name : (r.to_account_name || targetEmail)}`
      : (r.to_model || 'Unknown');
    return `
      <div style="display:flex; justify-content:space-between; align-items:center; background:#161b22; border:1px solid #30363d; border-radius:6px; padding:8px 12px; gap:8px;">
        <div style="display:flex; align-items:center; gap:8px; flex:1; flex-wrap:wrap;">
          <span style="font-size:11px; background:#1f242c; color:#79c0ff; border:1px solid #1f4277; padding:2px 8px; border-radius:4px; font-weight:600;">${escapeHtml(r.from_model)}</span>
          <span style="color:#58a6ff; font-weight:700; font-size:12px;">➔</span>
          <span style="font-size:11px; background:#1c2d20; color:#7ee787; border:1px solid #238636; padding:2px 8px; border-radius:4px; font-weight:600;" title="${escapeHtml(targetEmail)}">${escapeHtml(targetDisplay)}</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <button type="button" class="btn btn-xs ${isEnabled ? 'btn-success' : ''}" onclick="toggleRedirectionRule('${r.id}')" style="padding:2px 8px; font-size:10px; font-weight:600;">
            ${isEnabled ? 'ACTIVE' : 'OFF'}
          </button>
          <button type="button" class="btn btn-xs" onclick="deleteRedirectionRule('${r.id}')" style="padding:2px 6px; font-size:11px; background:transparent; border:1px solid #da3633; color:#f85149; border-radius:4px;" title="Delete Rule">🗑️</button>
        </div>
      </div>
    `;
  }).join('');
}

async function addRedirectionRule() {
  const fromSelect = document.getElementById('redir-from-select');
  const toSelect = document.getElementById('redir-to-select');
  if (!fromSelect || !toSelect) return;

  const fromModel = fromSelect.value.trim();
  const toAccount = toSelect.value.trim();

  if (!fromModel || !toAccount) {
    alert('Please select both a model and a target account profile.');
    return;
  }

  const accounts = accountLockState.accounts || [];
  const matchedAcc = accounts.find(a => (a.email || '').toLowerCase() === toAccount.toLowerCase());
  const toAccountName = matchedAcc && matchedAcc.name ? matchedAcc.name : toAccount;

  if (!accountLockState.redirections) {
    accountLockState.redirections = [];
  }

  // Check if a rule for this from_model already exists
  const existing = accountLockState.redirections.find(r => r.from_model.toLowerCase() === fromModel.toLowerCase());
  if (existing) {
    existing.to_account = toAccount;
    existing.to_account_name = toAccountName;
    existing.enabled = true;
  } else {
    accountLockState.redirections.push({
      id: 'redir_' + Date.now(),
      from_model: fromModel,
      to_account: toAccount,
      to_account_name: toAccountName,
      enabled: true
    });
  }

  await saveAccountState();
  renderRedirectionModalContent();
  if (typeof showToast === 'function') {
    showToast(`Rule saved: ${fromModel} ➔ ${toAccountName}`);
  }
}

async function toggleRedirectionRule(ruleId) {
  const rule = (accountLockState.redirections || []).find(r => r.id === ruleId);
  if (!rule) return;
  rule.enabled = !rule.enabled;
  await saveAccountState();
  renderRedirectionModalContent();
}

async function deleteRedirectionRule(ruleId) {
  accountLockState.redirections = (accountLockState.redirections || []).filter(r => r.id !== ruleId);
  await saveAccountState();
  renderRedirectionModalContent();
  if (typeof showToast === 'function') {
    showToast('Redirection profile removed');
  }
}

fetchAccountLock();
setInterval(() => {
  if (!editingAccId && !activePickingAccId && !accModelPendingDeletion) {
    fetchAccountLock();
  }
}, 6000);

// ========================================================
// REDIRECTION MODEL LIST: ADD / EDIT / DELETE + 10s UNDO
// ========================================================
let lastDeletedRedirModel = null;
let redirUndoTimer = null;
let redirUndoSec = 10;

function getHiddenRedirModels() {
  try {
    const raw = localStorage.getItem('crouter_hidden_redir_models');
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

function saveHiddenRedirModels(arr) {
  try { localStorage.setItem('crouter_hidden_redir_models', JSON.stringify(arr || [])); } catch (e) {}
}

function getEffectiveRedirModels() {
  const hidden = new Set(getHiddenRedirModels().map(x => x.toLowerCase()));
  const list = [];
  const seen = new Set();
  const base = Array.isArray(REDIRECTION_MODELS) ? REDIRECTION_MODELS : [];
  const custom = Array.isArray(accountLockState.custom_models) ? accountLockState.custom_models : [];

  for (const m of [...base, ...custom]) {
    const clean = (m || '').trim();
    if (!clean) continue;
    const key = clean.toLowerCase();
    if (hidden.has(key) || seen.has(key)) continue;
    seen.add(key);
    list.push(clean);
  }
  return list;
}

let redirActionCallback = null;

function openRedirActionModal({ title, desc, defaultValue, showInput, confirmText, isDanger, onConfirm }) {
  const modal = document.getElementById('redir-action-modal');
  const titleEl = document.getElementById('redir-action-title');
  const descEl = document.getElementById('redir-action-desc');
  const inputEl = document.getElementById('redir-action-input');
  const btnEl = document.getElementById('redir-action-confirm-btn');
  if (!modal || !titleEl || !descEl || !inputEl || !btnEl) return;

  titleEl.textContent = title || 'Action';
  descEl.textContent = desc || '';
  inputEl.style.display = showInput ? 'block' : 'none';
  inputEl.value = defaultValue || '';
  btnEl.textContent = confirmText || 'Save';
  btnEl.style.background = isDanger ? '#da3633' : '';
  btnEl.style.borderColor = isDanger ? '#f85149' : '';
  btnEl.style.color = isDanger ? '#ffffff' : '';

  redirActionCallback = onConfirm;
  modal.style.display = 'flex';
  if (showInput) setTimeout(() => { inputEl.focus(); inputEl.select(); }, 50);
}

function closeRedirActionModal() {
  const modal = document.getElementById('redir-action-modal');
  if (modal) modal.style.display = 'none';
  redirActionCallback = null;
}

async function confirmRedirActionModal() {
  const inputEl = document.getElementById('redir-action-input');
  const val = inputEl ? inputEl.value.trim() : '';
  const cb = redirActionCallback;
  closeRedirActionModal();
  if (typeof cb === 'function') await cb(val);
}

function promptAddRedirModel() {
  openRedirActionModal({
    title: '➕ Add New Model',
    desc: 'Enter the exact model name to add to your redirection dropdown:',
    defaultValue: '',
    showInput: true,
    confirmText: 'Add Model',
    isDanger: false,
    onConfirm: async (val) => {
      if (!val) return;
      const hidden = getHiddenRedirModels().filter(x => x.toLowerCase() !== val.toLowerCase());
      saveHiddenRedirModels(hidden);

      if (!accountLockState.custom_models) accountLockState.custom_models = [];
      if (!accountLockState.custom_models.some(m => m.toLowerCase() === val.toLowerCase())) {
        accountLockState.custom_models.push(val);
        await saveAccountState();
      }
      renderRedirectionModalContent();
      const fromSelect = document.getElementById('redir-from-select');
      if (fromSelect) fromSelect.value = val;
      if (typeof showToast === 'function') showToast(`Added model: ${val}`);
    }
  });
}

function promptEditRedirModel() {
  const fromSelect = document.getElementById('redir-from-select');
  if (!fromSelect || !fromSelect.value) return;
  const oldVal = fromSelect.value.trim();

  openRedirActionModal({
    title: '✏️ Edit Model Name',
    desc: `Rename "${oldVal}" across your list and matching rules:`,
    defaultValue: oldVal,
    showInput: true,
    confirmText: 'Save',
    isDanger: false,
    onConfirm: async (val) => {
      if (!val || val === oldVal) return;
      const isBuiltIn = (REDIRECTION_MODELS || []).some(m => m.toLowerCase() === oldVal.toLowerCase());
      if (isBuiltIn) {
        const hidden = getHiddenRedirModels();
        if (!hidden.some(x => x.toLowerCase() === oldVal.toLowerCase())) {
          hidden.push(oldVal);
          saveHiddenRedirModels(hidden);
        }
      }
      if (!accountLockState.custom_models) accountLockState.custom_models = [];
      accountLockState.custom_models = accountLockState.custom_models.filter(m => m.toLowerCase() !== oldVal.toLowerCase());
      if (!accountLockState.custom_models.some(m => m.toLowerCase() === val.toLowerCase())) {
        accountLockState.custom_models.push(val);
      }
      (accountLockState.redirections || []).forEach(r => {
        if ((r.from_model || '').toLowerCase() === oldVal.toLowerCase()) r.from_model = val;
      });

      await saveAccountState();
      renderRedirectionModalContent();
      fromSelect.value = val;
      if (typeof showToast === 'function') showToast(`Updated: ${oldVal} ➔ ${val}`);
    }
  });
}

function promptDeleteRedirModel() {
  const fromSelect = document.getElementById('redir-from-select');
  if (!fromSelect || !fromSelect.value) return;
  const target = fromSelect.value.trim();

  openRedirActionModal({
    title: '🗑️ Delete Model?',
    desc: `Are you sure you want to remove "${target}" from the model list? You will have 10 seconds to Undo.`,
    showInput: false,
    confirmText: 'Delete',
    isDanger: true,
    onConfirm: async () => {
      const wasCustom = (accountLockState.custom_models || []).some(m => m.toLowerCase() === target.toLowerCase());
      const wasBuiltIn = (REDIRECTION_MODELS || []).some(m => m.toLowerCase() === target.toLowerCase());

      if (wasCustom) {
        accountLockState.custom_models = (accountLockState.custom_models || []).filter(m => m.toLowerCase() !== target.toLowerCase());
      }
      if (wasBuiltIn) {
        const hidden = getHiddenRedirModels();
        if (!hidden.some(x => x.toLowerCase() === target.toLowerCase())) {
          hidden.push(target);
          saveHiddenRedirModels(hidden);
        }
      }

      await saveAccountState();
      renderRedirectionModalContent();
      lastDeletedRedirModel = { name: target, wasCustom, wasBuiltIn };
      showRedirUndoBar(target);
    }
  });
}

function showRedirUndoBar(modelName) {
  const bar = document.getElementById('redir-undo-bar');
  const msg = document.getElementById('redir-undo-msg');
  const btn = document.getElementById('redir-undo-btn');
  if (!bar || !msg || !btn) return;

  if (redirUndoTimer) clearInterval(redirUndoTimer);
  redirUndoSec = 10;
  msg.textContent = `Deleted "${modelName}"`;
  btn.textContent = `↩ Undo (${redirUndoSec}s)`;
  bar.style.display = 'flex';

  redirUndoTimer = setInterval(() => {
    redirUndoSec -= 1;
    if (redirUndoSec <= 0) {
      clearInterval(redirUndoTimer);
      redirUndoTimer = null;
      lastDeletedRedirModel = null;
      bar.style.display = 'none';
    } else {
      btn.textContent = `↩ Undo (${redirUndoSec}s)`;
    }
  }, 1000);
}

async function undoDeleteRedirModel() {
  if (!lastDeletedRedirModel) return;
  const { name, wasCustom, wasBuiltIn } = lastDeletedRedirModel;
  if (redirUndoTimer) { clearInterval(redirUndoTimer); redirUndoTimer = null; }
  lastDeletedRedirModel = null;

  const bar = document.getElementById('redir-undo-bar');
  if (bar) bar.style.display = 'none';

  if (wasBuiltIn) {
    const hidden = getHiddenRedirModels().filter(x => x.toLowerCase() !== name.toLowerCase());
    saveHiddenRedirModels(hidden);
  }
  if (wasCustom) {
    if (!accountLockState.custom_models) accountLockState.custom_models = [];
    if (!accountLockState.custom_models.some(m => m.toLowerCase() === name.toLowerCase())) {
      accountLockState.custom_models.push(name);
    }
  }

  await saveAccountState();
  renderRedirectionModalContent();
  const fromSelect = document.getElementById('redir-from-select');
  if (fromSelect) fromSelect.value = name;
  if (typeof showToast === 'function') showToast(`Restored model: ${name}`);
}
