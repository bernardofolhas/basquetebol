(function () {
    "use strict";

    function iniciarMapa(mapa) {
        var botaoGuardar = mapa.querySelector("[data-mapa-save]");
        var estado = mapa.querySelector("[data-mapa-save-status]");
        var alteracoes = new Map();
        var aGuardar = false;
        var chaveMensagem = "mapa-conteudos:mensagem:" + window.location.pathname;
        var botaoEcraCompleto = mapa.querySelector("[data-mapa-fullscreen]");

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

        function atualizarBotaoEcraCompleto() {
            if (!botaoEcraCompleto) return;
            var emEcraCompleto = document.fullscreenElement === mapa;
            botaoEcraCompleto.textContent = emEcraCompleto ? "Sair do ecrã completo" : "Ecrã completo";
            botaoEcraCompleto.setAttribute("aria-pressed", String(emEcraCompleto));
        }

        if (botaoEcraCompleto) {
            if (!document.fullscreenEnabled) {
                botaoEcraCompleto.hidden = true;
            } else {
                botaoEcraCompleto.addEventListener("click", async function () {
                    try {
                        if (document.fullscreenElement === mapa) await document.exitFullscreen();
                        else await mapa.requestFullscreen();
                    } catch (erro) {
                        atualizarEstado("Não foi possível abrir o ecrã completo.", "is-error");
                    }
                });
                document.addEventListener("fullscreenchange", atualizarBotaoEcraCompleto);
                atualizarBotaoEcraCompleto();
            }
        }

        async function atualizarMapaSemRecarregar(mensagem) {
            var quadroAtual = mapa.querySelector(".mapa-conteudos-viewport");
            var scrollTop = quadroAtual ? quadroAtual.scrollTop : 0;
            var scrollLeft = quadroAtual ? quadroAtual.scrollLeft : 0;
            var resposta = await fetch(window.location.href, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                cache: "no-store"
            });
            if (!resposta.ok) throw new Error("Não foi possível atualizar o mapa de conteúdos.");
            var paginaAtualizada = new DOMParser().parseFromString(await resposta.text(), "text/html");
            var mapaAtualizado = paginaAtualizada.querySelector("[data-mapa-conteudos]");
            if (!mapaAtualizado) throw new Error("Não foi possível atualizar o mapa de conteúdos.");

            mapa.replaceWith(mapaAtualizado);
            var quadroAtualizado = mapaAtualizado.querySelector(".mapa-conteudos-viewport");
            if (quadroAtualizado) {
                quadroAtualizado.scrollTop = scrollTop;
                quadroAtualizado.scrollLeft = scrollLeft;
            }
            iniciarMapa(mapaAtualizado);
            var estadoAtualizado = mapaAtualizado.querySelector("[data-mapa-save-status]");
            if (estadoAtualizado && mensagem) {
                estadoAtualizado.textContent = mensagem;
                estadoAtualizado.className = "mapa-save-status is-success";
            }
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

        function registarCelulaPrioridade(celula) {
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
        }
        mapa.querySelectorAll("[data-priority-cell]").forEach(registarCelulaPrioridade);

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
            if (!dialogo || !dialogo.open) return;
            if (typeof dialogo.close === "function") dialogo.close();
            else dialogo.removeAttribute("open");
        }

        function abrirDialogo() {
            if (!dialogo) return;
            if (typeof dialogo.showModal === "function") dialogo.showModal();
            else dialogo.setAttribute("open", "");
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

        function criarCabecalhoGrupo(classe, texto, area, subarea) {
            var cabecalho = document.createElement("th");
            cabecalho.className = "mapa-sticky " + classe;
            cabecalho.rowSpan = 1;
            cabecalho.textContent = texto;
            cabecalho.dataset.contentDropzone = "";
            cabecalho.dataset.targetArea = area;
            cabecalho.dataset.targetSubarea = subarea;
            return cabecalho;
        }

        function inserirConteudoNoMapa(resultado, dados) {
            var area = String(dados.area || "");
            var subarea = String(dados.subarea || "");
            var linhas = Array.from(mapa.querySelectorAll("[data-content-row]"));
            var linhasArea = linhas.filter(function (linha) { return linha.dataset.contentArea === area; });
            var linhasGrupo = linhasArea.filter(function (linha) {
                return (linha.dataset.contentSubarea || "") === subarea;
            });
            var referencia = linhasGrupo[linhasGrupo.length - 1]
                || linhasArea[linhasArea.length - 1]
                || linhas[linhas.length - 1];
            if (!referencia) throw new Error("Não foi possível apresentar o conteúdo acrescentado.");

            var linha = referencia.cloneNode(true);
            linha.querySelectorAll(".mapa-area-cell, .mapa-subarea-cell").forEach(function (cabecalho) {
                cabecalho.remove();
            });
            linha.dataset.contentId = resultado.conteudo_id;
            linha.dataset.contentArea = area;
            linha.dataset.contentSubarea = subarea;
            linha.dataset.moveUrl = mapa.dataset.createUrl + "/" + resultado.conteudo_id + "/mover";

            var celulaConteudo = linha.querySelector(".mapa-content-cell");
            if (!celulaConteudo) throw new Error("Não foi possível apresentar o conteúdo acrescentado.");
            celulaConteudo.dataset.targetArea = area;
            celulaConteudo.dataset.targetSubarea = subarea;
            var nome = String(dados.nome || "");
            celulaConteudo.querySelector(".mapa-content-name").textContent = nome;
            var pega = celulaConteudo.querySelector(".mapa-drag-handle");
            pega.title = "Arrastar linha para outro grupo";
            pega.setAttribute("aria-label", "Arrastar " + nome);
            var editar = celulaConteudo.querySelector("[data-edit-content]");
            editar.dataset.contentId = resultado.conteudo_id;
            editar.dataset.contentName = nome;
            editar.dataset.contentArea = area;
            editar.dataset.contentSubarea = subarea;
            editar.dataset.editUrl = mapa.dataset.createUrl + "/" + resultado.conteudo_id + "/editar";
            editar.setAttribute("aria-label", "Editar " + nome);
            var eliminar = celulaConteudo.querySelector("[data-delete-content]");
            eliminar.dataset.contentName = nome;
            eliminar.dataset.deleteUrl = mapa.dataset.createUrl + "/" + resultado.conteudo_id + "/eliminar";
            eliminar.setAttribute("aria-label", "Eliminar " + nome);
            linha.querySelectorAll("[data-priority-cell]").forEach(function (celula) {
                celula.dataset.contentId = resultado.conteudo_id;
                celula.dataset.value = "";
                celula.dataset.original = "";
                celula.textContent = "";
                celula.classList.remove("priority-1", "priority-2", "is-pending");
                celula.setAttribute("aria-label", nome + ", semana " + celula.dataset.week + ": sem prioridade");
            });

            if (linhasArea.length) {
                var cabecalhoAreaExistente = linhasArea.map(function (item) {
                    return item.querySelector(".mapa-area-cell");
                }).find(Boolean);
                if (cabecalhoAreaExistente) cabecalhoAreaExistente.rowSpan += 1;
            } else {
                celulaConteudo.insertAdjacentElement("beforebegin", criarCabecalhoGrupo("mapa-area-cell", area, area, ""));
            }
            if (linhasGrupo.length) {
                var cabecalhoSubareaExistente = linhasGrupo[0].querySelector(".mapa-subarea-cell");
                if (cabecalhoSubareaExistente) cabecalhoSubareaExistente.rowSpan += 1;
            } else {
                celulaConteudo.insertAdjacentElement("beforebegin", criarCabecalhoGrupo(
                    "mapa-subarea-cell", subarea || "Conteúdos", area, subarea
                ));
            }
            referencia.insertAdjacentElement("afterend", linha);

            linha.querySelectorAll("[data-priority-cell]").forEach(registarCelulaPrioridade);
            registarBotaoEliminacao(eliminar);
            registarPegaArrasto(pega);
            registarAlvoDeArrasto(celulaConteudo);
        }

        if (botaoAdicionar && dialogo && formulario) {
            botaoAdicionar.addEventListener("click", function () {
                if (!podeAlterarEstrutura()) return;
                prepararDialogoCriacao();
                abrirDialogo();
                window.setTimeout(function () { formulario.elements.area.focus(); }, 0);
            });
            mapa.addEventListener("click", function (event) {
                var botao = event.target.closest && event.target.closest("[data-edit-content]");
                if (!botao || !mapa.contains(botao)) return;
                event.preventDefault();
                event.stopPropagation();
                if (!podeAlterarEstrutura()) return;
                prepararDialogoEdicao(botao);
                abrirDialogo();
                window.setTimeout(function () { formulario.elements.nome.focus(); }, 0);
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
                    if (urlEdicao) {
                        fecharDialogo();
                        await atualizarMapaSemRecarregar(resultado.mensagem);
                        return;
                    }
                    inserirConteudoNoMapa(resultado, {
                        area: dadosFormulario.get("area"),
                        subarea: dadosFormulario.get("subarea"),
                        nome: dadosFormulario.get("nome")
                    });
                    fecharDialogo();
                    atualizarEstado(resultado.mensagem, "is-success");
                } catch (erro) {
                    estadoDialogo.textContent = erro.message;
                    botao.disabled = false;
                }
            });
        }

        function registarBotaoEliminacao(botao) {
            botao.addEventListener("click", async function () {
                if (!podeAlterarEstrutura()) return;
                if (!window.confirm('Eliminar "' + botao.dataset.contentName + '" deste mapa?')) return;
                botao.disabled = true;
                atualizarEstado("A eliminar conteúdo...", "is-pending");
                try {
                    var resultado = await enviarJson(botao.dataset.deleteUrl, {});
                    await atualizarMapaSemRecarregar(resultado.mensagem);
                } catch (erro) {
                    botao.disabled = false;
                    atualizarEstado(erro.message, "is-error");
                }
            });
        }
        mapa.querySelectorAll("[data-delete-content]").forEach(registarBotaoEliminacao);

        var linhaArrastada = null;
        function registarPegaArrasto(pega) {
            pega.addEventListener("dragstart", function (event) {
                if (!podeAlterarEstrutura()) {
                    event.preventDefault();
                    return;
                }
                var linha = pega.closest("[data-content-row]");
                if (!linha) return;
                linhaArrastada = linha;
                linha.classList.add("is-dragging");
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", linha.dataset.contentId);
            });
            pega.addEventListener("dragend", function () {
                var linha = pega.closest("[data-content-row]");
                if (linha) linha.classList.remove("is-dragging");
                mapa.querySelectorAll(".is-drop-target").forEach(function (alvo) {
                    alvo.classList.remove("is-drop-target");
                });
                linhaArrastada = null;
            });
        }
        mapa.querySelectorAll(".mapa-drag-handle").forEach(registarPegaArrasto);

        function registarAlvoDeArrasto(alvo) {
            alvo.addEventListener("dragover", function (event) {
                if (!linhaArrastada || alvo.closest("[data-content-row]") === linhaArrastada) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                alvo.classList.add("is-drop-target");
            });
            alvo.addEventListener("dragleave", function (event) {
                if (!alvo.contains(event.relatedTarget)) alvo.classList.remove("is-drop-target");
            });
            alvo.addEventListener("drop", async function (event) {
                event.preventDefault();
                event.stopPropagation();
                alvo.classList.remove("is-drop-target");
                var origem = linhaArrastada;
                var destino = alvo.dataset.targetArea ? alvo : alvo.closest("[data-content-row]");
                if (!origem || !destino || origem === destino || !podeAlterarEstrutura()) return;
                atualizarEstado("A mover conteúdo...", "is-pending");
                try {
                    var resultado = await enviarJson(origem.dataset.moveUrl, {
                        area: destino.dataset.targetArea || destino.dataset.contentArea,
                        subarea: destino.dataset.targetSubarea || destino.dataset.contentSubarea || "",
                        antes_de_conteudo_id: destino.closest("[data-content-row]")
                            ? Number(destino.closest("[data-content-row]").dataset.contentId)
                            : null
                    });
                    await atualizarMapaSemRecarregar(resultado.mensagem);
                } catch (erro) {
                    atualizarEstado(erro.message, "is-error");
                }
            });
        }
        mapa.querySelectorAll("[data-content-dropzone], [data-content-row]").forEach(registarAlvoDeArrasto);

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
