(function () {
    "use strict";

    function iniciarMapa(mapa) {
        var botaoGuardar = mapa.querySelector("[data-mapa-save]");
        var estado = mapa.querySelector("[data-mapa-save-status]");
        var alteracoes = new Map();
        var aGuardar = false;

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
                var resposta = await fetch(mapa.dataset.saveUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content
                    },
                    body: JSON.stringify({ alteracoes: Array.from(alteracoes.values()) })
                });
                var dados = await resposta.json();
                if (!resposta.ok || !dados.sucesso) throw new Error(dados.erro || "Não foi possível guardar as prioridades.");
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
