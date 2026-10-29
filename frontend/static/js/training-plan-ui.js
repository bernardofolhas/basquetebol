(function () {
    'use strict';
    const notes = new Map();
    const values = form => JSON.stringify([form.elements.organizacao.value, form.elements.coaching_points.value]);

    function grow(input) {
        if (!input.getClientRects().length) return;
        input.style.height = 'auto';
        input.style.height = `${input.scrollHeight + 2}px`;
    }

    function noteStatus(form, text, error = false) {
        const status = form.querySelector('[data-notes-status]');
        if (status) {
            status.textContent = text;
            status.dataset.error = String(error);
        }
    }

    function prepareNotes(form) {
        if (notes.has(form)) return notes.get(form);
        const state = {saved: values(form), timer: null, pending: null};
        notes.set(form, state);
        form.addEventListener('input', event => {
            if (!event.target.matches('textarea[data-autogrow]')) return;
            grow(event.target);
            clearTimeout(state.timer);
            noteStatus(form, 'Por guardar');
            state.timer = setTimeout(() => saveNotes(form), 800);
        });
        form.addEventListener('focusout', event => {
            if (event.target.matches('textarea[data-autogrow]') && !event.target.composing) saveNotes(form);
        });
        form.addEventListener('compositionstart', () => { clearTimeout(state.timer); state.composing = true; });
        form.addEventListener('compositionend', () => { state.composing = false; state.timer = setTimeout(() => saveNotes(form), 800); });
        return state;
    }

    async function saveNotes(form) {
        const state = prepareNotes(form);
        clearTimeout(state.timer);
        if (state.pending) return state.pending;
        if (!form.isConnected || state.composing) return;
        if (state.saved === values(form)) { noteStatus(form, 'Guardado'); return; }
        // One request per exercise; edits made while saving remain in the fields.
        const snapshot = values(form);
        const body = new FormData(form);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        noteStatus(form, 'A guardar...');
        let success = false;
        state.pending = (async () => {
            try {
                const response = await fetch(form.action, {
                    method: 'POST', body, signal: controller.signal,
                    headers: {'Accept': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || ''},
                });
                if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Sessão indisponível. Mantém esta página aberta e volta a tentar.');
                const data = await response.json();
                if (!response.ok || !data.sucesso) throw new Error(data.erro || 'Não foi possível guardar. Tenta novamente.');
                state.saved = snapshot;
                success = true;
                const modal = document.getElementById(`modal_exercicio_${form.dataset.trainingNotes}`);
                if (modal && !modal.open) {
                    ['organizacao', 'coaching_points'].forEach(name => {
                        const input = modal.querySelector(`[name="${name}"]`);
                        if (input) input.value = form.elements[name].value;
                    });
                }
                noteStatus(form, state.saved === values(form) ? 'Guardado' : 'Por guardar');
            } catch (error) {
                noteStatus(form, error.name === 'AbortError' ? 'Sem resposta. Carrega em Guardar para tentar novamente.' : error.message, true);
            } finally {
                clearTimeout(timeout);
                state.pending = null;
                if (success && state.saved !== values(form) && form.isConnected) state.timer = setTimeout(() => saveNotes(form), 300);
            }
        })();
        return state.pending;
    }

    function courts(panel, selectedId) {
        const cards = Array.from(panel.querySelectorAll('[data-editor-field]'));
        const count = panel.querySelector('[data-court-count]');
        if (count) count.textContent = `${cards.length} ${cards.length === 1 ? 'campo' : 'campos'}`;
        cards.forEach((card, index) => {
            const canvas = card.querySelector('canvas');
            card.id = `campo-${canvas.id}`;
            card.hidden = false;
            const label = card.querySelector('[data-court-label]');
            if (label) label.textContent = `Campo ${index + 1} · ${canvas.dataset.campoTipo === 'completo' ? 'Campo inteiro' : 'Meio-campo'}`;
        });
        const added = cards.find(card => card.querySelector('canvas').id === selectedId);
        const grid = panel.querySelector('.training-ink-grid');
        // Scroll only the court list, never the whole training page.
        if (added && grid) grid.scrollTop += added.getBoundingClientRect().top - grid.getBoundingClientRect().top;
    }

    function init(root = document) {
        root.querySelectorAll('[data-drawing-editor]').forEach(panel => courts(panel));
        root.querySelectorAll('[data-training-notes]').forEach(prepareNotes);
        root.querySelectorAll('[data-autogrow]').forEach(grow);
    }

    document.addEventListener('click', event => {
        const openAdd = event.target.closest('[data-training-open-add]');
        if (openAdd) {
            document.querySelector('[data-workspace-tab="exercicios"]')?.click();
            document.querySelector('[data-training-add]')?.click();
            document.getElementById('training-add-panel')?.scrollIntoView({block: 'start', behavior: 'auto'});
        }
        const collapse = event.target.closest('[data-training-collapse]');
        if (collapse) {
            const card = collapse.closest('[data-training-exercise-id]');
            const closed = card.classList.toggle('is-collapsed');
            collapse.textContent = closed ? 'Abrir' : 'Recolher';
            collapse.setAttribute('aria-expanded', String(!closed));
            if (!closed) card.querySelectorAll('[data-autogrow]').forEach(grow);
        }
        const bullet = event.target.closest('[data-note-bullet]');
        if (bullet) {
            const input = bullet.closest('form').elements[bullet.dataset.noteBullet];
            input.focus({preventScroll: true});
            const prefix = input.value && !input.value.endsWith('\n') ? '\n- ' : '- ';
            input.setRangeText(prefix, input.value.length, input.value.length, 'end');
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
        document.querySelectorAll('.training-more[open]').forEach(menu => {
            if (!menu.contains(event.target) || event.target.closest('button,a')) menu.open = false;
        });
        if (event.target.closest('[data-workspace-tab]')) requestAnimationFrame(() => document.querySelectorAll('[data-autogrow]').forEach(grow));
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        document.querySelectorAll('.training-more[open]').forEach(menu => { menu.open = false; menu.querySelector('summary').focus({preventScroll: true}); });
    });
    window.addEventListener('resize', () => document.querySelectorAll('[data-autogrow]').forEach(grow));
    window.addEventListener('beforeunload', event => {
        if (!Array.from(notes).some(([form, state]) => form.isConnected && (state.pending || state.saved !== values(form)))) return;
        event.preventDefault();
        event.returnValue = '';
    });
    window.TrainingPlanUI = {init, courts, saveNotes};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
    else init();
})();
