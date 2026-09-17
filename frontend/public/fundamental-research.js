/* Explicit local research tools: no AI requests, timers or automatic reports. */
(function (root) {
  "use strict";
  function project({price, eps, growth, multiple, discount, years}) {
    if (![price, eps, growth, multiple, discount, years].every(Number.isFinite) || price <= 0 || eps <= 0 || multiple <= 0 || growth <= -1 || discount <= -1 || ![3, 4, 5].includes(years)) throw new Error("Revisa los supuestos: precio, EPS y múltiplo positivos; horizonte de 3 a 5 años.");
    const future = eps * (1 + growth) ** years * multiple;
    const present = future / (1 + discount) ** years;
    if (!Number.isFinite(present) || present <= 0) throw new Error("Los supuestos no producen una valoración válida.");
    return {future, present, margin: (present-price)/present, upside: present/price-1, annual: (future/price)**(1/years)-1};
  }
  function capitalCost({riskFree, premium, beta, debtCost, tax, debtWeight}) {
    if (![riskFree,premium,beta,debtCost,tax,debtWeight].every(Number.isFinite) || riskFree<0 || premium<0 || beta<0 || debtCost<0 || tax<0 || tax>1 || debtWeight<0 || debtWeight>1) throw new Error("Revisa tasas, beta y ponderación de deuda (entre 0 y 100%).");
    const equityCost=riskFree+beta*premium;
    return {equityCost,wacc:(1-debtWeight)*equityCost+debtWeight*debtCost*(1-tax)};
  }
  function buildReport(data, capital, scenario, notes, generated = new Date().toISOString()) {
    const r=data.research, metrics=r.blocks.flatMap(b=>b.metrics);
    const n=v=>Number.isFinite(v)?v.toFixed(2):"Sin dato";
    const p=v=>Number.isFinite(v)?`${n(v*100)}%`:"Sin dato";
    const lines=[`# Investigación fundamental: ${data.ticker}`,`Generado: ${generated}`,`Datos consultados: ${r.as_of}`,`Moneda de los estados: ${r.currency||"No informada"}`,`Fuente: ${r.source}`,"",`Cobertura automática: ${r.coverage.available}/${r.coverage.total}. Disponibilidad no equivale a calidad empresarial ni a verificación independiente.`,"","## Métricas avanzadas"];
    metrics.forEach(m=>lines.push(`- ${m.label}: ${m.display}. ${m.explanation} Fuente: ${m.source}`));
    lines.push("","## Histórico anual","Cierre | Ingresos | FCF | Margen bruto | ROIC","--- | ---: | ---: | ---: | ---:");
    r.history.forEach(v=>lines.push(`${v.date} | ${n(v.revenue)} | ${n(v.fcf)} | ${p(v.grossMargin)} | ${p(v.roic)}`));
    lines.push("","## Coste de capital");
    if(capital){
      const i=capital.inputs;
      lines.push(`WACC estimado: ${p(capital.wacc)}. Coste del patrimonio: ${p(capital.equityCost)}.`, `ROIC anual menos WACC: ${Number.isFinite(capital.spread)?n(capital.spread*100)+" puntos porcentuales":"Sin dato"}.`, `Supuestos: tasa libre de riesgo ${p(i.riskFree)}; prima ${p(i.premium)}; beta ${n(i.beta)}; coste de deuda ${p(i.debtCost)}; impuesto ${p(i.tax)}; peso de deuda ${p(i.debtWeight)}.`, `Evidencia aportada: ${capital.evidence}`, `Calculado: ${capital.computed}`);
    }else lines.push("No calculado; faltan supuestos documentados.");
    lines.push("","## Escenarios");
    if(scenario){
      const b=scenario.base;
      lines.push(`Modelo por EPS y múltiplo, no DCF. Moneda: ${r.scenario.currency||"No informada"}. Precio: ${n(b.price)}; EPS base: ${n(b.eps)}; horizonte: ${b.years} años; rentabilidad exigida: ${p(b.discount)}.`, "Supuestos ilustrativos/editados por el usuario, no previsiones verificadas. Excluye dividendos.", "Escenario | Crecimiento EPS | P/E salida | Precio futuro | Valor descontado hoy | Margen de seguridad | Potencial | Retorno anual", "--- | ---: | ---: | ---: | ---: | ---: | ---: | ---:");
      scenario.rows.forEach(v=>lines.push(`${v.name} | ${p(v.growth)} | ${n(v.multiple)} | ${n(v.future)} | ${n(v.present)} | ${p(v.margin)} | ${p(v.upside)} | ${p(v.annual)}`));
      lines.push(`Calculado: ${scenario.computed}`);
    }else lines.push("No calculados. No se emite una valoración.");
    lines.push("","## Evidencia cualitativa aportada por el usuario",notes.trim()||"Pendiente de documentos. Moat y calidad de gestión no evaluables.","","## Conclusión de investigación","Calidad: requiere contexto sectorial e histórico. Solvencia: requiere revisar vencimientos y liquidez además de ratios. Valoración: condicionada a supuestos explícitos, no una recomendación. Confianza: fuente secundaria, pendiente de contraste con documentos oficiales.","","## Pendientes");
    metrics.filter(m=>m.value==null && !(capital && ["wacc","spread"].includes(m.key))).forEach(m=>lines.push(`- ${m.label}: ${m.explanation}`));
    lines.push("","No se han generado riesgos ni ventajas competitivas sin evidencia. Este informe no utiliza IA ni se actualiza automáticamente.");
    return lines.join("\n");
  }
  if (typeof module !== "undefined") module.exports = {project,capitalCost,buildReport};
  if (typeof document === "undefined") return;
  const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
  const num = v => Number.isFinite(v) ? v.toLocaleString("es", {maximumFractionDigits:2}) : "Sin dato";
  const pct = v => Number.isFinite(v) ? `${num(v*100)}%` : "Sin dato";
  function disclosure(label, parent) { const d = el("details", null, "research-section"); d.append(el("summary", label)); parent.append(d); return d; }
  function render(panel, data) {
    const r = data.research;
    const wrap = el("section", null, "research-tools");
    wrap.append(el("h3", "Investigación fundamental"));
    wrap.append(el("p", `${r.coverage.available}/${r.coverage.total} métricas avanzadas disponibles · Consulta ${new Date(r.as_of).toLocaleString()} · Sin IA`, "research-caption"));
    const advanced = disclosure("Métricas avanzadas · fórmulas y fuentes", wrap);
    const grid = el("div", null, "research-metrics");
    for (const m of r.blocks.flatMap(b=>b.metrics)) {
      const d = el("details", null, "research-metric");
      const summary = el("summary"); summary.append(el("span",m.label),el("strong",m.display)); d.append(summary);
      d.append(el("p",m.explanation));
      const a = el("a", "Consultar fuente"); a.href = m.source; a.target="_blank"; a.rel="noopener noreferrer"; d.append(a); grid.append(d);
    }
    advanced.append(grid);
    const hist = disclosure("Histórico anual · períodos comparables", wrap);
    hist.append(el("p", "Los ejercicios disponibles se muestran completos. Un historial corto no se presenta como tendencia de cinco años. ROIC usa capital promedio; no equivale al ROE trimestral del panel."));
    if (!r.history.length) hist.append(el("p","La fuente no entregó estados anuales."));
    else {
      const box = el("div",null,"research-table-scroll"); const table=el("table");
      const tr=el("tr"); ["Cierre","Ingresos", "FCF", "Margen bruto", "Margen operativo", "ROIC", "FCF / beneficio"].forEach(t=>tr.append(el("th",t))); table.append(tr);
      for (const p of [...r.history].reverse()) { const row=el("tr"); [p.date,`${num(p.revenue)} ${r.currency||""}`,`${num(p.fcf)} ${r.currency||""}`,pct(p.grossMargin),pct(p.operatingMargin),pct(p.roic),pct(p.conversion)].forEach(t=>row.append(el("td",t))); table.append(row); }
      box.append(table);hist.append(box);
    }
    let latestCapital = null;
    const capital = disclosure("Coste de capital · WACC con supuestos documentados",wrap);
    capital.append(el("p","Estimación editable: coste del patrimonio = tasa libre de riesgo + beta × prima; WACC = peso del patrimonio × coste del patrimonio + peso de deuda × coste de deuda × (1 − impuesto). Usa tasas de la misma moneda y pesos a valor de mercado. No se completan supuestos sin fuente."));
    const cf=el("form",null,"research-form"); const ci={};
    for(const [key,label,max] of [["riskFree","Tasa libre de riesgo (%)",100],["premium","Prima de riesgo (%)",100],["beta","Beta",10],["debtCost","Coste de deuda (%)",100],["tax","Impuesto normalizado (%)",100],["debtWeight","Peso de deuda (%)",100]]){
      const l=el("label",label), i=el("input");i.type="number";i.min=0;i.max=max;i.step="any";i.required=true;l.append(i);cf.append(l);ci[key]=i;
    }
    const evidenceLabel=el("label","Fuente, fecha y moneda de los supuestos"),evidence=el("input");evidence.required=true;evidenceLabel.append(evidence);cf.append(evidenceLabel);
    const cc=el("button","Calcular WACC","primary");cc.type="submit";cf.append(cc);const cr=el("p");cr.setAttribute("aria-live","polite");capital.append(cf,cr);
    if(!r.scenario.applicable){cf.hidden=true;cr.textContent="No aplicable al modelo genérico de empresas financieras.";}
    const invalidateCapital=()=>{latestCapital=null;cr.textContent="Supuestos modificados: vuelve a calcular.";};
    cf.addEventListener("input",invalidateCapital);cf.addEventListener("change",invalidateCapital);
    cf.onsubmit=e=>{e.preventDefault();try{
      const inputs=Object.fromEntries(Object.entries(ci).map(([k,v])=>[k,Number(v.value)/(k==="beta"?1:100)]));
      const values=capitalCost(inputs);const roic=r.blocks.flatMap(b=>b.metrics).find(m=>m.key==="roic")?.value;
      latestCapital={inputs,...values,evidence:evidence.value,computed:new Date().toISOString(),spread:Number.isFinite(roic)?roic-values.wacc:null};
      cr.textContent=`WACC estimado: ${pct(values.wacc)} · Coste del patrimonio: ${pct(values.equityCost)} · ROIC anual − WACC: ${Number.isFinite(latestCapital.spread)?num(latestCapital.spread*100)+" puntos porcentuales":"Sin dato"}. Compara un retorno histórico con un coste estimado, no garantiza rentabilidad futura.`;
    }catch(err){latestCapital=null;cr.textContent=err.message;}};
    const scenario = disclosure("Escenarios de valoración · supuestos editables",wrap);
    scenario.append(el("p", "Ejercicio por EPS y P/E de salida. Valores iniciales ilustrativos, no previsiones ni consenso. Descuenta el precio futuro al presente; excluye dividendos y supone que el crecimiento del EPS ya incorpora dilución. No es DCF ni valoración intrínseca completa."));
    let latestScenario = null;
    const form=el("form",null,"research-form");
    function input(label,value,min,max,step="any") { const l=el("label",label); const i=el("input"); i.type="number";i.required=true;i.step=step;if(min!=null)i.min=min;if(max!=null)i.max=max;i.value=value??"";l.append(i);form.append(l);return i; }
    const price=input(`Precio (${r.scenario.currency||"moneda no informada"})`,r.scenario.price,0.000001);
    const eps=input("EPS base (TTM, editable)",r.scenario.eps,0.000001);
    const years=input("Horizonte (años)",5,3,5,"1"); const rate=input("Rentabilidad exigida (%)",10,0,100);
    const cases=[['Conservador',0,12],['Base',5,18],['Optimista',10,24]].map(([name,g,m])=>({name,g:input(`${name}: crecimiento EPS (%)`,g,-99,100),m:input(`${name}: P/E de salida`,m,0.1,200)}));
    const calculate=el("button","Calcular escenarios","primary");calculate.type="submit";form.append(calculate);scenario.append(form);
    const result=el("div",null,"research-table-scroll");result.setAttribute("aria-live","polite");scenario.append(result);
    if(!r.scenario.applicable){ form.hidden=true;result.textContent="Empresa financiera: requiere un modelo sectorial antes de estimar valor."; }
    const invalidate=()=>{latestScenario=null;result.replaceChildren(el("p","Supuestos modificados. Pulsa Calcular para actualizar los resultados."));};form.addEventListener("input",invalidate);
    form.onsubmit=e=>{e.preventDefault();result.replaceChildren();try {
      const base={price:Number(price.value),eps:Number(eps.value),years:Number(years.value),discount:Number(rate.value)/100};
      const rows=cases.map(c=>({name:c.name, growth:Number(c.g.value)/100,multiple:Number(c.m.value),...project({...base,growth:Number(c.g.value)/100,multiple:Number(c.m.value)})}));
      latestScenario={base,rows,computed:new Date().toISOString()};
      const table=el("table"),head=el("tr");["Escenario","Precio futuro","Valor descontado hoy","Margen de seguridad","Potencial","Retorno anual sin dividendos"].forEach(s=>head.append(el("th",s)));table.append(head);
      rows.forEach(v=>{const row=el("tr");[v.name,num(v.future),num(v.present),pct(v.margin),pct(v.upside),pct(v.annual)].forEach(t=>row.append(el("td",t)));table.append(row);});result.append(table);
      const baseCase=rows[1]; const sensitivity=el("p",`Sensibilidad del caso base: con rentabilidad exigida de ${num(Number(rate.value)+2)}%, valor ${num(project({...base,growth:baseCase.growth,multiple:baseCase.multiple,discount:base.discount+.02}).present)}; con P/E de salida 20% menor, valor ${num(project({...base,growth:baseCase.growth,multiple:baseCase.multiple*.8}).present)}. Moneda: ${r.scenario.currency||"no informada"}.`); result.append(sensitivity);
    }catch(err){latestScenario=null;result.textContent=err.message;}};
    const report=disclosure("Informe de investigación · generar y guardar",wrap);
    report.append(el("p","Informe local de datos y escenarios, sin llamadas a IA. Añade evidencia para moat y gestión; no se deducen automáticamente de los ratios. Se guarda en este navegador por ticker y no se regenera al actualizar precios."));
    const notes=el("textarea");notes.rows=5;notes.placeholder="Ventaja competitiva, gestión, riesgos y documentos que los respaldan. Incluye fecha y URL de cada fuente.";notes.setAttribute("aria-label","Evidencia cualitativa y fuentes");report.append(notes);
    const noteKey=`fund-research-notes:${data.ticker}`,reportKey=`fund-research-report:${data.ticker}`;
    const status=el("p",null,"research-caption");
    const output=el("pre",null,"research-report");let saved="";
    try{notes.value=localStorage.getItem(noteKey)||"";saved=localStorage.getItem(reportKey)||"";}catch{status.textContent="Almacenamiento local no disponible. Puedes descargar el informe.";}
    notes.onchange=()=>{try{localStorage.setItem(noteKey,notes.value);}catch{status.textContent="No se pudo guardar la evidencia en este navegador.";}};
    const generate=el("button","Generar informe local","primary"),download=el("button","Descargar .md");generate.type=download.type="button"; download.disabled=!saved;output.textContent=saved;
    generate.onclick=()=>{
      if (latestCapital && (!cf.checkValidity() || Object.entries(ci).some(([k,v])=>Number(v.value)/(k==="beta"?1:100)!==latestCapital.inputs[k]) || evidence.value!==latestCapital.evidence)) latestCapital=null;
      if (latestScenario && (!form.checkValidity() || Number(price.value)!==latestScenario.base.price || Number(eps.value)!==latestScenario.base.eps || Number(years.value)!==latestScenario.base.years || Number(rate.value)/100!==latestScenario.base.discount || cases.some((c,i)=>Number(c.g.value)/100!==latestScenario.rows[i].growth || Number(c.m.value)!==latestScenario.rows[i].multiple))) latestScenario=null;
      saved=buildReport(data,latestCapital,latestScenario,notes.value);output.textContent=saved;download.disabled=false;
      try{localStorage.setItem(reportKey,saved);localStorage.setItem(noteKey,notes.value);status.textContent="Informe guardado en este navegador. La fecha del informe permite identificar su antigüedad.";}catch{status.textContent="Informe generado, pero no se pudo guardar. Descárgalo para conservarlo.";}
    };
    download.onclick=()=>{const u=URL.createObjectURL(new Blob([saved],{type:"text/markdown;charset=utf-8"}));const a=el("a");a.href=u;a.download=`fundamental-${data.ticker.replace(/[^a-z0-9_-]/gi,"_")}.md`;a.click();URL.revokeObjectURL(u);};
    report.append(generate,download,status,output);wrap.append(el("p","El WACC se estima en su calculadora. Altman, previsiones a largo plazo y reducción neta de acciones requieren fuentes o supuestos adicionales. No se sustituyen por cifras inventadas.","research-caption"));panel.append(wrap);
  }
  root.FundamentalResearch={render,project,capitalCost};
})(typeof window !== "undefined" ? window : globalThis);
