// Plugins / API Tools Manager UI
let pendingPluginUninstall = null;
let pluginUndoTimer = null;
let pluginInstallPollers = {};

async function loadPlugins() {
  const container = document.getElementById('plugins-grid');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-dim,#8b949e);padding:16px;">Loading plugins...</div>';

  try {
    if (typeof fetchConfig === 'function' && (typeof currentConfig === 'undefined' || !currentConfig || !currentConfig.providers)) {
      await fetchConfig();
    }
    const res = await fetch('/api/ui/tools');
    const data = await res.json();
    if (!data.ok || !data.tools) {
      container.innerHTML = '<div style="color:#f85149;padding:16px;">Failed to load plugins.</div>';
      return;
    }
    renderPlugins(data.tools);
  } catch (err) {
    container.innerHTML = `<div style="color:#f85149;padding:16px;">Error: ${err.message}</div>`;
  }
}

function getProviderSavedPort(toolId) {
  const cfg = (typeof currentConfig !== 'undefined') ? currentConfig : null;
  const p = cfg?.providers?.[toolId];
  if (!p || !p.base_url) return null;
  const match = p.base_url.match(/:(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

function getActionBtnHtml(toolId, toolName, currentPort) {
  const savedPort = getProviderSavedPort(toolId);
  if (savedPort === null) {
    return `<button id="crouter-btn-${toolId}" onclick="connectPluginToCrouter('${toolId}', '${toolName}')" style="background:linear-gradient(90deg,#6e40c9,#1f6feb);color:#fff;border:none;padding:6px 10px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:700;white-space:nowrap;">⚡ Add</button>`;
  }
  if (savedPort !== parseInt(currentPort, 10)) {
    return `<button id="crouter-btn-${toolId}" onclick="updatePluginPortInCrouter('${toolId}', '${toolName}')" style="background:#d29922;color:#0d1117;border:none;padding:6px 10px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:700;white-space:nowrap;">🔄 Port Update</button>`;
  }
  return `<button id="crouter-btn-${toolId}" onclick="openPluginModelEditor('${toolId}')" style="background:#21262d;color:#e6edf3;border:1px solid #30363d;padding:6px 10px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:600;white-space:nowrap;">✏ Edit</button>`;
}

function onPluginPortInput(toolId, toolName, val) {
  const ep = document.getElementById(`ep-${toolId}`);
  if (ep) ep.textContent = val;
  const btn = document.getElementById(`crouter-btn-${toolId}`);
  if (btn) {
    const newHtml = getActionBtnHtml(toolId, toolName, val);
    btn.outerHTML = newHtml;
  }
}

function renderPlugins(tools) {
  const container = document.getElementById('plugins-grid');
  if (!container) return;

  if (tools.length === 0) {
    container.innerHTML = '<div style="color:var(--text-dim,#8b949e);padding:16px;">No plugins found in registry.</div>';
    return;
  }

  container.innerHTML = tools.map(t => {
    const isPendingRemove = pendingPluginUninstall === t.id;
    const isInstalling = Boolean(pluginInstallPollers[t.id]);
    const savedPort = getProviderSavedPort(t.id);
    const activePort = savedPort || t.default_port || 1337;

    const instBadge = isPendingRemove
      ? '<span style="background:#f8514922;color:#f85149;border:1px solid #f8514955;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Removing in 10s...</span>'
      : (isInstalling
        ? '<span style="background:#d2992222;color:#d29922;border:1px solid #d2992255;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Installing...</span>'
        : (t.installed
          ? '<span style="background:#2ea04322;color:#3fb950;border:1px solid #3fb95055;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Installed</span>'
          : '<span style="background:#8b949e22;color:#8b949e;border:1px solid #8b949e55;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Not Installed</span>'));

    const runBadge = (t.installed && !isPendingRemove)
      ? (t.running
        ? `<span style="background:#1f6feb22;color:#58a6ff;border:1px solid #58a6ff55;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Running (PID: ${t.pid})</span>`
        : '<span style="background:#f8514922;color:#f85149;border:1px solid #f8514955;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">Stopped</span>')
      : '';

    return `
      <div style="background:rgba(22, 27, 34, 0.85);border:1px solid rgba(48, 54, 61, 0.9);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:14px;box-shadow:0 4px 12px rgba(0,0,0,0.2);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
          <div style="flex:1;min-width:0;">
            <div style="font-size:16px;font-weight:700;color:#e6edf3;margin-bottom:4px;">${t.name}</div>
            <div style="font-size:12px;color:#8b949e;line-height:1.4;">${t.description || ''}</div>
          </div>
          <div style="flex-shrink:0;display:flex;flex-direction:column;gap:6px;align-items:stretch;min-width:90px;">
            ${(t.installed && !isPendingRemove && !isInstalling)
              ? (!t.running
                ? `<button onclick="pluginAction('${t.id}', 'start')" style="background:#238636;color:#fff;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;white-space:nowrap;">▶ Start</button>`
                : `<button onclick="pluginAction('${t.id}', 'stop')" style="background:#da3633;color:#fff;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;white-space:nowrap;">⏹ Stop</button>`
              ) + getActionBtnHtml(t.id, t.name, activePort)
              : ''
            }
          </div>
        </div>

        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${instBadge}
          ${runBadge}
        </div>

        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;background:rgba(13, 17, 23, 0.7);padding:10px 12px;border-radius:8px;border:1px solid rgba(255,255,255,0.06);">
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;color:#8b949e;font-weight:600;">Port:</label>
            <input type="number" id="port-${t.id}" value="${activePort}" oninput="onPluginPortInput('${t.id}', '${t.name}', this.value)" style="width:76px;background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:5px 8px;border-radius:6px;font-size:12px;font-weight:600;">
          </div>
          <div style="font-size:12px;color:#8b949e;">Endpoint: <code style="color:#79c0ff;background:rgba(121,192,255,0.1);padding:2px 6px;border-radius:4px;">http://127.0.0.1:<span id="ep-${t.id}">${activePort}</span>/v1</code></div>
        </div>

        <!-- Progress & Live Log Container -->
        <div id="prog-wrap-${t.id}" style="display:${isInstalling ? 'flex' : 'none'};flex-direction:column;gap:8px;background:rgba(0,0,0,0.3);padding:12px;border-radius:8px;border:1px solid #30363d;">
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;">
            <span id="prog-stage-${t.id}" style="color:#e6edf3;font-weight:600;">Preparing...</span>
            <span id="prog-pct-${t.id}" style="color:#58a6ff;font-weight:700;">0%</span>
          </div>
          <div style="width:100%;height:8px;background:#21262d;border-radius:4px;overflow:hidden;">
            <div id="prog-bar-${t.id}" style="width:0%;height:100%;background:linear-gradient(90deg,#1f6feb,#3fb950);transition:width 0.3s ease;"></div>
          </div>
          <pre id="prog-logs-${t.id}" style="margin:0;max-height:110px;overflow-y:auto;background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:8px;font-size:11px;color:#8b949e;white-space:pre-wrap;word-break:break-all;font-family:monospace;"></pre>
          <button onclick="cancelPluginInstall('${t.id}')" style="background:#da3633;color:#fff;border:none;padding:7px 12px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">✖ Cancel & Delete Partial Files</button>
        </div>

        <div id="btn-row-${t.id}" style="display:${isInstalling ? 'none' : 'grid'};grid-template-columns:repeat(3, 1fr);gap:8px;">
          ${isPendingRemove
            ? `<button onclick="cancelPluginUninstall()" style="grid-column:1 / -1;background:#30363d;color:#e6edf3;border:1px solid #8b949e66;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;">↩ Undo Uninstall</button>`
            : (!t.installed
              ? `<button onclick="preparePluginInstall('${t.id}')" style="grid-column:1 / -1;background:#238636;color:#fff;border:none;padding:9px 14px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;">⬇ Install Plugin</button>`
              : `
                <button onclick="pluginAction('${t.id}', 'check')" style="background:#21262d;color:#e6edf3;border:1px solid #30363d;padding:8px 6px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:500;">🔍 Check</button>
                <button onclick="pluginAction('${t.id}', 'update')" style="background:#1f6feb;color:#fff;border:none;padding:8px 6px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:600;">🔄 Update</button>
                <button onclick="confirmPluginUninstall('${t.id}', '${t.name}')" style="background:rgba(248,81,73,0.1);color:#f85149;border:1px solid rgba(248,81,73,0.4);padding:8px 6px;border-radius:8px;cursor:pointer;font-size:11px;font-weight:600;">🗑 Uninstall</button>
              `
            )
          }
        </div>
        <div id="msg-${t.id}" style="font-size:12px;display:none;padding:8px 10px;border-radius:6px;background:rgba(255,255,255,0.05);border-left:3px solid #58a6ff;"></div>
      </div>
    `;
  }).join('');
}

// 1. Pre-install check & Confirmation Modal
async function preparePluginInstall(toolId) {
  const msgEl = document.getElementById(`msg-${toolId}`);
  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.style.color = '#e6edf3';
    msgEl.style.borderLeftColor = '#58a6ff';
    msgEl.textContent = 'Checking dependencies and download size...';
  }

  try {
    const res = await fetch('/api/ui/tools/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_id: toolId, action: 'install_plan' })
    });
    const plan = await res.json();
    if (msgEl) msgEl.style.display = 'none';

    if (!plan.ok) {
      if (msgEl) {
        msgEl.style.display = 'block';
        msgEl.style.color = '#f85149';
        msgEl.style.borderLeftColor = '#f85149';
        msgEl.textContent = plan.error || 'Could not prepare install plan.';
      }
      return;
    }

    const listHtml = plan.items.map(i => `<li style="margin-bottom:4px;">${i}</li>`).join('');
    const bodyHtml = `
      <div style="font-size:13px;line-height:1.5;color:#c9d1d9;">
        <div style="margin-bottom:8px;"><b>Estimated Download Size:</b> <span style="color:#3fb950;font-weight:700;">~${plan.estimated_size_mb} MB</span></div>
        <div style="margin-bottom:4px;font-weight:600;">Items to install:</div>
        <ul style="margin:0 0 8px 16px;padding:0;font-size:12px;color:#8b949e;">${listHtml}</ul>
        <div style="font-size:11px;color:#8b949e;">Proceed with installation?</div>
      </div>
    `;

    if (typeof openConfirmModal === 'function') {
      openConfirmModal(
        `Install ${plan.name}`,
        bodyHtml,
        'Install Now',
        () => executePluginInstall(toolId)
      );
    } else {
      executePluginInstall(toolId);
    }
  } catch (err) {
    if (msgEl) {
      msgEl.style.display = 'block';
      msgEl.style.color = '#f85149';
      msgEl.textContent = `Check failed: ${err.message}`;
    }
  }
}

// 2. Start Async Install & Poll Live Progress
async function executePluginInstall(toolId) {
  const wrap = document.getElementById(`prog-wrap-${toolId}`);
  const btnRow = document.getElementById(`btn-row-${toolId}`);
  const msgEl = document.getElementById(`msg-${toolId}`);
  if (wrap) wrap.style.display = 'flex';
  if (btnRow) btnRow.style.display = 'none';
  if (msgEl) msgEl.style.display = 'none';

  try {
    await fetch('/api/ui/tools/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_id: toolId, action: 'install_start' })
    });
    startInstallPolling(toolId);
  } catch (err) {
    if (wrap) wrap.style.display = 'none';
    if (btnRow) btnRow.style.display = 'grid';
    if (msgEl) {
      msgEl.style.display = 'block';
      msgEl.style.color = '#f85149';
      msgEl.textContent = `Start failed: ${err.message}`;
    }
  }
}

function startInstallPolling(toolId) {
  if (pluginInstallPollers[toolId]) clearInterval(pluginInstallPollers[toolId]);

  pluginInstallPollers[toolId] = setInterval(async () => {
    try {
      const res = await fetch(`/api/ui/tools/progress/${toolId}`);
      const prog = await res.json();

      const stageEl = document.getElementById(`prog-stage-${toolId}`);
      const pctEl = document.getElementById(`prog-pct-${toolId}`);
      const barEl = document.getElementById(`prog-bar-${toolId}`);
      const logsEl = document.getElementById(`prog-logs-${toolId}`);

      if (stageEl) stageEl.textContent = prog.stage || 'Installing...';
      if (pctEl) pctEl.textContent = `${prog.progress || 0}%`;
      if (barEl) barEl.style.width = `${prog.progress || 0}%`;
      if (logsEl && prog.logs) {
        logsEl.textContent = prog.logs.join('\n');
        logsEl.scrollTop = logsEl.scrollHeight;
      }

      if (prog.status === 'done' || prog.status === 'error' || prog.status === 'cancelled') {
        clearInterval(pluginInstallPollers[toolId]);
        delete pluginInstallPollers[toolId];

        setTimeout(() => {
          loadPlugins().then(() => {
            const msgEl = document.getElementById(`msg-${toolId}`);
            if (msgEl) {
              msgEl.style.display = 'block';
              msgEl.style.color = prog.status === 'done' ? '#3fb950' : '#f85149';
              msgEl.style.borderLeftColor = prog.status === 'done' ? '#3fb950' : '#f85149';
              msgEl.textContent = prog.stage;
            }
          });
        }, 700);
      }
    } catch (e) {
      // ignore transient poll errors
    }
  }, 800);
}

// 3. Cancel & Cleanup
async function cancelPluginInstall(toolId) {
  const stageEl = document.getElementById(`prog-stage-${toolId}`);
  if (stageEl) stageEl.textContent = 'Cancelling & deleting partial downloads...';

  await fetch('/api/ui/tools/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_id: toolId, action: 'install_cancel' })
  });
}

// 4. Uninstall with Confirm Modal + 10s Undo Toast
function confirmPluginUninstall(toolId, toolName) {
  if (typeof openConfirmModal === 'function') {
    openConfirmModal(
      'Uninstall Plugin',
      `Are you sure you want to uninstall <b>${toolName}</b>?`,
      'Uninstall',
      () => startPluginUninstall(toolId, toolName)
    );
  } else {
    startPluginUninstall(toolId, toolName);
  }
}

function startPluginUninstall(toolId, toolName) {
  if (pendingPluginUninstall) {
    commitPluginUninstall(pendingPluginUninstall);
  }
  pendingPluginUninstall = toolId;
  loadPlugins();

  if (typeof showUndoToast === 'function') {
    const origUndoBtn = document.querySelector('#undo-toast button');
    if (origUndoBtn) {
      origUndoBtn.onclick = cancelPluginUninstall;
    }
    showUndoToast(`Uninstalling '${toolName}' in 10s...`);
  }

  if (pluginUndoTimer) clearTimeout(pluginUndoTimer);
  pluginUndoTimer = setTimeout(() => {
    if (pendingPluginUninstall === toolId) {
      commitPluginUninstall(toolId);
    }
  }, 10000);
}

function cancelPluginUninstall() {
  if (pluginUndoTimer) {
    clearTimeout(pluginUndoTimer);
    pluginUndoTimer = null;
  }
  pendingPluginUninstall = null;
  if (typeof hideUndoToast === 'function') {
    hideUndoToast();
  }
  loadPlugins();
}

async function commitPluginUninstall(toolId) {
  pendingPluginUninstall = null;
  if (pluginUndoTimer) {
    clearTimeout(pluginUndoTimer);
    pluginUndoTimer = null;
  }
  if (typeof hideUndoToast === 'function') {
    hideUndoToast();
  }
  await pluginAction(toolId, 'uninstall');
}

// 5. Connect Plugin to Crouter Standby & Open Model Selection Modal
async function connectPluginToCrouter(toolId, toolName) {
  const msgEl = document.getElementById(`msg-${toolId}`);
  const portInput = document.getElementById(`port-${toolId}`);
  const port = portInput ? parseInt(portInput.value, 10) : 1337;

  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.style.color = '#e6edf3';
    msgEl.style.borderLeftColor = '#58a6ff';
    msgEl.textContent = 'Adding server to Standby & loading models...';
  }

  try {
    const res = await fetch('/api/ui/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: toolId,
        name: toolName || toolId,
        type: 'openai',
        base_url: `http://127.0.0.1:${port}/v1`,
        keys: ['g4f-local'],
        default_model: 'gpt-4o',
        models: ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo', 'claude-3-haiku']
      })
    });
    const data = await res.json();
    if (data.status === 'ok' || res.ok) {
      if (msgEl) {
        msgEl.style.color = '#3fb950';
        msgEl.style.borderLeftColor = '#3fb950';
        msgEl.textContent = `Added '${toolId}' to Standby! Opening Model Selector...`;
      }
      if (typeof fetchConfig === 'function') await fetchConfig();
      loadPlugins();
      if (typeof openModelsSelector === 'function') {
        openModelsSelector(toolId);
      }
    } else {
      throw new Error(data.message || 'Failed to add provider');
    }
  } catch (err) {
    if (msgEl) {
      msgEl.style.color = '#f85149';
      msgEl.style.borderLeftColor = '#f85149';
      msgEl.textContent = `Error: ${err.message}`;
    }
  }
}

// 5b. Update Port in Crouter & Restart Plugin if running
async function updatePluginPortInCrouter(toolId, toolName) {
  const msgEl = document.getElementById(`msg-${toolId}`);
  const portInput = document.getElementById(`port-${toolId}`);
  const port = portInput ? parseInt(portInput.value, 10) : 1337;

  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.style.color = '#e6edf3';
    msgEl.style.borderLeftColor = '#d29922';
    msgEl.textContent = `Updating port to ${port}...`;
  }

  try {
    const cfg = (typeof currentConfig !== 'undefined') ? currentConfig : null;
    const existing = cfg?.providers?.[toolId] || {};
    const res = await fetch('/api/ui/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: toolId,
        name: existing.name || toolName || toolId,
        type: existing.type || 'openai',
        base_url: `http://127.0.0.1:${port}/v1`,
        keys: existing.keys || ['g4f-local'],
        default_model: existing.default_model || 'gpt-4o',
        models: existing.models || ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo', 'claude-3-haiku']
      })
    });
    const data = await res.json();
    if (data.status === 'ok' || res.ok) {
      // Restart plugin on new port if running
      const statusRes = await fetch('/api/ui/tools');
      const statusData = await statusRes.json();
      const toolObj = (statusData.tools || []).find(x => x.id === toolId);
      if (toolObj && toolObj.running) {
        await fetch('/api/ui/tools/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tool_id: toolId, action: 'stop' })
        });
        await fetch('/api/ui/tools/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tool_id: toolId, action: 'start', port: port })
        });
      }
      if (typeof fetchConfig === 'function') await fetchConfig();
      loadPlugins();
      if (msgEl) {
        msgEl.style.color = '#3fb950';
        msgEl.style.borderLeftColor = '#3fb950';
        msgEl.textContent = `Port updated to ${port} successfully!`;
      }
    } else {
      throw new Error(data.message || 'Failed to update port');
    }
  } catch (err) {
    if (msgEl) {
      msgEl.style.color = '#f85149';
      msgEl.style.borderLeftColor = '#f85149';
      msgEl.textContent = `Error: ${err.message}`;
    }
  }
}

function openPluginModelEditor(toolId) {
  if (typeof openModelsSelector === 'function') {
    openModelsSelector(toolId);
  }
}

// 6. General Actions (Start, Stop, Check, Update, Uninstall)
async function pluginAction(toolId, action) {
  const msgEl = document.getElementById(`msg-${toolId}`);
  const portInput = document.getElementById(`port-${toolId}`);
  const port = portInput ? parseInt(portInput.value, 10) : null;

  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.style.color = '#e6edf3';
    msgEl.style.borderLeftColor = '#58a6ff';
    msgEl.textContent = `Running '${action}'... please wait.`;
  }

  try {
    const res = await fetch('/api/ui/tools/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_id: toolId, action: action, port: port })
    });
    const data = await res.json();
    if (msgEl) {
      msgEl.style.color = data.ok ? '#3fb950' : '#f85149';
      msgEl.style.borderLeftColor = data.ok ? '#3fb950' : '#f85149';
      msgEl.textContent = data.message || data.error || JSON.stringify(data);
    }
    if (action !== 'check') {
      setTimeout(loadPlugins, 600);
    }
  } catch (err) {
    if (msgEl) {
      msgEl.style.color = '#f85149';
      msgEl.style.borderLeftColor = '#f85149';
      msgEl.textContent = `Request error: ${err.message}`;
    }
  }
}
