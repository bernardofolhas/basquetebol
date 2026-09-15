(() => {
  function iniciar() {
    const source = document.getElementById('training-team-data');
    const root = document.querySelector('[data-training-plan]');
    if (!source || !root) return;

    const data = JSON.parse(source.textContent || '{}');
    const players = new Map((data.atletas || []).map(player => [Number(player.id), player]));
    let expectedIds = (data.previstos_ids || []).map(Number);
    let state = data.estado || {grupos: []};
    if (!Array.isArray(state.grupos)) state = state.equipas ? {grupos: [{id: 1, nome: 'Agrupamento 1', ...state}]} : {grupos: []};
    let drag = null;
    const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
    const groupRoot = root.querySelector('[data-random-team-groups]');
    const teamStatus = root.querySelector('[data-team-status]');
    const expectedStatus = root.querySelector('[data-expected-status]');
    const teamSize = root.querySelector('[data-team-size]');
    const postCount = root.querySelector('[data-post-count]');
    const postWrap = root.querySelector('[data-post-count-wrap]');

    const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const avatar = player => player.fotografia
      ? `<span class="training-expected-avatar"><img src="${escapeHTML(player.fotografia)}" alt=""></span>`
      : `<span class="training-expected-avatar">${escapeHTML(player.numero || player.nome?.slice(0, 1) || '?')}</span>`;

    async function post(path, body = {}) {
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

    function updateCounters(selector, value) {
      root.querySelectorAll(selector).forEach(element => { element.textContent = value; });
    }

    function updateRule() {
      const size = Number(teamSize?.value || 2);
      if (postWrap) postWrap.hidden = ![4, 5].includes(size);
      const rule = root.querySelector('[data-team-rule]');
      if (!rule) return;
      const postes = Number(postCount?.value || (size === 5 ? 2 : 1));
      if (size === 2) rule.textContent = '1 base · 1 extremo';
      else if (size === 3) rule.textContent = '1 base · 1 extremo · 1 poste';
      else rule.textContent = `1 base · ${size - 1 - postes} extremo(s) · ${postes} poste(s)`;
    }

    function renderGroups() {
      updateCounters('[data-random-group-count]', state.grupos.length);
      if (!groupRoot) return;
      if (!state.grupos.length) {
        groupRoot.innerHTML = '<p class="training-team-empty">Ainda não existem agrupamentos. Escolhe o número de jogadores e adiciona o primeiro.</p>';
        return;
      }
      groupRoot.innerHTML = state.grupos.map((group, groupIndex) => {
        const teams = (group.equipas || []).map((team, teamIndex) => {
          const slots = (team.slots || []).map((playerId, slotIndex) => {
            if (playerId === null) return '';
            const player = players.get(Number(playerId));
            if (!player) return '';
            const role = group.posicoes_ids?.[playerId] || (group.grandes_ids?.includes(Number(playerId)) ? 'Poste' : (player.posicao || 'Posição por definir'));
            return `<div class="training-team-player" draggable="true" tabindex="0" data-team-player="${playerId}" data-group-id="${group.id}" data-team-index="${teamIndex}" data-slot-index="${slotIndex}">${avatar(player)}<span class="min-w-0"><b>${escapeHTML(player.nome)}</b><small>${escapeHTML(role)}</small></span></div>`;
          }).join('');
          const total = (team.slots || []).filter(id => id !== null).length;
          return `<section class="training-random-team" data-random-team="${teamIndex}" data-group-id="${group.id}"><header><b>${escapeHTML(team.nome || `Equipa ${teamIndex + 1}`)}</b><span>${total} atleta(s)</span></header><div class="training-team-slots">${slots}</div></section>`;
        }).join('');
        const postes = Number(group.postes_por_equipa || (Number(group.tamanho) === 5 ? 2 : 1));
        const composition = Number(group.tamanho) >= 3 ? ` · objetivo: 1 base · ${Number(group.tamanho) - 1 - postes} extremo(s) · ${postes} poste(s)` : '';
        return `<article class="training-team-group" data-team-group-card="${group.id}"><header class="training-team-group-head"><div><span>Agrupamento ${groupIndex + 1}</span><h3>Equipas de ${group.tamanho}${composition}</h3></div><div><button type="button" class="ds-quiet-link" data-regenerate-group="${group.id}">Gerar novamente</button><button type="button" class="training-group-delete" data-delete-group="${group.id}">Eliminar</button></div></header><div class="training-random-teams" data-team-group="${group.id}">${teams}</div></article>`;
      }).join('');
    }

    function findGroup(groupId) {
      return state.grupos.find(group => Number(group.id) === Number(groupId));
    }

    function movePlayer(groupId, fromTeam, fromSlot, toTeam, toSlot = null) {
      const group = findGroup(groupId);
      if (!group?.equipas?.[fromTeam] || !group.equipas[toTeam]) return false;
      const playerId = group.equipas[fromTeam].slots[fromSlot];
      if (playerId === null || playerId === undefined) return false;
      if (fromTeam === toTeam && fromSlot === toSlot) return false;
      group.equipas[fromTeam].slots[fromSlot] = null;
      if (toSlot !== null && group.equipas[toTeam].slots[toSlot] === null) group.equipas[toTeam].slots[toSlot] = playerId;
      else group.equipas[toTeam].slots.push(playerId);
      return true;
    }

    async function saveGroup(groupId, previous) {
      const group = findGroup(groupId);
      if (!group) return;
      setStatus(teamStatus, 'A guardar organização...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias`, {
          grupo_id: Number(groupId),
          equipas: group.equipas.map(team => team.slots),
        });
        state = payload.estado;
        renderGroups();
        setStatus(teamStatus, 'Organização guardada automaticamente.');
      } catch (error) {
        state = previous;
        renderGroups();
        setStatus(teamStatus, error.message, true);
      }
    }

    function dropTargetAt(x, y) {
      const element = document.elementFromPoint(x, y);
      return element?.closest?.('[data-team-slot-empty],[data-random-team]') || null;
    }

    function completeMove(target) {
      if (!drag || !target || Number(target.dataset.groupId) !== drag.groupId) return;
      const previous = JSON.parse(JSON.stringify(state));
      const team = Number(target.dataset.teamIndex ?? target.dataset.randomTeam);
      const slot = target.matches('[data-team-slot-empty]') ? Number(target.dataset.slotIndex) : null;
      if (movePlayer(drag.groupId, drag.team, drag.slot, team, slot)) {
        renderGroups();
        saveGroup(drag.groupId, previous);
      }
    }

    groupRoot?.addEventListener('dragstart', event => {
      const item = event.target.closest('[data-team-player]');
      if (!item) return;
      drag = {groupId:Number(item.dataset.groupId),team:Number(item.dataset.teamIndex),slot:Number(item.dataset.slotIndex),pointer:false};
      item.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', item.dataset.teamPlayer);
    });
    groupRoot?.addEventListener('dragover', event => {
      const target = event.target.closest('[data-team-slot-empty],[data-random-team]');
      if (!target || Number(target.dataset.groupId) !== drag?.groupId) return;
      event.preventDefault();
      groupRoot.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
      target.closest('[data-random-team]')?.classList.add('is-drop-target');
    });
    groupRoot?.addEventListener('drop', event => {
      event.preventDefault();
      completeMove(event.target.closest('[data-team-slot-empty],[data-random-team]'));
      drag = null;
    });
    groupRoot?.addEventListener('dragend', () => {
      groupRoot.querySelectorAll('.is-dragging,.is-drop-target').forEach(item => item.classList.remove('is-dragging','is-drop-target'));
      drag = null;
    });

    groupRoot?.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' || event.button !== 0) return;
      const item = event.target.closest('[data-team-player]');
      if (!item) return;
      event.preventDefault();
      drag = {groupId:Number(item.dataset.groupId),team:Number(item.dataset.teamIndex),slot:Number(item.dataset.slotIndex),pointer:true,id:event.pointerId,x:event.clientX,y:event.clientY,item,ghost:null};
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
      groupRoot.querySelectorAll('.is-drop-target').forEach(item => item.classList.remove('is-drop-target'));
      const target = dropTargetAt(event.clientX, event.clientY);
      if (Number(target?.dataset.groupId) === drag.groupId) target.closest('[data-random-team]')?.classList.add('is-drop-target');
    }, {passive:false});
    document.addEventListener('pointerup', event => {
      if (!drag?.pointer || drag.id !== event.pointerId) return;
      const target = dropTargetAt(event.clientX, event.clientY);
      drag.ghost?.remove();
      drag.item?.classList.remove('is-dragging');
      completeMove(target);
      drag = null;
    });

    groupRoot?.addEventListener('click', async event => {
      const regenerate = event.target.closest('[data-regenerate-group]');
      const remove = event.target.closest('[data-delete-group]');
      if (regenerate) {
        const group = findGroup(Number(regenerate.dataset.regenerateGroup));
        if (!group) return;
        regenerate.disabled = true;
        setStatus(teamStatus, 'A gerar novamente este agrupamento...');
        try {
          const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias/gerar`, {grupo_id:group.id,tamanho:group.tamanho,postes_por_equipa:group.postes_por_equipa});
          state = payload.estado;
          renderGroups();
          setStatus(teamStatus, 'Agrupamento atualizado.');
        } catch (error) { setStatus(teamStatus, error.message, true); regenerate.disabled = false; }
      }
      if (remove) {
        if (!window.confirm('Eliminar apenas este agrupamento de equipas?')) return;
        remove.disabled = true;
        try {
          const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias/${remove.dataset.deleteGroup}/eliminar`);
          state = payload.estado;
          renderGroups();
          setStatus(teamStatus, payload.mensagem);
        } catch (error) { setStatus(teamStatus, error.message, true); remove.disabled = false; }
      }
    });

    teamSize?.addEventListener('change', () => {
      if (postCount) postCount.value = Number(teamSize.value) === 5 ? '2' : '1';
      updateRule();
    });
    postCount?.addEventListener('change', updateRule);
    root.querySelector('[data-toggle-all-expected]')?.addEventListener('click', () => {
      const boxes = [...root.querySelectorAll('[data-expected-player-options] input[type="checkbox"]')];
      const check = boxes.some(box => !box.checked);
      boxes.forEach(box => { box.checked = check; });
    });
    root.querySelector('[data-callup-sub18]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const selected = [...root.querySelectorAll('[data-sub18-option] input:checked')];
      const ids = selected.map(input => Number(input.value));
      const status = root.querySelector('[data-sub18-status]');
      if (!ids.length) {
        setStatus(status, 'Seleciona pelo menos um atleta Sub-18.', true);
        return;
      }
      button.disabled = true;
      setStatus(status, 'A convocar atletas...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/convocar-sub18`, {jogador_ids:ids});
        expectedIds = payload.jogador_ids;
        state = {grupos: []};
        const expectedRoot = root.querySelector('[data-expected-player-options]');
        (payload.adicionados || []).forEach(player => {
          players.set(Number(player.id), player);
          if (!expectedRoot?.querySelector(`input[value="${player.id}"]`)) {
            expectedRoot?.insertAdjacentHTML('beforeend', `<label class="training-expected-player"><input type="checkbox" value="${player.id}" checked>${avatar(player)}<span class="min-w-0"><b>${escapeHTML(player.nome)}</b><small>Convocado · ${escapeHTML(player.equipa)}</small></span></label>`);
          }
          root.querySelector(`[data-sub18-option="${player.id}"]`)?.remove();
        });
        root.querySelectorAll('[data-expected-player-options] input').forEach(input => { input.checked = expectedIds.includes(Number(input.value)); });
        const remaining = root.querySelectorAll('[data-sub18-option]').length;
        updateCounters('[data-sub18-available-count]', remaining);
        if (!remaining && !root.querySelector('[data-sub18-empty]')) {
          root.querySelector('[data-sub18-options]')?.insertAdjacentHTML('beforeend', '<p class="training-team-empty" data-sub18-empty>Não existem atletas Sub-18 disponíveis para convocar.</p>');
        }
        updateCounters('[data-expected-player-count]', expectedIds.length);
        renderGroups();
        setStatus(status, payload.mensagem);
        setStatus(expectedStatus, 'A convocatória foi incluída nos atletas previstos.');
        setStatus(teamStatus, 'A lista de atletas mudou. Cria novamente os agrupamentos.');
      } catch (error) { setStatus(status, error.message, true); }
      finally { button.disabled = false; }
    });
    root.querySelector('[data-save-expected]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const ids = [...root.querySelectorAll('[data-expected-player-options] input:checked')].map(input => Number(input.value));
      button.disabled = true;
      setStatus(expectedStatus, 'A guardar seleção...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/atletas-previstos`, {jogador_ids:ids});
        expectedIds = payload.jogador_ids;
        state = {grupos: []};
        renderGroups();
        updateCounters('[data-expected-player-count]', expectedIds.length);
        setStatus(expectedStatus, payload.mensagem);
        setStatus(teamStatus, 'A seleção mudou. Cria novamente os agrupamentos.');
      } catch (error) { setStatus(expectedStatus, error.message, true); }
      finally { button.disabled = false; }
    });
    root.querySelector('[data-generate-teams]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      setStatus(teamStatus, 'A adicionar agrupamento...');
      try {
        const payload = await post(`/treino/planos/${data.plano_id}/equipas-aleatorias/gerar`, {tamanho:Number(teamSize.value),postes_por_equipa:Number(postCount?.value || 1)});
        state = payload.estado;
        renderGroups();
        setStatus(teamStatus, 'Agrupamento adicionado. Podes criar outro ou arrastar os atletas para ajustar.');
      } catch (error) { setStatus(teamStatus, error.message, true); }
      finally { button.disabled = false; }
    });

    updateRule();
    renderGroups();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
