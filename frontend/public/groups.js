"use strict";
// Agrupación de watchlist en secciones colapsables -- compartido por Cross
// Monitor, Radar MA 200 y Análisis Fundamental (misma watchlist, mismos
// grupos, ver /api/watchlist/groups). Cada página inyecta su propio
// `watchlistApi(path, options)` ya resuelto con auth/manejo de 401; este
// módulo no sabe nada de eso, solo arma las llamadas y las secciones.
const WatchlistGroups = {
  list(api) { return api("/groups").then(r => r.groups); },
  create(api, name) { return api("/groups", { method: "POST", body: JSON.stringify({ name }) }).then(r => r.groups); },
  rename(api, oldName, newName) { return api(`/groups/${encodeURIComponent(oldName)}`, { method: "PUT", body: JSON.stringify({ name: newName }) }).then(r => r.groups); },
  remove(api, name) { return api(`/groups/${encodeURIComponent(name)}`, { method: "DELETE" }).then(r => r.groups); },
  move(api, name, direction) { return api(`/groups/${encodeURIComponent(name)}/move`, { method: "POST", body: JSON.stringify({ direction }) }).then(r => r.groups); },
  setTickerGroup(api, ticker, group) { return api(`/${encodeURIComponent(ticker)}/group`, { method: "PUT", body: JSON.stringify({ group }) }); },

  // Reparte `items` (cada uno con `.ticker` y `.group`) en el orden de
  // `groupNames`; lo no asignado (o cuyo grupo ya no existe) va al final
  // bajo un bucket "Sin categoría" (name: null).
  bucket(items, groupNames) {
    const byName = new Map(groupNames.map(n => [n, []]));
    const ungrouped = [];
    for (const item of items) {
      if (item.group && byName.has(item.group)) byName.get(item.group).push(item);
      else ungrouped.push(item);
    }
    const sections = groupNames.map(n => ({ name: n, items: byName.get(n) }));
    sections.push({ name: null, items: ungrouped });
    return sections;
  },

  isCollapsed(pageKey, name) {
    try { return localStorage.getItem(`wg-collapsed:${pageKey}:${name || ""}`) === "1"; }
    catch { return false; }
  },
  setCollapsed(pageKey, name, collapsed) {
    try { localStorage.setItem(`wg-collapsed:${pageKey}:${name || ""}`, collapsed ? "1" : "0"); }
    catch { /* localStorage no disponible (privado/bloqueado) -- se pierde solo la preferencia de colapso */ }
  },

  // Encabezado colapsable de una sección. `name` es null para "Sin
  // categoría" (sin controles de mover/renombrar/eliminar). Devuelve el
  // contenedor `body` donde la página debe agregar sus propias filas.
  renderSection(container, pageKey, name, count, handlers) {
    const wrap = document.createElement("div");
    wrap.className = "wg-section";
    const header = document.createElement("div");
    header.className = "wg-header";
    let collapsed = WatchlistGroups.isCollapsed(pageKey, name);
    const chev = document.createElement("button");
    chev.type = "button"; chev.className = "wg-chev"; chev.textContent = "▾";
    if (collapsed) chev.classList.add("collapsed");
    const title = document.createElement("span");
    title.className = "wg-title"; title.textContent = name || "Sin categoría";
    const countEl = document.createElement("span");
    countEl.className = "wg-count"; countEl.textContent = count;
    header.append(chev, title, countEl);
    const body = document.createElement("div");
    body.className = "wg-body";
    body.hidden = collapsed;
    if (name) {
      const actions = document.createElement("span");
      actions.className = "wg-actions";
      const mk = (label, title) => { const b = document.createElement("button"); b.type = "button"; b.className = "wg-icon-btn"; b.title = title; b.textContent = label; return b; };
      const up = mk("↑", "Subir grupo"), down = mk("↓", "Bajar grupo"), ren = mk("✎", "Renombrar grupo"), del = mk("🗑", "Eliminar grupo");
      up.onclick = (e) => { e.stopPropagation(); handlers.onMove?.("up"); };
      down.onclick = (e) => { e.stopPropagation(); handlers.onMove?.("down"); };
      ren.onclick = (e) => { e.stopPropagation(); handlers.onRename?.(); };
      del.onclick = (e) => { e.stopPropagation(); handlers.onDelete?.(); };
      actions.append(up, down, ren, del);
      header.append(actions);
    }
    header.addEventListener("click", () => {
      collapsed = !body.hidden;
      body.hidden = collapsed;
      chev.classList.toggle("collapsed", collapsed);
      WatchlistGroups.setCollapsed(pageKey, name, collapsed);
    });
    wrap.append(header, body);
    container.append(wrap);
    return body;
  },

  // Selector para asignar/cambiar el grupo de un ticker. `onChange(newGroupOrNull)`.
  renderPicker(groupNames, currentGroup, onChange) {
    const select = document.createElement("select");
    select.className = "wg-picker"; select.title = "Grupo";
    const opt = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; return o; };
    select.append(opt("", "Sin categoría"));
    for (const g of groupNames) select.append(opt(g, g));
    select.append(opt("__new__", "+ Nuevo grupo…"));
    select.value = currentGroup || "";
    select.addEventListener("click", (e) => e.stopPropagation());
    select.addEventListener("change", (e) => { e.stopPropagation(); onChange(select.value); });
    return select;
  },

  // Diálogo propio (no usa prompt()/confirm() nativos -- no funcionan en
  // algunos contextos embebidos, y un diálogo con el estilo de la app es
  // mejor experiencia que el prompt gris del navegador de todas formas).
  _dialog(message, { input = false, defaultValue = "", confirmLabel = "Aceptar", danger = false } = {}) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div"); overlay.className = "wg-dialog-overlay";
      const box = document.createElement("div"); box.className = "wg-dialog-box";
      const msg = document.createElement("p"); msg.textContent = message; box.append(msg);
      let field = null;
      if (input) {
        field = document.createElement("input"); field.type = "text"; field.value = defaultValue;
        field.className = "wg-dialog-input";
        box.append(field);
      }
      const actions = document.createElement("div"); actions.className = "wg-dialog-actions";
      const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = "Cancelar";
      const ok = document.createElement("button"); ok.type = "button";
      ok.className = danger ? "primary wg-dialog-danger" : "primary"; ok.textContent = confirmLabel;
      actions.append(cancel, ok); box.append(actions);
      overlay.append(box); document.body.append(overlay);
      if (field) { field.focus(); field.select(); }
      // El listener de Escape se saca en TODOS los caminos de cierre (botón,
      // click en el fondo, Escape) -- si solo se sacaba en el propio Escape,
      // cerrar con un click dejaba un listener de keydown pegado al
      // document para siempre, uno por cada diálogo abierto en la sesión.
      const onKeydown = (e) => { if (e.key === "Escape") close(input ? null : false); };
      const close = (value) => {
        document.removeEventListener("keydown", onKeydown);
        overlay.remove();
        resolve(value);
      };
      cancel.onclick = () => close(input ? null : false);
      ok.onclick = () => close(input ? field.value.trim() : true);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) close(input ? null : false); });
      document.addEventListener("keydown", onKeydown);
      if (field) field.addEventListener("keydown", (e) => { if (e.key === "Enter") ok.onclick(); });
    });
  },
  promptText(message, defaultValue = "") { return WatchlistGroups._dialog(message, { input: true, defaultValue }); },
  confirmAction(message, confirmLabel = "Eliminar") { return WatchlistGroups._dialog(message, { confirmLabel, danger: true }); },
};

// Ticker actualmente enfocado, compartido entre las 3 páginas (Cross Monitor,
// Radar MA 200, Análisis Fundamental) para que cambiar de página no reinicie
// la selección al primer ticker de la lista.
const SELECTED_TICKER_KEY = "cross-monitor:selected-ticker";
const SelectedTicker = {
  get() { try { return localStorage.getItem(SELECTED_TICKER_KEY) || null; } catch { return null; } },
  set(ticker) { try { if (ticker) localStorage.setItem(SELECTED_TICKER_KEY, ticker); } catch { /* localStorage no disponible */ } },
  clear() { try { localStorage.removeItem(SELECTED_TICKER_KEY); } catch { /* localStorage no disponible */ } },
};

// Botón "Editar lista" que revela los "×" de eliminar ticker (ver `.remove`
// en styles.css, oculto salvo dentro de `.editing`) -- mismo patrón en las 3
// páginas, factorizado acá para no triplicarlo.
const WatchlistEdit = {
  bindToggle(listEl, btnEl) {
    let editing = false;
    btnEl.addEventListener("click", () => {
      editing = !editing;
      listEl.classList.toggle("editing", editing);
      btnEl.textContent = editing ? "Listo" : "Editar lista";
      btnEl.classList.toggle("primary", editing);
    });
  },
  // Botón "×" listo para insertar en una fila de ticker; `onRemove` no recibe
  // argumentos (la página ya sabe qué ticker es por closure).
  renderRemoveButton(onRemove) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "remove"; btn.title = "Quitar de la lista"; btn.textContent = "×";
    btn.addEventListener("click", (e) => { e.stopPropagation(); onRemove(); });
    return btn;
  },
  // Hace que un contenedor no-<button> (necesario para poder anidar el "×")
  // se comporte como uno: foco por Tab y activación con Enter/Espacio.
  makeFocusable(el, onActivate) {
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onActivate(); }
    });
  },
};
