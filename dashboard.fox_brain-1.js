// ========================================================
// C-ROUTER FOX-MECHA AI BRAIN & INTERACTION CONTROLLER
// Centered Modal Window + Triple-Tap Detection
// Dual-Engine: Online (Default) & Local Offline Switcher
// ========================================================

(function() {
  let foxChatHistory = [];
  let isFoxThinking = false;
  let bubbleEl = null;
  let backdropEl = null;
  let pollInstallerTimer = null;
  let currentEngineMode = 'online';

  // Triple-tap tracker variables
  let tapCount = 0;
  let lastTapTime = 0;
  let tapTimer = null;

  function initFoxBrainUI() {
    if (document.getElementById('fox-speech-bubble')) return;

    // 1. Dim Backdrop
    backdropEl = document.createElement('div');
    backdropEl.id = 'fox-bubble-backdrop';
    backdropEl.className = 'fox-bubble-backdrop';
    backdropEl.onclick = window.closeFoxBrain;
    document.body.appendChild(backdropEl);

    // 2. Centered Modal Window
    bubbleEl = document.createElement('div');
    bubbleEl.id = 'fox-speech-bubble';
    bubbleEl.className = 'fox-speech-bubble';
    bubbleEl.innerHTML = `
      <div class="fox-bubble-header">
        <div class="fox-bubble-title">
          <span>🦊 FOX-MECHA AI</span>
          <span class="fox-brain-badge" id="fox-brain-badge">Online</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <!-- Dual Engine Selector Segmented Pill -->
          <div style="display:flex; background:#0e1622; border:1px solid #1f2d42; border-radius:12px; padding:2px; gap:2px;">
            <button type="button" id="btn-mode-online" onclick="switchFoxEngineMode('online')" style="background:#1f4273; color:#fff; border:none; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:600; cursor:pointer;">🌐 Online</button>
            <button type="button" id="btn-mode-local" onclick="switchFoxEngineMode('local')" style="background:none; color:#8b949e; border:none; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:600; cursor:pointer;">🏠 Local</button>
          </div>
          <button type="button" class="btn btn-xs" id="btn-toggle-local-setup" onclick="toggleLocalSetupCard()" title="Offline Local Engine Settings" style="background:#1b2434; border:1px solid #303e54; color:#79c0ff; font-size:10px; padding:2px 6px; border-radius:4px; cursor:pointer;">⚙️</button>
          <button type="button" class="fox-bubble-close" onclick="closeFoxBrain()">✕</button>
        </div>
      </div>

      <!-- ON-DEMAND LOCAL LLM SETUP BANNER / CARD -->
      <div id="fox-local-setup-card" style="display:none; padding:10px 14px; background:#080d14; border-bottom:1px solid #1a273a; font-size:11.5px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <strong style="color:#58a6ff;">🏠 Qwen2.5-0.5B Local Engine (Port 8327)</strong>
          <span id="fox-local-engine-tag" style="font-size:10px; color:#8b949e;">Checking...</span>
        </div>
        <div style="color:#8b949e; line-height:1.4; margin-bottom:8px;">
          ডিফল্টভাবে <strong>🌐 Online Mode</strong> একটিভ থাকে। আপনি চাইলে নিচে থেকে <strong>🏠 Local Brain</strong> ইনস্টল ও রান করে ১০০% অফলাইনে আনলিমিটেড চালাতে পারেন।
        </div>
        <div id="fox-local-progress-wrap" style="display:none; margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; font-size:10px; color:#79c0ff; margin-bottom:3px;">
            <span id="fox-local-step-text">Downloading...</span>
            <span id="fox-local-pct-text">0%</span>
          </div>
          <div style="width:100%; height:6px; background:#1b2434; border-radius:3px; overflow:hidden;">
            <div id="fox-local-progress-bar" style="width:0%; height:100%; background:#238636; transition:width 0.3s ease;"></div>
          </div>
        </div>
        <div id="fox-local-error-box" style="display:none; color:#f85149; font-size:10.5px; margin-bottom:6px;"></div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <button type="button" class="btn btn-xs" id="btn-start-local-download" onclick="startLocalEngineSetup()" style="background:#238636; color:#fff; border:none; padding:4px 10px; border-radius:4px; font-weight:600; cursor:pointer;">⚡ Download & Setup Local Brain</button>
          <button type="button" class="btn btn-xs" id="btn-remove-local-brain" onclick="openConfirmRemoveLocalBrain()" style="display:none; background:#21262d; border:1px solid #da3633; color:#f85149; padding:4px 10px; border-radius:4px; font-weight:600; cursor:pointer;">🗑️ Remove Local Brain</button>
        </div>
      </div>

      <div class="fox-chat-log" id="fox-chat-log">
        <div class="fox-msg-row">
          <div class="fox-msg bot">হেই! আমি ফক্স মেচা 🦊⚡ Claude Router-এর নিউরাল অ্যাসিস্ট্যান্ট! কিছু জানতে চাও নাকি?</div>
        </div>
      </div>
      <form class="fox-chat-input-bar" onsubmit="handleFoxChatSubmit(event)">
        <input type="text" id="fox-user-input" class="fox-chat-input" placeholder="ফক্সকে কিছু জিজ্ঞেস করুন..." autocomplete="off" />
        <button type="submit" class="fox-chat-send" id="fox-send-btn">➤</button>
      </form>
    `;
    document.body.appendChild(bubbleEl);
  }

  window.switchFoxEngineMode = async function(mode) {
    currentEngineMode = mode;
    const btnOnline = document.getElementById('btn-mode-online');
    const btnLocal = document.getElementById('btn-mode-local');
    if (btnOnline && btnLocal) {
      if (mode === 'online') {
        btnOnline.style.background = '#1f4273';
        btnOnline.style.color = '#fff';
        btnLocal.style.background = 'none';
        btnLocal.style.color = '#8b949e';
      } else {
        btnLocal.style.background = '#238636';
        btnLocal.style.color = '#fff';
        btnOnline.style.background = 'none';
        btnOnline.style.color = '#8b949e';
      }
    }
    try {
      await fetch('/api/ui/fox-local/set-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode })
      });
      checkLocalEngineStatus();
    } catch (e) {}
  };

  window.toggleLocalSetupCard = function() {
    const card = document.getElementById('fox-local-setup-card');
    if (!card) return;
    const isShown = card.style.display !== 'none';
    card.style.display = isShown ? 'none' : 'block';
    if (!isShown) {
      checkLocalEngineStatus();
    }
  };

  async function checkLocalEngineStatus() {
    try {
      const res = await fetch('/api/ui/fox-local/status', { method: 'POST', body: '{}' });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        const d = data.data;
        currentEngineMode = d.mode || 'online';
        
        // Update header segment styling & badge
        const btnOnline = document.getElementById('btn-mode-online');
        const btnLocal = document.getElementById('btn-mode-local');
        const badge = document.getElementById('fox-brain-badge');
        if (btnOnline && btnLocal) {
          if (currentEngineMode === 'online') {
            btnOnline.style.background = '#1f4273';
            btnOnline.style.color = '#fff';
            btnLocal.style.background = 'none';
            btnLocal.style.color = '#8b949e';
            if (badge && badge.innerText === 'Local') badge.innerText = 'Online';
          } else {
            btnLocal.style.background = '#238636';
            btnLocal.style.color = '#fff';
            btnOnline.style.background = 'none';
            btnOnline.style.color = '#8b949e';
            if (badge) badge.innerText = d.running ? 'Local' : 'Local (Off)';
          }
        }

        const tag = document.getElementById('fox-local-engine-tag');
        const btn = document.getElementById('btn-start-local-download');
        const btnRemove = document.getElementById('btn-remove-local-brain');
        const progWrap = document.getElementById('fox-local-progress-wrap');
        const stepText = document.getElementById('fox-local-step-text');
        const pctText = document.getElementById('fox-local-pct-text');
        const bar = document.getElementById('fox-local-progress-bar');
        const errBox = document.getElementById('fox-local-error-box');

        if (d.running) {
          if (tag) { tag.innerText = '🟢 Running on Port 8327' + (d.lora_installed ? ' + Bengali LoRA' : ''); tag.style.color = '#56d364'; }
          if (btn) { btn.innerText = '✓ Local Engine Active'; btn.disabled = true; btn.style.background = '#1b2434'; }
          if (btnRemove) { btnRemove.style.display = 'inline-block'; }
          if (progWrap) progWrap.style.display = 'none';
        } else if (d.installed) {
          if (tag) { tag.innerText = '🟡 Installed (Ready to Run)'; tag.style.color = '#e3b341'; }
          if (btn) { btn.innerText = '▶ Start Local Engine'; btn.disabled = false; btn.style.background = '#238636'; }
          if (btnRemove) { btnRemove.style.display = 'inline-block'; }
        } else {
          if (tag) { tag.innerText = '⚪ Not Installed'; tag.style.color = '#8b949e'; }
          if (btn) { btn.innerText = '⚡ Download & Setup Local Brain'; btn.disabled = false; btn.style.background = '#238636'; }
          if (btnRemove) { btnRemove.style.display = 'none'; }
        }

        const prog = d.progress;
        if (prog && prog.status && prog.status !== 'idle' && prog.status !== 'ready') {
          if (progWrap) progWrap.style.display = 'block';
          if (stepText) stepText.innerText = prog.step || 'Processing...';
          if (pctText) pctText.innerText = (prog.percent || 0) + '%';
          if (bar) bar.style.width = (prog.percent || 0) + '%';
          if (btn) btn.disabled = true;

          if (prog.status === 'error' && errBox) {
            errBox.style.display = 'block';
            errBox.innerText = prog.error_message || 'Setup encountered an error';
            if (btn) btn.disabled = false;
          }
        }
      }
    } catch (e) {}
  }

  window.startLocalEngineSetup = async function() {
    const btn = document.getElementById('btn-start-local-download');
    const progWrap = document.getElementById('fox-local-progress-wrap');
    const errBox = document.getElementById('fox-local-error-box');
    if (btn) btn.disabled = true;
    if (progWrap) progWrap.style.display = 'block';
    if (errBox) errBox.style.display = 'none';

    try {
      await fetch('/api/ui/fox-local/start-install', { method: 'POST', body: '{}' });
      if (pollInstallerTimer) clearInterval(pollInstallerTimer);
      pollInstallerTimer = setInterval(async () => {
        await checkLocalEngineStatus();
        const tag = document.getElementById('fox-local-engine-tag');
        if (tag && tag.innerText.includes('Running')) {
          clearInterval(pollInstallerTimer);
          pollInstallerTimer = null;
        }
      }, 1500);
    } catch (err) {
      if (errBox) {
        errBox.style.display = 'block';
        errBox.innerText = 'Failed: ' + err.message;
      }
      if (btn) btn.disabled = false;
    }
  };

  window.openConfirmRemoveLocalBrain = function() {
    if (typeof openConfirmModal === 'function') {
      openConfirmModal(
        'Remove Local Brain Model',
        `Are you sure you want to remove the local <strong>Qwen2.5-0.5B</strong> model file (~320MB)?<br>
         <span style="color:var(--text-muted); font-size:11px; margin-top:4px; display:inline-block;">
           Fox-Mecha will switch back to <strong>🌐 Online Mode</strong>. You will have 10 seconds to undo this action.
         </span>`,
        'Remove Local Brain',
        () => {
          if (typeof startLocalBrainDeletion === 'function') {
            startLocalBrainDeletion();
          }
        }
      );
    } else {
      if (confirm('Are you sure you want to remove the local brain model file?')) {
        fetch('/api/ui/fox-local/remove', { method: 'POST', body: '{}' })
          .then(() => checkLocalEngineStatus());
      }
    }
  };

  window.openFoxBrain = function() {
    initFoxBrainUI();
    const b = document.getElementById('fox-speech-bubble');
    const bd = document.getElementById('fox-bubble-backdrop');
    if (b) b.classList.add('is-open');
    if (bd) bd.classList.add('is-open');

    checkLocalEngineStatus();

    const input = document.getElementById('fox-user-input');
    if (input) {
      setTimeout(() => input.focus(), 180);
    }

    const bot = document.getElementById('crouter-bot');
    if (bot) {
      bot.classList.remove('is-waving');
      void bot.offsetWidth;
      bot.classList.add('is-waving');
      setTimeout(() => bot.classList.remove('is-waving'), 950);
    }
  };

  window.closeFoxBrain = function() {
    const b = document.getElementById('fox-speech-bubble');
    const bd = document.getElementById('fox-bubble-backdrop');
    if (b) b.classList.remove('is-open');
    if (bd) bd.classList.remove('is-open');
    if (pollInstallerTimer) {
      clearInterval(pollInstallerTimer);
      pollInstallerTimer = null;
    }
  };

  window.toggleFoxBrain = function() {
    const b = document.getElementById('fox-speech-bubble');
    if (b && b.classList.contains('is-open')) {
      window.closeFoxBrain();
    } else {
      window.openFoxBrain();
    }
  };

  // Intercept triggerBotReaction with Triple-Tap Logic
  const originalTrigger = window.triggerBotReaction;
  window.triggerBotReaction = function() {
    const now = Date.now();
    const diff = now - lastTapTime;
    lastTapTime = now;

    if (diff < 500) {
      tapCount++;
    } else {
      tapCount = 1;
    }

    if (tapTimer) clearTimeout(tapTimer);

    if (tapCount >= 3) {
      tapCount = 0;
      window.openFoxBrain();
      return;
    }

    tapTimer = setTimeout(() => {
      tapCount = 0;
      if (typeof originalTrigger === 'function') {
        try { originalTrigger(); } catch (e) {}
      }
    }, 380);
  };

  window.handleFoxChatSubmit = async function(e) {
    if (e) e.preventDefault();
    if (isFoxThinking) return;

    const input = document.getElementById('fox-user-input');
    const msg = (input ? input.value : '').trim();
    if (!msg) return;

    input.value = '';
    appendFoxMessage(msg, 'user');

    isFoxThinking = true;
    const sendBtn = document.getElementById('fox-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    const bot = document.getElementById('crouter-bot');
    if (bot) bot.classList.add('is-impatient');

    const thinkingId = appendFoxThinking();

    try {
      const res = await fetch('/api/fox/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          history: foxChatHistory,
          mode: currentEngineMode
        })
      });
      const data = await res.json();
      removeFoxThinking(thinkingId);

      if (res.ok && (data.status === 'ok' || data.reply)) {
        appendFoxMessage(data.reply, 'bot');
        foxChatHistory.push({ role: 'user', content: msg });
        foxChatHistory.push({ role: 'assistant', content: data.reply });

        const badge = document.getElementById('fox-brain-badge');
        const brainName = data.provider || data.brain || (data.mode === 'local' ? 'Local' : 'Online');
        if (badge && brainName) {
          badge.innerText = brainName.split(' ')[0];
        }

        if (data.action && typeof window.executeFoxSandboxAction === 'function') {
          window.executeFoxSandboxAction(data.action);
        }

        if (bot) {
          bot.classList.remove('is-impatient');
          bot.classList.add('is-settling');
          setTimeout(() => bot.classList.remove('is-settling'), 800);
        }
      } else {
        appendFoxMessage(data.message || 'উফ! ব্রেইনে এরর এসেছে।', 'bot');
        if (bot) bot.classList.remove('is-impatient');
      }
    } catch (err) {
      removeFoxThinking(thinkingId);
      appendFoxMessage('কানেকশন সমস্যা: ' + err.message, 'bot');
      if (bot) bot.classList.remove('is-impatient');
    } finally {
      isFoxThinking = false;
      if (sendBtn) sendBtn.disabled = false;
      if (input) input.focus();
    }
  };

  function appendFoxMessage(text, role) {
    const log = document.getElementById('fox-chat-log');
    if (!log) return;
    const row = document.createElement('div');
    row.className = 'fox-msg-row';
    const bubble = document.createElement('div');
    bubble.className = `fox-msg ${role}`;
    bubble.innerText = text;
    row.appendChild(bubble);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function appendFoxThinking() {
    const log = document.getElementById('fox-chat-log');
    if (!log) return null;
    const id = 'thinking-' + Date.now();
    const row = document.createElement('div');
    row.className = 'fox-msg-row';
    row.id = id;
    row.innerHTML = `
      <div class="fox-msg bot">
        <div class="fox-thinking-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return id;
  }

  function removeFoxThinking(id) {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  document.addEventListener('DOMContentLoaded', () => {
    initFoxBrainUI();
  });
})();
