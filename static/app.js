/**
 * Digital Twin Sanctuary — Nexus Lens Client
 * ============================================
 * Connects to the NetworkGraftServer WebSocket, receives STATE_UPDATE
 * messages, and drives the dashboard + SVG animation states.
 */

const WS_URL = `ws://${location.host}/graft`;

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS  = 30000;

// ---- DOM refs ----
const connectionBadge = document.getElementById("connection-badge");
const stateBadge      = document.getElementById("state-badge");
const statStreams      = document.getElementById("stat-streams");
const statFrictions   = document.getElementById("stat-frictions");
const statFootprints  = document.getElementById("stat-footprints");
const telemetryFeed   = document.getElementById("telemetry-feed");
const frictionFeed    = document.getElementById("friction-feed");
const stateLog        = document.getElementById("state-log");
const svgContainer    = document.getElementById("svg-container");
const reactorHeart    = document.getElementById("reactor-heart");
const sensorNodes     = document.querySelectorAll(".sensor-node");
const flowDots        = document.querySelectorAll(".flow-dot");

let reconnectAttempt = 0;
let ws = null;

// ---- State → visual mapping ----
const STATE_COLORS = {
  SYNCED:         { badge: "text-green-400",  svgClass: "golden-halo",       heart: "#f59e0b", node: "#f59e0b" },
  DRIFT_LEVEL_1:  { badge: "text-amber-400",  svgClass: "amber-drift",       heart: "#f59e0b", node: "#f59e0b" },
  BREACH_LEVEL_2: { badge: "text-red-400",    svgClass: "crimson-heartbeat", heart: "#dc2626", node: "#dc2626" },
  STASIS_LOCKED:  { badge: "text-red-600",    svgClass: "crimson-heartbeat", heart: "#991b1b", node: "#dc2626" },
};

function applyStateVisuals(state) {
  const cfg = STATE_COLORS[state] || STATE_COLORS.SYNCED;

  // Badge text + color
  stateBadge.textContent = state;
  stateBadge.className   = `text-2xl font-bold ${cfg.badge}`;

  // SVG container animation class
  svgContainer.className = svgContainer.className
    .replace(/golden-halo|amber-drift|crimson-heartbeat/g, "")
    .trim() + " " + cfg.svgClass;

  // Reactor heart color
  reactorHeart.setAttribute("fill", cfg.heart);

  // Sensor nodes stroke
  sensorNodes.forEach(n => n.setAttribute("stroke", cfg.node));
  flowDots.forEach(d => d.setAttribute("fill", cfg.node));
}

function appendEntry(container, html, maxEntries = 80) {
  // Clear placeholder italic text on first real entry
  const placeholder = container.querySelector("p.italic");
  if (placeholder) placeholder.remove();

  const div = document.createElement("div");
  div.className = "log-entry pl-2 py-0.5 text-gray-400";
  div.innerHTML = html;
  container.prepend(div);

  // Cap entries
  while (container.children.length > maxEntries) {
    container.removeChild(container.lastChild);
  }
}

function formatTime(unix) {
  return new Date(unix * 1000).toLocaleTimeString();
}

function handleStateUpdate(data) {
  const state = data.state || "SYNCED";
  applyStateVisuals(state);

  statStreams.textContent    = data.live_stream_count ?? 0;
  statFrictions.textContent  = data.friction_count ?? 0;
  statFootprints.textContent = data.spectral_footprints ?? 0;

  // Recent friction entries
  if (data.recent_friction && data.recent_friction.length > 0) {
    const latest = data.recent_friction[data.recent_friction.length - 1];
    const evt = latest.event || {};
    appendEntry(frictionFeed,
      `<span class="text-red-400">[${formatTime(latest.logged_at)}]</span> ${evt.type || "UNKNOWN"}`
    );
  }

  // State history
  if (data.state_history && data.state_history.length > 0) {
    const last = data.state_history[data.state_history.length - 1];
    appendEntry(stateLog,
      `<span class="text-amber-400">[${formatTime(last.at)}]</span> ${last.from} → ${last.to}`
    );
  }
}

// ---- WebSocket lifecycle ----

function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    reconnectAttempt = 0;
    connectionBadge.textContent = "CONNECTED";
    connectionBadge.className   = "px-3 py-1 rounded text-xs font-semibold bg-green-900/40 text-green-400";

    // Subscribe as UI client
    ws.send(JSON.stringify({ type: "UI_SUBSCRIBE" }));
  };

  ws.onmessage = (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    if (data.type === "STATE_UPDATE") {
      handleStateUpdate(data);
    }

    // Telemetry feed — log every message
    appendEntry(telemetryFeed,
      `<span class="text-cyan-500">[${formatTime(Date.now() / 1000)}]</span> ` +
      `<span class="text-gray-500">${data.status || data.type || "MSG"}</span> ` +
      `<span class="text-gray-400">${data.state || ""}</span>`
    );
  };

  ws.onclose = () => {
    connectionBadge.textContent = "DISCONNECTED";
    connectionBadge.className   = "px-3 py-1 rounded text-xs font-semibold bg-gray-800 text-gray-500";
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

function scheduleReconnect() {
  const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt), RECONNECT_MAX_MS);
  reconnectAttempt++;
  setTimeout(connect, delay);
}

// ---- Boot ----
connect();
