(function () {
    "use strict";

    function iniciarMapa(mapa) {
        var botaoGuardar = mapa.querySelector("[data-mapa-save]");
        var estado = mapa.querySelector("[data-mapa-save-status]");
        var alteracoes = new Map();
        var aGuardar = false;
        var chaveMensagem = "mapa-conteudos:mensagem:" + window.location.pathname;

        function csrfToken() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.content : "";
        }

        async function enviarJson(url, dados) {
            var resposta = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken(),
                    "X-Requested-With": "XMLHttpRequest"
                },
                body: JSON.stringify(dados || {})
            });
            var payload = await resposta.json();
            if (!resposta.ok || !payload.sucesso) throw new Error(payload.erro || "Não foi possível concluir a operação.");
            return payload;
        }

        function atualizarEstado(mensagem, classe) {
            estado.textContent = mensagem;
            estado.className = "mapa-save-status" + (classe ? " " + classe : "");
        }

        function atualizarBotao() {
            botaoGuardar.disabled = !alteracoes.size || aGuardar;
            if (!aGuardar && alteracoes.size) {
                atualizarEstado(alteracoes.size + (alteracoes.size === 1 ? " alteração por guardar" : " alterações por guardar"), "is-pending");
            } else if (!aGuardar && !alteracoes.size) {
                atualizarEstado("Sem alterações", "");
            }
        }

        try {
            var mensagemGuardada = window.sessionStorage.getItem(chaveMensagem);
            if (mensagemGuardada) {
                window.sessionStorage.removeItem(chaveMensagem);
                atualizarEstado(mensagemGuardada, "is-success");
                window.setTimeout(atualizarBotao, 2200);
            }
        } catch (erro) {}

        mapa.querySelectorAll("[data-priority-cell]").forEach(function (celula) {
            celula.dataset.original = celula.dataset.value || "";
            celula.addEventListener("click", function () {
                var atual = celula.dataset.value || "";
                var seguinte = atual === "" ? "1" : (atual === "1" ? "2" : "");
                var chave = celula.dataset.contentId + ":" + celula.dataset.week;

                celula.dataset.value = seguinte;
                celula.textContent = seguinte;
                celula.classList.toggle("priority-1", seguinte === "1");
                celula.classList.toggle("priority-2", seguinte === "2");
                celula.classList.toggle("is-pending", seguinte !== celula.dataset.original);
                celula.setAttribute("aria-label", celula.getAttribute("aria-label").split(":")[0] + ": " + (seguinte ? "prioridade " + seguinte : "sem prioridade"));

                if (seguinte === celula.dataset.original) alteracoes.delete(chave);
                else alteracoes.set(chave, {
                    conteudo_id: Number(celula.dataset.contentId),
                    semana_inicio: celula.dataset.week,
                    prioridade: seguinte ? Number(seguinte) : null
                });
                atualizarBotao();
            });
        });

        botaoGuardar.addEventListener("click", async function () {
            if (!alteracoes.size || aGuardar) return;
            aGuardar = true;
            botaoGuardar.disabled = true;
            atualizarEstado("A guardar...", "is-pending");
            try {
                await enviarJson(mapa.dataset.saveUrl, { alteracoes: Array.from(alteracoes.values()) });
                mapa.querySelectorAll("[data-priority-cell].is-pending").forEach(function (celula) {
                    celula.dataset.original = celula.dataset.value || "";
                    celula.classList.remove("is-pending");
                });
                alteracoes.clear();
                atualizarEstado("Prioridades guardadas", "is-success");
                window.setTimeout(atualizarBotao, 1800);
            } catch (erro) {
                atualizarEstado(erro.message, "is-error");
            } finally {
                aGuardar = false;
                botaoGuardar.disabled = !alteracoes.size;
            }
        });

        var dialogo = mapa.querySelector("[data-content-dialog]");
        var formulario = mapa.querySelector("[data-content-form]");
        var estadoDialogo = mapa.querySelector("[data-content-status]");
        var botaoAdicionar = mapa.querySelector("[data-mapa-add]");
        var tituloDialogo = mapa.querySelector("[data-content-dialog-title]");
        var kickerDialogo = mapa.querySelector("[data-content-dialog-kicker]");
        var botaoSubmeter = mapa.querySelector("[data-content-submit]");
        var urlEdicao = null;

        function podeAlterarEstrutura() {
            if (!alteracoes.size) return true;
            atualizarEstado("Guarda primeiro as prioridades pendentes.", "is-error");
            return false;
        }

        function fecharDialogo() {
            if (dialogo && dialogo.open) dialogo.close();
        }

        function prepararDialogoCriacao() {
            urlEdicao = null;
            estadoDialogo.textContent = "";
            formulario.reset();
            kickerDialogo.textContent = "Nova linha";
            tituloDialogo.textContent = "Acrescentar conteúdo";
            botaoSubmeter.textContent = "Acrescentar";
        }

        function prepararDialogoEdicao(botao) {
            urlEdicao = botao.dataset.editUrl;
            estadoDialogo.textContent = "";
            formulario.reset();
            formulario.elements.area.value = botao.dataset.contentArea || "";
            formulario.elements.subarea.value = botao.dataset.contentSubarea || "";
            formulario.elements.nome.value = botao.dataset.contentName || "";
            kickerDialogo.textContent = "Conteúdo existente";
            tituloDialogo.textContent = "Editar conteúdo";
            botaoSubmeter.textContent = "Guardar alterações";
        }

        if (botaoAdicionar && dialogo && formulario) {
            botaoAdicionar.addEventListener("click", function () {
                if (!podeAlterarEstrutura()) return;
                prepararDialogoCriacao();
                dialogo.showModal();
                window.setTimeout(function () { formulario.elements.area.focus(); }, 0);
            });
            mapa.querySelectorAll("[data-edit-content]").forEach(function (botao) {
                botao.addEventListener("click", function () {
                    if (!podeAlterarEstrutura()) return;
                    prepararDialogoEdicao(botao);
                    dialogo.showModal();
                    window.setTimeout(function () { formulario.elements.nome.focus(); }, 0);
                });
            });
            mapa.querySelectorAll("[data-content-cancel]").forEach(function (botao) {
                botao.addEventListener("click", fecharDialogo);
            });
            dialogo.addEventListener("click", function (event) {
                if (event.target === dialogo) fecharDialogo();
            });
            formulario.addEventListener("submit", async function (event) {
                event.preventDefault();
                var botao = formulario.querySelector('[type="submit"]');
                estadoDialogo.textContent = urlEdicao ? "A guardar..." : "A acrescentar...";
                botao.disabled = true;
                try {
                    var dadosFormulario = new FormData(formulario);
                    var resultado = await enviarJson(urlEdicao || mapa.dataset.createUrl, {
                        area: dadosFormulario.get("area"),
                        subarea: dadosFormulario.get("subarea"),
                        nome: dadosFormulario.get("nome")
                    });
                    window.sessionStorage.setItem(chaveMensagem, resultado.mensagem);
                    window.location.reload();
                } catch (erro) {
                    estadoDialogo.textContent = erro.message;
                    botao.disabled = false;
                }
            });
        }

        mapa.querySelectorAll("[data-delete-content]").forEach(function (botao) {
            botao.addEventListener("click", async function () {
                if (!podeAlterarEstrutura()) return;
                if (!window.confirm('Eliminar "' + botao.dataset.contentName + '" deste mapa?')) return;
                botao.disabled = true;
                atualizarEstado("A eliminar conteúdo...", "is-pending");
                try {
                    var resultado = await enviarJson(botao.dataset.deleteUrl, {});
                    window.sessionStorage.setItem(chaveMensagem, resultado.mensagem);
                    window.location.reload();
                } catch (erro) {
                    botao.disabled = false;
                    atualizarEstado(erro.message, "is-error");
                }
            });
        });

        var linhaArrastada = null;
        mapa.querySelectorAll("[data-content-row]").forEach(function (linha) {
            linha.addEventListener("dragstart", function (event) {
                if (!podeAlterarEstrutura()) {
                    event.preventDefault();
                    return;
                }
                linhaArrastada = linha;
                linha.classList.add("is-dragging");
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", linha.dataset.contentId);
            });
            linha.addEventListener("dragend", function () {
                linha.classList.remove("is-dragging");
                mapa.querySelectorAll(".is-drop-target").forEach(function (alvo) {
                    alvo.classList.remove("is-drop-target");
                });
                linhaArrastada = null;
            });
            linha.addEventListener("dragover", function (event) {
                if (!linhaArrastada || linhaArrastada === linha) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                linha.classList.add("is-drop-target");
            });
            linha.addEventListener("dragleave", function (event) {
                if (!linha.contains(event.relatedTarget)) linha.classList.remove("is-drop-target");
            });
            linha.addEventListener("drop", async function (event) {
                event.preventDefault();
                linha.classList.remove("is-drop-target");
                var origem = linhaArrastada;
                if (!origem || origem === linha || !podeAlterarEstrutura()) return;
                atualizarEstado("A mover conteúdo...", "is-pending");
                try {
                    var resultado = await enviarJson(origem.dataset.moveUrl, {
                        area: linha.dataset.contentArea,
                        subarea: linha.dataset.contentSubarea || ""
                    });
                    window.sessionStorage.setItem(chaveMensagem, resultado.mensagem);
                    window.location.reload();
                } catch (erro) {
                    atualizarEstado(erro.message, "is-error");
                }
            });
        });

        window.addEventListener("beforeunload", function (event) {
            if (!alteracoes.size) return;
            event.preventDefault();
            event.returnValue = "";
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-mapa-conteudos]").forEach(iniciarMapa);
    });
}());
