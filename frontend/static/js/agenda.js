(function () {
    function modal() {
        return document.getElementById('agenda-modal');
    }

    function campo(id) {
        return document.getElementById(id);
    }

    function mostrar() {
        const elemento = modal();
        if (!elemento) return;
        if (typeof elemento.showModal === 'function') elemento.showModal();
        else elemento.setAttribute('open', 'open');
    }

    function guardarPosicao() {
        sessionStorage.setItem('agenda:retorno', JSON.stringify({
            caminho: window.location.pathname + window.location.search,
            scrollY: window.scrollY,
        }));
    }

    async function submeterAgenda(formulario, action) {
        const botao = campo('agenda-submit');
        const textoOriginal = botao ? botao.textContent : '';
        if (botao) {
            botao.disabled = true;
            botao.textContent = 'A guardar…';
        }
        try {
            const resposta = await fetch(action || formulario.action, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: new FormData(formulario),
            });
            const dados = await resposta.json();
            if (!resposta.ok || !dados.sucesso) {
                throw new Error(dados.erro || 'Não foi possível concluir a operação.');
            }
            guardarPosicao();
            window.location.reload();
        } catch (erro) {
            window.alert(erro.message);
            if (botao) {
                botao.disabled = false;
                botao.textContent = textoOriginal;
            }
        }
    }

    function aplicarLimiteDaRecorrencia() {
        const recorrencia = campo('agenda-recorrencia');
        const dataFim = campo('agenda-data-fim');
        const limite = campo('agenda-limite-recorrencia');
        if (!recorrencia || !dataFim || !limite || recorrencia.value === 'unica') return;
        if (!dataFim.value && limite.value) dataFim.value = limite.value;
    }

    function abrirNovaAgenda(data) {
        const formulario = campo('agenda-form');
        if (!formulario) return;
        formulario.action = '/agenda/atividades';
        campo('agenda-modal-titulo').textContent = 'Nova atividade';
        campo('agenda-submit').textContent = 'Criar atividade';
        campo('agenda-duplicar').classList.add('hidden');
        campo('agenda-apagar').classList.add('hidden');
        campo('agenda-escopo-wrap').classList.add('hidden');
        campo('agenda-evento-id').value = '';
        campo('agenda-tipo').value = 'treino_equipa';
        campo('agenda-titulo').value = '';
        campo('agenda-data').value = data || '';
        campo('agenda-data-fim').value = '';
        campo('agenda-recorrencia').value = 'unica';
        campo('agenda-intervalo').value = '1';
        campo('agenda-hora-inicio').value = '';
        campo('agenda-hora-fim').value = '';
        if (campo('agenda-volume')) campo('agenda-volume').value = '';
        if (campo('agenda-rpe')) campo('agenda-rpe').value = '';
        campo('agenda-descricao').value = '';
        campo('agenda-espaco').value = '';
        if (campo('agenda-equipa')) campo('agenda-equipa').value = '';
        if (campo('agenda-aplica-todas')) campo('agenda-aplica-todas').checked = false;
        mostrar();
    }

    function abrirEdicaoAgenda(elemento) {
        const formulario = campo('agenda-form');
        if (!formulario) return;
        const id = elemento.dataset.agendaEventId;
        formulario.action = '/agenda/atividades/' + id + '/editar';
        campo('agenda-modal-titulo').textContent = 'Editar atividade';
        campo('agenda-submit').textContent = 'Guardar alterações';
        campo('agenda-duplicar').classList.remove('hidden');
        campo('agenda-apagar').classList.remove('hidden');
        campo('agenda-escopo-wrap').classList.toggle('hidden', !elemento.dataset.agendaSerieId);
        campo('agenda-evento-id').value = id;
        campo('agenda-tipo').value = elemento.dataset.agendaTipo || 'outro';
        campo('agenda-titulo').value = elemento.dataset.agendaTitulo || '';
        campo('agenda-data').value = elemento.dataset.agendaData || '';
        campo('agenda-data-fim').value = elemento.dataset.agendaDataFim || '';
        campo('agenda-recorrencia').value = elemento.dataset.agendaRecorrencia || 'unica';
        campo('agenda-intervalo').value = elemento.dataset.agendaRecorrenciaIntervalo || '1';
        if (elemento.dataset.agendaSerieId) campo('agenda-escopo').value = 'serie';
        campo('agenda-hora-inicio').value = elemento.dataset.agendaHoraInicio || '';
        campo('agenda-hora-fim').value = elemento.dataset.agendaHoraFim || '';
        campo('agenda-descricao').value = elemento.dataset.agendaDescricao || '';
        campo('agenda-espaco').value = elemento.dataset.agendaEspacoId || '';
        if (campo('agenda-equipa')) campo('agenda-equipa').value = elemento.dataset.agendaEquipaId || '';
        if (campo('agenda-aplica-todas')) campo('agenda-aplica-todas').checked = elemento.dataset.agendaAplicaTodas === 'true';
        mostrar();
    }

    function duplicarAgenda() {
        const id = campo('agenda-evento-id').value;
        const formulario = campo('agenda-form');
        if (!id || !formulario) return;
        formulario.action = '/agenda/atividades/' + id + '/duplicar';
        formulario.querySelectorAll('[required]').forEach(function (input) {
            input.removeAttribute('required');
        });
        submeterAgenda(formulario, formulario.action);
    }

    function apagarAgenda() {
        const id = campo('agenda-evento-id').value;
        const formulario = campo('agenda-form');
        if (!id || !formulario || !window.confirm('Remover esta atividade do calendário? As sessões de treino associadas também serão eliminadas.')) return;
        formulario.action = '/agenda/atividades/' + id + '/apagar';
        formulario.querySelectorAll('[required]').forEach(function (input) { input.removeAttribute('required'); });
        submeterAgenda(formulario, formulario.action);
    }

    document.addEventListener('click', function (evento) {
        // Os cartões do calendário também criam atividades; links internos têm prioridade.
        const link = evento.target.closest('a[href]');
        if (link && !link.dataset.agendaEventId) return;
        const existente = evento.target.closest('[data-agenda-event-id]');
        if (existente) {
            evento.preventDefault();
            evento.stopPropagation();
            abrirEdicaoAgenda(existente);
            return;
        }
        const novo = evento.target.closest('[data-agenda-new-date]');
        if (novo) {
            evento.preventDefault();
            evento.stopPropagation();
            abrirNovaAgenda(novo.dataset.agendaNewDate);
            return;
        }
    });

    document.addEventListener('change', function (evento) {
        if (evento.target.id === 'agenda-recorrencia') aplicarLimiteDaRecorrencia();
    });

    document.addEventListener('submit', function (evento) {
        const formulario = evento.target;
        if (formulario.id !== 'agenda-form') return;
        evento.preventDefault();
        submeterAgenda(formulario, formulario.action);
    });

    document.addEventListener('DOMContentLoaded', function () {
        try {
            const retorno = JSON.parse(sessionStorage.getItem('agenda:retorno') || 'null');
            const caminho = window.location.pathname + window.location.search;
            if (retorno && retorno.caminho === caminho) {
                sessionStorage.removeItem('agenda:retorno');
                window.requestAnimationFrame(function () { window.scrollTo(0, retorno.scrollY || 0); });
            }
        } catch (_) {
            sessionStorage.removeItem('agenda:retorno');
        }
    });

    window.abrirNovaAgenda = abrirNovaAgenda;
    window.abrirEdicaoAgenda = abrirEdicaoAgenda;
    window.duplicarAgenda = duplicarAgenda;
    window.apagarAgenda = apagarAgenda;
})();
