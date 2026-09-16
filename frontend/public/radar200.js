"use strict";
const radar = { items: [], detail: {}, selected: null, filter: "all", range: 252, token: "", chart: null, candles: null, average: null, type: "sma", trendLookback: 10 };
const $ = id => document.getElementById(id);
const threshold = () => Number($("threshold").value);
const valid = d => !d.error;
const near = d => valid(d) && Math.abs(d.distance_pct) <= threshold();
const signed = n => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
const trendIcon = t => t === "up" ? "↑" : t === "down" ? "↓" : t === "flat" ? "→" : "";
const trendClass = t => t === "up" ? "golden" : t === "down" ? "death" : "";
const trendLabel = t => t === "up" ? "Subiendo" : t === "down" ? "Bajando" : t === "flat" ? "Plana" : "Sin datos suficientes";
const trendTooltip = t => t ? `MA 200 ${trendLabel(t).toLowerCase()} en las últimas ${radar.trendLookback} sesiones` : "";
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
  $("update").disabled = true; $("average-type").disabled = true;
  $("radar-status").textContent = "Consultando cotizaciones…";
  const type = $("average-type").value;
  try {
    const res = await fetch(`/api/radar200?ma_type=${type}&refresh=${force}`, {headers: {"X-Auth-Token": radar.token}, signal: AbortSignal.timeout(120000)});
    if (res.status === 401) throw new Error("Abre Cross Monitor para iniciar sesión y vuelve a este radar.");
    if (!res.ok) throw new Error(`No se pudo obtener la lista (${res.status}).`);
    const data = await res.json(); radar.items = data.items; radar.type = data.ma_type;
    radar.trendLookback = data.ma_trend_lookback || radar.trendLookback;
    if (force) radar.detail = {}; // refresco: descarta detalle cacheado, se vuelve a pedir al dibujar
    const good = radar.items.filter(valid);
    if (!good.some(d => d.ticker === radar.selected)) radar.selected = good[0]?.ticker || null;
    $("radar-status").textContent = `${good.length} activos disponibles · ${radar.items.length-good.length} con error`;
    $("consulted").textContent = `Consulta: ${new Date().toLocaleTimeString()}`;
    $("ma-label").textContent = `${radar.type.toUpperCase()} 200 · Diario`;
    $("legend-label").textContent = `${radar.type.toUpperCase()} 200`;
    render(); await draw();
  } catch(e) {
    $("average-type").value = radar.type;
    $("radar-status").textContent = `${e.message} Los datos anteriores, si existen, no se han actualizado.`;
  } finally { $("update").disabled = false; $("average-type").disabled = false; }
}
function render() {
  const good = radar.items.filter(valid);
  $("total").textContent = good.length; $("near").textContent = good.filter(near).length;
  $("above").textContent = good.filter(d => d.distance_pct > 0).length;
  $("below").textContent = good.filter(d => d.distance_pct < 0).length;
  $("near-label").textContent = `Distancia absoluta ≤ ${threshold()}%`;
  const items = radar.items.filter(d => radar.filter === "all" || (valid(d) && (radar.filter === "near" ? near(d) : !near(d))));
  items.sort((a,b) => {
    if (!!a.error !== !!b.error) return a.error ? 1 : -1;
    if ($( "sort").value === "name" || a.error) return a.ticker.localeCompare(b.ticker);
    return (Math.abs(a.distance_pct)-Math.abs(b.distance_pct)) * ($("sort").value === "far" ? -1 : 1);
  });
  const list = $("distance-list"); list.replaceChildren();
  if (!items.length) { const el = document.createElement("div"); el.className = "empty"; el.textContent = "No hay activos en este filtro. Agrega símbolos desde Cross Monitor o cambia el umbral."; list.append(el); }
  for (const d of items) {
    const button = document.createElement("button"); button.className = `distance-item${radar.selected === d.ticker ? " selected" : ""}`;
    const top = document.createElement("div"); top.className = "distance-top";
    const nameGroup = document.createElement("span"); nameGroup.className = "distance-name";
    const name = document.createElement("strong"); name.textContent = d.ticker; nameGroup.append(name);
    if (!d.error && d.ma_trend) {
      const trend = document.createElement("span"); trend.className = `ma-trend ${trendClass(d.ma_trend)}`;
      trend.title = trendTooltip(d.ma_trend);
      trend.textContent = trendIcon(d.ma_trend); nameGroup.append(trend);
    }
    top.append(nameGroup);
    const distance = document.createElement("span"); distance.textContent = d.error ? "Sin datos" : signed(d.distance_pct); distance.className = d.distance_pct < 0 ? "death" : "golden"; top.append(distance);
    const bottom = document.createElement("div"); bottom.className = "distance-bottom";
    const label = document.createElement("span"); label.textContent = d.error || `${near(d) ? "Cerca" : "Lejos"} · ${d.distance_pct === 0 ? "En la media" : d.distance_pct > 0 ? "Por encima" : "Por debajo"}`;
    const price = document.createElement("span"); price.textContent = d.error ? "" : d.price.toFixed(2); bottom.append(label,price); button.append(top,bottom);
    if (!d.error) { const track = document.createElement("div"); track.className = `distance-track ${d.distance_pct < 0 ? "below" : ""}`; const fill = document.createElement("span"); fill.style.width = `${Math.min(100,Math.abs(d.distance_pct)/20*100)}%`; track.append(fill); button.append(track); button.onclick=()=>{radar.selected=d.ticker;render();draw();}; }
    else button.disabled=true;
    list.append(button);
  }
}
function setRange() {
  const detail = radar.detail[radar.selected]; if(!detail || !radar.chart) return;
  if (!radar.range) radar.chart.timeScale().fitContent();
  else radar.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,detail.bars.length-radar.range),to:detail.bars.length+3});
}
async function loadDetail(ticker) {
  if (radar.detail[ticker]) return radar.detail[ticker];
  const res = await fetch(`/api/radar200?ma_type=${radar.type}&ticker=${encodeURIComponent(ticker)}`, {headers: {"X-Auth-Token": radar.token}, signal: AbortSignal.timeout(60000)});
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (data.item.error) throw new Error(data.item.error);
  radar.detail[ticker] = data.item;
  return data.item;
}
async function draw() {
  radar.hideCursor?.();
  const d = radar.items.find(d=>d.ticker===radar.selected && valid(d));
  const metrics = $("selected-metrics"); metrics.replaceChildren();
  radar.candles?.setData([]); radar.average?.setData([]);
  if(!d) {$("chart-title").textContent="Sin activo seleccionado";$("chart-caption").textContent="No hay datos para dibujar.";return;}
  const chartTitle = document.createElement("strong");chartTitle.textContent=d.ticker;$("chart-title").replaceChildren(chartTitle);
  const maLabel = `${radar.type.toUpperCase()} 200`;
  const maValue = `${d.average.toFixed(2)}${d.ma_trend ? " " + trendIcon(d.ma_trend) : ""}`;
  for(const [label,value] of [["Último precio",d.price.toFixed(2)],[maLabel,maValue],["Distancia",signed(d.distance_pct)]]) {
    const div=document.createElement("div"),l=document.createElement("span"),v=document.createElement("strong");
    l.textContent=label;v.textContent=value;div.append(l,v);metrics.append(div);
    if (label === maLabel && d.ma_trend) { v.className = trendClass(d.ma_trend); v.title = trendTooltip(d.ma_trend); }
  }
  $("chart-caption").textContent = "Cargando gráfico…";
  let detail;
  try { detail = await loadDetail(d.ticker); }
  catch(e) { if (radar.selected === d.ticker) $("chart-caption").textContent = `No se pudo cargar el gráfico de ${d.ticker}: ${e.message}`; return; }
  if (radar.selected !== d.ticker) return; // el usuario cambió de selección mientras cargaba
  if(radar.chart){radar.candles.setData(detail.bars.map(b=>({time:b.t,open:b.o,high:b.h,low:b.l,close:b.c})));radar.average.applyOptions({title:maLabel});radar.average.setData(detail.bars.flatMap((b,i)=>detail.series[i]===null?[]:[{time:b.t,value:detail.series[i]}]));setRange();}
  $("chart-caption").textContent=`Última barra: ${d.bar_date} · ${near(d)?"Dentro":"Fuera"} del umbral ±${threshold()}%. La sesión en curso puede variar.`;
}
$("update").onclick=()=>load(true);$("average-type").onchange=()=>load();
$("threshold").onchange=()=>{render();draw();};$("sort").onchange=render;
document.querySelectorAll("[data-filter]").forEach(b=>b.onclick=()=>{radar.filter=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.classList.toggle("active",x===b));render();});
document.querySelectorAll("[data-range]").forEach(b=>b.onclick=()=>{radar.range=Number(b.dataset.range);document.querySelectorAll("[data-range]").forEach(x=>x.classList.toggle("active",x===b));setRange();});
function installDistanceCursor() {
  const host = $("own-chart");
  const measure = document.createElement("div"); measure.className = "distance-measure hidden";
  measure.innerHTML = '<i class="measure-dot start"></i><i class="measure-dot end"></i>';
  const tip = document.createElement("div"); tip.className = "distance-tooltip hidden";
  const date = document.createElement("div"), percent = document.createElement("strong"), values = document.createElement("div");
  tip.append(date, percent, values); host.append(measure, tip);
  radar.hideCursor = () => {measure.classList.add("hidden");tip.classList.add("hidden");};
  radar.chart.subscribeCrosshairMove(param => {
    radar.hideCursor();
    if (!param.point || param.time == null || param.point.x < 0 || param.point.y < 0 || param.point.x >= host.clientWidth || param.point.y >= host.clientHeight) return;
    const candle = param.seriesData.get(radar.candles), ma = param.seriesData.get(radar.average);
    if (!candle || !Number.isFinite(candle.close)) return;
    date.textContent = typeof param.time === "number" ? new Date(param.time * 1000).toISOString().slice(0,10) : `${param.time.year}-${String(param.time.month).padStart(2,"0")}-${String(param.time.day).padStart(2,"0")}`;
    if (!ma || !Number.isFinite(ma.value) || ma.value <= 0) {
      percent.textContent = "MA 200 no disponible"; percent.className = "";
      values.textContent = "Faltan 200 sesiones para esta fecha.";
    } else {
      const distance = (candle.close / ma.value - 1) * 100;
      percent.textContent = `${signed(distance)} · ${distance > 0 ? "por encima" : distance < 0 ? "por debajo" : "en la media"}`;
      percent.className = distance < 0 ? "death" : "golden";
      values.textContent = `Cierre ${candle.close.toFixed(2)} · ${radar.type.toUpperCase()} 200 ${ma.value.toFixed(2)}`;
      const x = radar.chart.timeScale().timeToCoordinate(param.time);
      const closeY = radar.candles.priceToCoordinate(candle.close), maY = radar.average.priceToCoordinate(ma.value);
      if (x !== null && closeY !== null && maY !== null) {
        measure.style.left = `${x}px`; measure.style.top = `${Math.min(closeY, maY)}px`;
        measure.style.height = `${Math.max(1, Math.abs(closeY-maY))}px`;
        measure.style.color = distance < 0 ? "var(--death)" : "var(--gold)";
        measure.classList.remove("hidden");
      }
    }
    tip.classList.remove("hidden");
    tip.style.left = `${Math.max(6, Math.min(param.point.x+18, host.clientWidth-tip.offsetWidth-8))}px`;
    tip.style.top = `${Math.max(6, Math.min(param.point.y+18, host.clientHeight-tip.offsetHeight-8))}px`;
  });
  host.addEventListener("mouseleave", radar.hideCursor);
  radar.chart.timeScale().subscribeVisibleLogicalRangeChange(radar.hideCursor);
}

async function main(){
  if(typeof LightweightCharts!=="undefined") {radar.chart=LightweightCharts.createChart($("own-chart"),{autoSize:true,layout:{background:{color:"transparent"},textColor:"#8e9dac"},grid:{vertLines:{color:"#192330"},horzLines:{color:"#192330"}},timeScale:{timeVisible:false}});radar.candles=radar.chart.addCandlestickSeries({upColor:"#69b6a1",downColor:"#ee8791",borderVisible:false,wickUpColor:"#69b6a1",wickDownColor:"#ee8791"});radar.average=radar.chart.addLineSeries({color:"#e7c46a",lineWidth:2,priceLineVisible:false});}
  if (radar.chart) installDistanceCursor();
  radar.token=await savedToken().catch(()=>"");await load();
  if("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(()=>{});
}
main();
