(function () {
  "use strict";
  var dialog = document.getElementById("pdf-configurador");
  if (!dialog) return;
  var destino = null;
  var grupoCalendario = dialog.querySelector('[data-pdf-grupo="calendario"]');
  var grupoJogos = dialog.querySelector('[data-pdf-grupo="jogos"]');
  var erro = dialog.querySelector("[data-pdf-erro]");

  function tipoDocumento(url) {
    var path = url.pathname.toLowerCase();
    if (/\/jogos\/equipas\/\d+\/pdf$/.test(path) || /\/equipas\/\d+\/jogos\/pdf$/.test(path)) return "jogos";
    if (path.indexOf("/treinos/pdf") >= 0) return "geral";
    if (path.indexOf("calendario") >= 0 || path.indexOf("/partilha/") >= 0) return "calendario";
    return "geral";
  }

  function abrir(link) {
    destino = new URL(link.href, window.location.href);
    var tipo = tipoDocumento(destino);
    grupoCalendario.hidden = tipo !== "calendario";
    grupoJogos.hidden = tipo !== "jogos";
    erro.hidden = true;
    dialog.showModal();
  }

  function fechar() {
    if (dialog.open) dialog.close();
    destino = null;
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest('a[href*="/pdf"]');
    if (!link || link.dataset.pdfDirect !== undefined || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    var url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin) return;
    event.preventDefault();
    abrir(link);
  });

  dialog.querySelectorAll("[data-pdf-fechar]").forEach(function (button) { button.addEventListener("click", fechar); });
  dialog.addEventListener("click", function (event) { if (event.target === dialog) fechar(); });
  dialog.addEventListener("cancel", function (event) { event.preventDefault(); fechar(); });
  function exportar() {
    if (!destino) return;
    var tipos = Array.from(dialog.querySelectorAll('input[name="pdf_tipo"]:checked')).map(function (item) { return item.value; });
    if (!grupoCalendario.hidden && !tipos.length) { erro.hidden = false; return; }
    if (!grupoJogos.hidden && !dialog.querySelector('input[name="pdf_casa"]').checked && !dialog.querySelector('input[name="pdf_fora"]').checked) { erro.hidden = false; return; }
    destino.searchParams.set("pdf_tipos", tipos.join(","));
    destino.searchParams.set("pdf_casa", dialog.querySelector('input[name="pdf_casa"]').checked ? "1" : "0");
    destino.searchParams.set("pdf_fora", dialog.querySelector('input[name="pdf_fora"]').checked ? "1" : "0");
    destino.searchParams.set("pdf_competicao", dialog.querySelector('input[name="pdf_competicao"]').value.trim());
    ["observacoes", "indicadores", "imagens"].forEach(function (nome) {
      destino.searchParams.set("pdf_" + nome, dialog.querySelector('input[name="pdf_' + nome + '"]').checked ? "1" : "0");
    });
    window.location.assign(destino.toString());
    fechar();
  }
  dialog.querySelector("[data-pdf-exportar]").addEventListener("click", exportar);
  dialog.querySelector("form").addEventListener("submit", function (event) { event.preventDefault(); exportar(); });
})();
