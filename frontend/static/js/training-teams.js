(() => {
  function iniciar() {
    const source = document.getElementById('training-team-data');
    const root = document.querySelector('[data-training-plan]');
    if (!source || !root) return;

    const data = JSON.parse(source.textContent || '{}');
    const players = new Map((data.atletas || []).map(player => [Number(player.id), player]));
    let expectedIds = (data.previstos_ids || []).map(Number);
    let state = data.estado || null;
    let drag = null;
    const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
    const teamRoot = root.querySelector('[data-random-teams]');
    const teamStatus = root.querySelector('[data-team-status]');
    const expectedStatus = root.querySelector('[data-expected-status]');
    const teamSize = root.querySelector('[data-team-size]');
    const postCount = root.querySelector('[data-post-count]');
    const postWrap = root.querySelector('[data-post-count-wrap]');

    const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const avatar = player => player.fotografia
      ? `<span class="training-expected-avatar"><img src="${escapeHTML(player.fotografia)}" alt=""></span>`
      : `<span class="training-expected-avatar">${escapeHTML(player.numero || player.nome?.slice(0, 1) || '?')}</span>`;

    async function post(path, body) {
      const response = await fetch(path, {
        method: 'POST',
        headers: {'Accept':'application/json','Content-Type':'application/json','X-CSRF-Token':csrf()},
        body: JSON.stringify(body),
      });
      let payload;
      try { payload = await response.json(); } catch (_) { payload = {}; }
      if (!response.ok || !payload.sucesso) throw new Error(payload.erro || 'Não foi possível guardar a alteração.');
      return payload;
    }

    function setStatus(element, message, error = false) {
      if (!element) return;
      element.textContent = message;
      element.style.color = error ? '#b42318' : '';
    }

    function updateRule() {
      const size = Number(teamSize?.value || 2);
      if (postWrap) postWrap.hidden = size !== 4;
      const rule = root.querySelector('[data-team-rule]');
      if (!rule) return;
      if (size === 2) rule.textContent = 'Sem restrição de posição.';
      else if (size === 4) rule.textContent = `${postCount?.value || 1} poste(s) ou atleta(s) mais alto(s) por equipa.`;
      else rule.textContent = 'Pelo menos 1 poste ou atleta mais alto por equipa.';
    }

    function renderTeams() {
      const count = root.querySelector('[data-random-team-count]');
      if (count) count.textContent = state?.equipas?.length || 0;
      if (!teamRoot) return;
      if (!state?.equipas?.length) {
        teamRoot.innerHTML = '<p class="training-team-empty">Ainda não foram geradas equipas para este treino.</p>';
        return;
      }
      teamRoot.innerHTML = state.equipas.map((team, teamIndex) => {
        const slots = (team.slots || []).map((playerId, slotIndex) => {
          if (playerId === null) return `<div class="training-team-vacancy" data-team-slot-empty data-team-index="${teamIndex}" data-slot-index="${slotIndex}">+ Lugar vazio</div>`;
          const player = players.get(Number(playerId));
          if (!player) return '';
          const role = state.grandes_ids?.includes(Number(playerId)) ? 'Poste/grande' : (player.posicao || player.equipa || 'Atleta');
          return `<div class="training-team-player" draggable="true" tabindex="0" data-team-player="${playerId}" data-team-index="${teamIndex}" data-slot-index="${slotIndex}">${avatar(player)}<span class="min-w-0"><b>${escapeHTML(player.nome)}</b><small>${escapeHTML(role)}</small></span></div>`;
        }).join('');
        const total = (team.slots || []).filter(id => id !== null).length;
        return `<section class="training-random-team" data-random-team="${teamIndex}"><header><b>${escapeHTML(team.nome || `Equipa ${teamIndex + 1}`)}</b><span>${total} atleta(s)</span></header><div class="training-team-slots">${slots}</div></section>`;
      }).join('');
    }

    function movePlayer(fromTeam, fromSlot, toTeam, toSlot = null) {
      if (!state?.equipas?.[fromTeam] || !state.equipas[toTeam]) return false;
      const playerId = state.equipas[fromTeam].slots[fromSlot];
      if (playerId === null || playerId === undefined) return false;
      if (fromTeam === toTeam && fromSlot === toSlot) return false;
      state.equipas[fromTeam].slots[fromSlot] = null;
      if (toSlot !== null && state.equipas[toTeam].slots[toSlot] === null) state.equipas[toTeam].slots[toSlot] = playerId;
      else state.equipas[toTeam].slots.push(playerId);
      return true;
    }

    async function saveTeams(previous) {
      setStatus(teamStatus, 'A guardar organização...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias`, {
          equipas: state.equipas.map(team => team.slots),
        });
        state = payload.estado;
        renderTeams();
        setStatus(teamStatus, 'Organização guardada automaticamente.');
      } catch (error) {
        state = previous;
        renderTeams();
        setStatus(teamStatus, error.message, true);
      }
    }

    function dropTargetAt(x, y) {
      const element = document.elementFromPoint(x, y);
      return element?.closest?.('[data-team-slot-empty],[data-random-team]') || null;
    }

    function completeMove(target) {
      if (!drag || !target) return;
      const previous = JSON.parse(JSON.stringify(state));
      const team = Number(target.dataset.teamIndex ?? target.dataset.randomTeam);
      const slot = target.matches('[data-team-slot-empty]') ? Number(target.dataset.slotIndex) : null;
      if (movePlayer(drag.team, drag.slot, team, slot)) {
        renderTeams();
        saveTeams(previous);
      }
    }

    teamRoot?.addEventListener('dragstart', event => {
      const item = event.target.closest('[data-team-player]');
      if (!item) return;
      drag = {team:Number(item.dataset.teamIndex), slot:Number(item.dataset.slotIndex), pointer:false};
      item.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', item.dataset.teamPlayer);
    });
    teamRoot?.addEventListener('dragover', event => {
      const target = event.target.closest('[data-team-slot-empty],[data-random-team]');
      if (!target) return;
      event.preventDefault();
      teamRoot.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
      target.closest('[data-random-team]')?.classList.add('is-drop-target');
    });
    teamRoot?.addEventListener('drop', event => {
      event.preventDefault();
      completeMove(event.target.closest('[data-team-slot-empty],[data-random-team]'));
      drag = null;
    });
    teamRoot?.addEventListener('dragend', () => {
      teamRoot.querySelectorAll('.is-dragging,.is-drop-target').forEach(item => item.classList.remove('is-dragging','is-drop-target'));
      drag = null;
    });

    teamRoot?.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' || event.button !== 0) return;
      const item = event.target.closest('[data-team-player]');
      if (!item) return;
      event.preventDefault();
      drag = {team:Number(item.dataset.teamIndex), slot:Number(item.dataset.slotIndex), pointer:true, id:event.pointerId, x:event.clientX, y:event.clientY, item, ghost:null};
      item.setPointerCapture?.(event.pointerId);
    });
    document.addEventListener('pointermove', event => {
      if (!drag?.pointer || drag.id !== event.pointerId) return;
      if (!drag.ghost && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 6) return;
      event.preventDefault();
      if (!drag.ghost) {
        drag.ghost = drag.item.cloneNode(true);
        drag.ghost.classList.add('training-team-drag-ghost');
        document.body.appendChild(drag.ghost);
        drag.item.classList.add('is-dragging');
      }
      drag.ghost.style.left = `${event.clientX}px`;
      drag.ghost.style.top = `${event.clientY}px`;
      teamRoot.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
      dropTargetAt(event.clientX, event.clientY)?.closest('[data-random-team]')?.classList.add('is-drop-target');
    }, {passive:false});
    document.addEventListener('pointerup', event => {
      if (!drag?.pointer || drag.id !== event.pointerId) return;
      const target = dropTargetAt(event.clientX, event.clientY);
      drag.ghost?.remove();
      drag.item?.classList.remove('is-dragging');
      completeMove(target);
      drag = null;
    });

    root.querySelectorAll('[data-training-dropdown]').forEach(details => details.addEventListener('toggle', () => {
      if (!details.open) return;
      root.querySelectorAll('[data-training-dropdown]').forEach(other => { if (other !== details) other.open = false; });
    }));
    teamSize?.addEventListener('change', updateRule);
    postCount?.addEventListener('change', updateRule);
    root.querySelector('[data-toggle-all-expected]')?.addEventListener('click', () => {
      const boxes = [...root.querySelectorAll('[data-expected-player-options] input[type="checkbox"]')];
      const check = boxes.some(box => !box.checked);
      boxes.forEach(box => { box.checked = check; });
    });
    root.querySelector('[data-save-expected]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const ids = [...root.querySelectorAll('[data-expected-player-options] input:checked')].map(input => Number(input.value));
      button.disabled = true;
      setStatus(expectedStatus, 'A guardar seleção...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/atletas-previstos`, {jogador_ids:ids});
        expectedIds = payload.jogador_ids;
        state = null;
        renderTeams();
        const count = root.querySelector('[data-expected-player-count]');
        if (count) count.textContent = expectedIds.length;
        setStatus(expectedStatus, payload.mensagem);
        setStatus(teamStatus, 'A seleção mudou. Gera novamente as equipas.');
      } catch (error) { setStatus(expectedStatus, error.message, true); }
      finally { button.disabled = false; }
    });
    root.querySelector('[data-generate-teams]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      setStatus(teamStatus, 'A gerar equipas equilibradas...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias/gerar`, {tamanho:Number(teamSize.value),postes_por_equipa:Number(postCount?.value || 1)});
        state = payload.estado;
        renderTeams();
        setStatus(teamStatus, 'Equipas geradas e guardadas. Arrasta para ajustar.');
      } catch (error) { setStatus(teamStatus, error.message, true); }
      finally { button.disabled = false; }
    });

    if (state?.tamanho && teamSize) teamSize.value = String(state.tamanho);
    if (state?.postes_por_equipa && postCount) postCount.value = String(state.postes_por_equipa);
    updateRule();
    renderTeams();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
