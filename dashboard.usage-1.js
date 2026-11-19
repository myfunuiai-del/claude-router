// dashboard.usage-1.js - Usage & Quotas Tab Renderer & Live Telemetry
// Initializing module namespace
let usagePollInterval = null;

function startUsagePolling() {
  const container = document.getElementById('view-usage');
  if (container && !container.innerHTML.trim()) {
    container.innerHTML = `
      <div class="panel" style="margin-top:12px; padding:16px; text-align:center;">
        <span class="live-pulse-dot"></span>
        <span style="font-size:12px; color:var(--text-muted); font-family:var(--mono);">Loading Usage &amp; Quotas telemetry...</span>
      </div>
    `;
  }
}

function stopUsagePolling() {
  if (usagePollInterval) {
    clearInterval(usagePollInterval);
    usagePollInterval = null;
  }
}
