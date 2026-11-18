// dashboard.chips-1.js - Model chip interaction, default model setting, and long-press promoter
// Modularized per gemini.md Rule 2 (Limit 400-500 lines)

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
