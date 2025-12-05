// dashboard.js
// Frontend logic for WindTurbineSim dashboard

const API_BASE = ""; // same origin

let autoTickTimer = null;
let lastKnownStreamStatus = null;

// -------------------------
// Helper functions
// -------------------------

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

async function apiPost(path, body = null) {
  const options = {
    method: "POST",
    headers: {},
  };
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(API_BASE + path, options);
  if (!res.ok) {
    let msg = `POST ${path} failed: ${res.status}`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        msg += ` (${data.detail})`;
      }
    } catch (_) {
      // ignore JSON parse error
    }
    throw new Error(msg);
  }
  return res.json();
}

function formatDateTime(value) {
  if (!value) return "–";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value; // fallback raw
    return d.toLocaleString();
  } catch {
    return value;
  }
}

function clearBadgeClasses(el) {
  el.classList.remove(
    "badge-neutral",
    "badge-success",
    "badge-warning",
    "badge-danger",
  );
}

function setBadge(el, text, tone = "neutral") {
  clearBadgeClasses(el);
  const cls =
    tone === "success"
      ? "badge-success"
      : tone === "warning"
      ? "badge-warning"
      : tone === "danger"
      ? "badge-danger"
      : "badge-neutral";
  el.classList.add("badge", cls);
  el.textContent = text;
}

// -------------------------
// Auto-tick handling
// -------------------------

function handleAutoTickForStatus(status) {
  if (status === lastKnownStreamStatus) {
    return; // no change
  }

  lastKnownStreamStatus = status;

  if (status === "RUNNING") {
    // Start auto-ticking if not already
    if (!autoTickTimer) {
      autoTickTimer = setInterval(async () => {
        try {
          await apiPost("/stream/tick");
          await refreshStatus();
          await refreshAttackEvents();
        } catch (err) {
          console.error("Auto tick failed:", err);
        }
      }, 1000); // tick every 1 second (simulation speed)
    }
  } else {
    // Stop auto-ticking
    if (autoTickTimer) {
      clearInterval(autoTickTimer);
      autoTickTimer = null;
    }
  }
}

// -------------------------
// UI updates: streaming status
// -------------------------

async function refreshStatus() {
  let data;
  try {
    data = await apiGet("/stream/status");
  } catch (err) {
    console.error(err);
    const streamBadge = document.getElementById("stream-status-badge");
    const connBadge = document.getElementById("connectivity-status-badge");
    const osBadge = document.getElementById("opensearch-status-badge");
    if (streamBadge) setBadge(streamBadge, "ERROR", "danger");
    if (connBadge) setBadge(connBadge, "UNKNOWN", "neutral");
    if (osBadge) setBadge(osBadge, "OFFLINE", "danger");
    return;
  }

  const streamBadge = document.getElementById("stream-status-badge");
  const connBadge = document.getElementById("connectivity-status-badge");
  const osBadge = document.getElementById("opensearch-status-badge");

  const lastTelemetryEl = document.getElementById("last-telemetry");
  const lastHeartbeatEl = document.getElementById("last-heartbeat");

  const cfgDataIntervalEl = document.getElementById("cfg-data-interval");
  const cfgHeartbeatIntervalEl = document.getElementById(
    "cfg-heartbeat-interval",
  );
  const cfgModeEl = document.getElementById("cfg-mode");
  const cfgIndexEl = document.getElementById("cfg-index");

  const queueSizeEl = document.getElementById("queue-size");
  const datasetPosEl = document.getElementById("dataset-position");

  const metricTotalEl = document.getElementById("metric-total-messages");
  const metricAttackedEl = document.getElementById(
    "metric-attacked-messages",
  );
  const metricStartedEl = document.getElementById("metric-started-at");
  const metricUpdatedEl = document.getElementById("metric-updated-at");

  const statusStr = data.status || "UNKNOWN";
  if (streamBadge) {
    let tone = "neutral";
    if (statusStr === "RUNNING") tone = "success";
    else if (statusStr === "ERROR") tone = "danger";
    setBadge(streamBadge, statusStr, tone);
  }

  const connStr = data.connectivity_status || "UNKNOWN";
  if (connBadge) {
    let tone = "neutral";
    if (connStr === "ONLINE") tone = "success";
    else if (connStr === "DEGRADED") tone = "warning";
    else if (connStr === "OFFLINE") tone = "danger";
    setBadge(connBadge, connStr, tone);
  }

  if (osBadge) {
    const connected = !!data.opensearch_connected;
    const label = connected ? "OpenSearch: OK" : "OpenSearch: OFFLINE";
    const tone = connected ? "success" : "danger";
    setBadge(osBadge, label, tone);

    if (data.opensearch_last_error && !connected) {
      osBadge.title = data.opensearch_last_error;
    } else {
      osBadge.removeAttribute("title");
    }
  }

  handleAutoTickForStatus(statusStr);

  if (lastTelemetryEl) {
    lastTelemetryEl.textContent = formatDateTime(
      data.last_telemetry_sent_at,
    );
  }
  if (lastHeartbeatEl) {
    lastHeartbeatEl.textContent = formatDateTime(
      data.last_heartbeat_sent_at,
    );
  }

  const cfg = data.config || {};
  if (cfgDataIntervalEl && typeof cfg.data_interval_seconds === "number") {
    cfgDataIntervalEl.textContent = `${cfg.data_interval_seconds}s`;
  }
  if (
    cfgHeartbeatIntervalEl &&
    typeof cfg.heartbeat_interval_seconds === "number"
  ) {
    cfgHeartbeatIntervalEl.textContent = `${cfg.heartbeat_interval_seconds}s`;
  }
  if (cfgModeEl && cfg.mode) {
    cfgModeEl.textContent = cfg.mode;
  }
  if (cfgIndexEl && (cfg.target_index || data.opensearch_index)) {
    cfgIndexEl.textContent = cfg.target_index || data.opensearch_index;
  }

  if (queueSizeEl) {
    queueSizeEl.textContent = "n/a";
  }

  if (
    datasetPosEl &&
    typeof data.current_dataset_position === "number"
  ) {
    datasetPosEl.textContent = data.current_dataset_position.toString();
  }

  if (
    metricTotalEl &&
    typeof data.total_messages_sent === "number"
  ) {
    metricTotalEl.textContent = data.total_messages_sent.toString();
  }
  if (
    metricAttackedEl &&
    typeof data.total_attacked_messages === "number"
  ) {
    metricAttackedEl.textContent = data.total_attacked_messages.toString();
  }

  if (metricStartedEl) metricStartedEl.textContent = "–";
  if (metricUpdatedEl)
    metricUpdatedEl.textContent = new Date().toLocaleString();
}

// -------------------------
// UI updates: attack profiles & events
// -------------------------

async function loadAttackProfiles() {
  const select = document.getElementById("attack-profile-select");
  if (!select) return;

  try {
    const profiles = await apiGet("/attack/profiles");
    select.innerHTML = "";

    if (!Array.isArray(profiles) || profiles.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No attack profiles available";
      select.appendChild(opt);
      return;
    }

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select an attack profile…";
    select.appendChild(placeholder);

    for (const p of profiles) {
      const opt = document.createElement("option");
      opt.value = p.attack_profile_id;
      opt.textContent = p.name;
      opt.dataset.category = p.attack_category;
      opt.dataset.durationMode = p.duration_mode;
      select.appendChild(opt);
    }
  } catch (err) {
    console.error("Failed to load attack profiles:", err);
    select.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Error loading profiles";
    select.appendChild(opt);
  }
}

function updateAttackSummaryFromEvent(event) {
  if (!event) return;

  const idEl = document.getElementById("last-attack-id");
  const profileEl = document.getElementById("last-attack-profile");
  const statusEl = document.getElementById("last-attack-status");
  const affectedEl = document.getElementById("last-attack-affected");
  const windowEl = document.getElementById("last-attack-window");

  if (idEl) idEl.textContent = event.attack_event_id;
  if (profileEl) profileEl.textContent = event.profile_name;
  if (affectedEl)
    affectedEl.textContent = event.affected_messages_count.toString();

  if (statusEl) {
    let tone = "neutral";
    if (event.status === "ACTIVE") tone = "success";
    else if (event.status === "COMPLETED") tone = "neutral";
    else if (event.status === "CANCELLED") tone = "warning";
    setBadge(statusEl, event.status, tone);
  }

  if (windowEl) {
    const start = formatDateTime(event.start_time);
    const end = event.end_time ? formatDateTime(event.end_time) : "ongoing";
    windowEl.textContent = `${start} → ${end}`;
  }
}

async function refreshAttackEvents() {
  let events;
  try {
    events = await apiGet("/attack/events");
  } catch (err) {
    console.error("Failed to load attack events:", err);
    return;
  }

  if (!Array.isArray(events)) return;

  const tbody = document.getElementById("attack-events-body");
  if (tbody) {
    tbody.innerHTML = "";
    for (const ev of events) {
      const tr = document.createElement("tr");

      const tdId = document.createElement("td");
      tdId.textContent = ev.attack_event_id;

      const tdProfile = document.createElement("td");
      tdProfile.textContent = ev.profile_name;

      const tdStatus = document.createElement("td");
      tdStatus.textContent = ev.status;

      const tdAffected = document.createElement("td");
      tdAffected.textContent = ev.affected_messages_count.toString();

      const tdStart = document.createElement("td");
      tdStart.textContent = formatDateTime(ev.start_time);

      const tdEnd = document.createElement("td");
      tdEnd.textContent = formatDateTime(ev.end_time);

      tr.appendChild(tdId);
      tr.appendChild(tdProfile);
      tr.appendChild(tdStatus);
      tr.appendChild(tdAffected);
      tr.appendChild(tdStart);
      tr.appendChild(tdEnd);

      tbody.appendChild(tr);
    }
  }

  // Update "last attack" summary with the last event, if any
  if (events.length > 0) {
    const lastEvent = events[events.length - 1];
    updateAttackSummaryFromEvent(lastEvent);
  }
}

// -------------------------
// Event handlers
// -------------------------

function attachEventHandlers() {
  const btnStart = document.getElementById("btn-start-stream");
  const btnStop = document.getElementById("btn-stop-stream");
  const btnRefreshStatus = document.getElementById("btn-refresh-status");
  const btnTriggerAttack = document.getElementById("btn-trigger-attack");

  if (btnStart) {
    btnStart.addEventListener("click", async () => {
      try {
        await apiPost("/stream/start");
        await refreshStatus();
      } catch (err) {
        console.error(err);
      }
    });
  }

  if (btnStop) {
    btnStop.addEventListener("click", async () => {
      try {
        await apiPost("/stream/stop");
        await refreshStatus();
      } catch (err) {
        console.error(err);
      }
    });
  }

  if (btnRefreshStatus) {
    btnRefreshStatus.addEventListener("click", async () => {
      await refreshStatus();
      await refreshAttackEvents();
    });
  }

  if (btnTriggerAttack) {
    btnTriggerAttack.addEventListener("click", async (event) => {
      event.preventDefault();
      const feedbackEl = document.getElementById("attack-feedback");
      const profileSelect = document.getElementById("attack-profile-select");
      const messagesInput = document.getElementById(
        "attack-messages-to-affect",
      );
      const durationInput = document.getElementById(
        "attack-duration-seconds",
      );

      if (!profileSelect || !profileSelect.value) {
        if (feedbackEl) {
          feedbackEl.textContent = "Select an attack profile first.";
        }
        return;
      }

      const payload = {
        attack_profile_id: profileSelect.value,
        messages_to_affect: null,
        duration_seconds: null,
        triggered_by: "ui",
      };

      const messagesVal = messagesInput && messagesInput.value.trim();
      if (messagesVal) {
        const n = Number(messagesVal);
        if (!Number.isNaN(n) && n > 0) {
          payload.messages_to_affect = n;
        }
      }

      const durationVal = durationInput && durationInput.value.trim();
      if (durationVal) {
        const d = Number(durationVal);
        if (!Number.isNaN(d) && d > 0) {
          payload.duration_seconds = d;
        }
      }

      try {
        const resp = await apiPost("/attack/trigger", payload);
        if (feedbackEl) {
          feedbackEl.textContent = `Attack triggered: ${resp.profile_name} (${resp.status})`;
        }
        updateAttackSummaryFromEvent(resp);
        await refreshAttackEvents();
      } catch (err) {
        console.error("Failed to trigger attack:", err);
        if (feedbackEl) {
          feedbackEl.textContent =
            "Error triggering attack (see console).";
        }
      }
    });
  }
}

// -------------------------
// Initialisation
// -------------------------

async function initDashboard() {
  attachEventHandlers();
  await loadAttackProfiles();
  await refreshStatus();
  await refreshAttackEvents();

  // Extra periodic refresh (on top of auto-tick)
  setInterval(async () => {
    await refreshStatus();
    await refreshAttackEvents();
  }, 3000);
}

document.addEventListener("DOMContentLoaded", () => {
  initDashboard().catch((err) => {
    console.error("Failed to initialise dashboard:", err);
  });
});
