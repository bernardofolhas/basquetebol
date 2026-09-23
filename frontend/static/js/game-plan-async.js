(function () {
  "use strict";

  var root = document.querySelector("[data-game-plan-root]");
  if (!root) return;

  function notify(message, isError) {
    var notice = document.querySelector(".studio-async-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "studio-async-notice";
      notice.setAttribute("role", "status");
      notice.setAttribute("aria-live", "polite");
      document.body.appendChild(notice);
    }
    notice.classList.toggle("is-error", Boolean(isError));
    notice.textContent = message;
    notice.classList.add("is-visible");
    window.clearTimeout(notice._hideTimer);
    notice._hideTimer = window.setTimeout(function () {
      notice.classList.remove("is-visible");
    }, 3200);
  }

  root.addEventListener("submit", async function (event) {
    var form = event.target.closest("form[data-game-plan-async]");
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    if (form.dataset.busy === "true") return;

    form.dataset.busy = "true";
    form.setAttribute("aria-busy", "true");
    var submitter = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
    var originalText = submitter ? submitter.textContent : "";
    if (submitter) {
      submitter.disabled = true;
      submitter.textContent = "A guardar...";
    }

    var region = root.querySelector('[data-plan-region="game-plan"]');
    var detailsState = Array.from(region.querySelectorAll("details")).map(function (item) {
      return item.open;
    });
    var scrollTop = window.scrollY;

    try {
      var body = new FormData(form);
      if (submitter && submitter.name && !body.has(submitter.name)) body.append(submitter.name, submitter.value);
      var response = await fetch(form.action, {
        method: (form.method || "POST").toUpperCase(),
        body: body,
        credentials: "same-origin",
        headers: {
          "Accept": "text/html",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || ""
        }
      });
      if (!response.ok) throw new Error("Não foi possível guardar a alteração.");

      var parsed = new DOMParser().parseFromString(await response.text(), "text/html");
      var incoming = parsed.querySelector('[data-plan-region="game-plan"]');
      var flash = parsed.querySelector("#flash-msg");
      if (flash && flash.classList.contains("ds-flash-error")) {
        throw new Error(flash.textContent.replace("×", "").trim());
      }
      if (!incoming) throw new Error("Não foi possível atualizar o plano de jogo.");

      region.innerHTML = incoming.innerHTML;
      Array.from(region.querySelectorAll("details")).forEach(function (item, index) {
        if (index < detailsState.length) item.open = detailsState[index];
      });
      notify(flash ? flash.textContent.replace("×", "").trim() : "Alteração guardada.", false);
      window.requestAnimationFrame(function () {
        window.scrollTo({ top: scrollTop, behavior: "auto" });
      });
    } catch (error) {
      notify(error.message || "Não foi possível concluir a operação.", true);
    } finally {
      form.dataset.busy = "false";
      form.removeAttribute("aria-busy");
      if (submitter && submitter.isConnected) {
        submitter.disabled = false;
        submitter.textContent = originalText;
      }
    }
  });
})();
