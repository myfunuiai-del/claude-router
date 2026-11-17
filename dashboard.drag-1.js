// Touch event listener for smooth mobile drag-and-drop
function setupCardTouchDrag(handle, card) {
  let isDragging = false;

  handle.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    isDragging = true;
    card.classList.add('is-dragging');
    e.stopPropagation();
  }, { passive: false });

  handle.addEventListener('touchmove', (e) => {
    if (!isDragging || e.touches.length !== 1) return;
    e.preventDefault(); // Stop screen scroll while dragging
    const touch = e.touches[0];
    const elemBelow = document.elementFromPoint(touch.clientX, touch.clientY);
    if (!elemBelow) return;

    const laneBody = elemBelow.closest('.lane-body');
    if (laneBody) {
      const afterElement = getDragAfterElement(laneBody, touch.clientY);
      if (afterElement == null) {
        laneBody.appendChild(card);
      } else if (afterElement !== card) {
        laneBody.insertBefore(card, afterElement);
      }
      updatePriorityBadges();
    }
  }, { passive: false });

  const finishTouch = () => {
    if (isDragging) {
      isDragging = false;
      card.classList.remove('is-dragging');
      saveDomOrderAndSync();
    }
  };

  handle.addEventListener('touchend', finishTouch);
  handle.addEventListener('touchcancel', finishTouch);
}

// Determine insertion position based on mouse/touch vertical coordinate
function getDragAfterElement(container, y) {
  const cards = [...container.querySelectorAll('.server-card:not(.is-dragging)')];
  return cards.reduce((closest, child) => {
    const box = child.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) {
      return { offset: offset, element: child };
    } else {
      return closest;
    }
  }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function setupContainerDragListeners(container) {
  container.ondragover = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    container.classList.add('drag-over');
    const dragging = document.querySelector('.is-dragging');
    if (!dragging) return;
    const afterElement = getDragAfterElement(container, e.clientY);
    if (afterElement == null) {
      container.appendChild(dragging);
    } else if (afterElement !== dragging) {
      container.insertBefore(dragging, afterElement);
    }
    updatePriorityBadges();
  };

  container.ondragleave = (e) => {
    container.classList.remove('drag-over');
  };

  container.ondrop = (e) => {
    e.preventDefault();
    container.classList.remove('drag-over');
    saveDomOrderAndSync();
  };
}

// Up / Down Priority Buttons
function moveCardUp(id) {
  const card = document.getElementById(`server-card-${id}`);
  if (!card || !card.parentElement) return;
  const prev = card.previousElementSibling;
  if (prev && prev.classList.contains('server-card')) {
    card.parentElement.insertBefore(card, prev);
    saveDomOrderAndSync();
  }
}

function moveCardDown(id) {
  const card = document.getElementById(`server-card-${id}`);
  if (!card || !card.parentElement) return;
  const next = card.nextElementSibling;
  if (next && next.classList.contains('server-card')) {
    card.parentElement.insertBefore(next, card);
    saveDomOrderAndSync();
  }
}

// Quick Move between Routed Pipeline and Standby Pool
function moveLaneQuick(id) {
  const card = document.getElementById(`server-card-${id}`);
  if (!card || !card.parentElement) return;
  const currentContainer = card.parentElement;
  const isCurrentlyRouted = currentContainer.id === 'container-routed';
  const targetContainer = document.getElementById(isCurrentlyRouted ? 'container-unrouted' : 'container-routed');
  
  targetContainer.appendChild(card);
  saveDomOrderAndSync();
}

// Update Visual Priority Badges and Button States in Real-Time
function updatePriorityBadges() {
  const cRouted = document.getElementById('container-routed');
  if (!cRouted) return;
  const routedCards = [...cRouted.querySelectorAll('.server-card')];
  const countRoutedEl = document.getElementById('count-routed');
  if (countRoutedEl) countRoutedEl.innerText = `${routedCards.length} Active`;

  // Clear empty message if has cards
  const emptyRouted = cRouted.querySelector('.lane-empty');
  if (routedCards.length > 0 && emptyRouted) emptyRouted.remove();

  routedCards.forEach((card, idx) => {
    const isOff = card.classList.contains('server-off');
    const slot = card.querySelector('.priority-badge-slot');
    if (slot) {
      if (isOff) {
        slot.innerHTML = '<span class="prio-tag prio-off">OFF</span>';
      } else if (idx === 0) {
        slot.innerHTML = '<span class="prio-tag prio-1">#1 PRIMARY</span>';
      } else if (idx === 1) {
        slot.innerHTML = '<span class="prio-tag prio-2">#2 FALLBACK 1</span>';
      } else if (idx === 2) {
        slot.innerHTML = '<span class="prio-tag prio-3">#3 FALLBACK 2</span>';
      } else {
        slot.innerHTML = `<span class="prio-tag prio-n">#${idx+1} FALLBACK ${idx}</span>`;
      }
    }
    const btnUp = card.querySelector('.btn-up');
    const btnDown = card.querySelector('.btn-down');
    if (btnUp) btnUp.disabled = (idx === 0);
    if (btnDown) btnDown.disabled = (idx === routedCards.length - 1);

    const btnLane = card.querySelector('.btn-lane-toggle');
    if (btnLane) {
      btnLane.innerText = '💤 Standby';
      btnLane.title = 'Move to Standby Pool';
    }
  });

  const cUnrouted = document.getElementById('container-unrouted');
  if (!cUnrouted) return;
  const unroutedCards = [...cUnrouted.querySelectorAll('.server-card')];
  const countUnroutedEl = document.getElementById('count-unrouted');
  if (countUnroutedEl) countUnroutedEl.innerText = `${unroutedCards.length} Standby`;

  // Clear empty message if has cards
  const emptyUnrouted = cUnrouted.querySelector('.lane-empty');
  if (unroutedCards.length > 0 && emptyUnrouted) emptyUnrouted.remove();

  unroutedCards.forEach((card, idx) => {
    const isOff = card.classList.contains('server-off');
    const slot = card.querySelector('.priority-badge-slot');
    if (slot) {
      slot.innerHTML = isOff
        ? '<span class="prio-tag prio-off">OFF</span>'
        : '<span class="prio-tag prio-standby">STANDBY</span>';
    }
    const btnUp = card.querySelector('.btn-up');
    const btnDown = card.querySelector('.btn-down');
    if (btnUp) btnUp.disabled = (idx === 0);
    if (btnDown) btnDown.disabled = (idx === unroutedCards.length - 1);

    const btnLane = card.querySelector('.btn-lane-toggle');
    if (btnLane) {
      btnLane.innerText = '⚡ Route';
      btnLane.title = 'Move to Active Routed Pipeline';
    }
  });
}

// Read visual order from DOM and sync to backend API
async function saveDomOrderAndSync() {
  const cRouted = document.getElementById('container-routed');
  const cUnrouted = document.getElementById('container-unrouted');
  if (!cRouted || !cUnrouted || !currentConfig) return;

  const routed = [...cRouted.querySelectorAll('.server-card')].map(c => c.dataset.providerId).filter(Boolean);
  const unrouted = [...cUnrouted.querySelectorAll('.server-card')].map(c => c.dataset.providerId).filter(Boolean);

  updatePriorityBadges();

  currentConfig.routed_providers = routed;
  currentConfig.unrouted_providers = unrouted;
  if (routed.length > 0) currentConfig.active_provider = routed[0];

  try {
    const res = await fetch('/api/ui/route-pool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        routed_providers: routed,
        unrouted_providers: unrouted,
        active_provider: routed[0] || ''
      })
    });
    const data = await res.json();
    if (res.ok) {
      const primaryName = currentConfig.providers[routed[0]]?.name || routed[0] || 'None';
      showToast(`Priority updated: #1 ${primaryName} (${routed.length} active)`);
      currentConfig = data.config;
      fetchStatus();
    }
  } catch (err) {
    showToast('Error saving priority order', true);
  }
}
