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
    if (textarea.dataset.studioTextarea === "true") return;
    textarea.dataset.studioTextarea = "true";
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

  function studioRegions(container, key) {
    return Array.from(container.querySelectorAll("[data-studio-region]")).filter(function (region) {
      return region.dataset.studioRegion === key;
    });
  }

  function notify(message, type) {
    var notice = document.querySelector(".studio-async-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "studio-async-notice";
      notice.setAttribute("role", "status");
      notice.setAttribute("aria-live", "polite");
      document.body.appendChild(notice);
    }
    notice.classList.toggle("is-error", type === "error");
    notice.textContent = message;
    notice.classList.add("is-visible");
    window.clearTimeout(notice._studioTimer);
    notice._studioTimer = window.setTimeout(function () { notice.classList.remove("is-visible"); }, 3200);
  }

  function init() {
    var tabs = document.querySelector(".scouting-tabs");
    if (!tabs && !document.querySelector(".scouting-hero")) return;
    document.body.classList.add("scouting-studio-mode");
    if (!tabs) return;
    var root = document.querySelector("[data-scouting-studio-root], [data-customizable-dashboard]") || tabs.parentElement;

    function enhance(scope) {
      var sections = Array.from(root.querySelectorAll(".scouting-section, .scouting-plan-card, .scouting-plan-lineups"));
      sections.forEach(function (section, index) {
        section.classList.add("studio-work-block");
        section.dataset.studioIndex = String(index + 1).padStart(2, "0");
        section.dataset.studioLabel = sectionLabel(section, index);
      });
      Array.from((scope || root).querySelectorAll("form")).forEach(function (form) {
        if (meaningfulFields(form).length && !form.classList.contains("scouting-delete-form")) form.classList.add("studio-guided-form");
      });
      Array.from((scope || root).querySelectorAll("textarea")).forEach(initTextarea);
      Array.from((scope || root).querySelectorAll("dialog")).forEach(function (dialog) {
        if (dialog.dataset.studioDialog === "true") return;
        dialog.dataset.studioDialog = "true";
        dialog.addEventListener("toggle", function () {
          if (!dialog.open) return;
          var field = meaningfulFields(dialog).find(function (item) { return !isFilled(item); });
          if (field) window.setTimeout(function () { field.focus(); }, 80);
        });
      });
    }

    enhance(root);
    var sections = Array.from(root.querySelectorAll(".studio-work-block"));
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
      var forms = Array.from(root.querySelectorAll("form")).filter(function (form) {
        return meaningfulFields(form).length > 0 && !form.classList.contains("scouting-delete-form");
      });
      forms.forEach(function (form) {
        var ownFields = meaningfulFields(form);
        var ownFilled = ownFields.filter(isFilled).length;
        form.dataset.studioState = ownFilled === 0 ? "empty" : (ownFilled === ownFields.length ? "complete" : "started");
      });
      var started = forms.filter(function (form) { return form.dataset.studioState !== "empty"; }).length;
      var percent = forms.length ? Math.round((started / forms.length) * 100) : 100;
      bar.style.width = percent + "%";
      status.textContent = forms.length ? started + " de " + forms.length + " blocos com informação" : "Dossier pronto";
      Array.from(root.querySelectorAll(".studio-work-block")).forEach(function (section) {
        var sectionFields = meaningfulFields(section);
        var sectionFilled = sectionFields.filter(isFilled).length;
        section.dataset.studioState = !sectionFields.length || sectionFilled === sectionFields.length ? "complete" : (sectionFilled ? "started" : "empty");
      });
    }

    function highlightInputs() {
      return Array.from(root.querySelectorAll('[data-studio-region="individual-profile"] form[action*="/itens-associados/"] .scout-highlight-toggle input[name="destaque"]'));
    }

    function syncHighlightAll() {
      var master = root.querySelector("[data-scout-highlight-all]");
      if (!master) return;
      var inputs = highlightInputs();
      var selected = inputs.filter(function (input) { return input.checked; }).length;
      master.checked = inputs.length > 0 && selected === inputs.length;
      master.indeterminate = selected > 0 && selected < inputs.length;
    }

    async function postHighlight(url, checked) {
      var body = new FormData();
      body.append("destaque", checked ? "true" : "false");
      var response = await fetch(url, {
        method: "POST", body: body, credentials: "same-origin",
        headers: {"Accept": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || ""}
      });
      if (!response.ok || !(response.headers.get("content-type") || "").includes("application/json")) {
        throw new Error("Não foi possível guardar a seleção.");
      }
      var result = await response.json();
      if (!result.ok) throw new Error(result.erro || "Não foi possível guardar a seleção.");
    }

    syncHighlightAll();
    root.addEventListener("change", async function (event) {
      var toggle = event.target.closest('[data-scout-highlight-all], .scout-highlight-toggle input[name="destaque"]');
      if (!toggle || !toggle.closest('[data-studio-region="individual-profile"]')) return;
      var master = toggle.matches("[data-scout-highlight-all]");
      var form = toggle.closest("form");
      if (!master && (!form || !/\/itens-associados\/\d+\/guardar$/.test(form.action))) return;
      var inputs = highlightInputs();
      var previous = inputs.map(function (input) { return input.checked; });
      if (master) inputs.forEach(function (input) { input.checked = toggle.checked; });
      else syncHighlightAll();
      var url = master ? toggle.dataset.highlightUrl : form.action.replace(/\/guardar$/, "/destaque");
      var saving = master ? [toggle].concat(inputs) : [toggle];
      saving.forEach(function (input) { input.disabled = true; });
      try {
        await postHighlight(url, toggle.checked);
        notify(master ? "Visibilidade de todos os itens guardada." : "Visibilidade no cartão guardada.", "success");
      } catch (error) {
        if (master) inputs.forEach(function (input, index) { input.checked = previous[index]; });
        else toggle.checked = !toggle.checked;
        notify(error.message || "Não foi possível guardar a seleção.", "error");
      } finally {
        saving.forEach(function (input) { if (input.isConnected) input.disabled = false; });
        syncHighlightAll();
        update();
      }
    });

    root.addEventListener("input", update);
    root.addEventListener("change", function (event) {
      var picker = event.target.closest("[data-stat-game-picker]");
      if (picker) root.querySelectorAll("[data-stat-game]").forEach(function (row) { row.hidden = row.dataset.statGame !== picker.value; });
      var toggle = event.target.closest("[data-defense-toggle]");
      if (toggle) {
        var notes = root.querySelector('[data-defense-notes="' + toggle.dataset.defenseToggle + '"]');
        if (notes) notes.hidden = !toggle.checked;
      }
      update();
    });
    root.addEventListener("click", function (event) {
      var opener = event.target.closest("[data-open-library]");
      if (!opener) return;
      var dialog = root.querySelector('[data-library-dialog="' + opener.dataset.openLibrary + '"]');
      if (dialog && !dialog.open) dialog.showModal();
    });
    root.addEventListener("input", function (event) {
      var search = event.target.closest("[data-library-search]");
      if (!search) return;
      var dialog = search.closest("[data-library-dialog]");
      var select = dialog && dialog.querySelector("[data-library-options]");
      if (!select) return;
      var term = search.value.trim().toLowerCase();
      Array.from(select.options).forEach(function (option, index) {
        if (index) option.hidden = Boolean(term && !option.text.toLowerCase().includes(term));
      });
    });

    root.addEventListener("submit", async function (event) {
      var form = event.target.closest("form[data-studio-async]");
      if (!form || event.defaultPrevented) return;
      event.preventDefault();
      if (form.dataset.studioBusy === "true") return;
      form.dataset.studioBusy = "true";
      form.setAttribute("aria-busy", "true");
      var submitter = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
      var originalText = submitter ? submitter.textContent : "";
      if (submitter) {
        submitter.disabled = true;
        if (!submitter.classList.contains("scouting-icon-danger")) submitter.textContent = "A guardar...";
      }
      var scrollRoot = document.scrollingElement || document.documentElement;
      var scrollTop = scrollRoot.scrollTop;
      var detailsState = {};
      var refreshKeys = (form.dataset.studioRefresh || "").split(/\s+/).filter(Boolean);
      refreshKeys.forEach(function (key) {
        studioRegions(root, key).forEach(function (region, regionIndex) {
          detailsState[key + ":" + regionIndex] = Array.from(region.querySelectorAll("details")).map(function (item) { return item.open; });
        });
      });
      try {
        var body = new FormData(form);
        if (submitter && submitter.name && !body.has(submitter.name)) body.append(submitter.name, submitter.value);
        var actionOverride = submitter ? submitter.getAttribute("formaction") : null;
        var methodOverride = submitter ? submitter.getAttribute("formmethod") : null;
        var action = actionOverride || form.action;
        var method = methodOverride || form.method;
        var response = await fetch(action, {
          method: (method || "POST").toUpperCase(), body: body, credentials: "same-origin",
          headers: {"Accept": "text/html", "X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || ""}
        });
        if (!response.ok) throw new Error("Não foi possível concluir a operação.");
        var parsed = new DOMParser().parseFromString(await response.text(), "text/html");
        var parsedRoot = parsed.querySelector("[data-scouting-studio-root], [data-customizable-dashboard]");
        var flash = parsed.querySelector("#flash-msg");
        if (!parsedRoot) throw new Error("A sessão deixou de ser válida. Atualiza a página e volta a tentar.");
        if (flash && flash.classList.contains("ds-flash-error")) throw new Error(flash.textContent.replace("×", "").trim());
        if (!refreshKeys.length) throw new Error("Esta ação ainda não suporta atualização local.");
        var previousOverflowAnchor = scrollRoot.style.overflowAnchor;
        scrollRoot.style.overflowAnchor = "none";
        refreshKeys.forEach(function (key) {
          var currentRegions = studioRegions(root, key);
          var incomingRegions = studioRegions(parsedRoot, key);
          if (!currentRegions.length || currentRegions.length !== incomingRegions.length) throw new Error("Não foi possível atualizar este bloco.");
          currentRegions.forEach(function (current, index) {
            current.innerHTML = incomingRegions[index].innerHTML;
            var states = detailsState[key + ":" + index] || [];
            Array.from(current.querySelectorAll("details")).forEach(function (item, detailIndex) { item.open = Boolean(states[detailIndex]); });
            enhance(current);
          });
        });
        syncHighlightAll();
        var dialog = form.closest("dialog");
        if (form.dataset.studioReset === "true" && form.isConnected) form.reset();
        if (form.dataset.studioClose === "true" && dialog && dialog.isConnected && dialog.open) dialog.close();
        notify(flash ? flash.textContent.replace("×", "").trim() : "Alteração guardada.", "success");
        update();
        scrollRoot.scrollTop = scrollTop;
        window.requestAnimationFrame(function () {
          scrollRoot.scrollTop = scrollTop;
          window.requestAnimationFrame(function () { scrollRoot.style.overflowAnchor = previousOverflowAnchor; });
        });
      } catch (error) {
        scrollRoot.style.overflowAnchor = previousOverflowAnchor || "";
        notify(error.message || "Não foi possível concluir a operação.", "error");
      } finally {
        form.dataset.studioBusy = "false";
        form.removeAttribute("aria-busy");
        if (submitter && submitter.isConnected) { submitter.disabled = false; submitter.textContent = originalText; }
      }
    });

    nextButton.addEventListener("click", function () {
      var target = Array.from(root.querySelectorAll("form")).find(function (form) { return form.dataset.studioState !== "complete" && form.offsetParent !== null; });
      if (!target) target = Array.from(root.querySelectorAll(".studio-work-block")).find(function (section) { return section.dataset.studioState !== "complete"; });
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

    update();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
