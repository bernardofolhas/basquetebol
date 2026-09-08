(function () {
  "use strict";

  const root = document.querySelector("[data-playbook-studio]");
  if (!root) return;

  const COURTS = {
    meio: { width: 702, height: 622, src: "/static/campos/campo_meio.png?v=20260908-madeira-1" },
    completo: { width: 697, height: 1222, src: "/static/campos/campo_completo.png?v=20260908-madeira-1" },
  };
  const imported = root.dataset.imported === "true";
  const setplayId = Number(root.dataset.setplayId);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const canvas = document.querySelector("#pbs-board");
  const ctx = canvas?.getContext("2d");
  const previewCanvas = document.querySelector("[data-preview-canvas]");
  const previewCtx = previewCanvas?.getContext("2d");
  const scenesList = document.querySelector("[data-scenes-list]");
  const notes = document.querySelector("[data-scene-notes]");
  const saveState = document.querySelector("[data-save-state]");
  const data = JSON.parse(document.querySelector("#pbs-studio-data")?.textContent || "{}");
  const movementTypes = new Set(["seta", "seta_tracejada", "seta_zigzag", "seta_curva", "bloqueio", "linha"]);
  const markerTypes = new Set(["jogador_ataque", "jogador_defesa", "bola", "cone", "coach"]);

  let scenes = (data.passos || []).map(normalizeScene).sort((a, b) => a.ordem - b.ordem);
  let activeId = scenes[0]?.id || null;
  let tool = "selecionar";
  let selectedId = null;
  let gesture = null;
  let saveTimer = null;
  let notesTimer = null;
  let draggedSceneId = null;
  let previewFrame = 0;
  let previewStarted = 0;
  let previewPlaying = false;
  let pencilTap = { time: 0, x: 0, y: 0 };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function uid() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function normalizeScene(raw) {
    const saved = raw.estado && typeof raw.estado === "object" ? raw.estado : {};
    const savedWidth = Number(saved.largura) || 0;
    const savedHeight = Number(saved.altura) || 0;
    const courtType = ["meio", "completo"].includes(saved.campoTipo)
      ? saved.campoTipo
      : (savedWidth && savedHeight && savedHeight > savedWidth ? "completo" : "meio");
    const court = COURTS[courtType];
    const sx = court.width / Math.max(1, savedWidth || court.width);
    const sy = court.height / Math.max(1, savedHeight || court.height);
    const objects = Array.isArray(saved.objectos) ? saved.objectos.map((item) => {
      const object = clone(item);
      object.id = object.id || uid();
      if (Number.isFinite(Number(object.x))) object.x = Number(object.x) * sx;
      if (Number.isFinite(Number(object.y))) object.y = Number(object.y) * sy;
      if (Array.isArray(object.pontos)) {
        object.pontos = object.pontos.map((p) => ({ x: Number(p.x) * sx, y: Number(p.y) * sy }));
      }
      if (window.TacticalLegacy?.eRecorte(object)) {
        object.largura = Number(object.largura || 1) * sx;
        object.altura = Number(object.altura || 1) * sy;
      }
      return object;
    }) : [];
    return {
      id: Number(raw.id),
      ordem: Number(raw.ordem) || 0,
      observacao: raw.observacao || "",
      desenho: raw.desenho || null,
      imagemCoach: raw.imagemCoach || null,
      courtType,
      objects,
      undo: [],
      redo: [],
      converted: Boolean(saved.objectos),
    };
  }

  function activeScene() {
    return scenes.find((scene) => scene.id === activeId) || null;
  }

  function dimensions(scene = activeScene()) {
    return COURTS[scene?.courtType] || COURTS.meio;
  }

  function fitStageCourt(wrap, court) {
    const stage = document.querySelector("[data-stage]");
    if (!stage || !wrap) return;
    const style = window.getComputedStyle(stage);
    const horizontalPadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const verticalPadding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const availableWidth = Math.max(1, stage.clientWidth - horizontalPadding);
    const availableHeight = Math.max(1, stage.clientHeight - verticalPadding);
    const scale = Math.min(availableWidth / court.width, availableHeight / court.height);
    wrap.style.width = `${Math.floor(court.width * scale)}px`;
    wrap.style.height = `${Math.floor(court.height * scale)}px`;
  }

  function setStatus(label, state = "") {
    if (!saveState) return;
    saveState.classList.toggle("is-saving", state === "saving");
    saveState.classList.toggle("is-error", state === "error");
    saveState.lastChild.textContent = label;
  }

  function toast(message) {
    const el = document.querySelector("[data-toast]");
    if (!el) return;
    el.textContent = message;
    el.classList.add("is-visible");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("is-visible"), 2200);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": csrf,
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.sucesso === false) throw new Error(payload.erro || "Não foi possível guardar.");
    return payload;
  }

  function snapshot(scene) {
    scene.undo.push(clone(scene.objects));
    if (scene.undo.length > 40) scene.undo.shift();
    scene.redo = [];
  }

  function pointFromEvent(event) {
    const rect = canvas.getBoundingClientRect();
    const court = dimensions();
    return {
      x: Math.max(0, Math.min(court.width, (event.clientX - rect.left) * court.width / rect.width)),
      y: Math.max(0, Math.min(court.height, (event.clientY - rect.top) * court.height / rect.height)),
    };
  }

  function distanceToSegment(point, a, b) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = dx * dx + dy * dy;
    if (!length) return Math.hypot(point.x - a.x, point.y - a.y);
    const t = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length));
    return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
  }

  function hitObject(object, point, margin = 0) {
    if (markerTypes.has(object.tipo)) return Math.hypot(point.x - object.x, point.y - object.y) <= 30 + margin;
    if (window.TacticalLegacy?.eRecorte(object)) return window.TacticalLegacy.contemPonto(object, point);
    const points = object.pontos || [];
    for (let i = 1; i < points.length; i += 1) {
      if (distanceToSegment(point, points[i - 1], points[i]) <= Math.max(14, Number(object.largura) || 5) + margin) return true;
    }
    return false;
  }

  function objectAt(point) {
    const objects = activeScene()?.objects || [];
    for (let i = objects.length - 1; i >= 0; i -= 1) if (hitObject(objects[i], point)) return objects[i];
    return null;
  }

  function drawMarker(target, object, alpha = 1) {
    const size = 26 * (Number(object.tamanho) || 1);
    target.save();
    target.globalAlpha = alpha;
    if (object.tipo === "jogador_ataque") {
      target.beginPath(); target.arc(object.x, object.y, size, 0, Math.PI * 2);
      target.fillStyle = "#ef5b2a"; target.fill(); target.strokeStyle = "#a92f10"; target.lineWidth = 4; target.stroke();
      target.fillStyle = "#fff"; target.font = `700 ${Math.round(size * .78)}px DM Sans`; target.textAlign = "center"; target.textBaseline = "middle";
      target.fillText(object.numero ?? "", object.x, object.y + 1);
    } else if (object.tipo === "jogador_defesa") {
      target.beginPath(); target.moveTo(object.x, object.y - size * 1.15); target.lineTo(object.x + size, object.y + size * .78); target.lineTo(object.x - size, object.y + size * .78); target.closePath();
      target.fillStyle = "#2e65cd"; target.fill(); target.strokeStyle = "#15449b"; target.lineWidth = 4; target.stroke();
      target.fillStyle = "#fff"; target.font = `700 ${Math.round(size * .68)}px DM Sans`; target.textAlign = "center"; target.textBaseline = "middle";
      target.fillText(object.numero ?? "", object.x, object.y + size * .17);
    } else if (object.tipo === "bola") {
      target.beginPath(); target.arc(object.x, object.y, size * .48, 0, Math.PI * 2); target.fillStyle = "#e97125"; target.fill(); target.strokeStyle = "#8b3614"; target.lineWidth = 3; target.stroke();
      target.beginPath(); target.moveTo(object.x - size * .45, object.y); target.lineTo(object.x + size * .45, object.y); target.moveTo(object.x, object.y - size * .45); target.quadraticCurveTo(object.x + size * .28, object.y, object.x, object.y + size * .45); target.stroke();
    } else if (object.tipo === "cone") {
      target.beginPath(); target.moveTo(object.x, object.y - size * .75); target.lineTo(object.x + size * .58, object.y + size * .58); target.lineTo(object.x - size * .58, object.y + size * .58); target.closePath(); target.fillStyle = "#ee7128"; target.fill();
    } else {
      target.beginPath(); target.arc(object.x, object.y, size, 0, Math.PI * 2); target.fillStyle = "#fff"; target.fill(); target.strokeStyle = "#20201d"; target.lineWidth = 4; target.stroke();
      target.fillStyle = "#20201d"; target.font = `700 ${Math.round(size * .8)}px DM Sans`; target.textAlign = "center"; target.textBaseline = "middle"; target.fillText("C", object.x, object.y + 1);
    }
    target.restore();
  }

  function zigzagPoints(points) {
    if (points.length < 2) return points;
    const output = [points[0]];
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1]; const b = points[index];
      const length = Math.hypot(b.x - a.x, b.y - a.y); const count = Math.max(2, Math.floor(length / 18));
      const nx = -(b.y - a.y) / Math.max(1, length); const ny = (b.x - a.x) / Math.max(1, length);
      for (let step = 1; step < count; step += 1) {
        const ratio = step / count; const side = step % 2 ? 8 : -8;
        output.push({ x: a.x + (b.x - a.x) * ratio + nx * side, y: a.y + (b.y - a.y) * ratio + ny * side });
      }
      output.push(b);
    }
    return output;
  }

  function drawLine(target, object, alpha = 1) {
    let points = object.pontos || [];
    if (points.length < 2) return;
    if (object.tipo === "seta_zigzag") points = zigzagPoints(points);
    target.save(); target.globalAlpha = alpha; target.strokeStyle = object.cor || "#202936"; target.fillStyle = object.cor || "#202936";
    target.lineWidth = Number(object.largura) || 6; target.lineCap = "round"; target.lineJoin = "round";
    target.setLineDash(object.tipo === "seta_tracejada" ? [15, 12] : []);
    target.beginPath(); target.moveTo(points[0].x, points[0].y);
    if (object.tipo === "seta_curva" || object.tipo === "caneta") {
      for (let i = 1; i < points.length - 1; i += 1) target.quadraticCurveTo(points[i].x, points[i].y, (points[i].x + points[i + 1].x) / 2, (points[i].y + points[i + 1].y) / 2);
      target.lineTo(points.at(-1).x, points.at(-1).y);
    } else points.slice(1).forEach((point) => target.lineTo(point.x, point.y));
    target.stroke(); target.setLineDash([]);
    const end = points.at(-1); const before = points.at(-2); const angle = Math.atan2(end.y - before.y, end.x - before.x);
    if (object.tipo === "bloqueio") {
      target.beginPath(); target.moveTo(end.x - Math.sin(angle) * 18, end.y + Math.cos(angle) * 18); target.lineTo(end.x + Math.sin(angle) * 18, end.y - Math.cos(angle) * 18); target.stroke();
    } else if (!["linha", "caneta"].includes(object.tipo)) {
      target.beginPath(); target.moveTo(end.x, end.y); target.lineTo(end.x - 22 * Math.cos(angle - .5), end.y - 22 * Math.sin(angle - .5)); target.lineTo(end.x - 22 * Math.cos(angle + .5), end.y - 22 * Math.sin(angle + .5)); target.closePath(); target.fill();
    }
    target.restore();
  }

  function drawObject(target, object, alpha = 1) {
    if (markerTypes.has(object.tipo)) drawMarker(target, object, alpha);
    else if (window.TacticalLegacy?.eRecorte(object)) {
      target.save(); target.globalAlpha = alpha; window.TacticalLegacy.desenharRecorte(target, object, render); target.restore();
    } else drawLine(target, object, alpha);
  }

  function drawSelection(target, object) {
    if (!object) return;
    target.save(); target.strokeStyle = "#e94d33"; target.lineWidth = 3; target.setLineDash([8, 6]);
    if (markerTypes.has(object.tipo)) { target.beginPath(); target.arc(object.x, object.y, 36, 0, Math.PI * 2); target.stroke(); }
    else if (window.TacticalLegacy?.eRecorte(object)) window.TacticalLegacy.desenharSeleccao(target, object);
    else if (object.pontos?.length) {
      const xs = object.pontos.map((p) => p.x); const ys = object.pontos.map((p) => p.y);
      target.strokeRect(Math.min(...xs) - 8, Math.min(...ys) - 8, Math.max(...xs) - Math.min(...xs) + 16, Math.max(...ys) - Math.min(...ys) + 16);
    }
    target.restore();
  }

  function render(target = ctx, objects = activeScene()?.objects || [], selection = true) {
    if (!target) return;
    target.clearRect(0, 0, target.canvas.width, target.canvas.height);
    objects.forEach((object) => drawObject(target, object));
    if (selection && target === ctx) drawSelection(target, objects.find((object) => object.id === selectedId));
  }

  function stateFor(scene) {
    const court = dimensions(scene);
    return { largura: court.width, altura: court.height, campoTipo: scene.courtType, objectos: scene.objects, versaoStudio: 3 };
  }

  async function saveScene(scene = activeScene(), immediate = false) {
    if (!scene || imported || !canvas) return;
    clearTimeout(saveTimer);
    const run = async () => {
      setStatus("A guardar…", "saving");
      try {
        await window.TacticalLegacy?.aguardarRecortes(scene.objects);
        const court = dimensions(scene);
        const output = document.createElement("canvas"); output.width = court.width; output.height = court.height;
        render(output.getContext("2d"), scene.objects, false);
        const image = output.toDataURL("image/png");
        await api(`/playbook/passos/${scene.id}/desenho`, { method: "POST", body: JSON.stringify({ dados: image, estado: stateFor(scene) }) });
        scene.desenho = image; setStatus("Guardado"); renderScenes();
      } catch (error) { setStatus("Erro ao guardar", "error"); toast(error.message); }
    };
    if (immediate) await run(); else saveTimer = setTimeout(run, 500);
  }

  async function convertLegacyScene(scene) {
    if (!scene || scene.converted || scene.objects.length || !scene.desenho || !window.TacticalLegacy) return;
    scene.converted = true;
    const image = new Image();
    image.onload = () => {
      const court = dimensions(scene);
      scene.objects = window.TacticalLegacy.decomporImagem(image, court.width, court.height).map((object) => ({ ...object, id: uid() }));
      render(); renderScenes();
    };
    image.src = scene.desenho;
  }

  function renderThumbnail(scene, holder) {
    if (imported) {
      const image = document.createElement("img");
      image.alt = ""; image.src = scene.imagemCoach || scene.desenho || "";
      holder.append(image); return;
    }
    const court = dimensions(scene);
    holder.style.aspectRatio = `${court.width} / ${court.height}`;
    const base = document.createElement("img"); base.alt = ""; base.src = court.src; holder.append(base);
    const thumb = document.createElement("canvas"); thumb.width = court.width; thumb.height = court.height; holder.append(thumb);
    const thumbCtx = thumb.getContext("2d");
    if (scene.objects.length) scene.objects.forEach((object) => drawObject(thumbCtx, object));
    else if (scene.desenho) {
      const image = new Image(); image.onload = () => thumbCtx.drawImage(image, 0, 0, court.width, court.height); image.src = scene.desenho;
    }
  }

  function renderScenes() {
    scenesList.innerHTML = "";
    document.querySelector("[data-scenes-empty]")?.toggleAttribute("hidden", scenes.length > 0);
    scenes.forEach((scene, index) => {
      const item = document.createElement("div");
      item.className = `pbs-scene${scene.id === activeId ? " is-active" : ""}`;
      item.dataset.sceneId = scene.id; item.draggable = true; item.tabIndex = 0;
      const number = document.createElement("span"); number.className = "pbs-scene-number"; number.textContent = index + 1;
      const preview = document.createElement("div"); preview.className = "pbs-scene-preview"; renderThumbnail(scene, preview);
      const actions = document.createElement("span"); actions.className = "pbs-scene-actions";
      const duplicate = document.createElement("button"); duplicate.type = "button"; duplicate.title = "Duplicar cena"; duplicate.ariaLabel = "Duplicar cena"; duplicate.textContent = "⧉";
      const remove = document.createElement("button"); remove.type = "button"; remove.title = "Eliminar cena"; remove.ariaLabel = "Eliminar cena"; remove.textContent = "×";
      actions.append(duplicate, remove); item.append(number, preview, actions); scenesList.append(item);
      item.addEventListener("click", (event) => { if (!event.target.closest("button")) activateScene(scene.id); });
      item.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) activateScene(scene.id); });
      duplicate.addEventListener("click", () => duplicateScene(scene));
      remove.addEventListener("click", () => deleteScene(scene));
      item.addEventListener("dragstart", (event) => { draggedSceneId = scene.id; item.classList.add("is-dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(scene.id)); });
      item.addEventListener("dragend", () => { draggedSceneId = null; clearDropMarks(); item.classList.remove("is-dragging"); });
      item.addEventListener("dragover", (event) => { event.preventDefault(); clearDropMarks(); const before = event.clientY < item.getBoundingClientRect().top + item.offsetHeight / 2; item.classList.add(before ? "is-drop-before" : "is-drop-after"); });
      item.addEventListener("drop", (event) => { event.preventDefault(); const before = event.clientY < item.getBoundingClientRect().top + item.offsetHeight / 2; moveScene(draggedSceneId, scene.id, before); });
    });
  }

  function clearDropMarks() {
    scenesList.querySelectorAll(".is-drop-before,.is-drop-after").forEach((el) => el.classList.remove("is-drop-before", "is-drop-after"));
  }

  async function persistSceneOrder() {
    scenes.forEach((scene, index) => { scene.ordem = index; });
    try { await api(`/playbook/setplays/${setplayId}/passos/reordenar`, { method: "POST", body: JSON.stringify({ passo_ids: scenes.map((scene) => scene.id) }) }); }
    catch (error) { toast(error.message); }
  }

  function moveScene(sourceId, targetId, before) {
    if (!sourceId || sourceId === targetId) return;
    const sourceIndex = scenes.findIndex((scene) => scene.id === sourceId);
    let targetIndex = scenes.findIndex((scene) => scene.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const [scene] = scenes.splice(sourceIndex, 1);
    targetIndex = scenes.findIndex((candidate) => candidate.id === targetId);
    scenes.splice(targetIndex + (before ? 0 : 1), 0, scene);
    renderScenes(); persistSceneOrder();
  }

  async function addScene() {
    try {
      const payload = await api(`/playbook/setplays/${setplayId}/passos/novo`, { method: "POST", body: "{}" });
      const scene = normalizeScene(payload.passo); scenes.push(scene); activeId = scene.id; renderScenes(); activateScene(scene.id); toast("Nova cena adicionada.");
    } catch (error) { toast(error.message); }
  }

  async function duplicateScene(scene) {
    try {
      await saveScene(scene, true);
      const payload = await api(`/playbook/passos/${scene.id}/duplicar`, { method: "POST", body: "{}" });
      const copy = normalizeScene(payload.passo); const index = scenes.indexOf(scene); scenes.splice(index + 1, 0, copy);
      activeId = copy.id; renderScenes(); activateScene(copy.id); toast("Cena duplicada.");
    } catch (error) { toast(error.message); }
  }

  async function deleteScene(scene) {
    if (!window.confirm("Eliminar esta cena?")) return;
    try {
      await api(`/playbook/passos/${scene.id}/eliminar`, { method: "POST", body: "{}" });
      const index = scenes.indexOf(scene); scenes.splice(index, 1);
      if (activeId === scene.id) activeId = scenes[Math.min(index, scenes.length - 1)]?.id || null;
      renderScenes(); activateScene(activeId); toast("Cena eliminada.");
    } catch (error) { toast(error.message); }
  }

  function activateScene(id) {
    activeId = id; selectedId = null; gesture = null;
    const scene = activeScene();
    document.querySelector("[data-scene-label]").textContent = scene ? `Cena ${scenes.indexOf(scene) + 1}` : "Sem cenas";
    if (notes) notes.value = scene?.observacao || "";
    if (imported) {
      const image = document.querySelector("[data-imported-image]"); const empty = document.querySelector("[data-imported-empty]");
      const src = scene?.imagemCoach || scene?.desenho || ""; image.src = src; image.hidden = !src; empty.hidden = Boolean(src);
      setupImportedForms(scene);
    } else { syncCourt(scene); render(); convertLegacyScene(scene); }
    renderScenes(); renderTimeline();
  }

  function syncCourt(scene = activeScene()) {
    if (!scene || !canvas) return;
    const court = dimensions(scene); const wrap = document.querySelector("[data-court-wrap]");
    if (canvas.width !== court.width) canvas.width = court.width;
    if (canvas.height !== court.height) canvas.height = court.height;
    document.querySelector("[data-court-image]").src = court.src;
    wrap.style.aspectRatio = `${court.width} / ${court.height}`;
    fitStageCourt(wrap, court);
    document.querySelectorAll("[data-court-type]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.courtType === scene.courtType);
    });
  }

  function switchCourt(nextType) {
    const scene = activeScene();
    if (!scene || !COURTS[nextType] || scene.courtType === nextType) return;
    const previous = dimensions(scene);
    const next = COURTS[nextType];
    snapshot(scene);
    const sx = next.width / previous.width;
    const sy = next.height / previous.height;
    scene.objects.forEach((object) => {
      if (Number.isFinite(Number(object.x))) {
        object.x = Number(object.x) * sx;
        object.y = Number(object.y) * sy;
      }
      if (Array.isArray(object.pontos)) {
        object.pontos = object.pontos.map((point) => ({ x: Number(point.x) * sx, y: Number(point.y) * sy }));
      }
      if (window.TacticalLegacy?.eRecorte(object)) {
        object.largura = Number(object.largura || 1) * sx;
        object.altura = Number(object.altura || 1) * sy;
      }
    });
    scene.courtType = nextType;
    syncCourt(scene);
    render();
    renderScenes();
    saveScene(scene);
    toast(nextType === "completo" ? "Campo inteiro aplicado." : "Meio-campo aplicado.");
  }

  function setTool(next) {
    tool = next; selectedId = null; gesture = null;
    root.classList.toggle("pbs-tool-select", next === "selecionar");
    document.querySelectorAll("[data-tool]").forEach((button) => button.classList.toggle("is-active", button.dataset.tool === next));
    render();
  }

  function playerNumber() {
    return Math.max(0, Math.min(99, Number(document.querySelector("[data-player-number]")?.value) || 0));
  }

  function addMarker(point) {
    const scene = activeScene(); if (!scene) return;
    snapshot(scene); scene.objects.push({ id: uid(), tipo: tool, x: point.x, y: point.y, tamanho: 1, numero: tool.startsWith("jogador_") ? playerNumber() : null });
    selectedId = scene.objects.at(-1).id; setTool("selecionar"); saveScene(scene); renderTimeline(); render();
  }

  function eraseAt(point) {
    const scene = activeScene(); if (!scene) return;
    const object = objectAt(point); if (!object) return;
    if (!gesture?.snapshotTaken) { snapshot(scene); if (gesture) gesture.snapshotTaken = true; }
    if (object.tipo === "caneta" && object.pontos?.length > 3) {
      const fragments = []; let current = [];
      object.pontos.forEach((p) => { if (Math.hypot(p.x - point.x, p.y - point.y) <= 22) { if (current.length > 1) fragments.push(current); current = []; } else current.push(p); });
      if (current.length > 1) fragments.push(current);
      scene.objects.splice(scene.objects.indexOf(object), 1, ...fragments.map((pontos) => ({ ...object, id: uid(), pontos })));
    } else scene.objects.splice(scene.objects.indexOf(object), 1);
    selectedId = null; render(); renderTimeline(); saveScene(scene);
  }

  function pointerDown(event) {
    if (!activeScene() || event.button === 2) return;
    event.preventDefault(); canvas.setPointerCapture?.(event.pointerId);
    const point = pointFromEvent(event);
    if (event.pointerType === "pen" && event.buttons === 0) return;
    if (event.pointerType === "pen") {
      const now = performance.now();
      if (now - pencilTap.time < 330 && Math.hypot(point.x - pencilTap.x, point.y - pencilTap.y) < 34) {
        setTool(tool === "borracha" ? "caneta" : "borracha"); pencilTap.time = 0; toast(tool === "borracha" ? "Borracha ativa" : "Caneta ativa"); return;
      }
      pencilTap = { time: now, x: point.x, y: point.y };
      if (event.button === 5 || (event.buttons & 32)) setTool("borracha");
    }
    const scene = activeScene();
    if (tool === "borracha") { gesture = { pointerId: event.pointerId, snapshotTaken: false }; eraseAt(point); return; }
    if (markerTypes.has(tool)) { addMarker(point); return; }
    if (tool === "selecionar") {
      const object = objectAt(point); selectedId = object?.id || null;
      if (object) {
        snapshot(scene);
        gesture = { pointerId: event.pointerId, object, start: point, original: clone(object) };
      }
      render(); return;
    }
    snapshot(scene);
    const line = { id: uid(), tipo: tool, pontos: [point], cor: "#202936", largura: tool === "caneta" ? 6 : 7 };
    scene.objects.push(line); selectedId = line.id; gesture = { pointerId: event.pointerId, object: line, start: point, drawing: true };
    render();
  }

  function pointerMove(event) {
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    event.preventDefault(); const point = pointFromEvent(event); const scene = activeScene(); if (!scene) return;
    if (tool === "borracha") { eraseAt(point); return; }
    if (gesture.drawing) {
      const points = gesture.object.pontos; const last = points.at(-1);
      if (tool === "caneta" || Math.hypot(point.x - last.x, point.y - last.y) > 8) points.push(point);
    } else if (gesture.object) {
      const dx = point.x - gesture.start.x; const dy = point.y - gesture.start.y; const object = gesture.object; const original = gesture.original;
      if (Number.isFinite(original.x)) { object.x = original.x + dx; object.y = original.y + dy; }
      if (original.pontos) object.pontos = original.pontos.map((p) => ({ x: p.x + dx, y: p.y + dy }));
    }
    render();
  }

  function pointerUp(event) {
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const scene = activeScene(); const wasDrawing = gesture.drawing; const object = gesture.object; gesture = null;
    if (wasDrawing && object?.pontos?.length < 2) scene.objects.splice(scene.objects.indexOf(object), 1);
    render(); renderTimeline(); saveScene(scene);
  }

  function undo() {
    const scene = activeScene(); if (!scene?.undo.length) return;
    scene.redo.push(clone(scene.objects)); scene.objects = scene.undo.pop(); selectedId = null; render(); renderTimeline(); saveScene(scene);
  }

  function redo() {
    const scene = activeScene(); if (!scene?.redo.length) return;
    scene.undo.push(clone(scene.objects)); scene.objects = scene.redo.pop(); selectedId = null; render(); renderTimeline(); saveScene(scene);
  }

  function clearScene() {
    const scene = activeScene(); if (!scene?.objects.length || !window.confirm("Limpar todos os elementos desta cena?")) return;
    snapshot(scene); scene.objects = []; selectedId = null; render(); renderTimeline(); saveScene(scene);
  }

  function movementLabel(object, index) {
    const labels = { seta: "Movimento", seta_curva: "Movimento curvo", seta_tracejada: "Passe", seta_zigzag: "Drible", bloqueio: "Bloqueio", linha: "Indicação" };
    const start = object.pontos?.[0];
    const players = activeScene()?.objects.filter((item) => item.tipo.startsWith("jogador_") && start) || [];
    const player = players.sort((a, b) => Math.hypot(a.x - start.x, a.y - start.y) - Math.hypot(b.x - start.x, b.y - start.y))[0];
    return { title: player && Math.hypot(player.x - start.x, player.y - start.y) < 95 ? `Jogador ${player.numero}: ${labels[object.tipo] || "Ação"}` : labels[object.tipo] || `Ação ${index + 1}`, player };
  }

  function renderTimeline() {
    const holder = document.querySelector("[data-timeline]"); const empty = document.querySelector("[data-timeline-empty]");
    if (!holder || imported) return;
    holder.innerHTML = "";
    const actions = activeScene()?.objects.filter((object) => movementTypes.has(object.tipo)) || [];
    empty.hidden = actions.length > 0;
    let lastGroup = null;
    actions.forEach((object, index) => {
      if (object.grupo && object.grupo !== lastGroup) {
        const group = document.createElement("div"); group.className = "pbs-group-label"; group.textContent = "Ao mesmo tempo"; holder.append(group); lastGroup = object.grupo;
      } else if (!object.grupo) lastGroup = null;
      const row = document.createElement("div"); row.className = `pbs-action${object.grupo ? " is-grouped" : ""}`; row.dataset.actionId = object.id;
      const check = document.createElement("input"); check.type = "checkbox"; check.ariaLabel = "Selecionar ação";
      const text = document.createElement("span"); text.className = "pbs-action-text"; const info = movementLabel(object, index);
      text.innerHTML = `<strong>${info.title}</strong><span>${object.grupo ? "Execução simultânea" : `Passo ${index + 1}`}</span>`;
      const remove = document.createElement("button"); remove.type = "button"; remove.ariaLabel = "Eliminar ação"; remove.textContent = "×";
      check.addEventListener("change", updateGroupButton);
      row.addEventListener("click", (event) => { if (!event.target.closest("button,input")) { selectedId = object.id; render(); } });
      remove.addEventListener("click", () => { const scene = activeScene(); snapshot(scene); scene.objects.splice(scene.objects.indexOf(object), 1); if (selectedId === object.id) selectedId = null; render(); renderTimeline(); saveScene(scene); });
      row.append(check, text, remove); holder.append(row);
    });
    updateGroupButton();
  }

  function updateGroupButton() {
    const selected = [...document.querySelectorAll(".pbs-action input:checked")];
    const button = document.querySelector("[data-group-selected]"); if (button) button.disabled = selected.length < 2;
  }

  function groupSelected() {
    const ids = [...document.querySelectorAll(".pbs-action input:checked")].map((input) => input.closest(".pbs-action").dataset.actionId);
    if (ids.length < 2) return;
    const scene = activeScene(); snapshot(scene); const group = uid(); scene.objects.filter((object) => ids.includes(object.id)).forEach((object) => { object.grupo = group; });
    renderTimeline(); saveScene(scene); toast("Ações agrupadas no mesmo momento.");
  }

  async function saveNotes() {
    const scene = activeScene(); if (!scene || notes.value === scene.observacao) return;
    scene.observacao = notes.value; setStatus("A guardar…", "saving");
    try { await api(`/playbook/passos/${scene.id}/observacao-json`, { method: "POST", body: JSON.stringify({ observacao: scene.observacao }) }); setStatus("Guardado"); }
    catch (error) { setStatus("Erro ao guardar", "error"); toast(error.message); }
  }

  function setupImportedForms(scene) {
    const upload = document.querySelector("[data-image-form]"); const remove = document.querySelector("[data-delete-image-form]");
    if (upload) upload.action = scene ? `/playbook/passos/${scene.id}/imagem` : "";
    if (remove) { remove.action = scene ? `/playbook/passos/${scene.id}/imagem/eliminar` : ""; remove.hidden = !scene?.imagemCoach; }
  }

  function actionPlan(scene) {
    const actions = scene.objects.filter((object) => movementTypes.has(object.tipo) && object.pontos?.length > 1);
    const groups = [];
    actions.forEach((object) => {
      if (object.grupo) {
        let group = groups.find((candidate) => candidate.key === object.grupo);
        if (!group) { group = { key: object.grupo, actions: [] }; groups.push(group); }
        group.actions.push(object);
      } else groups.push({ key: object.id, actions: [object] });
    });
    return groups;
  }

  function pointAlong(points, progress) {
    if (!points?.length) return null;
    if (points.length === 1) return points[0];
    const lengths = []; let total = 0;
    for (let index = 1; index < points.length; index += 1) { const length = Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y); lengths.push(length); total += length; }
    let wanted = total * progress;
    for (let index = 0; index < lengths.length; index += 1) {
      if (wanted <= lengths[index]) { const ratio = wanted / Math.max(1, lengths[index]); return { x: points[index].x + (points[index + 1].x - points[index].x) * ratio, y: points[index].y + (points[index + 1].y - points[index].y) * ratio }; }
      wanted -= lengths[index];
    }
    return points.at(-1);
  }

  function animatedObjects(scene, groupIndex, progress) {
    const objects = clone(scene.objects); const groups = actionPlan(scene); const group = groups[groupIndex]; if (!group) return objects;
    group.actions.forEach((action) => {
      const copy = objects.find((object) => object.id === action.id); if (copy) copy.previewProgress = progress;
      const start = action.pontos[0];
      let actor = objects.filter((object) => object.tipo.startsWith("jogador_")).sort((a, b) => Math.hypot(a.x - start.x, a.y - start.y) - Math.hypot(b.x - start.x, b.y - start.y))[0];
      if (action.tipo === "seta_tracejada") actor = objects.filter((object) => object.tipo === "bola").sort((a, b) => Math.hypot(a.x - start.x, a.y - start.y) - Math.hypot(b.x - start.x, b.y - start.y))[0] || actor;
      if (actor && Math.hypot(actor.x - start.x, actor.y - start.y) < 110) Object.assign(actor, pointAlong(action.pontos, progress));
    });
    return objects;
  }

  function previewDuration() {
    return scenes.reduce((total, scene) => total + Math.max(1, actionPlan(scene).length) * 1500, 0);
  }

  function renderPreview(progress) {
    const duration = previewDuration(); let remaining = progress * duration; let scene = scenes[0]; let groupIndex = 0; let local = 0;
    for (const candidate of scenes) {
      const groups = Math.max(1, actionPlan(candidate).length); const sceneDuration = groups * 1500;
      if (remaining <= sceneDuration) { scene = candidate; groupIndex = Math.min(groups - 1, Math.floor(remaining / 1500)); local = (remaining % 1500) / 1500; break; }
      remaining -= sceneDuration; scene = candidate; groupIndex = groups - 1; local = 1;
    }
    const index = Math.max(0, scenes.indexOf(scene));
    document.querySelector("[data-preview-scene]").textContent = `Cena ${index + 1} de ${scenes.length}`;
    document.querySelector("[data-preview-notes]").textContent = scene?.observacao || "Sem instruções.";
    const importedImage = document.querySelector("[data-preview-imported]");
    if (imported) { importedImage.src = scene?.imagemCoach || scene?.desenho || ""; importedImage.hidden = !importedImage.src; previewCanvas.hidden = true; }
    else {
      importedImage.hidden = true; previewCanvas.hidden = false;
      const court = dimensions(scene); const wrap = document.querySelector(".pbs-preview-court");
      previewCanvas.width = court.width; previewCanvas.height = court.height; wrap.style.aspectRatio = `${court.width} / ${court.height}`;
      document.querySelector("[data-preview-court-image]").src = court.src;
      render(previewCtx, scene ? animatedObjects(scene, groupIndex, local) : [], false);
    }
    document.querySelector("[data-preview-progress]").value = Math.round(progress * 1000);
    document.querySelector("[data-preview-time]").textContent = `0:${String(Math.round(duration * progress / 1000)).padStart(2, "0")}`;
  }

  function previewTick(time) {
    if (!previewPlaying) return;
    if (!previewStarted) previewStarted = time;
    const speed = Number(document.querySelector("[data-preview-speed]").value) || 1;
    const progress = Math.min(1, (time - previewStarted) * speed / Math.max(1, previewDuration())); renderPreview(progress);
    if (progress >= 1) { previewPlaying = false; document.querySelector("[data-preview-play]").textContent = "▶"; return; }
    previewFrame = requestAnimationFrame(previewTick);
  }

  function togglePreview() {
    previewPlaying = !previewPlaying; const button = document.querySelector("[data-preview-play]"); button.textContent = previewPlaying ? "Ⅱ" : "▶";
    if (previewPlaying) { const progress = Number(document.querySelector("[data-preview-progress]").value) / 1000; previewStarted = performance.now() - previewDuration() * progress / (Number(document.querySelector("[data-preview-speed]").value) || 1); previewFrame = requestAnimationFrame(previewTick); }
    else cancelAnimationFrame(previewFrame);
  }

  function openPreview() {
    if (!scenes.length) { toast("Adiciona uma cena antes de pré-visualizar."); return; }
    previewPlaying = false; previewStarted = 0; renderPreview(0); document.querySelector("[data-preview-dialog]").showModal();
  }

  function closePreview() {
    previewPlaying = false; cancelAnimationFrame(previewFrame); document.querySelector("[data-preview-dialog]").close();
  }

  async function saveDetails(event) {
    event.preventDefault(); const form = event.currentTarget; const body = Object.fromEntries(new FormData(form));
    try {
      const payload = await api(`/playbook/setplays/${setplayId}/editar-json`, { method: "POST", body: JSON.stringify(body) });
      data.setplay = payload.setplay; document.querySelector("[data-play-title]").textContent = payload.setplay.nome;
      document.querySelector(".pbs-play-title span").textContent = payload.setplay.categoria || "Sem categoria";
      document.title = `${payload.setplay.nome} | Playbook Studio`; form.closest("dialog").close(); toast("Informação atualizada.");
    } catch (error) { toast(error.message); }
  }

  function closeMobilePanels(except) {
    [document.querySelector(".pbs-scenes-panel"), document.querySelector(".pbs-toolbar"), document.querySelector(".pbs-inspector")].forEach((panel) => { if (panel !== except) panel?.classList.remove("is-mobile-open"); });
    except?.classList.toggle("is-mobile-open");
  }

  function bindEvents() {
    document.querySelectorAll("[data-add-scene]").forEach((button) => button.addEventListener("click", addScene));
    document.querySelectorAll("[data-tool]").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.tool)));
    document.querySelectorAll("[data-court-type]").forEach((button) => button.addEventListener("click", () => switchCourt(button.dataset.courtType)));
    canvas?.addEventListener("pointerdown", pointerDown, { passive: false }); canvas?.addEventListener("pointermove", pointerMove, { passive: false });
    canvas?.addEventListener("pointerup", pointerUp, { passive: false }); canvas?.addEventListener("pointercancel", pointerUp, { passive: false });
    canvas?.addEventListener("contextmenu", (event) => event.preventDefault());
    document.querySelector("[data-undo]")?.addEventListener("click", undo); document.querySelector("[data-redo]")?.addEventListener("click", redo); document.querySelector("[data-clear]")?.addEventListener("click", clearScene);
    document.querySelector("[data-group-selected]")?.addEventListener("click", groupSelected);
    notes?.addEventListener("input", () => { clearTimeout(notesTimer); notesTimer = setTimeout(saveNotes, 550); }); notes?.addEventListener("blur", saveNotes);
    document.querySelectorAll("[data-panel-tab]").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll("[data-panel-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.panelTab));
    }));
    document.querySelectorAll("[data-open-preview]").forEach((button) => button.addEventListener("click", openPreview)); document.querySelector("[data-close-preview]")?.addEventListener("click", closePreview);
    document.querySelector("[data-preview-play]")?.addEventListener("click", togglePreview);
    document.querySelector("[data-preview-restart]")?.addEventListener("click", () => { previewPlaying = false; previewStarted = 0; document.querySelector("[data-preview-play]").textContent = "▶"; renderPreview(0); });
    document.querySelector("[data-preview-progress]")?.addEventListener("input", (event) => { previewPlaying = false; document.querySelector("[data-preview-play]").textContent = "▶"; renderPreview(Number(event.target.value) / 1000); });
    document.querySelector("[data-open-details]")?.addEventListener("click", () => document.querySelector("[data-details-dialog]").showModal());
    document.querySelector("[data-details-form]")?.addEventListener("submit", saveDetails);
    document.querySelector("[data-share]")?.addEventListener("click", async () => { try { await navigator.clipboard.writeText(location.href); toast("Ligação copiada."); } catch (_) { toast("Não foi possível copiar a ligação."); } });
    document.querySelector("[data-mobile-scenes]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-scenes-panel")));
    document.querySelector("[data-mobile-tools]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-toolbar")));
    document.querySelector("[data-mobile-inspector]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-inspector")));
    document.addEventListener("keydown", (event) => {
      if (event.target.matches("input,textarea,select")) return;
      const shortcuts = { v: "selecionar", a: "jogador_ataque", d: "jogador_defesa", m: "seta", p: "seta_tracejada", g: "seta_zigzag", e: "borracha" };
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      else if (["Backspace", "Delete"].includes(event.key) && selectedId) { const scene = activeScene(); const object = scene.objects.find((item) => item.id === selectedId); if (object) { snapshot(scene); scene.objects.splice(scene.objects.indexOf(object), 1); selectedId = null; render(); renderTimeline(); saveScene(scene); } }
      else if (shortcuts[event.key.toLowerCase()]) setTool(shortcuts[event.key.toLowerCase()]);
    });
  }

  async function init() {
    document.querySelectorAll('form[method="post"]').forEach((form) => { if (!form.querySelector('[name="csrf_token"]')) { const input = document.createElement("input"); input.type = "hidden"; input.name = "csrf_token"; input.value = csrf; form.prepend(input); } });
    bindEvents(); renderScenes();
    if (!scenes.length && !imported) await addScene(); else activateScene(activeId);
    setTool("selecionar");
    const stage = document.querySelector("[data-stage]");
    if (stage && window.ResizeObserver) {
      new ResizeObserver(() => {
        const scene = activeScene();
        if (scene && !imported) fitStageCourt(document.querySelector("[data-court-wrap]"), dimensions(scene));
      }).observe(stage);
    }
  }

  init();
})();
