"use strict";
/**
 * Pestaña David Trullás: lista de activos + gráfico (Lightweight Charts de
 * TradingView) + panel de diagnóstico. Todo el cálculo vive en el backend
 * (/api/trullas, backend/app/trullas.py); esta página solo pide y dibuja.
 *
 * Contrato resumido que devuelve el backend en `item.summary`:
 * @typedef {Object} TrullasSummary
 * @property {string} ticker
 * @property {"bullish"|"bearish"|"neutral"} macroTrend  Tendencia diaria del activo (precio y pendiente vs SMA 200)
 * @property {"buy"|"sell"|"wait"} smaSignal              Señal SMA 200/70/6 en el intervalo elegido
 * @property {"bullish"|"bearish"|null} divergenceDetected Divergencia activa (P2 dentro de las últimas 40 velas)
 * @property {number|null} targetPrice66                  Objetivo de retroceso 66 % (Dow)
 * @property {number|null} targetPrice618                 Objetivo de retroceso 61,8 % (Fibonacci)
 * @property {number|null} atrStop                        Stop sugerido a N × ATR(14)
 */
const tr = { items: [], groups: [], detail: {}, selected: null, filter: "all", search: "", assetFilter: "all",
  range: 180, token: "", chart: null, stoch: null, series: {}, priceLines: [], stochLines: [], abort: null };
const $ = id => document.getElementById(id);
const GROUPS_PAGE_KEY = "trullas";
const LOGIN_MSG = "Abre Cross Monitor para iniciar sesión y vuelve a esta pestaña.";
const COLORS = { s200: "#3b82f6", s70: "#ef4444", s6: "#22c55e", ray: "#e7c46a", t66: "#e7c46a", t618: "#c084fc",
  abs: "#8e9dac", k: "#e5eaf1", d: "#e7c46a" };

const SIGNAL = { buy: ["Compra", "golden"], sell: ["Venta", "death"], wait: ["Espera", ""] };
const TREND = { bullish: ["Alcista", "golden"], bearish: ["Bajista", "death"], neutral: ["Lateral", ""] };
const RS = { strong: ["Fuerte", "rs-strong"], neutral: ["Neutro", "rs-neutral"], weak: ["Débil", "rs-weak"], none: ["—", "rs-none"] };
const valid = d => !d.error;
// Decimales según el precio del activo (forex necesita 4), no según el valor:
// un ATR de 9,8 en una acción de 700 se muestra con 2, igual que su precio.
const decimals = ref => Math.abs(ref) < 10 ? 4 : 2;
const num = (n, digits) => n.toLocaleString("es", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const px = (n, ref = tr.refPrice ?? n) => n == null || !Number.isFinite(n) ? "—" : num(n, decimals(ref));
const pct = (n, digits = 2) => n == null ? "—" : `${n >= 0 ? "+" : "−"}${num(Math.abs(n), digits)}%`;
const pp = n => n == null ? "—" : `${n >= 0 ? "+" : "−"}${num(Math.abs(n), 1)} pp`;
const vol = n => n == null ? "—" : n >= 1e9 ? `${(n / 1e9).toFixed(2)} B` : n >= 1e6 ? `${(n / 1e6).toFixed(2)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} K` : n.toFixed(0);
const dateOf = t => { const d = new Date(t * 1000); return interval() === "1d" ? d.toISOString().slice(0, 10) : d.toISOString().slice(0, 16).replace("T", " "); };
const interval = () => $("interval").value;
const atrMult = () => Number($("atr-mult").value);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

async function watchlistApi(path, options = {}) {
  const res = await fetch(`/api/watchlist${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Auth-Token": tr.token, ...(options.headers || {}) },
  });
  if (res.status === 401) throw new Error(LOGIN_MSG);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

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

async function load(force = false) {
  $("update").disabled = true;
  $("tr-status").textContent = "Calculando diagnóstico de la lista…";
  try {
    const res = await fetch(`/api/trullas?refresh=${force}`, { headers: { "X-Auth-Token": tr.token }, signal: AbortSignal.timeout(180000) });
    if (res.status === 401) throw new Error(LOGIN_MSG);
    if (!res.ok) throw new Error(`No se pudo obtener la lista (${res.status}).`);
    tr.items = (await res.json()).items;
    tr.groups = await WatchlistGroups.list(watchlistApi).catch(() => tr.groups);
    if (force) tr.detail = {};
    const good = tr.items.filter(valid);
    if (!good.some(d => d.ticker === tr.selected)) {
      const saved = SelectedTicker.get();
      tr.selected = (saved && good.find(d => d.ticker === saved)?.ticker) || good[0]?.ticker || null;
    }
    $("tr-status").textContent = `${good.length} activos analizados · ${tr.items.length - good.length} con error`;
    $("consulted").textContent = `Consulta: ${new Date().toLocaleTimeString()}`;
    render(); await draw();
  } catch (e) {
    $("tr-status").textContent = `${e.message} Los datos anteriores, si existen, no se han actualizado.`;
  } finally { $("update").disabled = false; }
}

// ------------------------------------------------------------------ lista
function matches(d) {
  if (tr.assetFilter !== "all" && d.asset_class !== tr.assetFilter) return false;
  if (tr.search && !d.ticker.includes(tr.search)) return false;
  if (tr.filter === "all") return true;
  if (!valid(d)) return false;
  if (tr.filter === "div") return !!d.summary.divergenceDetected;
  return d.summary.smaSignal === tr.filter;
}

function render() {
  const good = tr.items.filter(valid);
  $("total").textContent = good.length;
  $("count-buy").textContent = good.filter(d => d.summary.smaSignal === "buy").length;
  $("count-sell").textContent = good.filter(d => d.summary.smaSignal === "sell").length;
  $("count-div").textContent = good.filter(d => d.summary.divergenceDetected).length;
  const items = tr.items.filter(matches).sort((a, b) => (!!a.error - !!b.error) || a.ticker.localeCompare(b.ticker));
  const list = $("tr-list"); list.replaceChildren();
  if (!items.length) { list.append(el("div", "empty", "No hay activos con este filtro. Agrega símbolos o cambia el filtro.")); return; }
  const sections = WatchlistGroups.bucket(items, tr.groups);
  for (const section of sections) {
    if (!section.items.length && !section.name) continue;
    if (!section.name && tr.groups.length === 0) { for (const d of section.items) list.append(buildItem(d)); continue; }
    const body = WatchlistGroups.renderSection(list, GROUPS_PAGE_KEY, section.name, section.items.length, {
      onMove: dir => groupAction(() => WatchlistGroups.move(watchlistApi, section.name, dir)),
      onRename: () => renameGroupPrompt(section.name),
      onDelete: () => deleteGroupPrompt(section.name),
    });
    if (!section.items.length) body.append(el("div", "wg-empty", "Sin tickers en este grupo todavía — asígnalos desde el selector de cada ticker."));
    for (const d of section.items) body.append(buildItem(d));
  }
}

function buildItem(d) {
  // <div> y no <button>: debe anidar el botón "×" (ver radar200.js).
  const item = el("div", `distance-item tr-item${tr.selected === d.ticker ? " selected" : ""}${d.error ? " disabled" : ""}`);
  const top = el("div", "distance-top");
  const name = el("span", "distance-name");
  name.append(el("strong", null, d.ticker), el("span", "tr-class", d.asset_class_label || ""));
  top.append(name);
  const right = el("span", "distance-top-right");
  if (!d.error) {
    const [label, cls] = RS[d.relative_strength?.label || "none"];
    const badge = el("span", `rs-badge ${cls}`, label);
    const rs = d.relative_strength;
    badge.title = rs?.value == null ? "Fuerza relativa sin referencia disponible"
      : `Fuerza relativa 3M vs ${rs.benchmark} (${rs.sector_name}): ${pp(rs.value)}`;
    right.append(badge);
  }
  right.append(WatchlistEdit.renderRemoveButton(() => removeTicker(d.ticker)));
  top.append(right);
  const bottom = el("div", "distance-bottom");
  if (d.error) bottom.append(el("span", null, d.error));
  else {
    const [sig, sigCls] = SIGNAL[d.summary.smaSignal];
    const info = el("span", "tr-chips");
    info.append(el("span", `tr-chip ${sigCls}`, sig));
    if (d.summary.divergenceDetected) info.append(el("span", `tr-chip ${d.summary.divergenceDetected === "bullish" ? "golden" : "death"}`, "◇ Div."));
    bottom.append(info, el("span", null, px(d.price, d.price)));
  }
  bottom.append(WatchlistGroups.renderPicker(tr.groups, d.group, value => assignTickerGroup(d.ticker, value)));
  item.append(top, bottom);
  if (!d.error) {
    const select = () => { tr.selected = d.ticker; SelectedTicker.set(d.ticker); render(); draw(); };
    item.addEventListener("click", select);
    WatchlistEdit.makeFocusable(item, select);
  }
  return item;
}

async function removeTicker(t) {
  try {
    await watchlistApi(`/${encodeURIComponent(t)}`, { method: "DELETE" });
    tr.items = tr.items.filter(x => x.ticker !== t);
    if (tr.selected === t) {
      tr.selected = tr.items.find(valid)?.ticker || null;
      if (tr.selected) SelectedTicker.set(tr.selected); else SelectedTicker.clear();
      draw();
    }
    render();
  } catch (e) { $("tr-status").textContent = `No se pudo eliminar ${t}: ${e.message}`; }
}

async function groupAction(fn) {
  try { tr.groups = await fn(); render(); } catch (e) { $("tr-status").textContent = e.message; }
}

async function assignTickerGroup(ticker, value) {
  if (value === "__new__") {
    const name = await WatchlistGroups.promptText("Nombre del nuevo grupo:");
    if (!name) { render(); return; }
    try { tr.groups = await WatchlistGroups.create(watchlistApi, name); value = name; }
    catch (e) { $("tr-status").textContent = e.message; render(); return; }
  }
  try {
    await WatchlistGroups.setTickerGroup(watchlistApi, ticker, value || null);
    const item = tr.items.find(d => d.ticker === ticker);
    if (item) item.group = value || null;
    render();
  } catch (e) { $("tr-status").textContent = e.message; }
}

async function renameGroupPrompt(name) {
  const next = await WatchlistGroups.promptText("Nuevo nombre del grupo:", name);
  if (!next || next === name) return;
  await groupAction(() => WatchlistGroups.rename(watchlistApi, name, next));
  for (const d of tr.items) if (d.group === name) d.group = next;
  render();
}

async function deleteGroupPrompt(name) {
  if (!(await WatchlistGroups.confirmAction(`¿Eliminar el grupo "${name}"? Los tickers vuelven a "Sin categoría".`))) return;
  await groupAction(() => WatchlistGroups.remove(watchlistApi, name));
  for (const d of tr.items) if (d.group === name) d.group = null;
  render();
}

async function createGroupPrompt() {
  const name = await WatchlistGroups.promptText("Nombre del nuevo grupo:");
  if (name) await groupAction(() => WatchlistGroups.create(watchlistApi, name));
}

async function addTicker() {
  const input = $("tr-ticker-input");
  const t = input.value.trim().toUpperCase();
  if (!t) return;
  input.value = "";
  $("tr-status").textContent = `Agregando ${t}…`;
  try {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(t)}`, { method: "POST", headers: { "X-Auth-Token": tr.token } });
    if (res.status === 401) throw new Error(LOGIN_MSG);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    tr.selected = t; SelectedTicker.set(t);
    await load();
  } catch (e) { $("tr-status").textContent = `No se pudo agregar ${t}: ${e.message}`; }
}

// ---------------------------------------------------------------- detalle
async function loadDetail(ticker) {
  const key = `${ticker}|${interval()}|${atrMult()}`;
  // Cancelar antes de mirar la caché: si no, una petición lenta de otro
  // intervalo seguiría viva y dibujaría encima al terminar.
  tr.abort?.abort();
  if (tr.detail[key]) return tr.detail[key];
  tr.abort = new AbortController();
  const timeout = AbortSignal.timeout(90000);
  const signal = AbortSignal.any ? AbortSignal.any([tr.abort.signal, timeout]) : tr.abort.signal;
  const res = await fetch(`/api/trullas?ticker=${encodeURIComponent(ticker)}&interval=${interval()}&atr_mult=${atrMult()}`,
    { headers: { "X-Auth-Token": tr.token }, signal });
  if (res.status === 401) throw new Error(LOGIN_MSG);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  const { item } = await res.json();
  if (item.error) throw new Error(item.error);
  tr.detail[key] = item;
  return item;
}

function tradingViewSymbol(t, cls) {
  const special = { "^GSPC": "SP:SPX", "^NDX": "NASDAQ:NDX", "^IXIC": "NASDAQ:IXIC", "^DJI": "DJ:DJI", "^RUT": "TVC:RUT", "^VIX": "TVC:VIX" };
  if (special[t]) return special[t];
  if (cls === "index") return t.slice(1);
  if (cls === "forex") return `FX:${t.replace("=X", "")}`;
  if (cls === "future") return `${t.replace("=F", "")}1!`;
  if (cls === "crypto") return `COINBASE:${t.replace("-", "")}`;
  return t;
}

function clearChart() {
  for (const s of Object.values(tr.series)) s.setData([]);
  tr.series.candles?.setMarkers([]);
  for (const line of tr.priceLines) tr.series.candles.removePriceLine(line);
  for (const line of tr.stochLines) tr.series.k.removePriceLine(line);
  tr.priceLines = []; tr.stochLines = [];
}

async function draw() {
  const d = tr.items.find(x => x.ticker === tr.selected && valid(x));
  const metrics = $("selected-metrics"); metrics.replaceChildren();
  tr.refPrice = d?.price;
  if (tr.chart) clearChart();
  $("tv-link").hidden = true;
  if (!d) {
    $("chart-title").textContent = "Sin activo seleccionado";
    $("chart-caption").textContent = "No hay datos para dibujar.";
    $("diag-panel").replaceChildren(el("div", "empty", "El diagnóstico aparece al seleccionar un activo."));
    return;
  }
  const title = el("strong", null, d.ticker);
  $("chart-title").replaceChildren(title, document.createTextNode(` · ${d.asset_class_label} · ${$("interval").selectedOptions[0].textContent}`));
  $("tv-link").href = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol(d.ticker, d.asset_class))}`;
  $("tv-link").hidden = false;
  $("chart-caption").textContent = "Calculando diagnóstico…";
  $("diag-panel").replaceChildren(el("div", "empty", "Calculando diagnóstico…"));
  let detail;
  try { detail = await loadDetail(d.ticker); }
  catch (e) {
    if (e.name === "AbortError") return; // otra selección reemplazó a esta
    if (tr.selected === d.ticker) {
      $("chart-caption").textContent = `No se pudo cargar ${d.ticker}: ${e.message}`;
      $("diag-panel").replaceChildren(el("div", "empty", e.message));
    }
    return;
  }
  if (tr.selected !== d.ticker || detail.interval !== interval() || detail.volatility.mult !== atrMult()) return;
  tr.refPrice = detail.price;
  for (const [label, value, cls] of [["Último precio", px(detail.price)], ["SMA 200", px(detail.sma.sma200)],
    ["SMA 70", px(detail.sma.sma70)], ["SMA 6", px(detail.sma.sma6)], ["Señal", SIGNAL[detail.summary.smaSignal][0], SIGNAL[detail.summary.smaSignal][1]]]) {
    const box = el("div"); const v = el("strong", cls, value);
    box.append(el("span", null, label), v); metrics.append(box);
  }
  renderDiagnosis(detail);
  if (tr.chart) plot(detail);
  $("chart-caption").textContent = `Última vela: ${dateOf(detail.bar_time)} UTC · La vela en curso puede variar. Order flow Level-2 no disponible con los proveedores actuales.`;
}

function plot(detail) {
  const bars = detail.bars, s = detail.series;
  const line = key => bars.flatMap((b, i) => s[key][i] == null ? [] : [{ time: b.t, value: s[key][i] }]);
  // El estocástico va en otro gráfico: se rellenan huecos con "whitespace" para
  // que ambos tengan el mismo índice lógico por vela y se puedan sincronizar.
  const padded = key => bars.map((b, i) => s[key][i] == null ? { time: b.t } : { time: b.t, value: s[key][i] });
  tr.series.candles.setData(bars.map(b => ({ time: b.t, open: b.o, high: b.h, low: b.l, close: b.c })));
  tr.series.volume.setData(bars.flatMap(b => b.v ? [{ time: b.t, value: b.v, color: b.c >= b.o ? "#69b6a133" : "#ee879133" }] : []));
  tr.series.s200.setData(line("sma200")); tr.series.s70.setData(line("sma70")); tr.series.s6.setData(line("sma6"));
  tr.series.k.setData(padded("stoch_k")); tr.series.d.setData(padded("stoch_d"));
  tr.stochLines = [80, 20].map(price => tr.series.k.createPriceLine({ price, color: "#26313e", lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
  // Solo la divergencia activa: una antigua no tiene objetivo en el panel, tampoco en el gráfico.
  const div = detail.divergence.active ? detail.divergence.latest : null;
  const markers = [];
  if (div) {
    const bull = div.direction === "bullish";
    const color = bull ? "#22c55e" : "#ef4444";
    const pos = bull ? "belowBar" : "aboveBar";
    const shape = bull ? "arrowUp" : "arrowDown";
    markers.push({ time: div.p1.t, position: pos, color, shape, text: "P1" }, { time: div.p2.t, position: pos, color, shape, text: "P2" },
      { time: div.absolute.t, position: bull ? "aboveBar" : "belowBar", color: COLORS.abs, shape: "circle", text: "Abs" });
    tr.series.ray.setData([{ time: div.p1.t, value: div.p1.price }, { time: div.p2.t, value: div.p2.price }]);
    tr.series.proj.setData([{ time: div.p2.t, value: div.p2.price }, { time: bars[bars.length - 1].t, value: div.target66 }]);
    if (div.p1.stoch != null && div.p2.stoch != null) tr.series.stochRay.setData([{ time: div.p1.t, value: div.p1.stoch }, { time: div.p2.t, value: div.p2.stoch }]);
    const pl = (price, color, title, lineStyle = 2) => tr.series.candles.createPriceLine({ price, color, title, lineWidth: 1, lineStyle, axisLabelVisible: true });
    tr.priceLines.push(pl(div.target66, COLORS.t66, "66% Dow", 0), pl(div.target618, COLORS.t618, "61,8% Fib"), pl(div.absolute.price, COLORS.abs, "Absoluto", 3));
  }
  if (detail.volatility.stop != null) {
    tr.priceLines.push(tr.series.candles.createPriceLine({ price: detail.volatility.stop, color: "#ee8791", lineWidth: 1, lineStyle: 1,
      title: `Stop ${detail.volatility.mult}×ATR`, axisLabelVisible: true }));
  }
  const cross = detail.sma.last_cross;
  if (cross) markers.push({ time: cross.t, position: cross.type === "up" ? "belowBar" : "aboveBar", color: cross.type === "up" ? COLORS.s6 : COLORS.s70,
    shape: "square", text: cross.type === "up" ? "6↑70" : "6↓70" });
  tr.series.candles.setMarkers(markers.sort((a, b) => a.time - b.time));
  tr.chart.timeScale().applyOptions({ timeVisible: interval() !== "1d" });
  tr.stoch.timeScale().applyOptions({ timeVisible: interval() !== "1d" });
  setRange();
}

function setRange() {
  const detail = tr.detail[`${tr.selected}|${interval()}|${atrMult()}`];
  if (!detail || !tr.chart) return;
  const n = detail.bars.length;
  // Tras un setData, el estocástico emite su propio cambio de rango ("todo")
  // en el siguiente frame y la sincronización lo copiaría al principal: se
  // aplica el rango elegido después de ese frame y en ambos gráficos.
  requestAnimationFrame(() => {
    for (const chart of [tr.chart, tr.stoch]) {
      if (!tr.range) chart.timeScale().fitContent();
      else chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - tr.range), to: n + 3 });
    }
  });
}

// ------------------------------------------------------------ diagnóstico
function card(title, stateText, stateCls, rows, note) {
  const box = el("article", `diag-card ${stateCls || ""}`);
  const head = el("div", "diag-head");
  head.append(el("h3", null, title), el("strong", `diag-state ${stateCls || ""}`, stateText));
  box.append(head);
  const dl = el("dl", "diag-rows");
  for (const [k, v, cls] of rows) { dl.append(el("dt", null, k), el("dd", cls, v)); }
  box.append(dl);
  if (note) box.append(el("p", "diag-note", note));
  return box;
}

function renderDiagnosis(d) {
  const panel = $("diag-panel"); panel.replaceChildren();
  const head = el("div", "diag-title");
  head.append(el("h2", null, d.ticker), el("span", null, `${d.asset_class_label} · ${$("interval").selectedOptions[0].textContent}`));
  panel.append(head);

  // 1. Top-down
  const td = d.top_down;
  const [trend, trendCls] = TREND[td.macro_trend];
  const rs = d.relative_strength;
  const rows = td.levels.map(l => [`${l.level}${l.symbol ? ` (${l.symbol})` : ""}`,
    l.trend ? `${TREND[l.trend][0]} · ${pct(l.distance_pct, 1)} vs SMA 200` : "Sin referencia", l.trend ? TREND[l.trend][1] : ""]);
  rows.push(["Fuerza relativa 3M", rs.value == null ? "—" : `${RS[rs.label][0]} · ${pp(rs.value)} vs ${rs.benchmark}`, RS[rs.label][1]]);
  panel.append(card("1 · Filtro top-down", trend, trendCls, rows,
    td.aligned ? "Mercado y sector no contradicen la tendencia del activo." : td.macro_trend === "neutral"
      ? "El activo no tiene tendencia macro definida: no hay sesgo que filtrar."
      : "Algún nivel superior va en contra: la señal pierde calidad."));

  // 2. Medias móviles
  const sma = d.sma;
  const [sig, sigCls] = SIGNAL[sma.signal];
  const slope = v => v == null ? "—" : `${v > 0 ? "↑ positiva" : v < 0 ? "↓ negativa" : "→ plana"}`;
  const cross = sma.last_cross;
  panel.append(card("2 · Medias 200 / 70 / 6", sig + (sma.fresh && sma.signal !== "wait" ? " · nueva" : ""), sigCls, [
    ["Pendiente SMA 200", slope(sma.slope200), sma.slope200 > 0 ? "golden" : "death"],
    ["Pendiente SMA 70", slope(sma.slope70), sma.slope70 > 0 ? "golden" : "death"],
    ["SMA 70 vs 200", sma.sma70 > sma.sma200 ? "Por encima" : "Por debajo"],
    ["Último cruce 6/70", cross ? `${cross.type === "up" ? "Alcista" : "Bajista"} · hace ${cross.bars_ago} velas` : "—"],
  ], sma.note));

  // 3. Divergencias
  const div = d.divergence;
  const latest = div.latest;
  const divState = div.active ? (latest.direction === "bullish" ? "Alcista activa" : "Bajista activa") : latest ? "Antigua" : "Sin divergencia";
  const divCls = div.active ? (latest.direction === "bullish" ? "golden" : "death") : "";
  const divRows = latest ? [
    ["P1", `${dateOf(latest.p1.t)} · ${px(latest.p1.price)}`],
    ["P2", `${dateOf(latest.p2.t)} · ${px(latest.p2.price)} · hace ${latest.bars_ago} velas`],
    ["Volumen P1 → P2", `${vol(latest.p1.volume)} → ${vol(latest.p2.volume)}`, latest.volume ? divCls || "gold" : ""],
    ["Estocástico P1 → P2", latest.p1.stoch == null ? "—" : `${num(latest.p1.stoch, 1)} → ${num(latest.p2.stoch, 1)}`, latest.stochastic ? divCls || "gold" : ""],
  ] : [["Pivotes recientes", `${div.pivot_highs.length} máximos · ${div.pivot_lows.length} mínimos`]];
  divRows.push(["Estocástico (14,3,5)", div.stoch_k == null ? "—" : `%K ${num(div.stoch_k, 1)} · %D ${num(div.stoch_d, 1)}`]);
  const confirmedBy = latest ? [latest.volume && "volumen", latest.stochastic && "estocástico"].filter(Boolean).join(" y ") : "";
  panel.append(card("3 · Divergencias", divState, divCls, divRows,
    latest ? `Confirmada por ${confirmedBy}.${div.active ? "" : " P2 tiene más de 40 velas: ya no se considera activa."}`
      : (div.has_volume ? "Los dos últimos pivotes no muestran asimetría de volumen ni de estocástico." : "Este activo no informa volumen: solo se evalúa el estocástico.")));

  // 4. Retroceso
  const target = div.active ? latest : null;
  panel.append(card("4 · Objetivo de retroceso", target ? `${px(target.target66)}` : "Sin objetivo", target ? "gold" : "", target ? [
    ["Extremo absoluto", `${px(target.absolute.price)} · ${dateOf(target.absolute.t)}`],
    ["Rango (Abs − P2)", px(target.range)],
    ["Objetivo 66% Dow", `${px(target.target66)} · ${pct((target.target66 / d.price - 1) * 100)}`, "gold"],
    ["Objetivo 61,8% Fib", `${px(target.target618)} · ${pct((target.target618 / d.price - 1) * 100)}`, "fib"],
  ] : [["Estado", "Requiere una divergencia activa entre P1 y P2"]],
  target ? "Distancias medidas desde el último precio. En el gráfico: rayo P1→P2, proyección hacia el 66% y líneas horizontales." : null));

  // 5. Volatilidad
  const v = d.volatility;
  const rel = v.relative_volume;
  panel.append(card("5 · Volatilidad y stop", v.stop == null ? "—" : px(v.stop), "death", [
    ["ATR (14)", v.atr == null ? "—" : `${px(v.atr)} · ${num(v.atr_pct, 2)}% del precio`],
    [`Stop largo (−${v.mult}×ATR)`, px(v.stop_long), v.side === "long" ? "death" : ""],
    [`Stop corto (+${v.mult}×ATR)`, px(v.stop_short), v.side === "short" ? "death" : ""],
    ["Volumen relativo (20)", rel == null ? "—" : `${num(rel, 2)}×${rel >= 2 ? " · vela de gran volumen" : ""}`, rel >= 2 ? "gold" : ""],
  ], `Stop sugerido para el sesgo ${v.side === "short" ? "corto" : "largo"}. ${d.order_flow.reason}`));
}

// ---------------------------------------------------------------- gráfico
function createCharts() {
  if (typeof LightweightCharts === "undefined") return;
  const base = { autoSize: true, layout: { background: { color: "transparent" }, textColor: "#8e9dac" },
    grid: { vertLines: { color: "#192330" }, horzLines: { color: "#192330" } }, timeScale: { timeVisible: false, rightOffset: 3 } };
  tr.chart = LightweightCharts.createChart($("tr-chart"), base);
  tr.series.candles = tr.chart.addCandlestickSeries({ upColor: "#69b6a1", downColor: "#ee8791", borderVisible: false, wickUpColor: "#69b6a1", wickDownColor: "#ee8791" });
  tr.series.volume = tr.chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  tr.chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  const lineOpts = (color, width, title) => ({ color, lineWidth: width, priceLineVisible: false, lastValueVisible: false, title, crosshairMarkerVisible: false });
  tr.series.s200 = tr.chart.addLineSeries(lineOpts(COLORS.s200, 2, "200"));
  tr.series.s70 = tr.chart.addLineSeries(lineOpts(COLORS.s70, 2, "70"));
  tr.series.s6 = tr.chart.addLineSeries(lineOpts(COLORS.s6, 1, "6"));
  tr.series.ray = tr.chart.addLineSeries({ ...lineOpts(COLORS.ray, 2, ""), lineStyle: 0 });
  tr.series.proj = tr.chart.addLineSeries({ ...lineOpts(COLORS.t66, 1, ""), lineStyle: 2 });
  tr.stoch = LightweightCharts.createChart($("tr-stoch"), { ...base, rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 } } });
  tr.series.k = tr.stoch.addLineSeries({ ...lineOpts(COLORS.k, 1, "%K"), lastValueVisible: true });
  tr.series.d = tr.stoch.addLineSeries({ ...lineOpts(COLORS.d, 1, "%D"), lastValueVisible: true });
  tr.series.stochRay = tr.stoch.addLineSeries({ ...lineOpts(COLORS.ray, 2, ""), lineStyle: 0 });
  // Sincroniza el desplazamiento/zoom de ambos gráficos (mismo índice lógico por vela).
  let syncing = false;
  const sync = (from, to) => from.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (syncing || !range) return;
    syncing = true; to.timeScale().setVisibleLogicalRange(range); syncing = false;
  });
  sync(tr.chart, tr.stoch); sync(tr.stoch, tr.chart);
}

// ---------------------------------------------------------------- eventos
$("update").onclick = () => load(true);
$("tr-add-btn").onclick = addTicker;
$("tr-group-btn").onclick = createGroupPrompt;
$("tr-ticker-input").addEventListener("keydown", e => { if (e.key === "Enter") addTicker(); });
$("tr-search").addEventListener("input", e => { tr.search = e.target.value.trim().toUpperCase(); render(); });
$("asset-filter").onchange = e => { tr.assetFilter = e.target.value; render(); };
$("interval").onchange = () => draw();
$("atr-mult").onchange = () => draw();
WatchlistEdit.bindToggle($("tr-list"), $("edit-btn"));
document.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => {
  tr.filter = b.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach(x => x.classList.toggle("active", x === b));
  render();
});
document.querySelectorAll("[data-range]").forEach(b => b.onclick = () => {
  tr.range = Number(b.dataset.range);
  document.querySelectorAll("[data-range]").forEach(x => x.classList.toggle("active", x === b));
  setRange();
});

// El video solo se carga al abrir el desplegable (no consume datos mientras
// está cerrado) y se descarga al cerrarlo, para que no siga sonando oculto.
$("method-video").addEventListener("toggle", e => {
  const frame = e.target.querySelector("iframe");
  if (e.target.open) { if (!frame.src) frame.src = frame.dataset.src; }
  else frame.removeAttribute("src");
});

async function main() {
  createCharts();
  // Igual que Cross Monitor: en la propia PC el token de desarrollo no protege
  // de nadie, así que se prueba si no hay uno guardado (ver app.js).
  const isLocalHost = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  tr.token = (await savedToken().catch(() => "")) || (isLocalHost ? "dev-token" : "");
  await load();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
}
main();
