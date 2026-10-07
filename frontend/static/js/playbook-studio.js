(function () {
  "use strict";

  const root = document.querySelector("[data-playbook-studio]");
  if (!root) return;

  const COURTS = {
    meio: { width: 702, height: 622, src: "/static/campos/campo_meio.png?v=20260908-madeira-1" },
    completo: { width: 697, height: 1222, src: "/static/campos/campo_completo.png?v=20260908-madeira-1" },
  };
  const imported = root.dataset.imported === "true";
  const training = root.dataset.trainingExercise === "true";
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
  const movementTypes = new Set(["seta", "seta_tracejada", "seta_zigzag", "seta_curva", "bloqueio", "linha", "lancamento"]);
  const markerTypes = new Set(["jogador_ataque", "jogador_defesa", "bola", "cone", "coach"]);
  const straightLineTypes = new Set(["linha"]);
  const curvedMovementTypes = new Set(["seta", "seta_tracejada", "seta_zigzag", "bloqueio", "lancamento"]);
  const playerMovementTypes = new Set(["seta", "seta_zigzag", "seta_curva", "bloqueio"]);
  const PREVIEW_READ_MS = 700;
  const PREVIEW_MOVE_MS = 850;
  const pathMetrics = new WeakMap();

  let scenes = (data.passos || []).map(normalizeScene).sort((a, b) => a.ordem - b.ordem);
  let activeId = Number(root.dataset.initialScene) || scenes[0]?.id || null;
  let tool = "selecionar";
  let selectedId = null;
  let gesture = null;
  const saveTimers = new Map();
  const saveQueues = new Map();
  const unsavedScenes = new Set();
  const notesTimers = new Map();
  const notesQueues = new Map();
  const unsavedNotes = new Set();
  const failedSaves = new Set();
  let draggedSceneId = null;
  let previewFrame = 0;
  let previewLastTime = null;
  let previewElapsed = 0;
  let previewPlan = null;
  let previewSceneId = null;
  let previewPlaying = false;
  let confirmedSceneIds = scenes.map(scene => scene.id);
  let orderSaveQueue = Promise.resolve();
  let orderRevision = 0;
  let unsavedOrder = false;
  let pencilTap = { time: 0, x: 0, y: 0 };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function uid() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function nextPlayerNumber(scene = activeScene()) {
    const used = (scene?.objects || [])
      .filter((object) => object.tipo?.startsWith("jogador_"))
      .map((object) => Number(object.numero))
      .filter(Number.isFinite);
    return Math.min(99, Math.max(0, ...used) + 1);
  }

  function updatePlayerNumber(value = nextPlayerNumber()) {
    const input = document.querySelector("[data-player-number]");
    if (input) input.value = String(value);
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
      legacyBackground: saved.fundoLegado || null,
      undo: [],
      redo: [],
      converted: Boolean(saved.objectos) && !saved.fundoLegado,
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

  function refreshSaveStatus() {
    if (failedSaves.size) setStatus("Não guardado", "error");
    else if (unsavedScenes.size || unsavedNotes.size || unsavedOrder) setStatus("A guardar…", "saving");
    else setStatus("Guardado");
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
    let payload;
    try { payload = await response.json(); }
    catch (_) { throw new Error("Resposta inválida. Verifica a ligação e se a sessão continua ativa antes de voltar a guardar."); }
    if (!payload || typeof payload !== "object" || response.redirected) throw new Error("Não foi possível confirmar a gravação. Verifica a tua sessão.");
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
    const total = pathLength(points);
    const waves = Math.max(1, Math.round(total / 30));
    const count = Math.max(2, Math.ceil(total / 3));
    return Array.from({ length: count + 1 }, (_, index) => {
      const t = index / count;
      const point = pointAlong(points, t);
      const before = pointAlong(points, Math.max(0, t - 1 / count));
      const after = pointAlong(points, Math.min(1, t + 1 / count));
      const angle = Math.atan2(after.y - before.y, after.x - before.x);
      const offset = index === 0 || index === count ? 0 : Math.sin(t * waves * Math.PI * 2) * Math.min(7, total / 8);
      return { x: point.x - Math.sin(angle) * offset, y: point.y + Math.cos(angle) * offset };
    });
  }

  function pathLength(points) {
    return points.slice(1).reduce((sum, point, index) => sum + Math.hypot(point.x - points[index].x, point.y - points[index].y), 0);
  }

  function trimPath(points, trim) {
    const limit = Math.max(0, pathLength(points) - trim);
    const result = [points[0]];
    let travelled = 0;
    for (let i = 1; i < points.length; i += 1) {
      const a = points[i - 1]; const b = points[i];
      const length = Math.hypot(b.x - a.x, b.y - a.y);
      if (travelled + length >= limit) {
        const t = length ? (limit - travelled) / length : 0;
        result.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
        break;
      }
      result.push(b); travelled += length;
    }
    return result;
  }

  function smoothMovement(points) {
    // Resample before smoothing so pointer speed does not change the curve.
    const count = Math.max(2, Math.min(400, Math.ceil(pathLength(points) / 8)));
    let result = Array.from({ length: count + 1 }, (_, i) => pointAlong(points, i / count));
    for (let pass = 0; pass < 2; pass += 1) {
      const next = [result[0]];
      for (let i = 1; i < result.length; i += 1) {
        const a = result[i - 1]; const b = result[i];
        next.push({ x: a.x * .75 + b.x * .25, y: a.y * .75 + b.y * .25 });
        next.push({ x: a.x * .25 + b.x * .75, y: a.y * .25 + b.y * .75 });
      }
      next.push(result.at(-1)); result = next;
    }
    return result;
  }

  function fitCurve(points) {
    if (!points?.length) return [];
    if (points.length < 3) return [points[0], points.at(-1)];
    const start = points[0];
    const end = points.at(-1);
    const segmentLengths = [];
    let totalLength = 0;
    for (let index = 1; index < points.length; index += 1) {
      const length = Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y);
      segmentLengths.push(length);
      totalLength += length;
    }
    if (totalLength < 2) return [start, end];

    let travelled = 0;
    let numeratorX = 0;
    let numeratorY = 0;
    let denominator = 0;
    for (let index = 1; index < points.length - 1; index += 1) {
      travelled += segmentLengths[index - 1];
      const t = travelled / totalLength;
      const weight = 2 * (1 - t) * t;
      const baseX = ((1 - t) ** 2) * start.x + (t ** 2) * end.x;
      const baseY = ((1 - t) ** 2) * start.y + (t ** 2) * end.y;
      numeratorX += weight * (points[index].x - baseX);
      numeratorY += weight * (points[index].y - baseY);
      denominator += weight * weight;
    }
    const fallback = points[Math.floor(points.length / 2)];
    const control = denominator > 0
      ? { x: numeratorX / denominator, y: numeratorY / denominator }
      : fallback;
    const cleaned = [];
    for (let step = 0; step <= 24; step += 1) {
      const t = step / 24;
      const inverse = 1 - t;
      cleaned.push({
        x: inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x,
        y: inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y,
      });
    }
    return cleaned;
  }

  function smoothFreehand(points) {
    const cleaned = points.filter((point, index) => index === 0 || Math.hypot(point.x - points[index - 1].x, point.y - points[index - 1].y) > 3);
    if (cleaned.length < 4) return cleaned;
    const start = cleaned[0];
    const end = cleaned.at(-1);
    const pathLength = cleaned.slice(1).reduce((total, point, index) => total + Math.hypot(point.x - cleaned[index].x, point.y - cleaned[index].y), 0);
    const centre = cleaned.reduce((sum, point) => ({ x: sum.x + point.x, y: sum.y + point.y }), { x: 0, y: 0 });
    centre.x /= cleaned.length;
    centre.y /= cleaned.length;
    const radii = cleaned.map((point) => Math.hypot(point.x - centre.x, point.y - centre.y));
    const radius = radii.reduce((total, value) => total + value, 0) / radii.length;
    const radiusError = radii.reduce((total, value) => total + Math.abs(value - radius), 0) / radii.length;
    const isCircle = pathLength > 80 && radius > 12 && Math.hypot(end.x - start.x, end.y - start.y) < Math.max(30, radius * .55) && radiusError / radius < .24;
    if (isCircle) {
      const firstAngle = Math.atan2(start.y - centre.y, start.x - centre.x);
      return Array.from({ length: 37 }, (_, index) => {
        const angle = firstAngle + (Math.PI * 2 * index) / 36;
        return { x: centre.x + radius * Math.cos(angle), y: centre.y + radius * Math.sin(angle) };
      });
    }
    const smoothed = [cleaned[0]];
    for (let index = 1; index < cleaned.length; index += 1) {
      const previous = cleaned[index - 1];
      const current = cleaned[index];
      smoothed.push({ x: previous.x * .25 + current.x * .75, y: previous.y * .25 + current.y * .75 });
    }
    smoothed[smoothed.length - 1] = cleaned.at(-1);
    return smoothed;
  }

  function cleanDrawnLine(object) {
    if (!object?.pontos?.length) return;
    const start = object.pontos[0];
    const end = object.pontos.at(-1);
    if (object.tipo === "caneta") object.pontos = smoothFreehand(object.pontos);
    else if (object.tipo === "seta_curva") {
      object.pontos = fitCurve(object.pontos);
      object.curva = true;
    } else if (curvedMovementTypes.has(object.tipo)) {
      const length = Math.hypot(end.x - start.x, end.y - start.y);
      const deviation = object.pontos.slice(1, -1).reduce((max, point) => Math.max(max, distanceToSegment(point, start, end)), 0);
      object.curva = object.pontos.length > 2 && deviation > Math.max(8, length * .07);
      if (!object.curva) object.pontos = [start, end];
      else {
        const signed = object.pontos.slice(1, -1).map(point =>
          ((end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (point.x - start.x)) / Math.max(1, length)
        );
        const singleBend = length > 8 && pathLength(object.pontos) < length * 2.2
          && !(Math.max(...signed) > 8 && Math.min(...signed) < -8);
        object.pontos = singleBend ? fitCurve(object.pontos) : smoothMovement(object.pontos);
      }
    } else if (straightLineTypes.has(object.tipo)) object.pontos = [start, end];
  }

  function drawLine(target, object, alpha = 1) {
    const trajectory = object.pontos || [];
    if (trajectory.length < 2) return;
    const hasArrow = !["linha", "caneta", "bloqueio"].includes(object.tipo);
    const headLength = Math.min(22, pathLength(trajectory) * .4);
    const end = trajectory.at(-1);
    const before = [...trajectory].reverse().find(point => Math.hypot(end.x - point.x, end.y - point.y) > .01) || trajectory[0];
    const angle = Math.atan2(end.y - before.y, end.x - before.x);
    const base = { x: end.x - Math.cos(angle) * headLength, y: end.y - Math.sin(angle) * headLength };
    let points = hasArrow ? trimPath(trajectory, headLength) : trajectory;
    if (hasArrow) points[points.length - 1] = base;
    if (object.tipo === "seta_zigzag") points = zigzagPoints(points);
    target.save(); target.globalAlpha = alpha; target.strokeStyle = object.cor || "#202936"; target.fillStyle = object.cor || "#202936";
    target.lineWidth = Number(object.largura) || 6; target.lineCap = hasArrow ? "butt" : "round"; target.lineJoin = "round";
    target.setLineDash(object.tipo === "seta_tracejada" ? [15, 12] : []);
    target.beginPath(); target.moveTo(points[0].x, points[0].y);
    if (object.tipo === "caneta") {
      for (let i = 1; i < points.length - 1; i += 1) target.quadraticCurveTo(points[i].x, points[i].y, (points[i].x + points[i + 1].x) / 2, (points[i].y + points[i + 1].y) / 2);
      target.lineTo(points.at(-1).x, points.at(-1).y);
    } else if (object.tipo === "lancamento") {
      target.lineWidth = Math.max(2, target.lineWidth * .55);
      target.beginPath();
      for (const side of [-1, 1]) {
        points.forEach((point, index) => {
          const a = points[Math.max(0, index - 1)]; const b = points[Math.min(points.length - 1, index + 1)];
          const tangent = Math.atan2(b.y - a.y, b.x - a.x);
          const x = point.x - Math.sin(tangent) * side * 5;
          const y = point.y + Math.cos(tangent) * side * 5;
          if (index === 0) target.moveTo(x, y); else target.lineTo(x, y);
        });
      }
    } else points.slice(1).forEach((point) => target.lineTo(point.x, point.y));
    target.stroke(); target.setLineDash([]);
    if (object.tipo === "bloqueio") {
      target.beginPath(); target.moveTo(end.x - Math.sin(angle) * 18, end.y + Math.cos(angle) * 18); target.lineTo(end.x + Math.sin(angle) * 18, end.y - Math.cos(angle) * 18); target.stroke();
    } else if (!["linha", "caneta"].includes(object.tipo)) {
      const baseX = base.x;
      const baseY = base.y;
      const halfWidth = Math.min(10, headLength * .5);
      target.beginPath();
      target.moveTo(end.x, end.y);
      target.lineTo(baseX - Math.sin(angle) * halfWidth, baseY + Math.cos(angle) * halfWidth);
      target.lineTo(baseX + Math.sin(angle) * halfWidth, baseY - Math.cos(angle) * halfWidth);
      target.closePath(); target.fill();
    }
    target.restore();
  }

  function drawObject(target, object, alpha = 1) {
    if (object.hidden) return;
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
    const orderedObjects = [...objects.filter((object) => !markerTypes.has(object.tipo)), ...objects.filter((object) => markerTypes.has(object.tipo))];
    orderedObjects.forEach((object) => drawObject(target, object));
    if (selection && target === ctx) drawSelection(target, objects.find((object) => object.id === selectedId));
  }

  function stateFor(scene) {
    const court = dimensions(scene);
    return { largura: court.width, altura: court.height, campoTipo: scene.courtType, objectos: scene.objects, versaoStudio: 3 };
  }

  async function saveScene(scene = activeScene(), immediate = false) {
    if (!scene || imported || !canvas) return;
    try { await convertLegacyScene(scene); }
    catch (error) { failedSaves.add(`drawing:${scene.id}`); refreshSaveStatus(); toast(error.message); if (immediate) throw error; return; }
    clearTimeout(saveTimers.get(scene.id));
    saveTimers.delete(scene.id);
    unsavedScenes.add(scene.id);
    failedSaves.delete(`drawing:${scene.id}`); refreshSaveStatus();
    const revision = (scene.saveRevision || 0) + 1;
    scene.saveRevision = revision;
    const savedScene = { ...scene, objects: clone(scene.objects) };
    const run = async () => {
      try {
        await window.TacticalLegacy?.aguardarRecortes(savedScene.objects);
        const court = dimensions(savedScene);
        const output = document.createElement("canvas"); output.width = court.width; output.height = court.height;
        render(output.getContext("2d"), savedScene.objects, false);
        const image = output.toDataURL("image/png");
        const url = training ? `/treino/exercicios/${setplayId}/desenho` : `/playbook/passos/${scene.id}/desenho`;
        await api(url, { method: "POST", body: JSON.stringify({ numero: scene.id, dados: image, estado: stateFor(savedScene) }) });
        if (scene.saveRevision === revision) { scene.desenho = image; unsavedScenes.delete(scene.id); }
        failedSaves.delete(`drawing:${scene.id}`); refreshSaveStatus(); renderScenes();
        return true;
      } catch (error) { failedSaves.add(`drawing:${scene.id}`); refreshSaveStatus(); toast(error.message); return false; }
    };
    const enqueue = () => {
      saveTimers.delete(scene.id);
      const pending = (saveQueues.get(scene.id) || Promise.resolve()).then(run);
      saveQueues.set(scene.id, pending);
      pending.finally(() => { if (saveQueues.get(scene.id) === pending) saveQueues.delete(scene.id); });
      return pending;
    };
    if (immediate) {
      if (!await enqueue()) throw new Error("Guarda a cena antes de continuar.");
    } else saveTimers.set(scene.id, setTimeout(enqueue, 350));
  }

  async function convertLegacyScene(scene) {
    if (!scene || scene.converted || (!scene.legacyBackground && scene.objects.length) || !(scene.legacyBackground || scene.desenho)) return;
    if (scene.conversionPromise) return scene.conversionPromise;
    if (!window.TacticalLegacy) throw new Error("Não foi possível carregar o desenho antigo.");
    scene.conversionPromise = new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        try {
          const court = dimensions(scene);
          const legacy = window.TacticalLegacy.decomporImagem(image, court.width, court.height).map((object) => ({ ...object, id: uid() }));
          scene.objects = scene.legacyBackground ? [...legacy, ...scene.objects] : legacy;
          scene.legacyBackground = null;
          scene.converted = true;
          if (activeId === scene.id) render();
          renderScenes(); resolve();
        } catch (error) { scene.conversionPromise = null; reject(error); }
      };
      image.onerror = () => { scene.conversionPromise = null; reject(new Error("Não foi possível carregar o desenho antigo.")); };
      image.src = scene.legacyBackground || scene.desenho;
    });
    return scene.conversionPromise;
  }

  function renderThumbnail(scene, holder) {
    if (imported) {
      const image = document.createElement("img");
      image.alt = ""; image.draggable = false; image.src = scene.imagemCoach || scene.desenho || "";
      holder.append(image); return;
    }
    const court = dimensions(scene);
    holder.style.aspectRatio = `${court.width} / ${court.height}`;
    const base = document.createElement("img"); base.alt = ""; base.draggable = false; base.src = court.src; holder.append(base);
    const thumb = document.createElement("canvas"); thumb.width = court.width; thumb.height = court.height; holder.append(thumb);
    const thumbCtx = thumb.getContext("2d");
    if (scene.objects.length) render(thumbCtx, scene.objects, false);
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
      const up = document.createElement("button"); up.type = "button"; up.title = "Subir cena"; up.ariaLabel = "Subir cena"; up.textContent = "↑"; up.disabled = index === 0;
      const down = document.createElement("button"); down.type = "button"; down.title = "Descer cena"; down.ariaLabel = "Descer cena"; down.textContent = "↓"; down.disabled = index === scenes.length - 1;
      const duplicate = document.createElement("button"); duplicate.type = "button"; duplicate.title = "Duplicar cena"; duplicate.ariaLabel = "Duplicar cena"; duplicate.textContent = "⧉";
      const remove = document.createElement("button"); remove.type = "button"; remove.title = "Eliminar cena"; remove.ariaLabel = "Eliminar cena"; remove.textContent = "×";
      actions.append(up, down, duplicate, remove); item.append(number, preview, actions); scenesList.append(item);
      item.addEventListener("click", (event) => { if (!event.target.closest("button")) activateScene(scene.id); });
      item.addEventListener("keydown", (event) => {
        if (event.target.closest("button")) return;
        if (event.altKey && event.key === "ArrowUp" && index > 0) { event.preventDefault(); moveScene(scene.id, scenes[index - 1].id, true); }
        else if (event.altKey && event.key === "ArrowDown" && index < scenes.length - 1) { event.preventDefault(); moveScene(scene.id, scenes[index + 1].id, false); }
        else if (["Enter", " "].includes(event.key)) activateScene(scene.id);
      });
      up.addEventListener("click", () => moveScene(scene.id, scenes[index - 1]?.id, true));
      down.addEventListener("click", () => moveScene(scene.id, scenes[index + 1]?.id, false));
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
    const ids = scenes.map(scene => scene.id);
    const revision = ++orderRevision;
    unsavedOrder = true;
    failedSaves.delete("order");
    refreshSaveStatus();
    const url = training ? `/treino/exercicios/${setplayId}/studio/cenas/reordenar` : `/playbook/setplays/${setplayId}/passos/reordenar`;
    const save = async () => {
      try {
        const response = await api(url, { method: "POST", body: JSON.stringify({ passo_ids: ids }) });
        if (!Array.isArray(response.passo_ids) || response.passo_ids.some((id, index) => id !== ids[index]) || response.passo_ids.length !== ids.length) {
          throw new Error("O servidor não confirmou a nova ordem.");
        }
        confirmedSceneIds = ids;
        if (revision === orderRevision) { unsavedOrder = false; refreshSaveStatus(); toast("Ordem das cenas guardada."); }
      } catch (error) {
        if (revision !== orderRevision) return;
        unsavedOrder = false;
        failedSaves.add("order");
        const positions = new Map(confirmedSceneIds.map((id, index) => [id, index]));
        scenes.sort((a, b) => (positions.get(a.id) ?? scenes.length) - (positions.get(b.id) ?? scenes.length));
        scenes.forEach((scene, index) => { scene.ordem = index; });
        previewPlan = null;
        renderScenes();
        document.querySelector("[data-scene-label]").textContent = `Cena ${scenes.findIndex(scene => scene.id === activeId) + 1}`;
        refreshSaveStatus();
        toast(`Ordem não guardada: ${error.message}`);
      }
    };
    orderSaveQueue = orderSaveQueue.then(save, save);
    return orderSaveQueue;
  }

  function moveScene(sourceId, targetId, before) {
    if (!sourceId || sourceId === targetId) return;
    const previousOrder = scenes.map(scene => scene.id);
    const sourceIndex = scenes.findIndex((scene) => scene.id === sourceId);
    let targetIndex = scenes.findIndex((scene) => scene.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const [scene] = scenes.splice(sourceIndex, 1);
    targetIndex = scenes.findIndex((candidate) => candidate.id === targetId);
    scenes.splice(targetIndex + (before ? 0 : 1), 0, scene);
    if (scenes.every((item, index) => item.id === previousOrder[index])) { clearDropMarks(); return; }
    scenes.forEach((item, index) => { item.ordem = index; });
    previewPlan = null;
    renderScenes();
    document.querySelector("[data-scene-label]").textContent = `Cena ${scenes.findIndex(item => item.id === activeId) + 1}`;
    persistSceneOrder();
  }

  async function addScene() {
    try {
      await orderSaveQueue;
      const previous = activeScene();
      if (previous && !imported) await saveScene(previous, true);
      const url = training ? `/treino/exercicios/${setplayId}/studio/cenas/novo` : `/playbook/setplays/${setplayId}/passos/novo`;
      const payload = await api(url, { method: "POST", body: JSON.stringify({ tipo: previous?.courtType || "meio" }) });
      const scene = normalizeScene(payload.passo);
      if (previous && !imported) {
        scene.courtType = previous.courtType;
        scene.objects = continuationObjects(previous);
      }
      scenes.push(scene); confirmedSceneIds = scenes.map(item => item.id); activeId = scene.id; renderScenes(); activateScene(scene.id);
      if (scene.objects.length) await saveScene(scene, true);
      toast(previous && !imported ? "Nova cena criada a partir da posição final." : "Nova cena adicionada.");
    } catch (error) { toast(error.message); }
  }

  async function duplicateScene(scene) {
    try {
      await orderSaveQueue;
      await saveScene(scene, true);
      const url = training ? `/treino/exercicios/${setplayId}/studio/cenas/${scene.id}/duplicar` : `/playbook/passos/${scene.id}/duplicar`;
      const payload = await api(url, { method: "POST", body: "{}" });
      const copy = normalizeScene(payload.passo); const index = scenes.indexOf(scene); scenes.splice(index + 1, 0, copy);
      confirmedSceneIds = scenes.map(item => item.id);
      activeId = copy.id; renderScenes(); activateScene(copy.id); toast("Cena duplicada.");
    } catch (error) { toast(error.message); }
  }

  async function deleteScene(scene) {
    if (!window.confirm("Eliminar esta cena?")) return;
    try {
      await orderSaveQueue;
      clearTimeout(saveTimers.get(scene.id)); saveTimers.delete(scene.id);
      clearTimeout(notesTimers.get(scene.id)); notesTimers.delete(scene.id);
      await Promise.all([saveQueues.get(scene.id), notesQueues.get(scene.id)]);
      const url = training ? `/treino/exercicios/${setplayId}/campos/${scene.id}/apagar` : `/playbook/passos/${scene.id}/eliminar`;
      await api(url, { method: "POST", body: "{}" });
      unsavedScenes.delete(scene.id); unsavedNotes.delete(scene.id);
      failedSaves.delete(`drawing:${scene.id}`); failedSaves.delete(`notes:${scene.id}`); refreshSaveStatus();
      const index = scenes.indexOf(scene); scenes.splice(index, 1); confirmedSceneIds = scenes.map(item => item.id);
      if (activeId === scene.id) activeId = scenes[Math.min(index, scenes.length - 1)]?.id || null;
      renderScenes(); activateScene(activeId); toast("Cena eliminada.");
    } catch (error) { if (unsavedScenes.has(scene.id)) saveScene(scene); if (unsavedNotes.has(scene.id)) saveNotes(scene, scene.observacao); toast(error.message); }
  }

  function activateScene(id) {
    if (activeId !== id && notes) saveNotes(activeScene(), notes.value, true);
    activeId = id; selectedId = null; gesture = null;
    const scene = activeScene();
    document.querySelector("[data-scene-label]").textContent = scene ? `Cena ${scenes.indexOf(scene) + 1}` : "Sem cenas";
    if (notes) notes.value = scene?.observacao || "";
    if (imported) {
      const image = document.querySelector("[data-imported-image]"); const empty = document.querySelector("[data-imported-empty]");
      const src = scene?.imagemCoach || scene?.desenho || ""; image.src = src; image.hidden = !src; empty.hidden = Boolean(src);
      setupImportedForms(scene);
    } else { syncCourt(scene); render(); convertLegacyScene(scene).catch((error) => toast(error.message)); updatePlayerNumber(nextPlayerNumber(scene)); }
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
    if (next.startsWith("jogador_")) updatePlayerNumber(nextPlayerNumber());
    render();
  }

  function playerNumber() {
    return Math.max(0, Math.min(99, Number(document.querySelector("[data-player-number]")?.value) || 0));
  }

  function addMarker(point) {
    const scene = activeScene(); if (!scene) return;
    const isPlayer = tool.startsWith("jogador_");
    const insertedTool = tool;
    const insertedNumber = isPlayer ? playerNumber() : null;
    snapshot(scene); scene.objects.push({ id: uid(), tipo: tool, x: point.x, y: point.y, tamanho: 1, numero: insertedNumber });
    if (isPlayer) updatePlayerNumber(Math.min(99, insertedNumber + 1));
    selectedId = scene.objects.at(-1).id;
    setTool(isPlayer ? insertedTool : "selecionar");
    saveScene(scene); renderTimeline(); render();
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
      if (straightLineTypes.has(gesture.object.tipo)) {
        if (points.length === 1) points.push(point); else points[1] = point;
      } else if (tool === "caneta" || curvedMovementTypes.has(gesture.object.tipo) || Math.hypot(point.x - last.x, point.y - last.y) > 8) points.push(point);
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
    if (wasDrawing && object && event.type !== "pointercancel") {
      const point = pointFromEvent(event);
      if (straightLineTypes.has(object.tipo)) {
        if (object.pontos.length === 1) object.pontos.push(point); else object.pontos[1] = point;
      } else if (Math.hypot(point.x - object.pontos.at(-1).x, point.y - object.pontos.at(-1).y) > 2) object.pontos.push(point);
      cleanDrawnLine(object);
    }
    if (wasDrawing && object?.pontos?.length >= 2) {
      if (pathLength(object.pontos) < 2) scene.objects.splice(scene.objects.indexOf(object), 1);
    } else if (wasDrawing && object) scene.objects.splice(scene.objects.indexOf(object), 1);
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
    const labels = { seta: "Movimento", seta_curva: "Movimento curvo", seta_tracejada: "Passe", seta_zigzag: "Drible", bloqueio: "Bloqueio", linha: "Indicação", lancamento: "Lançamento" };
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
    actions.forEach((object, index) => {
      const row = document.createElement("div"); row.className = "pbs-action"; row.dataset.actionId = object.id;
      const text = document.createElement("span"); text.className = "pbs-action-text"; const info = movementLabel(object, index);
      text.innerHTML = `<strong>${info.title}</strong><span>Movimento simultâneo</span>`;
      const remove = document.createElement("button"); remove.type = "button"; remove.ariaLabel = "Eliminar ação"; remove.textContent = "×";
      row.addEventListener("click", (event) => { if (!event.target.closest("button")) { selectedId = object.id; render(); } });
      remove.addEventListener("click", () => { const scene = activeScene(); snapshot(scene); scene.objects.splice(scene.objects.indexOf(object), 1); if (selectedId === object.id) selectedId = null; render(); renderTimeline(); saveScene(scene); });
      row.append(text, remove); holder.append(row);
    });
  }

  async function saveNotes(scene = activeScene(), value = notes?.value, immediate = false) {
    if (!scene || value === undefined || (value === scene.observacao && !unsavedNotes.has(scene.id))) return;
    clearTimeout(notesTimers.get(scene.id)); notesTimers.delete(scene.id);
    scene.observacao = value;
    const revision = scene.notesRevision = (scene.notesRevision || 0) + 1;
    unsavedNotes.add(scene.id); failedSaves.delete(`notes:${scene.id}`); refreshSaveStatus();
    const run = async () => {
      try {
        const url = training ? `/treino/exercicios/${setplayId}/studio/cenas/${scene.id}/observacao-json` : `/playbook/passos/${scene.id}/observacao-json`;
        await api(url, { method: "POST", body: JSON.stringify({ observacao: value }) });
        if (scene.notesRevision === revision) unsavedNotes.delete(scene.id);
        failedSaves.delete(`notes:${scene.id}`); refreshSaveStatus();
      } catch (error) { failedSaves.add(`notes:${scene.id}`); refreshSaveStatus(); toast(error.message); }
    };
    const enqueue = () => {
      notesTimers.delete(scene.id);
      const pending = (notesQueues.get(scene.id) || Promise.resolve()).then(run);
      notesQueues.set(scene.id, pending);
      pending.finally(() => { if (notesQueues.get(scene.id) === pending) notesQueues.delete(scene.id); });
      return pending;
    };
    if (immediate) await enqueue();
    else notesTimers.set(scene.id, setTimeout(enqueue, 550));
  }

  function setupImportedForms(scene) {
    const upload = document.querySelector("[data-image-form]"); const remove = document.querySelector("[data-delete-image-form]");
    if (upload) upload.action = scene ? `/playbook/passos/${scene.id}/imagem` : "";
    if (remove) { remove.action = scene ? `/playbook/passos/${scene.id}/imagem/eliminar` : ""; remove.hidden = !scene?.imagemCoach; }
  }

  function actionPlan(scene) {
    const actions = scene.objects.filter((object) => movementTypes.has(object.tipo) && object.pontos?.length > 1);
    return actions.length ? [{ key: scene.id, actions }] : [];
  }

  function nearestMarker(objects, start, predicate) {
    const candidates = objects.filter(predicate).sort((a, b) => (
      Math.hypot(a.x - start.x, a.y - start.y) - Math.hypot(b.x - start.x, b.y - start.y)
    ));
    const nearest = candidates[0];
    return nearest && Math.hypot(nearest.x - start.x, nearest.y - start.y) < 110 ? nearest : null;
  }

  function continuationObjects(scene) {
    const markers = scene.objects
      .filter((object) => markerTypes.has(object.tipo))
      .map((object) => ({ ...clone(object), id: uid() }));
    actionPlan(scene).forEach(group => applyMovementGroup(markers, group, 1));
    return markers;
  }

  function applyMovementGroup(objects, group, progress) {
    const changes = [];
    group.actions.forEach(action => {
      const start = action.pontos[0];
      const position = pointAlong(action.pontos, progress);
      const isBall = ["seta_tracejada", "lancamento"].includes(action.tipo);
      const actor = isBall
        ? nearestMarker(objects, start, object => object.tipo === "bola")
        : playerMovementTypes.has(action.tipo)
          ? nearestMarker(objects, start, object => object.tipo?.startsWith("jogador_")) : null;
      if (!actor) return;
      changes.push({ actor, position });
      if (action.tipo === "seta_zigzag") {
        const ball = nearestMarker(objects, actor, object => object.tipo === "bola");
        if (ball && Math.hypot(ball.x - actor.x, ball.y - actor.y) < 45) {
          changes.push({ actor: ball, position: { x: position.x + ball.x - actor.x, y: position.y + ball.y - actor.y } });
        }
      }
    });
    // Resolve simultaneous actions against the same starting positions.
    changes.forEach(({ actor, position }) => Object.assign(actor, position));
  }

  function pointAlong(points, progress) {
    if (!points?.length) return null;
    if (points.length === 1) return points[0];
    // Only immutable paths compiled for playback are cached.
    const cached = pathMetrics.get(points);
    const lengths = cached?.lengths || []; let total = cached?.total || 0;
    if (!cached) for (let index = 1; index < points.length; index += 1) { const length = Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y); lengths.push(length); total += length; }
    let wanted = total * progress;
    for (let index = 0; index < lengths.length; index += 1) {
      if (wanted <= lengths[index]) { const ratio = lengths[index] ? wanted / lengths[index] : 0; return { x: points[index].x + (points[index + 1].x - points[index].x) * ratio, y: points[index].y + (points[index + 1].y - points[index].y) * ratio }; }
      wanted -= lengths[index];
    }
    return points.at(-1);
  }

  function animatedObjects(scene, groupIndex, progress) {
    const objects = clone(scene.objects); const groups = actionPlan(scene);
    objects.forEach((object) => {
      if (movementTypes.has(object.tipo) || object.tipo === "caneta") object.hidden = true;
    });
    for (let index = 0; index <= groupIndex && index < groups.length; index += 1) {
      applyMovementGroup(objects, groups[index], index < groupIndex ? 1 : progress);
    }
    return objects;
  }

  function previewActor(action, objects) {
    const start = action.pontos[0];
    if (["seta_tracejada", "lancamento"].includes(action.tipo)) {
      return nearestMarker(objects, start, object => object.tipo === "bola");
    }
    return playerMovementTypes.has(action.tipo)
      ? nearestMarker(objects, start, object => object.tipo?.startsWith("jogador_")) : null;
  }

  function previewTransition(scene, nextScene) {
    if (!nextScene) return { actions: new Map(), targets: new Map(), moving: false };
    const markers = scene.objects.filter(object => markerTypes.has(object.tipo));
    const actions = new Map();
    (actionPlan(scene)[0]?.actions || []).forEach(action => {
      const actor = previewActor(action, markers);
      if (actor && !actions.has(actor.id)) actions.set(actor.id, action);
    });
    const targets = new Map();
    const scaleX = dimensions(scene).width / dimensions(nextScene || scene).width;
    const scaleY = dimensions(scene).height / dimensions(nextScene || scene).height;
    const available = (nextScene?.objects || []).filter(object => markerTypes.has(object.tipo))
      .map(object => ({ ...object, x: object.x * scaleX, y: object.y * scaleY }));
    const used = new Set();
    const assign = (marker, candidates) => {
      const expected = actions.get(marker.id)?.pontos.at(-1) || marker;
      const target = candidates.filter(candidate => !used.has(candidate))
        .sort((a, b) => Math.hypot(a.x - expected.x, a.y - expected.y) - Math.hypot(b.x - expected.x, b.y - expected.y))[0];
      if (target) { used.add(target); targets.set(marker.id, target); }
    };
    markers.forEach(marker => assign(marker, available.filter(candidate => candidate.tipo === marker.tipo && candidate.id === marker.id)));
    markers.forEach(marker => {
      if (targets.has(marker.id) || marker.numero == null) return;
      assign(marker, available.filter(candidate => candidate.tipo === marker.tipo && candidate.numero != null && String(candidate.numero) === String(marker.numero)));
    });
    while (true) {
      let closest = null;
      markers.filter(marker => !targets.has(marker.id)).forEach(marker => {
        const expected = actions.get(marker.id)?.pontos.at(-1) || marker;
        available.filter(candidate => !used.has(candidate) && candidate.tipo === marker.tipo
          && (marker.numero == null || candidate.numero == null)).forEach(candidate => {
          const distance = Math.hypot(candidate.x - expected.x, candidate.y - expected.y);
          if (!closest || distance < closest.distance) closest = { marker, candidate, distance };
        });
      });
      if (!closest) break;
      assign(closest.marker, [closest.candidate]);
    }
    const moved = markers.some(marker => {
      const target = targets.get(marker.id);
      return target && Math.hypot(target.x - marker.x, target.y - marker.y) > .01;
    });
    return { actions, targets, moving: actions.size > 0 || moved };
  }

  function animatedTransitionObjects(scene, transition, progress) {
    const objects = clone(scene.objects);
    objects.forEach(object => {
      if (movementTypes.has(object.tipo) || object.tipo === "caneta") object.hidden = true;
      if (!markerTypes.has(object.tipo)) return;
      const start = { x: object.x, y: object.y };
      const action = transition.actions.get(object.id);
      const target = transition.targets.get(object.id);
      if (action) {
        const pathStart = action.pontos[0], pathEnd = action.pontos.at(-1);
        const destination = target || pathEnd;
        const point = pointAlong(action.pontos, progress);
        object.x = point.x + (start.x - pathStart.x) * (1 - progress) + (destination.x - pathEnd.x) * progress;
        object.y = point.y + (start.y - pathStart.y) * (1 - progress) + (destination.y - pathEnd.y) * progress;
      } else if (target) {
        object.x = start.x + (target.x - start.x) * progress;
        object.y = start.y + (target.y - start.y) * progress;
      }
    });
    objects.filter(object => object.tipo === "bola" && !transition.actions.has(object.id)).forEach(ball => {
      const start = scene.objects.find(candidate => candidate.id === ball.id);
      const dribbler = scene.objects.find(candidate => transition.actions.get(candidate.id)?.tipo === "seta_zigzag"
        && Math.hypot(candidate.x - start.x, candidate.y - start.y) < 45);
      if (!dribbler) return;
      const movingPlayer = objects.find(candidate => candidate.id === dribbler.id);
      const finalPlayer = transition.targets.get(dribbler.id) || transition.actions.get(dribbler.id).pontos.at(-1);
      const target = transition.targets.get(ball.id);
      const offset = { x: start.x - dribbler.x, y: start.y - dribbler.y };
      ball.x = movingPlayer.x + offset.x + (target ? target.x - finalPlayer.x - offset.x : 0) * progress;
      ball.y = movingPlayer.y + offset.y + (target ? target.y - finalPlayer.y - offset.y : 0) * progress;
    });
    return objects;
  }

  function scenePreviewDuration(transition) {
    return PREVIEW_READ_MS + (imported || !transition.moving ? 0 : PREVIEW_MOVE_MS);
  }

  function previewDuration() {
    if (!previewPlan) preparePreview();
    return previewPlan.reduce((sum, item) => sum + item.duration, 0);
  }

  function preparePreview() {
    previewPlan = scenes.map((scene, index) => {
      const transition = previewTransition(scene, scenes[index + 1]);
      transition.actions.forEach(action => {
        const lengths = action.pontos.slice(1).map((point, i) => Math.hypot(point.x - action.pontos[i].x, point.y - action.pontos[i].y));
        pathMetrics.set(action.pontos, { lengths, total: lengths.reduce((a, b) => a + b, 0) });
      });
      return { scene, transition, duration: scenePreviewDuration(transition) };
    });
  }

  function previewAt(progress) {
    if (!previewPlan) preparePreview();
    let remaining = Math.max(0, Math.min(1, progress)) * previewDuration();
    for (let index = 0; index < scenes.length; index += 1) {
      const scene = scenes[index];
      const { duration, transition } = previewPlan[index];
      if (remaining < duration || index === scenes.length - 1) {
        const reading = imported || remaining < PREVIEW_READ_MS || !transition.moving;
        const elapsed = Math.max(0, remaining - PREVIEW_READ_MS);
        const local = Math.min(1, elapsed / PREVIEW_MOVE_MS);
        const objects = reading ? scene.objects : animatedTransitionObjects(scene, transition, local * local * (3 - 2 * local));
        return { scene, index, reading, objects };
      }
      remaining -= duration;
    }
    return { scene: null, index: 0, reading: true, objects: [] };
  }

  function renderPreview(progress) {
    const duration = previewDuration();
    const { scene, index, reading, objects } = previewAt(progress);
    document.querySelector("[data-preview-scene]").textContent = `Cena ${index + 1} de ${scenes.length} · ${reading ? "Desenho" : "Movimento"}`;
    document.querySelector("[data-preview-notes]").textContent = scene?.observacao || "Sem instruções.";
    const importedImage = document.querySelector("[data-preview-imported]");
    if (imported) {
      const src = scene?.imagemCoach || scene?.desenho || "";
      if (previewSceneId !== scene?.id) { previewSceneId = scene?.id; importedImage.src = src; fitPreviewCourt(); }
      importedImage.hidden = !src; previewCanvas.hidden = true;
      document.querySelector("[data-preview-court-image]").hidden = true;
    }
    else {
      importedImage.hidden = true; previewCanvas.hidden = false;
      const court = dimensions(scene); const wrap = document.querySelector(".pbs-preview-court");
      if (previewSceneId !== scene?.id) {
        previewSceneId = scene?.id;
        previewCanvas.width = court.width; previewCanvas.height = court.height; wrap.style.aspectRatio = `${court.width} / ${court.height}`;
        document.querySelector("[data-preview-court-image]").src = court.src;
        fitPreviewCourt();
      }
      render(previewCtx, objects, false);
    }
    document.querySelector("[data-preview-progress]").value = Math.round(progress * 1000);
    const seconds = Math.round(duration * progress / 1000);
    document.querySelector("[data-preview-time]").textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function previewTick(time) {
    if (!previewPlaying) return;
    const speed = Number(document.querySelector("[data-preview-speed]").value) || 1;
    if (previewLastTime !== null) previewElapsed += Math.max(0, time - previewLastTime) * speed;
    previewLastTime = time;
    const progress = Math.min(1, previewElapsed / Math.max(1, previewDuration())); renderPreview(progress);
    if (progress >= 1) { pausePreview(); return; }
    previewFrame = requestAnimationFrame(previewTick);
  }

  function togglePreview() {
    if (previewPlaying) { pausePreview(); return; }
    if (previewElapsed >= previewDuration()) previewElapsed = 0;
    previewPlaying = true; previewLastTime = null;
    const button = document.querySelector("[data-preview-play]"); button.textContent = "Ⅱ"; button.setAttribute("aria-label", "Pausar animação");
    cancelAnimationFrame(previewFrame); previewFrame = requestAnimationFrame(previewTick);
  }

  function pausePreview() {
    previewPlaying = false; previewLastTime = null; cancelAnimationFrame(previewFrame);
    const button = document.querySelector("[data-preview-play]"); button.textContent = "▶"; button.setAttribute("aria-label", "Reproduzir animação");
  }

  function seekPreview(progress) {
    pausePreview(); previewElapsed = progress * previewDuration(); renderPreview(progress);
  }

  function fitPreviewCourt() {
    const stage = document.querySelector(".pbs-preview-stage");
    const wrap = document.querySelector(".pbs-preview-court");
    if (!stage || !wrap) return;
    const court = dimensions(scenes.find(scene => scene.id === previewSceneId));
    const scale = Math.max(0, Math.min((stage.clientWidth - 24) / court.width, (stage.clientHeight - 24) / court.height));
    wrap.style.width = `${court.width * scale}px`; wrap.style.height = `${court.height * scale}px`;
  }

  async function openPreview() {
    if (!scenes.length) { toast("Adiciona uma cena antes de pré-visualizar."); return; }
    try { await Promise.all(scenes.map(convertLegacyScene)); }
    catch (error) { toast(error.message); return; }
    pausePreview(); previewElapsed = 0; previewSceneId = null; preparePreview();
    document.querySelector("[data-preview-dialog]").showModal(); renderPreview(0); togglePreview();
  }

  function closePreview() {
    pausePreview(); document.querySelector("[data-preview-dialog]").close();
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
    notes?.addEventListener("input", () => saveNotes()); notes?.addEventListener("blur", () => saveNotes(activeScene(), notes.value, true));
    document.querySelectorAll("[data-panel-tab]").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll("[data-panel-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === button.dataset.panelTab));
    }));
    document.querySelectorAll("[data-open-preview]").forEach((button) => button.addEventListener("click", openPreview)); document.querySelector("[data-close-preview]")?.addEventListener("click", closePreview);
    document.querySelector("[data-preview-play]")?.addEventListener("click", togglePreview);
    document.querySelector("[data-preview-restart]")?.addEventListener("click", () => { seekPreview(0); togglePreview(); });
    document.querySelector("[data-preview-progress]")?.addEventListener("input", event => seekPreview(Number(event.target.value) / 1000));
    document.querySelector("[data-preview-dialog]")?.addEventListener("close", pausePreview);
    document.addEventListener("visibilitychange", () => { if (document.hidden) pausePreview(); });
    window.addEventListener("resize", fitPreviewCourt);
    window.addEventListener("beforeunload", event => { if (unsavedScenes.size || unsavedNotes.size) { event.preventDefault(); event.returnValue = ""; } });
    document.querySelector("[data-retry-save]")?.addEventListener("click", async () => {
      for (const scene of scenes.filter(scene => unsavedScenes.has(scene.id))) { try { await saveScene(scene, true); } catch (error) { toast(error.message); } }
      for (const scene of scenes.filter(scene => unsavedNotes.has(scene.id))) await saveNotes(scene, scene.observacao, true);
    });
    document.querySelector("[data-open-details]")?.addEventListener("click", () => document.querySelector("[data-details-dialog]").showModal());
    document.querySelector("[data-details-form]")?.addEventListener("submit", saveDetails);
    document.querySelector("[data-share]")?.addEventListener("click", async () => { try { await navigator.clipboard.writeText(location.href); toast("Ligação copiada."); } catch (_) { toast("Não foi possível copiar a ligação."); } });
    document.querySelector("[data-mobile-scenes]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-scenes-panel")));
    document.querySelector("[data-mobile-tools]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-toolbar")));
    document.querySelector("[data-mobile-inspector]")?.addEventListener("click", () => closeMobilePanels(document.querySelector(".pbs-inspector")));
    document.addEventListener("keydown", (event) => {
      if (document.querySelector("dialog[open]")) return;
      if (event.target.matches("input,textarea,select")) return;
      const shortcuts = { v: "selecionar", a: "jogador_ataque", d: "jogador_defesa", m: "seta", p: "seta_tracejada", g: "seta_zigzag", l: "lancamento", e: "borracha" };
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      else if (["Backspace", "Delete"].includes(event.key) && selectedId) { const scene = activeScene(); const object = scene.objects.find((item) => item.id === selectedId); if (object) { snapshot(scene); scene.objects.splice(scene.objects.indexOf(object), 1); selectedId = null; render(); renderTimeline(); saveScene(scene); } }
      else if (shortcuts[event.key.toLowerCase()]) setTool(shortcuts[event.key.toLowerCase()]);
    });
  }

  async function init() {
    document.querySelectorAll('form[method="post"]').forEach((form) => { if (!form.querySelector('[name="csrf_token"]')) { const input = document.createElement("input"); input.type = "hidden"; input.name = "csrf_token"; input.value = csrf; form.prepend(input); } });
    bindEvents(); renderScenes();
    if (!scenes.length && !imported && !training) await addScene(); else activateScene(activeId);
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
