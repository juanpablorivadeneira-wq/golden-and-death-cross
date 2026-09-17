"use strict";
const state = { items: [], groups: [], detail: {}, selected: null, token: "" };
const $ = id => document.getElementById(id);
const GROUPS_PAGE_KEY = "fundamentals";

async function savedToken() {
  return new Promise(resolve => {
    const req = indexedDB.open("cross-monitor", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("kv");
    req.onerror = () => resolve("");
    req.onsuccess = () => {
      const db = req.result;
      const get = db.transaction("kv").objectStore("kv").get("token");
      get.onsuccess = () => { resolve(get.result || ""); db.close(); };
      get.onerror = () => { resolve(""); db.close(); };
    };
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Auth-Token": state.token, ...(options.headers || {}) },
  });
  if (res.status === 401) throw new Error("Abre Cross Monitor para iniciar sesión y vuelve a esta página.");
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}
const watchlistApi = (path, options) => api(`/api/watchlist${path}`, options);

async function load(force = false) {
  $("update").disabled = true;
  $("fund-status").textContent = "Consultando watchlist…";
  try {
    const [data, groups] = await Promise.all([api("/api/watchlist"), WatchlistGroups.list(watchlistApi)]);
    state.items = data.tickers;
    state.groups = groups;
    if (!state.items.some(t => t.ticker === state.selected)) state.selected = state.items.find(t => !t.error)?.ticker || null;
    $("fund-status").textContent = `${state.items.length} activos en tu watchlist`;
    $("consulted").textContent = `Consulta: ${new Date().toLocaleTimeString()}`;
    renderList();
    if (state.selected) await selectTicker(state.selected, force);
  } catch(e) {
    $("fund-status").textContent = e.message;
  } finally { $("update").disabled = false; }
}

function buildFundItem(t) {
  const btn = document.createElement("button"); btn.className = `fund-item${state.selected === t.ticker ? " selected" : ""}`;
  const name = document.createElement("strong"); name.textContent = t.ticker;
  const price = document.createElement("span"); price.textContent = t.price != null ? t.price.toFixed(2) : "";
  const picker = WatchlistGroups.renderPicker(state.groups, t.group, (value) => assignTickerGroup(t.ticker, value));
  btn.append(name, price, picker);
  btn.onclick = () => selectTicker(t.ticker, false);
  return btn;
}

async function assignTickerGroup(ticker, value) {
  if (value === "__new__") {
    const name = await WatchlistGroups.promptText("Nombre del nuevo grupo:");
    if (!name) { renderList(); return; }
    try {
      state.groups = await WatchlistGroups.create(watchlistApi, name);
      value = name;
    } catch(e) { $("fund-status").textContent = e.message; renderList(); return; }
  }
  try {
    await WatchlistGroups.setTickerGroup(watchlistApi, ticker, value || null);
    const item = state.items.find(t => t.ticker === ticker);
    if (item) item.group = value || null;
    renderList();
  } catch(e) { $("fund-status").textContent = e.message; }
}

async function renameGroupPrompt(name) {
  const next = await WatchlistGroups.promptText("Nuevo nombre del grupo:", name);
  if (!next || next === name) return;
  try {
    state.groups = await WatchlistGroups.rename(watchlistApi, name, next);
    for (const t of state.items) if (t.group === name) t.group = next;
    renderList();
  } catch(e) { $("fund-status").textContent = e.message; }
}

async function deleteGroupPrompt(name) {
  if (!(await WatchlistGroups.confirmAction(`¿Eliminar el grupo "${name}"? Los tickers vuelven a "Sin categoría".`))) return;
  try {
    state.groups = await WatchlistGroups.remove(watchlistApi, name);
    for (const t of state.items) if (t.group === name) t.group = null;
    renderList();
  } catch(e) { $("fund-status").textContent = e.message; }
}

async function moveGroupBy(name, direction) {
  try {
    state.groups = await WatchlistGroups.move(watchlistApi, name, direction);
    renderList();
  } catch(e) { $("fund-status").textContent = e.message; }
}

async function createGroupPrompt() {
  const name = await WatchlistGroups.promptText("Nombre del nuevo grupo:");
  if (!name) return;
  try {
    state.groups = await WatchlistGroups.create(watchlistApi, name);
    renderList();
  } catch(e) { $("fund-status").textContent = e.message; }
}
$("fund-group-btn").onclick = createGroupPrompt;

function renderList() {
  const list = $("fund-list"); list.replaceChildren();
  if (!state.items.length && !state.groups.length) {
    const el = document.createElement("div"); el.className = "empty";
    el.textContent = "Agrega tickers desde Cross Monitor o el Radar."; list.append(el); return;
  }
  const sections = WatchlistGroups.bucket(state.items, state.groups);
  for (const section of sections) {
    // El bucket "Sin categoría" solo se muestra si tiene tickers -- no es un
    // grupo real, no tiene sentido un encabezado vacío para él. Un grupo real
    // sí se muestra aunque esté vacío: si no, apenas creado (o tras vaciarlo)
    // desaparecería y no habría forma de renombrarlo/eliminarlo.
    if (!section.items.length && !section.name) continue;
    if (!section.name && state.groups.length === 0) {
      for (const t of section.items) list.append(buildFundItem(t));
      continue;
    }
    const body = WatchlistGroups.renderSection(list, GROUPS_PAGE_KEY, section.name, section.items.length, {
      onMove: (dir) => moveGroupBy(section.name, dir),
      onRename: () => renameGroupPrompt(section.name),
      onDelete: () => deleteGroupPrompt(section.name),
    });
    if (!section.items.length) {
      const empty = document.createElement("div"); empty.className = "wg-empty";
      empty.textContent = "Sin tickers en este grupo todavía — asígnalos desde el selector de cada ticker.";
      body.append(empty);
    }
    for (const t of section.items) body.append(buildFundItem(t));
  }
}

const SEM_LEVELS = ["green", "yellow", "red", "none"];

// Medidor de aguja semicircular (venta fuerte -> compra fuerte) para el
// resumen técnico -- trazo fino y degradé suave (saturado en las puntas,
// apagado al centro/neutral), no bandas sólidas: la posición de la aguja ya
// comunica el veredicto, así que el arco es solo una referencia de fondo.
function polarPoint(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: (cx + r * Math.cos(rad)).toFixed(2), y: (cy - r * Math.sin(rad)).toFixed(2) };
}
let _techGaugeSeq = 0;
function buildTechnicalGauge(score) {
  if (score == null) return null;
  const cx = 50, cy = 48, r = 40;
  const gradId = `tech-gauge-grad-${_techGaugeSeq++}`;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 100 54");
  svg.setAttribute("class", "tech-gauge");
  const defs = document.createElementNS(SVG_NS, "defs");
  const grad = document.createElementNS(SVG_NS, "linearGradient");
  grad.setAttribute("id", gradId);
  grad.setAttribute("x1", "0%"); grad.setAttribute("y1", "0%"); grad.setAttribute("x2", "100%"); grad.setAttribute("y2", "0%");
  for (const [offset, color] of [["0%", "#e5484d"], ["25%", "#f2babe"], ["50%", "#c8ccd1"], ["75%", "#b7ddc4"], ["100%", "#22c55e"]]) {
    const stop = document.createElementNS(SVG_NS, "stop");
    stop.setAttribute("offset", offset); stop.setAttribute("stop-color", color);
    grad.append(stop);
  }
  defs.append(grad);
  const p0 = polarPoint(cx, cy, r, 180), p1 = polarPoint(cx, cy, r, 0);
  const arc = document.createElementNS(SVG_NS, "path");
  arc.setAttribute("d", `M ${p0.x} ${p0.y} A ${r} ${r} 0 0 1 ${p1.x} ${p1.y}`);
  arc.setAttribute("stroke", `url(#${gradId})`);
  arc.setAttribute("stroke-width", "3");
  arc.setAttribute("fill", "none");
  arc.setAttribute("stroke-linecap", "round");
  const angle = 180 - ((score - 1) / 9) * 180;
  const tip = polarPoint(cx, cy, r - 12, angle);
  const needle = document.createElementNS(SVG_NS, "line");
  needle.setAttribute("x1", cx); needle.setAttribute("y1", cy);
  needle.setAttribute("x2", tip.x); needle.setAttribute("y2", tip.y);
  needle.setAttribute("class", "tech-needle");
  needle.setAttribute("stroke-width", "1.5");
  needle.setAttribute("stroke-linecap", "round");
  const hub = document.createElementNS(SVG_NS, "circle");
  hub.setAttribute("cx", cx); hub.setAttribute("cy", cy); hub.setAttribute("r", "2.5");
  hub.setAttribute("class", "tech-needle-hub");
  svg.append(defs, arc, needle, hub);
  return svg;
}

// El color de la celda activa SIEMPRE viene del "level" ya calculado por el
// backend para este semáforo, nunca de la posición del número en la escala:
// así el color del medidor nunca puede contradecir el veredicto grande de la
// tarjeta (antes, un score=7 se pintaba amarillo por posición fija aunque el
// veredicto real fuera "Comprar"/verde).
function renderGauge(score, level) {
  if (score == null || !Number.isFinite(score)) return null;
  const gauge = document.createElement("div"); gauge.className = "sem-gauge";
  const heading = document.createElement("div"); heading.className = "score-heading";
  const label = document.createElement("span"); label.textContent = "Puntuación del modelo";
  const number = document.createElement("strong"); number.textContent = `${score}/10`;
  heading.append(label, number);
  const track = document.createElement("div"); track.className = "score-track";
  track.setAttribute("role", "meter"); track.setAttribute("aria-label", "Puntuación del modelo");
  track.setAttribute("aria-valuemin", "1"); track.setAttribute("aria-valuemax", "10"); track.setAttribute("aria-valuenow", String(score));
  const bands = document.createElement("div"); bands.className = "score-bands";
  const labels = document.createElement("div"); labels.className = "score-labels";
  for (let i = 0; i < 5; i++) {
    const band = document.createElement("span"); band.className = `score-band band-${i}`;
    const tick = document.createElement("span"); tick.className = `band-${i}`;
    tick.textContent = `${i * 2 + 1}–${i * 2 + 2}`;
    bands.append(band); labels.append(tick);
  }
  const marker = document.createElement("span"); marker.className = "score-marker";
  marker.style.left = `${Math.max(2, Math.min(98, ((score - 1) / 9) * 100))}%`;
  marker.setAttribute("aria-hidden", "true");
  track.append(bands, marker); gauge.append(heading, track, labels); return gauge;
}

const CONSENSUS_LEGEND = [
  ["buy", "Comprar", "green"],
  ["hold", "Mantener", "yellow"],
  ["sell", "Vender", "red"],
];

function buildConsensusRing(breakdown) {
  const { buy = 0, hold = 0, sell = 0 } = breakdown;
  const total = buy + hold + sell;
  if (!total) return null;
  const buyPct = (buy / total) * 100;
  const holdPct = (hold / total) * 100;
  const ring = document.createElement("div"); ring.className = "consensus-ring";
  ring.style.background = `conic-gradient(var(--ok) 0 ${buyPct}%, var(--gold) ${buyPct}% ${buyPct + holdPct}%, var(--death) ${buyPct + holdPct}% 100%)`;
  const center = document.createElement("div"); center.className = "consensus-ring-center";
  const num = document.createElement("strong"); num.textContent = total;
  const lbl = document.createElement("span"); lbl.textContent = total === 1 ? "analista" : "analistas";
  center.append(num, lbl);
  ring.append(center);
  return ring;
}

function buildConsensusLegend(breakdown) {
  const legend = document.createElement("div"); legend.className = "consensus-legend";
  for (const [key, text, cls] of CONSENSUS_LEGEND) {
    const row = document.createElement("span"); row.className = "consensus-legend-row";
    const dot = document.createElement("span"); dot.className = `consensus-dot level-${cls}`;
    const count = document.createElement("span"); count.textContent = `${breakdown[key]} ${text}`;
    row.append(dot, count);
    legend.append(row);
  }
  return legend;
}

function renderSemaphore(container, title, sem, detailText, customVisual) {
  const level = SEM_LEVELS.includes(sem.level) ? sem.level : "none";
  const art = document.createElement("article"); art.className = `semaphore ${level}`;
  const label = document.createElement("span"); label.className = "semaphore-label"; label.textContent = title;
  const value = document.createElement("strong"); value.className = "semaphore-value"; value.textContent = sem.label;
  const detail = document.createElement("small"); detail.className = "semaphore-detail"; detail.textContent = detailText || "";
  art.append(label);
  // El anillo (y ahora el medidor técnico) van a la derecha del veredicto
  // (misma fila), no apilados debajo -- así no suman su propia altura a la
  // del texto grande.
  const ring = sem.breakdown ? buildConsensusRing(sem.breakdown) : null;
  const sideVisual = customVisual || ring;
  if (sideVisual) {
    const head = document.createElement("div"); head.className = "semaphore-head-row";
    head.append(value, sideVisual);
    art.append(head, detail);
    if (ring) art.append(buildConsensusLegend(sem.breakdown));
  } else {
    art.append(value, detail);
    const gauge = renderGauge(sem.score, level);
    if (gauge) art.append(gauge);
  }
  container.append(art);
}

async function selectTicker(ticker, force) {
  state.selected = ticker;
  renderList();
  const panel = $("fund-detail"); panel.replaceChildren();
  const loading = document.createElement("div"); loading.className = "empty"; loading.textContent = `Cargando ${ticker}…`; panel.append(loading);
  try {
    const data = await api(`/api/fundamentals/${encodeURIComponent(ticker)}${force ? "?refresh=true" : ""}`);
    state.detail[ticker] = data;
    if (state.selected !== ticker) return;
    renderDetail(data);
  } catch(e) {
    if (state.selected !== ticker) return;
    panel.replaceChildren();
    const err = document.createElement("div"); err.className = "empty"; err.textContent = `No se pudo cargar ${ticker}: ${e.message}`; panel.append(err);
  }
}

const SVG_NS = "http://www.w3.org/2000/svg";
// Campos donde bajar es la dirección favorable (menor deuda = mejor).
const INVERT_TREND_FIELDS = new Set(["debtToEquity"]);

// Mini-tendencia inline (sin librerías): normaliza los valores a un polyline
// dentro de un viewBox fijo. El color sale de si la dirección es favorable,
// no de si sube o baja en sí -- para la mayoría de los campos subir es bueno
// (ingresos, márgenes, ROE), pero para deuda/patrimonio bajar es lo bueno
// (`invert=true` lo marca explícitamente, no lo adivina el gráfico).
function buildSparkline(values, invert = false) {
  if (!values || values.length < 2) return null;
  const w = 56, h = 18, pad = 2;
  const min = Math.min(...values), max = Math.max(...values);
  const range = (max - min) || Math.abs(max) || 1;
  const stepX = (w - pad * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const rose = values[values.length - 1] >= values[0];
  const favorable = invert ? !rose : rose;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", `fm-sparkline ${favorable ? "up" : "down"}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const poly = document.createElementNS(SVG_NS, "polyline");
  poly.setAttribute("points", points.join(" "));
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "currentColor");
  poly.setAttribute("stroke-width", "1.5");
  poly.setAttribute("stroke-linecap", "round");
  poly.setAttribute("stroke-linejoin", "round");
  svg.append(poly);
  return svg;
}

function renderDetail(data) {
  const panel = $("fund-detail"); panel.replaceChildren();
  if (data.error) {
    const err = document.createElement("div"); err.className = "empty"; err.textContent = data.error; panel.append(err); return;
  }
  const head = document.createElement("div"); head.className = "fund-detail-head";
  const h2 = document.createElement("h2"); h2.textContent = data.ticker;
  const sub = document.createElement("span"); sub.textContent = [data.sector, data.industry].filter(Boolean).join(" · ") || data.quote_type;
  head.append(h2, sub); panel.append(head);

  if (data.is_fund) {
    const note = document.createElement("div"); note.className = "empty";
    note.textContent = `${data.ticker} es un ${data.quote_type === "ETF" ? "ETF" : "fondo"}, no una empresa — el análisis fundamental no aplica.`;
    panel.append(note); return;
  }

  const sems = document.createElement("section"); sems.className = "semaphores";
  const health = data.semaphores.health, ac = data.semaphores.analyst_consensus, tp = data.semaphores.target_price;
  const tech = data.semaphores.technical;
  renderSemaphore(sems, "Salud Fundamental", health, health.detail || "");
  renderSemaphore(sems, "Consenso de Analistas", ac, ac.analysts ? `${ac.analysts} analista${ac.analysts === 1 ? "" : "s"}` : "");
  renderSemaphore(sems, "Precio Objetivo", tp, tp.target_price != null ? `Objetivo promedio: ${tp.target_price.toFixed(2)}` : "");
  if (tech) {
    const detail = tech.moving_averages && tech.oscillators
      ? `Medias: ${tech.moving_averages.label} · Osciladores: ${tech.oscillators.label}`
      : "";
    renderSemaphore(sems, "Análisis Técnico", { ...tech, level: tech.color }, detail, buildTechnicalGauge(tech.score));
  }
  panel.append(sems);

  const blocksWrap = document.createElement("div"); blocksWrap.className = "fund-blocks";
  for (const block of data.blocks) {
    const section = document.createElement("div"); section.className = "fund-block";
    const head = document.createElement("button"); head.type = "button"; head.className = "fund-block-head";
    const h3 = document.createElement("h3"); h3.textContent = block.title;
    const headCaret = document.createElement("span"); headCaret.className = "fm-caret"; headCaret.textContent = "▾"; headCaret.title = "Mostrar/ocultar todas las explicaciones";
    head.append(h3, headCaret);
    const list = document.createElement("div"); list.className = "fm-list";
    const rows = [];
    for (const m of block.metrics) {
      const row = document.createElement("div"); row.className = `fm-row status-${m.status}`;
      const main = document.createElement("button"); main.type = "button"; main.className = "fm-row-main";
      const label = document.createElement("span"); label.className = "fm-label"; label.textContent = m.label;
      const value = document.createElement("strong"); value.className = "fm-value"; value.textContent = m.display;
      const caret = document.createElement("span"); caret.className = "fm-caret"; caret.textContent = "▾"; caret.title = "Cómo leer esto";
      const sparkline = buildSparkline(m.trend, INVERT_TREND_FIELDS.has(m.key));
      main.append(label, value);
      if (sparkline) main.append(sparkline);
      main.append(caret);
      const explain = document.createElement("div"); explain.className = "fm-explain hidden"; explain.textContent = m.explanation;
      main.onclick = () => row.classList.toggle("expanded") ? explain.classList.remove("hidden") : explain.classList.add("hidden");
      row.append(main, explain);
      list.append(row);
      rows.push(row);
    }
    head.onclick = () => {
      const opening = !head.classList.contains("expanded");
      head.classList.toggle("expanded", opening);
      for (const row of rows) {
        row.classList.toggle("expanded", opening);
        row.querySelector(".fm-explain").classList.toggle("hidden", !opening);
      }
    };
    section.append(head, list);
    blocksWrap.append(section);
  }
  panel.append(blocksWrap);
  if (data.research) FundamentalResearch.render(panel, data);
}

async function addTicker() {
  const input = $("fund-ticker-input");
  const t = input.value.trim().toUpperCase();
  if (!t) return;
  input.value = "";
  $("fund-status").textContent = `Agregando ${t}…`;
  try {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(t)}`, { method: "POST", headers: { "X-Auth-Token": state.token } });
    if (res.status === 401) throw new Error("Abre Cross Monitor para iniciar sesión y vuelve a esta página.");
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    state.selected = t;
    await load();
  } catch(e) {
    $("fund-status").textContent = `No se pudo agregar ${t}: ${e.message}`;
  }
}
$("fund-add-btn").onclick = addTicker;
$("fund-ticker-input").addEventListener("keydown", e => { if (e.key === "Enter") addTicker(); });

$("update").onclick = () => load(true);

async function main() {
  state.token = await savedToken().catch(() => "");
  await load();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
}
main();
