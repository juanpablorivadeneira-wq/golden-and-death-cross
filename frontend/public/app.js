// Cross Monitor PWA — la UI consume la API del backend; no calcula indicadores.
"use strict";

// ═══════════════════════════════════════════════════════
//  TOKEN EN INDEXEDDB
// ═══════════════════════════════════════════════════════
const DB_NAME = "cross-monitor";
const STORE = "kv";

function idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet(key) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE).objectStore(STORE).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(key, value) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ═══════════════════════════════════════════════════════
//  ESTADO
// ═══════════════════════════════════════════════════════
const state = {
  token: null,
  maType: "ema",
  fastLen: 50,
  slowLen: 200,
  tickers: [],        // [{ticker, price, regime, ...}] tal como llega de la API
  selected: null,
  pollSeconds: 300,
  timer: null,
  chart: null, priceSeries: null, fastSeries: null, slowSeries: null,
};

// ═══════════════════════════════════════════════════════
//  API
// ═══════════════════════════════════════════════════════
async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Token": state.token || "",
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    showAuth("Token inválido. Vuelve a ingresarlo.");
    throw new Error("No autorizado");
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* sin cuerpo */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ═══════════════════════════════════════════════════════
//  AUTENTICACIÓN
// ═══════════════════════════════════════════════════════
function showAuth(message) {
  document.getElementById("auth-overlay").classList.remove("hidden");
  document.getElementById("auth-error").textContent = message || "";
}

async function tryLogin(token) {
  state.token = token;
  try {
    await api("/settings");            // cualquier endpoint autenticado sirve de prueba
    await idbSet("token", token);
    document.getElementById("auth-overlay").classList.add("hidden");
    await loadSettings();
    await refreshAll();
    restartTimer();
    return true;
  } catch (e) {
    state.token = null;
    return false;
  }
}

// ═══════════════════════════════════════════════════════
//  ALERTAS (registro local de la sesión)
// ═══════════════════════════════════════════════════════
function logAlert(text, type) {
  const log = document.getElementById("alert-log");
  const div = document.createElement("div");
  div.className = `entry ${type || ""}`;
  div.textContent = text;
  log.insertBefore(div, log.children[1] || null);
}

// ═══════════════════════════════════════════════════════
//  ACTUALIZACIÓN
// ═══════════════════════════════════════════════════════
async function refreshAll() {
  const statusEl = document.getElementById("status-text");
  statusEl.textContent = "Consultando watchlist…";
  try {
    const data = await api("/watchlist");
    state.maType = data.ma_type;
    state.fastLen = data.fast_len;
    state.slowLen = data.slow_len;
    updateMaLabels();

    // Detección de cambio de régimen respecto a lo que la UI ya mostraba
    for (const t of data.tickers) {
      const prev = state.tickers.find(x => x.ticker === t.ticker);
      if (prev && !prev.error && !t.error && prev.regime !== t.regime) {
        logAlert(`${new Date().toLocaleTimeString()} · ${t.regime === "golden" ? "GOLDEN" : "DEATH"} CROSS — ${t.ticker}`, t.regime);
      }
    }
    state.tickers = data.tickers;

    const ok = data.tickers.filter(t => !t.error).length;
    const fail = data.tickers.length - ok;
    statusEl.textContent = fail === 0
      ? `${ok} tickers monitoreados · datos diarios (servidor)`
      : `${ok} OK · ${fail} con error de datos`;
    document.getElementById("last-update").textContent = new Date().toLocaleTimeString();
    renderWatchlist();

    if (!state.selected) {
      const first = data.tickers.find(t => !t.error);
      if (first) selectTicker(first.ticker);
    } else {
      renderChart(state.selected);
    }
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  }
}

// ═══════════════════════════════════════════════════════
//  WATCHLIST
// ═══════════════════════════════════════════════════════
const expanded = new Set();

function renderWatchlist() {
  const el = document.getElementById("watchlist");
  el.innerHTML = "";
  if (state.tickers.length === 0) {
    el.innerHTML = '<div class="empty">Agrega un ticker para comenzar el monitoreo.</div>';
    return;
  }
  const maLabel = state.maType.toUpperCase();
  for (const d of state.tickers) {
    const t = d.ticker;
    const card = document.createElement("div");
    card.className = "card"
      + (state.selected === t ? " selected" : "")
      + (d.regime === "death" ? " state-death" : "")
      + (expanded.has(t) ? " expanded" : "");

    if (d.error) {
      card.innerHTML = `<div class="card-row">
          <span class="ticker">${t}</span>
          <span class="gap-mini death" style="margin-left:auto;">${d.error}</span>
          <button class="retry" data-t="${t}">Reintentar</button>
          <button class="remove" title="Quitar" data-t="${t}">×</button>
        </div>`;
    } else {
      const isG = d.regime === "golden";
      const badgeClass = isG ? "golden" : "death";
      const label = isG ? "GOLDEN" : "DEATH";
      const crossInfo = d.cross_date
        ? `${d.cross_date} (hace ${d.sessions_since_cross} sesiones)` : "—";
      const proximity = Math.max(0, Math.min(100, 100 - (Math.abs(d.gap_pct) / 5) * 100));
      const estText = d.est_sessions_to_cross != null
        ? `Al ritmo actual, cruce estimado en <strong>~${Math.round(d.est_sessions_to_cross)} sesiones</strong>`
        : (d.converging ? "Las medias convergen lentamente" : "Las medias divergen — sin cruce a la vista");
      card.innerHTML = `
        <div class="card-row">
          <button class="chev" title="Ver detalle" data-t="${t}">▶</button>
          <span class="ticker">${t}</span>
          <span class="badge ${badgeClass}${d.fresh_cross ? " fresh" : ""}">${label}${d.fresh_cross ? " · HOY" : ""}</span>
          <span class="sess-mini" title="Sesiones desde el último cruce">${d.sessions_since_cross != null ? "hace " + d.sessions_since_cross + " ses" : "—"}</span>
          <span class="gap-mini ${badgeClass}" title="Brecha entre medias">${d.gap_pct >= 0 ? "+" : ""}${d.gap_pct.toFixed(2)}%</span>
          <span class="price">${d.price.toFixed(2)}</span>
          <button class="remove" title="Quitar de la lista" data-t="${t}">×</button>
        </div>
        <div class="card-body">
          <div class="card-detail">
            <div class="metric"><div class="k">${maLabel} ${state.fastLen}</div><div class="v fast">${d.ma_fast.toFixed(2)}</div></div>
            <div class="metric"><div class="k">${maLabel} ${state.slowLen}</div><div class="v slow">${d.ma_slow.toFixed(2)}</div></div>
            <div class="metric"><div class="k">Último cruce</div><div class="v" style="font-size:11px;">${crossInfo}</div></div>
          </div>
          <div class="gauge">
            <div class="gauge-track"><div class="gauge-fill ${badgeClass}" style="width:${proximity}%"></div></div>
            <div class="gauge-label">Brecha entre medias: <strong>${d.gap_pct.toFixed(2)}%</strong> · ${estText}</div>
          </div>
        </div>`;
    }

    card.addEventListener("click", (ev) => {
      if (ev.target.classList.contains("remove")) return;
      if (ev.target.classList.contains("retry")) return;
      if (ev.target.classList.contains("chev")) {
        if (expanded.has(t)) expanded.delete(t); else expanded.add(t);
        renderWatchlist();
        return;
      }
      if (!d.error) selectTicker(t);
    });
    const rm = card.querySelector(".remove");
    if (rm) rm.addEventListener("click", (ev) => { ev.stopPropagation(); removeTicker(t); });
    const rt = card.querySelector(".retry");
    if (rt) rt.addEventListener("click", (ev) => { ev.stopPropagation(); refreshAll(); });
    el.appendChild(card);
  }
}

let editMode = false;
function toggleEditMode() {
  editMode = !editMode;
  document.getElementById("watchlist").classList.toggle("editing", editMode);
  const btn = document.getElementById("edit-btn");
  btn.textContent = editMode ? "Listo" : "Editar lista";
  btn.classList.toggle("primary", editMode);
}

async function addTicker() {
  const input = document.getElementById("ticker-input");
  const t = input.value.trim().toUpperCase();
  if (!t) return;
  input.value = "";
  const statusEl = document.getElementById("status-text");
  statusEl.textContent = `Consultando ${t}…`;
  try {
    await api(`/watchlist/${encodeURIComponent(t)}`, { method: "POST" });
    logAlert(`${t} agregado a la watchlist`);
    await refreshAll();
    selectTicker(t);
  } catch (e) {
    statusEl.textContent = `Error al agregar ${t}: ${e.message}`;
  }
}

async function removeTicker(t) {
  try {
    await api(`/watchlist/${encodeURIComponent(t)}`, { method: "DELETE" });
    state.tickers = state.tickers.filter(x => x.ticker !== t);
    if (state.selected === t) state.selected = null;
    renderWatchlist();
  } catch (e) {
    logAlert(`No se pudo eliminar ${t}: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════
//  GRÁFICO — lightweight-charts con series de la API
// ═══════════════════════════════════════════════════════
function initChart() {
  const container = document.getElementById("own-chart");
  container.innerHTML = "";
  if (typeof LightweightCharts === "undefined") {
    container.innerHTML = '<div class="empty">No se pudo cargar la librería de gráficos.</div>';
    return;
  }
  state.chart = LightweightCharts.createChart(container, {
    layout: { background: { color: "transparent" }, textColor: "#7C8494", fontFamily: "Consolas, monospace" },
    grid: { vertLines: { color: "#1A1E27" }, horzLines: { color: "#1A1E27" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#262B36" },
    timeScale: { borderColor: "#262B36", timeVisible: false },
    autoSize: true,
  });
}

function clearSeries() {
  for (const key of ["priceSeries", "fastSeries", "slowSeries"]) {
    if (state[key]) { try { state.chart.removeSeries(state[key]); } catch (e) { /* ya removida */ } state[key] = null; }
  }
}

const ohlcCache = {};  // ticker -> respuesta de /quotes/{t}/ohlc

async function renderChart(t) {
  if (!state.chart) return;
  let data = ohlcCache[t];
  if (!data) {
    try {
      data = await api(`/quotes/${encodeURIComponent(t)}/ohlc`);
      ohlcCache[t] = data;
      setTimeout(() => delete ohlcCache[t], 5 * 60 * 1000); // TTL alineado con el backend
    } catch (e) {
      logAlert(`No se pudo cargar el gráfico de ${t}: ${e.message}`);
      return;
    }
  }
  if (state.selected !== t) return; // el usuario cambió de ticker mientras cargaba

  const maLabel = state.maType.toUpperCase();
  clearSeries();

  state.priceSeries = state.chart.addCandlestickSeries({
    upColor: "#26A69A", downColor: "#EF5350",
    borderUpColor: "#26A69A", borderDownColor: "#EF5350",
    wickUpColor: "#26A69A", wickDownColor: "#EF5350",
  });
  state.priceSeries.setData(data.bars.map(b => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c })));

  state.fastSeries = state.chart.addLineSeries({
    color: "#E8B93E", lineWidth: 2, priceLineVisible: false, title: `${maLabel} ${state.fastLen}`,
  });
  state.slowSeries = state.chart.addLineSeries({
    color: "#5B8DEF", lineWidth: 2, priceLineVisible: false, title: `${maLabel} ${state.slowLen}`,
  });
  state.fastSeries.setData(data.bars.map((b, i) => data.ma_fast[i] != null ? { time: b.t, value: data.ma_fast[i] } : null).filter(Boolean));
  state.slowSeries.setData(data.bars.map((b, i) => data.ma_slow[i] != null ? { time: b.t, value: data.ma_slow[i] } : null).filter(Boolean));

  state.priceSeries.setMarkers(data.crosses.map(c => ({
    time: c.t,
    position: c.type === "golden" ? "belowBar" : "aboveBar",
    color: c.type === "golden" ? "#E8B93E" : "#E5484D",
    shape: c.type === "golden" ? "arrowUp" : "arrowDown",
    text: c.type === "golden" ? "GOLDEN" : "DEATH",
  })));
  state.chart.timeScale().fitContent();
}

function selectTicker(t) {
  state.selected = t;
  renderWatchlist();
  document.getElementById("chart-title").innerHTML = `<strong>${t}</strong> · Diario`;
  renderChart(t);
}

function updateMaLabels() {
  const maLabel = state.maType.toUpperCase();
  document.getElementById("ma-subtitle").textContent = `${maLabel} ${state.fastLen} / ${state.slowLen} · Diario`;
  document.getElementById("legend-fast").textContent = `${maLabel} ${state.fastLen}`;
  document.getElementById("legend-slow").textContent = `${maLabel} ${state.slowLen}`;
  document.getElementById("ma-type").value = state.maType;
}

async function loadSettings() {
  const s = await api("/settings");
  state.maType = s.ma_type;
  state.fastLen = s.fast_len;
  state.slowLen = s.slow_len;
  updateMaLabels();
}

// ═══════════════════════════════════════════════════════
//  NOTIFICACIONES PUSH (Web Push con VAPID)
// ═══════════════════════════════════════════════════════
function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - base64.length % 4) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map(ch => ch.charCodeAt(0)));
}

async function enablePush() {
  const btn = document.getElementById("notif-btn");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    logAlert("Este navegador no soporta notificaciones push. En iPhone: instala la app desde Safari (Compartir → Agregar a pantalla de inicio) y ábrela desde el ícono.");
    return;
  }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      logAlert("Permiso de notificaciones denegado.");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const { publicKey } = await api("/push/vapid-public-key");
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    }
    const json = sub.toJSON();
    await api("/push/subscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    });
    btn.textContent = "Notificaciones activas";
    logAlert("Notificaciones push activadas. El servidor avisará ante cualquier cruce.");
  } catch (e) {
    logAlert(`No se pudo activar el push: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════
//  EVENTOS DE UI
// ═══════════════════════════════════════════════════════
function restartTimer() {
  if (state.timer) clearInterval(state.timer);
  state.timer = setInterval(refreshAll, state.pollSeconds * 1000);
}

document.getElementById("add-btn").addEventListener("click", addTicker);
document.getElementById("edit-btn").addEventListener("click", toggleEditMode);
document.getElementById("ticker-input").addEventListener("keydown", e => { if (e.key === "Enter") addTicker(); });
document.getElementById("refresh-btn").addEventListener("click", refreshAll);
document.getElementById("ma-type").addEventListener("change", async e => {
  try {
    await api("/settings", { method: "PUT", body: JSON.stringify({ ma_type: e.target.value }) });
    Object.keys(ohlcCache).forEach(k => delete ohlcCache[k]);
    await refreshAll();
  } catch (err) {
    logAlert(`No se pudo cambiar el tipo de MA: ${err.message}`);
  }
});
document.getElementById("poll-interval").addEventListener("change", e => {
  state.pollSeconds = parseInt(e.target.value, 10);
  restartTimer();
});
document.getElementById("notif-btn").addEventListener("click", enablePush);
document.getElementById("auth-btn").addEventListener("click", async () => {
  const token = document.getElementById("auth-input").value.trim();
  if (!token) return;
  if (!(await tryLogin(token))) {
    document.getElementById("auth-error").textContent = "Token incorrecto.";
  }
});
document.getElementById("auth-input").addEventListener("keydown", e => {
  if (e.key === "Enter") document.getElementById("auth-btn").click();
});

window.addEventListener("error", e => logAlert(`Error: ${e.message}`));

// ═══════════════════════════════════════════════════════
//  INICIO
// ═══════════════════════════════════════════════════════
async function main() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(e => logAlert(`Service worker: ${e.message}`));
  }
  initChart();
  const saved = await idbGet("token").catch(() => null);
  if (saved && await tryLogin(saved)) return;
  showAuth();
}

main();
