async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  return res.json();
}

async function refresh() {
  const res = await fetch("/api/status");
  const s = await res.json();

  document.getElementById("osBadge").textContent = `OPENSEARCH: ${s.opensearch_ok ? "OK" : "DOWN"}`;
  document.getElementById("osBadge").className = `badge ${s.opensearch_ok ? "ok" : "down"}`;

  document.getElementById("connectivityPill").textContent = s.connectivity;
  document.getElementById("connectivityPill").style.color = s.connectivity === "ONLINE" ? "var(--ok)" : "var(--bad)";
  document.getElementById("connectivityPill").style.borderColor = s.connectivity === "ONLINE" ? "rgba(46,229,157,.35)" : "rgba(255,92,122,.35)";

  document.getElementById("streamStatus").textContent = s.stream_running ? "RUNNING" : "STOPPED";
  document.getElementById("lastTelemetry").textContent = s.last_telemetry_iso || "—";
  document.getElementById("lastHeartbeat").textContent = s.last_heartbeat_iso || "—";

  document.getElementById("telemetryInterval").textContent = `${s.telemetry_interval_s}s`;
  document.getElementById("heartbeatInterval").textContent = `${s.heartbeat_interval_s}s`;
  document.getElementById("targetIndex").textContent = s.target_index;
  document.getElementById("datasetPos").textContent = s.dataset_position;

  document.getElementById("totalMessages").textContent = s.total_messages;
  document.getElementById("attackedMessages").textContent = s.attacked_messages;
}

document.getElementById("btnStart").addEventListener("click", async () => {
  await post("/api/stream/start");
  await refresh();
});

document.getElementById("btnStop").addEventListener("click", async () => {
  await post("/api/stream/stop");
  await refresh();
});

document.getElementById("btnAttack").addEventListener("click", async () => {
  const profile = document.getElementById("attackProfile").value;
  const messages_to_affect = parseInt(document.getElementById("attackMessages").value || "10", 10);
  const duration_s = parseInt(document.getElementById("attackDuration").value || "30", 10);

  if (!profile) return;

  await post("/api/attack/trigger", { profile, duration_s, messages_to_affect });
  document.getElementById("attackInfo").textContent = `Triggered: ${profile} (duration=${duration_s}s, messages=${messages_to_affect})`;
});

refresh();
setInterval(refresh, 2000);
