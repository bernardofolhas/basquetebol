(() => {
  const categoryOrder = ["tecnica", "tatica", "fisica", "psicologica"];
  const categoryNames = {tecnica: "Técnica", tatica: "Tática", fisica: "Física", psicologica: "Psicológica"};
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
  const average = values => values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
  const formatNumber = value => Number.isInteger(value) ? String(value) : Number(value).toFixed(1).replace(".", ",");
  const formatDate = value => new Intl.DateTimeFormat("pt-PT", {day:"2-digit", month:"short"}).format(new Date(`${value}T12:00:00`));
  const unique = values => [...new Set(values)];

  document.querySelectorAll("[data-analysis-dashboard]").forEach(root => {
    const source = root.querySelector("[data-analysis-source]");
    const records = JSON.parse(source?.textContent || "[]");
    const lockedPlayer = Number(root.dataset.playerLocked || 0);
    const playerCatalog = JSON.parse(root.querySelector("[data-analysis-players]")?.textContent || "[]");
    const parameterCatalog = JSON.parse(root.querySelector("[data-analysis-parameters]")?.textContent || "[]");
    const players = [...new Map([...playerCatalog.map(item => [item.id, item.nome]), ...records.map(item => [item.jogador_id, item.jogador])]).entries()].sort((a,b) => a[1].localeCompare(b[1], "pt"));
    const parameters = [...new Map([...parameterCatalog.map(item => [item.id, {id:item.id, name:item.nome, category:item.categoria, unit:item.unidade}]), ...records.map(item => [item.parametro_id, {id:item.parametro_id, name:item.parametro, category:item.categoria, unit:item.unidade}])].map(item => [item[0],item[1]])).values()].sort((a,b) => a.name.localeCompare(b.name, "pt"));
    const state = {
      players: new Set(lockedPlayer ? [lockedPlayer] : players.map(item => item[0])),
      categories: new Set(categoryOrder),
      parameters: new Set(parameters.map(item => item.id)),
    };

    const playerOptions = root.querySelector("[data-analysis-player-options]");
    if (playerOptions) playerOptions.innerHTML = players.map(([id,name]) => `<label><input type="checkbox" value="${id}" data-analysis-player checked> ${escapeHtml(name)}</label>`).join("");
    const parameterOptions = root.querySelector("[data-analysis-parameter-options]");
    if (parameterOptions) parameterOptions.innerHTML = parameters.map(item => `<label data-parameter-category="${item.category}"><input type="checkbox" value="${item.id}" data-analysis-parameter checked> <span>${escapeHtml(item.name)} <small>· ${escapeHtml(categoryNames[item.category] || item.category)}</small></span></label>`).join("");

    const period = root.querySelector("[data-analysis-period]");
    const from = root.querySelector("[data-analysis-from]");
    const to = root.querySelector("[data-analysis-to]");
    const dates = records.map(item => item.data).sort();
    if (dates.length) { from.value = dates[0]; to.value = dates[dates.length - 1]; }

    function syncSet(selector, target) {
      state[target] = new Set([...root.querySelectorAll(selector)].filter(input => input.checked).map(input => Number.isNaN(Number(input.value)) ? input.value : Number(input.value)));
    }
    function dateRange() {
      if (!dates.length) return [null, null];
      if (period.value === "custom") return [from.value || dates[0], to.value || dates[dates.length - 1]];
      if (period.value === "all") return [dates[0], dates[dates.length - 1]];
      const end = new Date(`${dates[dates.length - 1]}T12:00:00`);
      const start = new Date(end); start.setDate(start.getDate() - Number(period.value));
      return [start.toISOString().slice(0,10), dates[dates.length - 1]];
    }
    function selectedRecords() {
      const [start,end] = dateRange();
      return records.filter(item => state.players.has(item.jogador_id) && state.categories.has(item.categoria) && state.parameters.has(item.parametro_id) && (!start || item.data >= start) && (!end || item.data <= end));
    }
    function setText(selector, value) { const element = root.querySelector(selector); if (element) element.textContent = value; }
    function updateLabels() {
      if (!lockedPlayer) setText("[data-analysis-player-label]", state.players.size === players.length ? "Toda a equipa" : `${state.players.size} selecionado(s)`);
      setText("[data-analysis-category-label]", state.categories.size === categoryOrder.length ? "Todas" : `${state.categories.size} selecionada(s)`);
      setText("[data-analysis-parameter-label]", state.parameters.size === parameters.length ? "Todos" : `${state.parameters.size} selecionado(s)`);
      root.querySelectorAll("[data-parameter-category]").forEach(label => { label.hidden = !state.categories.has(label.dataset.parameterCategory); });
    }
    function renderTrend(filtered) {
      const groups = new Map();
      filtered.forEach(item => { if (!groups.has(item.data)) groups.set(item.data, []); groups.get(item.data).push(item.normalizado); });
      const points = [...groups.entries()].sort((a,b) => a[0].localeCompare(b[0])).map(([date,values]) => ({date,value:average(values)}));
      setText('[data-chart-note="trend"]', `${points.length} momento(s)`);
      const target = root.querySelector('[data-chart="trend"]');
      if (!points.length) { target.innerHTML = ""; return; }
      const width=680,height=220,left=42,right=18,top=15,bottom=35,usableW=width-left-right,usableH=height-top-bottom;
      const coords = points.map((point,index) => ({...point,x:left+(points.length===1?usableW/2:index*usableW/(points.length-1)),y:top+(100-point.value)*usableH/100}));
      const line = coords.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
      const area = `${left},${height-bottom} ${line} ${coords[coords.length-1].x},${height-bottom}`;
      const grids = [0,25,50,75,100].map(value => { const y=top+(100-value)*usableH/100; return `<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" class="analysis-grid-line"/><text x="${left-8}" y="${y+3}" text-anchor="end" class="analysis-axis-label">${value}</text>`; }).join("");
      const labels = coords.map((point,index) => (points.length <= 7 || index % Math.ceil(points.length/7)===0 || index===points.length-1) ? `<text x="${point.x}" y="${height-10}" text-anchor="middle" class="analysis-axis-label">${escapeHtml(formatDate(point.date))}</text>` : "").join("");
      const circles = coords.map(point => `<circle cx="${point.x}" cy="${point.y}" r="4" class="analysis-line-point"><title>${escapeHtml(formatDate(point.date))}: ${formatNumber(point.value)}%</title></circle>`).join("");
      target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução do desempenho">${grids}<polygon points="${area}" class="analysis-line-fill"/><polyline points="${line}" class="analysis-line-path"/>${circles}${labels}</svg>`;
    }
    function renderBars(targetSelector, entries, emptyLabel) {
      const target = root.querySelector(targetSelector);
      if (!entries.length) { target.innerHTML = `<p class="text-sm text-slate-400">${escapeHtml(emptyLabel)}</p>`; return; }
      target.innerHTML = entries.map(([label,value]) => `<div class="analysis-bar-row"><span class="analysis-bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</span><span class="analysis-bar-track"><span class="analysis-bar-fill" style="width:${Math.max(2,value)}%"></span></span><strong class="analysis-bar-value">${formatNumber(value)}</strong></div>`).join("");
    }
    function renderDimensions(filtered) {
      const entries = categoryOrder.filter(category => state.categories.has(category)).map(category => [categoryNames[category], average(filtered.filter(item => item.categoria===category).map(item => item.normalizado))]).filter(item => item[1] !== null);
      renderBars('[data-chart="dimensions"]', entries, "Sem dimensões avaliadas.");
    }
    function renderRanking(filtered) {
      const entries = players.filter(([id]) => state.players.has(id)).map(([id,name]) => [name, average(filtered.filter(item => item.jogador_id===id).map(item => item.normalizado))]).filter(item => item[1] !== null).sort((a,b) => b[1]-a[1]);
      renderBars('[data-chart="ranking"]', entries, "Sem atletas avaliados.");
    }
    function renderMatrix(filtered) {
      const target = root.querySelector('[data-chart="matrix"]');
      const visiblePlayers = players.filter(([id]) => state.players.has(id) && filtered.some(item => item.jogador_id===id));
      const visibleParameters = parameters.filter(item => state.parameters.has(item.id) && state.categories.has(item.category) && filtered.some(record => record.parametro_id===item.id));
      if (!visiblePlayers.length || !visibleParameters.length) { target.innerHTML='<p class="p-5 text-sm text-slate-400">Sem valores para construir a matriz.</p>'; return; }
      const head = visibleParameters.map(item => `<th title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</th>`).join("");
      const body = visiblePlayers.map(([id,name]) => `<tr><td>${escapeHtml(name)}</td>${visibleParameters.map(parameter => { const values=filtered.filter(item => item.jogador_id===id && item.parametro_id===parameter.id); if(!values.length)return '<td><span class="analysis-cell analysis-cell-empty">-</span></td>'; const raw=average(values.map(item=>item.valor)),normalized=average(values.map(item=>item.normalizado)); const tone=normalized>=70?'high':normalized>=45?'mid':'low'; return `<td><span class="analysis-cell analysis-cell-${tone}" title="${formatNumber(normalized)}% da escala">${formatNumber(raw)}${parameter.unit ? ` ${escapeHtml(parameter.unit)}` : ''}</span></td>`; }).join("")}</tr>`).join("");
      target.innerHTML = `<table class="analysis-matrix"><thead><tr><th>Atleta</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }
    function render() {
      updateLabels();
      const filtered = selectedRecords();
      const selectedPlayerCount = lockedPlayer ? 1 : state.players.size;
      const covered = unique(filtered.map(item => item.jogador_id)).length;
      const mean = average(filtered.map(item => item.normalizado));
      const moments = unique(filtered.map(item => `${item.data}:${item.sessao_id || "livre"}`)).length;
      const byDate = new Map(); filtered.forEach(item => { if(!byDate.has(item.data))byDate.set(item.data,[]); byDate.get(item.data).push(item.normalizado); });
      const time = [...byDate.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([,values])=>average(values));
      const evolution = time.length > 1 ? time[time.length-1]-time[0] : null;
      setText('[data-kpi="coverage"]', selectedPlayerCount ? `${Math.round(covered/selectedPlayerCount*100)}%` : "-");
      setText('[data-kpi-note="coverage"]', `${covered} de ${selectedPlayerCount} atleta(s)`);
      setText('[data-kpi="average"]', mean===null ? "-" : `${formatNumber(mean)}%`);
      const evolutionElement=root.querySelector('[data-kpi="evolution"]'); evolutionElement.textContent=evolution===null?"-":`${evolution>=0?"+":""}${formatNumber(evolution)} pp`; evolutionElement.classList.toggle("is-positive",evolution>0); evolutionElement.classList.toggle("is-negative",evolution<0);
      setText('[data-kpi="moments"]', moments);
      setText('[data-kpi-note="moments"]', `${filtered.length} valor(es) considerado(s)`);
      root.querySelector("[data-analysis-empty]").hidden = filtered.length > 0;
      root.querySelector("[data-analysis-content]").hidden = filtered.length === 0;
      renderTrend(filtered); renderDimensions(filtered); renderRanking(filtered); renderMatrix(filtered);
    }

    root.addEventListener("change", event => {
      if (event.target.matches("[data-analysis-player]")) syncSet("[data-analysis-player]", "players");
      if (event.target.matches("[data-analysis-category]")) syncSet("[data-analysis-category]", "categories");
      if (event.target.matches("[data-analysis-parameter]")) syncSet("[data-analysis-parameter]", "parameters");
      if (event.target === period && period.value !== "custom" && dates.length) { const range=dateRange(); from.value=range[0]; to.value=range[1]; }
      render();
    });
    root.querySelectorAll("[data-select-all],[data-clear-all]").forEach(button => button.addEventListener("click", () => {
      const group=button.dataset.selectAll || button.dataset.clearAll; const checked=Boolean(button.dataset.selectAll); const selector={players:"[data-analysis-player]",categories:"[data-analysis-category]",parameters:"[data-analysis-parameter]"}[group];
      root.querySelectorAll(selector).forEach(input => { if(!input.closest("[hidden]"))input.checked=checked; }); syncSet(selector,group); render();
    }));
    root.querySelector("[data-analysis-reset]").addEventListener("click", () => {
      root.querySelectorAll("[data-analysis-player],[data-analysis-category],[data-analysis-parameter]").forEach(input=>input.checked=true); state.players=new Set(lockedPlayer?[lockedPlayer]:players.map(item=>item[0])); state.categories=new Set(categoryOrder); state.parameters=new Set(parameters.map(item=>item.id)); period.value="all"; if(dates.length){from.value=dates[0];to.value=dates[dates.length-1];} render();
    });
    document.addEventListener("click", event => { root.querySelectorAll(".analysis-filter-menu[open]").forEach(menu => { if(!menu.contains(event.target))menu.removeAttribute("open"); }); });
    render();
  });
})();
