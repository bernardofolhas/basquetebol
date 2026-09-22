(function () {
  "use strict";

  function meaningfulFields(root) {
    return Array.from(root.querySelectorAll("input, select, textarea")).filter(function (field) {
      return !field.disabled && !field.closest("[data-dashboard-customizer-anchor]") && !["hidden", "submit", "button", "file"].includes(field.type);
    });
  }

  function isFilled(field) {
    if (field.type === "checkbox" || field.type === "radio") return field.checked;
    return String(field.value || "").trim() !== "";
  }

  function sectionLabel(section, index) {
    var heading = section.querySelector("h1, h2, h3");
    return heading ? heading.textContent.trim() : "Bloco " + (index + 1);
  }

  function initTextarea(textarea) {
    var resize = function () {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(Math.max(textarea.scrollHeight, 92), 320) + "px";
    };
    textarea.addEventListener("input", resize);
    resize();

    if (textarea.closest(".studio-field-shell")) return;
    var shell = document.createElement("div");
    shell.className = "studio-field-shell";
    textarea.parentNode.insertBefore(shell, textarea);
    shell.appendChild(textarea);
    var count = document.createElement("small");
    count.className = "studio-char-count";
    shell.appendChild(count);
    var updateCount = function () {
      var length = textarea.value.trim().length;
      count.textContent = length ? length + " caracteres" : "Pronto para preencher";
    };
    textarea.addEventListener("input", updateCount);
    updateCount();
  }

  function init() {
    var tabs = document.querySelector(".scouting-tabs");
    if (!tabs && !document.querySelector(".scouting-hero")) return;
    document.body.classList.add("scouting-studio-mode");
    if (!tabs) return;
    var root = document.querySelector("[data-customizable-dashboard]") || tabs.parentElement;
    var sections = Array.from(root.querySelectorAll(".scouting-section, .scouting-plan-card, .scouting-roster-group, .scouting-plan-lineups"));
    var forms = Array.from(root.querySelectorAll("form")).filter(function (form) {
      return meaningfulFields(form).length > 0 && !form.classList.contains("scouting-delete-form");
    });

    sections.forEach(function (section, index) {
      section.classList.add("studio-work-block");
      section.dataset.studioIndex = String(index + 1).padStart(2, "0");
      section.dataset.studioLabel = sectionLabel(section, index);
    });
    forms.forEach(function (form) { form.classList.add("studio-guided-form"); });
    root.querySelectorAll("textarea").forEach(initTextarea);
    if (!sections.length) return;

    var strip = document.createElement("section");
    strip.className = "studio-progress-strip";
    strip.innerHTML = '<div class="studio-progress-copy"><span>SCOUTING STUDIO</span><strong>Construção do dossier</strong><small data-studio-status>Leitura dos campos...</small></div><div class="studio-progress-meter"><i data-studio-bar></i></div><div class="studio-progress-actions"><button type="button" data-studio-next>Próximo por preencher</button><button type="button" data-studio-toggle>Expandir editores</button></div>';
    tabs.insertAdjacentElement("afterend", strip);

    var bar = strip.querySelector("[data-studio-bar]");
    var status = strip.querySelector("[data-studio-status]");
    var nextButton = strip.querySelector("[data-studio-next]");
    var toggleButton = strip.querySelector("[data-studio-toggle]");

    function update() {
      forms.forEach(function (form) {
        var ownFields = meaningfulFields(form);
        var ownFilled = ownFields.filter(isFilled).length;
        form.dataset.studioState = ownFilled === 0 ? "empty" : (ownFilled === ownFields.length ? "complete" : "started");
      });
      var started = forms.filter(function (form) { return form.dataset.studioState !== "empty"; }).length;
      var percent = forms.length ? Math.round((started / forms.length) * 100) : 100;
      bar.style.width = percent + "%";
      status.textContent = forms.length ? started + " de " + forms.length + " blocos com informação" : "Dossier pronto";
      sections.forEach(function (section) {
        var sectionFields = meaningfulFields(section);
        var sectionFilled = sectionFields.filter(isFilled).length;
        section.dataset.studioState = !sectionFields.length || sectionFilled === sectionFields.length ? "complete" : (sectionFilled ? "started" : "empty");
      });
    }

    root.addEventListener("input", update);
    root.addEventListener("change", update);
    nextButton.addEventListener("click", function () {
      var target = forms.find(function (form) { return form.dataset.studioState !== "complete" && form.offsetParent !== null; });
      if (!target) target = sections.find(function (section) { return section.dataset.studioState !== "complete"; });
      if (!target) return;
      var details = target.closest("details");
      if (details) details.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      var field = meaningfulFields(target).find(function (item) { return !isFilled(item); });
      if (field) window.setTimeout(function () { field.focus({ preventScroll: true }); }, 350);
    });

    toggleButton.addEventListener("click", function () {
      var editors = Array.from(root.querySelectorAll("details.scouting-editor"));
      if (!editors.length) return;
      var shouldOpen = editors.some(function (item) { return !item.open; });
      editors.forEach(function (item) { item.open = shouldOpen; });
      toggleButton.textContent = shouldOpen ? "Recolher editores" : "Expandir editores";
    });

    root.querySelectorAll("dialog").forEach(function (dialog) {
      dialog.addEventListener("toggle", function () {
        if (!dialog.open) return;
        var field = meaningfulFields(dialog).find(function (item) { return !isFilled(item); });
        if (field) window.setTimeout(function () { field.focus(); }, 80);
      });
    });

    update();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
