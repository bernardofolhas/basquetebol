(() => {
  const root = document.querySelector("[data-statboard]");
  if (!root) return;

  const gameId = Number(root.dataset.gameId);
  const userId = Number(root.dataset.userId);
  const canEdit = root.dataset.canEdit === "true";
  const serverEvents = JSON.parse(root.querySelector("[data-stats-events]")?.textContent || "[]");
  const storageKey = `basket-stats:${userId}:${gameId}`;
  const clockKey = `${storageKey}:clock`;
  const labels = {
    ll_c: "LL convertido", ll_f: "LL falhado", dois_c: "2P convertido", dois_f: "2P falhado",
    tres_c: "3P convertido", tres_f: "3P falhado", ressalto_ofensivo: "Ressalto ofensivo",
    ressalto_defensivo: "Ressalto defensivo", assistencia: "Assistência", roubo: "Roubo",
    perda: "Perda", desarme: "Desarme", falta: "Falta pessoal", falta_sofrida: "Falta sofrida",
    entrada_campo: "Entrada em campo", saida_campo: "Saída de campo",
  };
  const points = { ll_c: 1, dois_c: 2, tres_c: 3 };
  const fieldGoalTypes = new Set(["dois_c", "dois_f", "tres_c", "tres_f"]);
  const actionsWithoutPosition = new Set(["falta", "falta_sofrida"]);
  const lineupTypes = new Set(["entrada_campo", "saida_campo"]);
  const playerButtons = [...root.querySelectorAll("[data-player-id]")];
  const playerData = JSON.parse(root.querySelector("[data-stats-players]")?.textContent || "[]");
  const players = new Map(playerData.map(player => [Number(player.id), {
    id: Number(player.id),
    name: player.name,
    number: String(player.number || "–"),
  }]));
  const requiredLineupSize = Math.min(5, players.size);

  let dirty = loadJson(storageKey, []);
  let events = mergeEvents(serverEvents, dirty);
  let selectedPlayer = null;
  let clock = loadJson(clockKey, { seconds: 600, running: false, period: 1, updatedAt: Date.now() });
  let timer = null;
  let syncTimer = null;
  let syncing = false;
  let syncRequested = false;
  let resetting = false;
  let pendingAction = null;
  let selectedPosition = null;
  let lineupDraft = new Set();
  let shotSide = "equipa";

  function loadJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; }
  }

  function saveLocal() {
    if (dirty.length) localStorage.setItem(storageKey, JSON.stringify(dirty));
    else localStorage.removeItem(storageKey);
    localStorage.setItem(clockKey, JSON.stringify({ ...clock, updatedAt: Date.now() }));
  }

  function mergeEvents(base, pending) {
    const map = new Map(base.map(item => [item.client_uid, item]));
    pending.forEach(item => map.set(item.client_uid, { ...map.get(item.client_uid), ...item }));
    return [...map.values()];
  }

  function uid() {
    return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function active() { return events.filter(item => !item.anulado); }
  function currentSeconds() { return Math.max(0, Number(clock.seconds) || 0); }
  function formatClock(seconds) {
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }
  function clockElement() { return root.querySelector("[data-clock]"); }

  function updateClock() {
    if (clockElement()) clockElement().textContent = formatClock(currentSeconds());
    const period = root.querySelector("[data-period]");
    if (period) period.value = String(clock.period);
  }

  function startTimer() {
    clearInterval(timer);
    if (!clock.running) return;
    timer = setInterval(() => {
      if (clock.seconds <= 0) {
        clock.running = false;
        clearInterval(timer);
      } else {
        clock.seconds -= 1;
      }
      updateClock();
      renderPlayingTimes();
      saveLocal();
    }, 1000);
  }

  function markDirty(event) {
    dirty = dirty.filter(item => item.client_uid !== event.client_uid);
    dirty.push({ ...event, sincronizado: false });
    saveLocal();
  }

  function playerFor(id) { return players.get(Number(id)); }

  function clearPlayerSelection() {
    selectedPlayer = null;
    const label = root.querySelector("[data-selected-player]");
    if (label) label.textContent = "Nenhum selecionado";
  }

  function buildEvent(type, side = "equipa", position = null, playerId = selectedPlayer) {
    const player = playerId ? playerFor(playerId) : null;
    return {
      client_uid: uid(), jogador_id: side === "equipa" ? playerId : null,
      jogador: player?.name || null, lado: side, tipo: type,
      periodo: Number(root.querySelector("[data-period]")?.value || 1),
      segundos_restantes: currentSeconds(), posicao_x: position?.x ?? null,
      posicao_y: position?.y ?? null, anulado: false, sincronizado: false,
    };
  }

  function addEvent(type, side = "equipa", position = null) {
    if (!canEdit) return;
    const lineup = currentLineup();
    if (side === "equipa" && lineup.size !== requiredLineupSize) {
      notify("Define primeiro os cinco atletas em campo.", "danger");
      openLineupDialog();
      return;
    }
    if (side === "equipa" && !selectedPlayer) {
      notify("Seleciona primeiro um atleta.", "danger");
      return;
    }
    if (side === "equipa" && !lineup.has(selectedPlayer)) {
      notify("O atleta selecionado está no banco. Altera primeiro o cinco em campo.", "danger");
      clearPlayerSelection();
      renderActionState();
      return;
    }
    const event = buildEvent(type, side, position);
    events.push(event);
    markDirty(event);
    render();
    scheduleSync();
  }

  function addLineupChanges(nextLineup) {
    const current = currentLineup();
    const leaving = [...current].filter(id => !nextLineup.has(id));
    const entering = [...nextLineup].filter(id => !current.has(id));
    const changes = [
      ...leaving.map(id => buildEvent("saida_campo", "equipa", null, id)),
      ...entering.map(id => buildEvent("entrada_campo", "equipa", null, id)),
    ];
    if (!changes.length) {
      notify("O cinco em campo já está atualizado.");
      return false;
    }
    if (selectedPlayer && !nextLineup.has(selectedPlayer)) clearPlayerSelection();
    changes.forEach(event => { events.push(event); markDirty(event); });
    render();
    scheduleSync();
    return true;
  }

  function requestEvent(type, side = "equipa") {
    if (!canEdit) return;
    if (side === "equipa" && currentLineup().size !== requiredLineupSize) {
      notify("Define primeiro os cinco atletas em campo.", "danger");
      openLineupDialog();
      return;
    }
    if (side === "equipa" && !selectedPlayer) {
      notify("Seleciona primeiro um atleta.", "danger");
      return;
    }
    if (actionsWithoutPosition.has(type)) { addEvent(type, side); return; }
    const dialog = root.querySelector("[data-court-dialog]");
    if (!dialog) {
      notify("Não foi possível abrir o campo. Atualiza a página e volta a tentar.", "danger");
      return;
    }
    pendingAction = { type, side };
    selectedPosition = null;
    dialog.classList.toggle("is-opponent", side === "adversario");
    dialog.querySelector("[data-court-title]").textContent = labels[type] || "Assinalar ação";
    dialog.querySelector("[data-court-description]").textContent = `${side === "adversario" ? "Adversário" : "Nossa equipa"} · toca no local onde aconteceu a ação.`;
    const marker = dialog.querySelector("[data-court-marker]");
    marker.hidden = true;
    marker.style.left = "";
    marker.style.top = "";
    dialog.querySelector("[data-court-confirm]").disabled = true;
    dialog.querySelector("[data-court-hint]").textContent = "Seleciona um ponto no campo para continuar.";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeCourtDialog() {
    const dialog = root.querySelector("[data-court-dialog]");
    if (!dialog) return;
    pendingAction = null;
    selectedPosition = null;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
  }

  function lineupEvents(period = Number(clock.period)) {
    return active()
      .filter(item => item.lado === "equipa" && item.jogador_id && lineupTypes.has(item.tipo) && Number(item.periodo) === period)
      .sort((a, b) => (Number(b.segundos_restantes) || 0) - (Number(a.segundos_restantes) || 0));
  }

  function currentLineup(period = Number(clock.period)) {
    const lineup = new Set();
    lineupEvents(period).forEach(event => {
      if (event.tipo === "entrada_campo") lineup.add(Number(event.jogador_id));
      else lineup.delete(Number(event.jogador_id));
    });
    return lineup;
  }

  function playingSeconds(playerId) {
    let total = 0;
    for (let period = 1; period <= Number(clock.period); period += 1) {
      let enteredAt = null;
      lineupEvents(period).filter(event => Number(event.jogador_id) === playerId).forEach(event => {
        const seconds = Math.max(0, Number(event.segundos_restantes) || 0);
        if (event.tipo === "entrada_campo" && enteredAt === null) enteredAt = seconds;
        if (event.tipo === "saida_campo" && enteredAt !== null) {
          total += Math.max(0, enteredAt - seconds);
          enteredAt = null;
        }
      });
      if (enteredAt !== null) {
        total += period < Number(clock.period) ? enteredAt : Math.max(0, enteredAt - currentSeconds());
      }
    }
    return total;
  }

  function selectPlayer(playerId) {
    const player = playerFor(playerId);
    if (!player) return;
    const lineup = currentLineup();
    if (lineup.size === requiredLineupSize && !lineup.has(player.id)) {
      notify("Este atleta está no banco. Altera primeiro o cinco em campo.");
      return;
    }
    selectedPlayer = player.id;
    root.querySelectorAll("[data-player-id]").forEach(item => item.classList.toggle("is-selected", Number(item.dataset.playerId) === player.id));
    root.querySelectorAll("[data-lineup-player]").forEach(item => item.classList.toggle("is-selected", Number(item.dataset.lineupPlayer) === player.id));
    const label = root.querySelector("[data-selected-player]");
    if (label) label.textContent = player.name;
    renderActionState();
  }

  function renderLineup() {
    const lineup = currentLineup();
    const target = root.querySelector("[data-lineup-slots]");
    if (!target) return;
    target.innerHTML = "";
    [...lineup].slice(0, requiredLineupSize).forEach(id => {
      const player = playerFor(id);
      if (!player) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `stat-lineup-player${selectedPlayer === id ? " is-selected" : ""}`;
      button.dataset.lineupPlayer = String(id);
      const number = document.createElement("strong");
      number.textContent = player.number;
      const copy = document.createElement("span");
      const name = document.createElement("span");
      name.textContent = player.name;
      const time = document.createElement("small");
      time.dataset.lineupTime = String(id);
      time.textContent = formatClock(playingSeconds(id));
      copy.append(name, time);
      button.append(number, copy);
      button.addEventListener("click", () => selectPlayer(id));
      target.append(button);
    });
    for (let index = lineup.size; index < requiredLineupSize; index += 1) {
      const empty = document.createElement("div");
      empty.className = "stat-lineup-empty";
      empty.textContent = `Lugar ${index + 1}`;
      target.append(empty);
    }
    root.querySelector("[data-lineup-count]").textContent = `${lineup.size}/${requiredLineupSize}`;
    const manage = root.querySelector("[data-lineup-manage]");
    if (manage) manage.textContent = lineup.size === requiredLineupSize ? "Alterar cinco" : "Definir cinco";
    playerButtons.forEach(button => button.classList.toggle("is-on-court", lineup.has(Number(button.dataset.playerId))));
  }

  function renderLineupDialog(message = "") {
    root.querySelectorAll("[data-lineup-option]").forEach(button => {
      const selected = lineupDraft.has(Number(button.dataset.lineupOption));
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      button.querySelector("small").textContent = selected ? "Em campo" : "Banco";
    });
    const complete = lineupDraft.size === requiredLineupSize;
    const hint = root.querySelector("[data-lineup-dialog-hint]");
    hint.className = message ? "is-error" : complete ? "is-complete" : "";
    hint.textContent = message || (complete ? `${requiredLineupSize} atletas selecionados.` : `Selecionados ${lineupDraft.size}/${requiredLineupSize}.`);
    root.querySelector("[data-lineup-save]").disabled = !complete;
  }

  function openLineupDialog() {
    if (!canEdit || !requiredLineupSize) return;
    if (clock.running) {
      clock.running = false;
      startTimer();
      saveLocal();
      notify("Relógio pausado para alterar o cinco em campo.");
    }
    lineupDraft = new Set(currentLineup());
    renderLineupDialog();
    const dialog = root.querySelector("[data-lineup-dialog]");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeLineupDialog() {
    const dialog = root.querySelector("[data-lineup-dialog]");
    if (!dialog) return;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
  }

  function applyLineup() {
    if (lineupDraft.size !== requiredLineupSize) return;
    const changed = addLineupChanges(lineupDraft);
    closeLineupDialog();
    if (changed) notify("Cinco em campo atualizado.", "success");
  }

  function undo() {
    const event = [...events].reverse().find(item => !item.anulado && !lineupTypes.has(item.tipo));
    if (!event) { notify("Não existem ações de jogo para desfazer."); return; }
    event.anulado = true;
    markDirty(event);
    render();
    scheduleSync();
  }

  function notify(message, tone = "warning") {
    const stack = root.querySelector("[data-warning-stack]");
    if (!stack) return;
    const item = document.createElement("div");
    item.className = `stat-warning${tone === "danger" ? " is-danger" : tone === "success" ? " is-success" : ""}`;
    item.textContent = message;
    stack.prepend(item);
    stack.hidden = false;
    setTimeout(() => { item.remove(); stack.hidden = !stack.children.length; }, 4500);
  }

  async function sync(showFeedback = true) {
    if (syncing) { syncRequested = true; return; }
    if (!canEdit || !dirty.length) {
      if (showFeedback) notify("Todos os dados já estão sincronizados.");
      updateConnection();
      return;
    }
    if (!navigator.onLine) {
      if (showFeedback) notify("Sem internet. Os dados ficaram guardados neste dispositivo.");
      updateConnection();
      return;
    }
    syncing = true;
    syncRequested = false;
    let completed = false;
    const batch = [...dirty];
    const button = root.querySelector("[data-stat-sync]");
    if (button) button.disabled = true;
    try {
      const response = await fetch(`/estatisticas/jogos/${gameId}/sincronizar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
        body: JSON.stringify({ eventos: batch }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || "Falha de sincronização");
      const sent = new Set(batch.map(item => item.client_uid));
      dirty = dirty.filter(item => !sent.has(item.client_uid));
      events = mergeEvents(result.eventos, dirty);
      if (dirty.length) localStorage.setItem(storageKey, JSON.stringify(dirty));
      else localStorage.removeItem(storageKey);
      completed = true;
      render();
      if (showFeedback) notify("Estatísticas sincronizadas com sucesso.", "success");
    } catch (_) {
      if (showFeedback) notify("Não foi possível sincronizar. Nada foi perdido.", "danger");
    } finally {
      syncing = false;
      if (button) button.disabled = false;
      updateConnection();
      if (navigator.onLine && dirty.length && (syncRequested || completed)) {
        syncRequested = false;
        setTimeout(() => sync(false), 150);
      }
    }
  }

  function scheduleSync() {
    if (!navigator.onLine) return;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => sync(false), 650);
  }

  async function resetStatistics() {
    if (resetting) return;
    if (syncing) { notify("Aguarda pela sincronização atual e tenta novamente."); return; }
    if (!navigator.onLine) { notify("É necessária ligação à internet para eliminar a folha estatística.", "danger"); return; }
    if (!window.confirm("Eliminar todas as ações desta folha estatística e recomeçar do zero? Esta ação não pode ser anulada.")) return;
    resetting = true;
    clearTimeout(syncTimer);
    const button = root.querySelector("[data-stat-reset]");
    if (button) button.disabled = true;
    try {
      const response = await fetch(`/estatisticas/jogos/${gameId}/reiniciar`, {
        method: "POST", headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.message || "Falha ao reiniciar estatística");
      dirty = [];
      events = [];
      clearPlayerSelection();
      pendingAction = null;
      selectedPosition = null;
      localStorage.removeItem(storageKey);
      localStorage.removeItem(clockKey);
      clock = { seconds: 600, running: false, period: 1, updatedAt: Date.now() };
      startTimer();
      playerButtons.forEach(item => item.classList.remove("is-selected", "is-on-court"));
      const selectedLabel = root.querySelector("[data-selected-player]");
      if (selectedLabel) selectedLabel.textContent = "Nenhum selecionado";
      render();
      notify(`Folha estatística eliminada. ${result.eventos_eliminados || 0} ação(ões) removida(s).`, "success");
    } catch (error) {
      notify(error.message || "Não foi possível reiniciar a estatística.", "danger");
    } finally {
      resetting = false;
      if (button) button.disabled = false;
      updateConnection();
    }
  }

  function totalsFor(playerId) {
    const list = active().filter(item => item.lado === "equipa" && item.jogador_id === playerId && !lineupTypes.has(item.tipo));
    const count = type => list.filter(item => item.tipo === type).length;
    const llc = count("ll_c"), llt = llc + count("ll_f"), c2 = count("dois_c"), t2 = c2 + count("dois_f");
    const c3 = count("tres_c"), t3 = c3 + count("tres_f"), ro = count("ressalto_ofensivo"), rd = count("ressalto_defensivo");
    const ast = count("assistencia"), stl = count("roubo"), to = count("perda"), blk = count("desarme"), pf = count("falta");
    const pts = llc + c2 * 2 + c3 * 3;
    return { pts, llc, llt, c2, t2, c3, t3, ro, rd, rt: ro + rd, ast, stl, to, blk, pf, eff: pts + ro + rd + ast + stl + blk - (llt - llc) - (t2 - c2) - (t3 - c3) - to };
  }

  function renderBoxscore() {
    const lineup = currentLineup();
    root.querySelectorAll("[data-boxscore-player]").forEach(row => {
      const id = Number(row.dataset.boxscorePlayer);
      const stats = totalsFor(id);
      const cells = row.querySelectorAll("td");
      const values = [formatClock(playingSeconds(id)), stats.pts, `${stats.llc}/${stats.llt}`, `${stats.c2}/${stats.t2}`, `${stats.c3}/${stats.t3}`, stats.ro, stats.rd, stats.rt, stats.ast, stats.stl, stats.to, stats.blk, stats.pf, stats.eff];
      values.forEach((value, index) => { cells[index + 1].textContent = value; });
      const badge = root.querySelector(`[data-player-points="${id}"]`);
      if (badge) badge.textContent = `${stats.pts} pts${lineup.has(id) ? " · campo" : ""}`;
    });
  }

  function renderPlayingTimes() {
    renderBoxscore();
    root.querySelectorAll("[data-lineup-time]").forEach(item => {
      item.textContent = formatClock(playingSeconds(Number(item.dataset.lineupTime)));
    });
  }

  function renderScores() {
    ["equipa", "adversario"].forEach(side => {
      const score = active().filter(item => item.lado === side).reduce((sum, item) => sum + (points[item.tipo] || 0), 0);
      root.querySelector(`[data-score="${side}"]`).textContent = score;
    });
  }

  function renderFeed() {
    const target = root.querySelector("[data-stat-feed]");
    if (!target) return;
    const list = [...active()].filter(item => !lineupTypes.has(item.tipo)).reverse().slice(0, 20);
    target.innerHTML = "";
    if (!list.length) {
      target.innerHTML = '<p class="stat-feed-empty">As ações surgem aqui durante o jogo.</p>';
      return;
    }
    list.forEach(item => {
      const node = document.createElement("div");
      node.className = "stat-feed-item";
      const who = item.lado === "adversario" ? "Adversário" : (item.jogador || "Atleta");
      node.innerHTML = "<div><strong></strong><span></span></div><b></b>";
      node.querySelector("strong").textContent = who;
      node.querySelector("span").textContent = `${labels[item.tipo] || item.tipo}${item.posicao_x != null ? " · posição registada" : ""}`;
      node.querySelector("b").textContent = `${item.periodo}º · ${formatClock(item.segundos_restantes ?? 0)}`;
      target.appendChild(node);
    });
  }

  function renderShotChart() {
    const target = root.querySelector("[data-shot-points]");
    if (!target) return;
    const shots = active().filter(item => item.lado === shotSide && fieldGoalTypes.has(item.tipo) && item.posicao_x != null && item.posicao_y != null);
    const made = shots.filter(item => item.tipo.endsWith("_c")).length;
    target.innerHTML = "";
    shots.forEach(item => {
      const marker = document.createElement("span");
      const converted = item.tipo.endsWith("_c");
      marker.className = `stat-shot-point ${converted ? "is-made" : "is-missed"}`;
      marker.style.left = `${item.posicao_x}%`;
      marker.style.top = `${item.posicao_y}%`;
      marker.title = `${labels[item.tipo]} · ${item.jogador || (shotSide === "adversario" ? "Adversário" : "Atleta")}`;
      marker.setAttribute("aria-label", marker.title);
      target.append(marker);
    });
    const percentage = shots.length ? Math.round((made / shots.length) * 100) : 0;
    root.querySelector("[data-shot-summary]").textContent = `${made}/${shots.length} · ${percentage}%`;
    root.querySelector("[data-shot-empty]").hidden = shots.length > 0;
    root.querySelectorAll("[data-shot-side]").forEach(button => button.classList.toggle("is-active", button.dataset.shotSide === shotSide));
  }

  function renderWarnings() {
    const stack = root.querySelector("[data-warning-stack]");
    if (!stack) return;
    stack.querySelectorAll("[data-auto-warning]").forEach(item => item.remove());
    const list = [];
    root.querySelectorAll("[data-boxscore-player]").forEach(row => {
      const stats = totalsFor(Number(row.dataset.boxscorePlayer));
      if (stats.pf >= 5) list.push([`${row.cells[0].textContent.trim()}: ${stats.pf} faltas, atleta excluído.`, "danger"]);
      else if (stats.pf === 4) list.push([`${row.cells[0].textContent.trim()}: 4 faltas pessoais.`, "warning"]);
    });
    const teamFouls = active().filter(item => item.lado === "equipa" && item.tipo === "falta" && item.periodo === Number(clock.period)).length;
    if (teamFouls >= 5) list.push([`${teamFouls} faltas de equipa no ${clock.period}º período.`, "warning"]);
    list.reverse().forEach(([message, tone]) => {
      const item = document.createElement("div");
      item.dataset.autoWarning = "true";
      item.className = `stat-warning${tone === "danger" ? " is-danger" : ""}`;
      item.textContent = message;
      stack.prepend(item);
    });
    stack.hidden = !stack.children.length;
  }

  function updateConnection() {
    const online = navigator.onLine;
    root.querySelector("[data-online-dot]")?.classList.toggle("is-online", online);
    root.querySelector("[data-online-label]").textContent = online ? "Online" : "Modo offline";
    root.querySelector("[data-sync-label]").textContent = dirty.length ? `${dirty.length} ação(ões) por sincronizar` : "Tudo sincronizado";
  }

  function renderActionState() {
    playerButtons.forEach(item => item.classList.toggle("is-selected", Number(item.dataset.playerId) === selectedPlayer));
    root.querySelectorAll("[data-lineup-player]").forEach(item => item.classList.toggle("is-selected", Number(item.dataset.lineupPlayer) === selectedPlayer));
    root.querySelectorAll("[data-stat-action]").forEach(button => { button.disabled = !selectedPlayer; });
  }

  function render() {
    renderScores();
    renderLineup();
    renderBoxscore();
    renderFeed();
    renderShotChart();
    renderWarnings();
    updateConnection();
    updateClock();
    renderActionState();
  }

  playerButtons.forEach(button => button.addEventListener("click", () => selectPlayer(Number(button.dataset.playerId))));
  root.querySelectorAll("[data-stat-action]").forEach(button => button.addEventListener("click", () => requestEvent(button.dataset.statAction)));
  root.querySelectorAll("[data-opponent-action]").forEach(button => button.addEventListener("click", () => requestEvent(button.dataset.opponentAction, "adversario")));
  root.querySelectorAll("[data-shot-side]").forEach(button => button.addEventListener("click", () => { shotSide = button.dataset.shotSide; renderShotChart(); }));
  root.querySelector("[data-lineup-manage]")?.addEventListener("click", openLineupDialog);
  root.querySelectorAll("[data-lineup-option]").forEach(button => button.addEventListener("click", () => {
    const id = Number(button.dataset.lineupOption);
    if (lineupDraft.has(id)) lineupDraft.delete(id);
    else if (lineupDraft.size < requiredLineupSize) lineupDraft.add(id);
    else { renderLineupDialog("O cinco já está completo. Retira primeiro um atleta."); return; }
    renderLineupDialog();
  }));
  root.querySelector("[data-lineup-save]")?.addEventListener("click", applyLineup);
  root.querySelectorAll("[data-lineup-cancel]").forEach(button => button.addEventListener("click", closeLineupDialog));
  root.querySelector("[data-lineup-dialog]")?.addEventListener("cancel", event => { event.preventDefault(); closeLineupDialog(); });
  root.querySelector("[data-lineup-dialog]")?.addEventListener("click", event => { if (event.target === event.currentTarget) closeLineupDialog(); });
  root.querySelector("[data-stat-court]")?.addEventListener("click", event => {
    const court = event.currentTarget;
    const rect = court.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
    selectedPosition = { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    const marker = root.querySelector("[data-court-marker]");
    marker.hidden = false;
    marker.style.left = `${x}%`;
    marker.style.top = `${y}%`;
    root.querySelector("[data-court-confirm]").disabled = false;
    root.querySelector("[data-court-hint]").textContent = "Posição selecionada. Confirma para registar a ação.";
  });
  root.querySelector("[data-court-confirm]")?.addEventListener("click", () => {
    if (!pendingAction || !selectedPosition) return;
    const action = pendingAction;
    const position = selectedPosition;
    closeCourtDialog();
    addEvent(action.type, action.side, position);
  });
  root.querySelectorAll("[data-court-cancel]").forEach(button => button.addEventListener("click", closeCourtDialog));
  root.querySelector("[data-court-dialog]")?.addEventListener("cancel", event => { event.preventDefault(); closeCourtDialog(); });
  root.querySelector("[data-court-dialog]")?.addEventListener("click", event => { if (event.target === event.currentTarget) closeCourtDialog(); });
  root.querySelector("[data-stat-undo]")?.addEventListener("click", undo);
  root.querySelector("[data-stat-sync]")?.addEventListener("click", () => sync(true));
  root.querySelector("[data-stat-reset]")?.addEventListener("click", resetStatistics);
  root.querySelector("[data-period]")?.addEventListener("change", event => {
    clock.period = Number(event.target.value);
    clock.seconds = 600;
    clock.running = false;
    clearPlayerSelection();
    startTimer();
    saveLocal();
    render();
    if (!currentLineup().size) notify(`Define o cinco inicial do ${clock.period}º período.`);
  });
  clockElement()?.addEventListener("click", () => {
    if (!clock.running && currentLineup().size !== requiredLineupSize) {
      notify("Define primeiro os cinco atletas em campo.", "danger");
      openLineupDialog();
      return;
    }
    clock.running = !clock.running;
    startTimer();
    saveLocal();
  });
  document.addEventListener("keydown", event => {
    if (!canEdit || root.querySelector("[data-court-dialog]")?.open || root.querySelector("[data-lineup-dialog]")?.open || event.ctrlKey || event.metaKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
    const map = { "1": "ll_c", "2": "dois_c", "3": "tres_c", q: "ll_f", w: "dois_f", e: "tres_f", r: "ressalto_defensivo", o: "ressalto_ofensivo", a: "assistencia", s: "roubo", t: "perda", b: "desarme", f: "falta" };
    if (event.key.toLowerCase() === "z") { event.preventDefault(); undo(); }
    else if (map[event.key.toLowerCase()]) { event.preventDefault(); requestEvent(map[event.key.toLowerCase()]); }
  });
  window.addEventListener("online", () => { updateConnection(); sync(false); });
  window.addEventListener("offline", () => { updateConnection(); notify("Ligação perdida. Podes continuar: as ações ficam guardadas neste dispositivo."); });
  window.addEventListener("beforeunload", saveLocal);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.ready.then(registration => registration.active?.postMessage({ type: "CACHE_STATS_PAGE", url: window.location.href })).catch(() => {});
  }
  updateClock();
  startTimer();
  render();
  if (navigator.onLine) sync(false);
})();
