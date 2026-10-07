const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function studio(options = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../static/js/playbook-studio.js'), 'utf8');
  const sandbox = { document: { querySelector: selector => selector === '[data-playbook-studio]' ? { dataset: {} } : null }, window: {}, ...options };
  vm.runInNewContext(source.replace('  init();', `
    globalThis.api = { drawLine, cleanDrawnLine, normalizeScene, stateFor, continuationObjects, moveScene,
      animatedObjects, previewAt, previewDuration, zigzagPoints, pointAlong, preparePreview,
      togglePreview, pausePreview, seekPreview, previewTick, saveScene, saveNotes, convertLegacyScene,
      times: { read: PREVIEW_READ_MS, move: PREVIEW_MOVE_MS },
      playback() { return { playing: previewPlaying, elapsed: previewElapsed }; },
      pending() { return { timers: saveTimers.size, queues: saveQueues.size, unsaved: Array.from(unsavedScenes) }; },
      orderPending() { return orderSaveQueue; },
      sceneIds() { return scenes.map(scene => scene.id); },
      setScenes(value) { scenes = value; previewPlan = null; activeId = value[0]?.id; confirmedSceneIds = value.map(scene => scene.id); } };
  `), sandbox);
  return sandbox.api;
}

function recordingCanvas() {
  let points = [];
  const strokes = [], fills = [];
  return {
    strokes, fills, save() {}, restore() {}, setLineDash() {},
    beginPath() { points = []; }, closePath() {},
    moveTo(x, y) { points.push({ x, y, move: true }); },
    lineTo(x, y) { points.push({ x, y }); },
    quadraticCurveTo(cx, cy, x, y) { points.push({ x, y }); },
    stroke() { strokes.push(points.slice()); }, fill() { fills.push(points.slice()); }
  };
}

const marker = (id, x, y, tipo = 'jogador_ataque') => ({ id, tipo, x, y });
const action = (id, tipo, pontos) => ({ id, tipo, pontos });
const scene = (id, objects) => ({ id, objects, courtType: 'meio', ordem: id });
const coordinates = point => ({ x: point.x, y: point.y });

function environment() {
  const nodes = new Map(), timers = new Map(), frames = new Map(), requests = [];
  let serial = 0;
  function node() {
    const classes = new Set();
    const el = { dataset: {}, style: {}, clientWidth: 800, clientHeight: 500, width: 702, height: 622,
      value: '1', lastChild: {}, append() {}, setAttribute() {}, toggleAttribute() {}, addEventListener() {}, querySelectorAll: () => [],
      toDataURL: () => 'data:image/png;base64,test',
      classList: { toggle(c, active) { active ? classes.add(c) : classes.delete(c); }, contains: c => classes.has(c), add: c => classes.add(c), remove: c => classes.delete(c) }
    };
    const ctx = new Proxy({ canvas: el }, { get: (target, key) => key in target ? target[key] : () => {} });
    el.getContext = () => ctx;
    return el;
  }
  const document = {
    querySelector(selector) {
      if (selector === '#pbs-studio-data') return { textContent: '{}' };
      if (selector === 'meta[name="csrf-token"]') return null;
      if (!nodes.has(selector)) nodes.set(selector, node());
      return nodes.get(selector);
    }, createElement: node
  };
  const options = { document, window: {}, FormData: class {}, Image: class {},
    setTimeout(fn) { const id = ++serial; timers.set(id, fn); return id; }, clearTimeout: id => timers.delete(id),
    requestAnimationFrame(fn) { const id = ++serial; frames.set(id, fn); return id; }, cancelAnimationFrame: id => frames.delete(id),
    async fetch(url, options) {
      const payload = JSON.parse(options.body);
      requests.push({ url, payload });
      return { ok: true, json: async () => url.endsWith('/reordenar')
        ? { sucesso: true, passo_ids: payload.passo_ids } : {} };
    }
  };
  document.querySelector('[data-playbook-studio]').dataset.setplayId = '1';
  return { options, nodes, frames, requests,
    async flush() { const pending = [...timers.values()]; timers.clear(); await Promise.all(pending.map(fn => fn())); },
    frame(time) { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(time)); }
  };
}

test('reordering scenes persists the new order and updates the active scene number', async () => {
  const env = environment(), api = studio(env.options);
  api.setScenes([scene(1, []), scene(2, []), scene(3, [])]);

  api.moveScene(1, 3, false);
  await api.orderPending();

  assert.deepEqual(api.sceneIds(), [2, 3, 1]);
  assert.equal(env.requests.length, 1);
  assert.equal(env.requests[0].url, '/playbook/setplays/1/passos/reordenar');
  assert.deepEqual(Array.from(env.requests[0].payload.passo_ids), [2, 3, 1]);
  assert.equal(env.nodes.get('[data-scene-label]').textContent, 'Cena 3');
  assert.equal(env.nodes.get('[data-save-state]').lastChild.textContent, 'Guardado');
});

test('rapid scene reorders reach the server in revision order', async () => {
  const env = environment();
  const originalFetch = env.options.fetch;
  let unblockFirst;
  const firstBlocked = new Promise(resolve => { unblockFirst = resolve; });
  let firstStarted;
  const firstRequest = new Promise(resolve => { firstStarted = resolve; });
  env.options.fetch = async (url, options) => {
    if (url.endsWith('/reordenar') && !env.requests.length) {
      firstStarted();
      await firstBlocked;
    }
    return originalFetch(url, options);
  };
  const api = studio(env.options);
  api.setScenes([scene(1, []), scene(2, []), scene(3, [])]);

  api.moveScene(1, 3, false);
  await firstRequest;
  api.moveScene(2, 1, false);
  assert.equal(env.requests.length, 0);
  unblockFirst();
  await api.orderPending();

  assert.deepEqual(api.sceneIds(), [3, 1, 2]);
  assert.deepEqual(env.requests.map(request => Array.from(request.payload.passo_ids)), [[2, 3, 1], [3, 1, 2]]);
  assert.equal(env.nodes.get('[data-save-state]').lastChild.textContent, 'Guardado');
});

test('a rejected scene order restores the last confirmed order', async () => {
  const env = environment();
  env.options.fetch = async () => ({ ok: false, json: async () => ({ erro: 'Falha de rede' }) });
  const api = studio(env.options);
  api.setScenes([scene(1, []), scene(2, []), scene(3, [])]);

  api.moveScene(1, 3, false);
  await api.orderPending();

  assert.deepEqual(api.sceneIds(), [1, 2, 3]);
  assert.equal(env.nodes.get('[data-scene-label]').textContent, 'Cena 1');
  assert.equal(env.nodes.get('[data-save-state]').lastChild.textContent, 'Não guardado');
  assert.match(env.nodes.get('[data-toast]').textContent, /Falha de rede/);
});

test('training exercise scenes use the training reorder endpoint', async () => {
  const env = environment();
  env.nodes.get('[data-playbook-studio]').dataset = { trainingExercise: 'true', setplayId: '42' };
  const api = studio(env.options);
  api.setScenes([scene(1, []), scene(2, [])]);

  api.moveScene(2, 1, true);
  await api.orderPending();

  assert.equal(env.requests[0].url, '/treino/exercicios/42/studio/cenas/reordenar');
  assert.deepEqual(api.sceneIds(), [2, 1]);
});

test('playback changes speed without jumping, resumes without wall-clock drift and schedules one frame', () => {
  const env = environment(), api = studio(env.options);
  api.setScenes([
    scene(1, [marker('p', 0, 0), action('a', 'seta', [{ x: 0, y: 0 }, { x: 200, y: 0 }])]),
    scene(2, [marker('p', 200, 0)])
  ]);
  api.preparePreview(); api.togglePreview();
  env.frame(0); env.frame(1000);
  assert.equal(api.playback().elapsed, 1000);
  env.nodes.get('[data-preview-speed]').value = '2';
  env.frame(1100);
  assert.equal(api.playback().elapsed, 1200);
  api.pausePreview(); assert.equal(env.frames.size, 0);
  api.togglePreview(); env.frame(9000);
  assert.equal(api.playback().elapsed, 1200);
  api.seekPreview(0); api.togglePreview();
  assert.equal(env.frames.size, 1);
  env.frame(10000); env.frame(12000);
  assert.equal(api.playback().playing, false);
  assert.equal(env.frames.size, 0);
});

test('autosave keeps pending drawings from different scenes and snapshots the latest edit', async () => {
  const env = environment(), api = studio(env.options);
  const a = scene(1, []), b = scene(2, []); api.setScenes([a, b]);
  await api.saveScene(a); await api.saveScene(b);
  a.objects.push(marker('p', 10, 20)); await api.saveScene(a);
  assert.equal(api.pending().timers, 2);
  await env.flush();
  assert.equal(env.requests.length, 2);
  assert.equal(env.requests.find(r => r.url.includes('/1/')).payload.estado.objectos[0].x, 10);
  assert.equal(api.pending().unsaved.length, 0);
});

test('training scenes save drawings and notes through exercise routes', async () => {
  const env = environment();
  Object.assign(env.options.document.querySelector('[data-playbook-studio]').dataset, { trainingExercise: 'true', setplayId: '42' });
  const api = studio(env.options), field = scene(5, [marker('p', 10, 20)]);
  api.setScenes([field]);
  await api.saveScene(field, true);
  await api.saveNotes(field, 'Passar e cortar', true);

  assert.equal(env.requests[0].url, '/treino/exercicios/42/desenho');
  assert.equal(env.requests[0].payload.numero, 5);
  assert.equal(env.requests[0].payload.estado.campoTipo, 'meio');
  assert.equal(env.requests[1].url, '/treino/exercicios/42/studio/cenas/5/observacao-json');
  assert.equal(env.requests[1].payload.observacao, 'Passar e cortar');
});

test('a legacy exercise drawing is converted before the Studio saves it', async () => {
  const env = environment();
  env.options.window.TacticalLegacy = {
    decomporImagem: () => [{ tipo: 'recorte', x: 4, y: 8 }],
    aguardarRecortes: async () => {},
    eRecorte: () => false
  };
  env.options.Image = class {
    set src(value) { this.value = value; queueMicrotask(() => this.onload()); }
  };
  const api = studio(env.options);
  const field = api.normalizeScene({ id: 1, desenho: 'data:image/png;base64,dGVzdA==', estado: { campoTipo: 'meio' } });
  api.setScenes([field]);
  await api.saveScene(field, true);

  assert.equal(env.requests[0].payload.estado.objectos.length, 1);
  assert.equal(field.converted, true);
});

test('notes retain their original scene and a drawing success cannot hide a failed save', async () => {
  const env = environment();
  const fetch = env.options.fetch;
  env.options.fetch = async (url, options) => {
    if (url.includes('/1/observacao')) throw new Error('offline');
    return fetch(url, options);
  };
  const api = studio(env.options), a = scene(1, []), b = scene(2, []);
  api.setScenes([a, b]);
  await api.saveNotes(a, 'Instrucoes da primeira'); await api.saveNotes(b, 'Instrucoes da segunda');
  await env.flush(); await api.saveScene(b, true);
  assert.equal(env.requests.find(r => r.url.includes('/2/observacao')).payload.observacao, 'Instrucoes da segunda');
  assert.equal(env.nodes.get('[data-save-state]').classList.contains('is-error'), true);
  env.options.fetch = fetch;
});

test('an HTML login response never reports a drawing as saved', async () => {
  const env = environment();
  env.options.fetch = async () => ({ ok: true, redirected: true, json: async () => { throw new Error('HTML'); } });
  const api = studio(env.options), a = scene(1, []); api.setScenes([a]);
  await assert.rejects(api.saveScene(a, true), /Guarda a cena/);
  assert.equal(api.pending().unsaved.length, 1);
  assert.equal(env.nodes.get('[data-save-state]').classList.contains('is-error'), true);
});

test('successive saves of one scene reach the server in revision order', async () => {
  const env = environment(), fetch = env.options.fetch;
  let release, entered;
  const firstStarted = new Promise(resolve => { entered = resolve; });
  const blocked = new Promise(resolve => { release = resolve; });
  env.options.fetch = async (url, options) => { if (!env.requests.length) { entered(); await blocked; } return fetch(url, options); };
  const api = studio(env.options), a = scene(1, [marker('p', 10, 20)]); api.setScenes([a]);
  const first = api.saveScene(a, true); await firstStarted;
  a.objects[0].x = 30; const second = api.saveScene(a, true);
  release(); await Promise.all([first, second]);
  assert.deepEqual(env.requests.map(r => r.payload.estado.objectos[0].x), [10, 30]);
  assert.equal(api.pending().unsaved.length, 0);
});

test('arrow tips end at the gesture endpoint and shafts stop before the triangle', () => {
  const api = studio();
  for (const tipo of ['seta', 'seta_tracejada', 'seta_zigzag', 'lancamento']) {
    for (const pontos of [
      [{ x: 0, y: 0 }, { x: 120, y: 0 }],
      [{ x: 0, y: 0 }, { x: 50, y: 70 }, { x: 120, y: 90 }, { x: 120, y: 90 }],
      [{ x: 4, y: 2 }, { x: 0, y: 2 }]
    ]) {
      const ctx = recordingCanvas();
      api.drawLine(ctx, action('a', tipo, pontos));
      assert.deepEqual(coordinates(ctx.fills[0][0]), pontos.at(-1));
      assert.notDeepEqual(coordinates(ctx.strokes[0].at(-1)), pontos.at(-1));
      assert.equal(ctx.lineCap, 'butt');
      assert.ok(ctx.strokes.flat().every(p => Number.isFinite(p.x) && Number.isFinite(p.y)));
    }
  }
});

test('curved dribble has a smooth oscillation on both sides of its trajectory', () => {
  const api = studio();
  const object = action('d', 'seta_zigzag', Array.from({ length: 41 }, (_, i) => ({ x: i * 5, y: 70 * Math.sin(i / 40 * Math.PI) })));
  api.cleanDrawnLine(object);
  assert.equal(object.curva, true);
  assert.ok(Math.max(...object.pontos.map(p => p.y)) > 60);
  const wave = api.zigzagPoints(object.pontos);
  const offsets = wave.slice(1, -1).map((p, i) => {
    const t = (i + 1) / (wave.length - 1);
    const centre = api.pointAlong(object.pontos, t);
    const before = api.pointAlong(object.pontos, Math.max(0, t - .01));
    const after = api.pointAlong(object.pontos, Math.min(1, t + .01));
    return (after.x - before.x) * (p.y - centre.y) - (after.y - before.y) * (p.x - centre.x);
  });
  assert.ok(offsets.some(value => value > 1));
  assert.ok(offsets.some(value => value < -1));
  const ctx = recordingCanvas();
  api.drawLine(ctx, object);
  assert.ok(ctx.strokes[0].length > 30);
});

test('a hand-drawn single bend becomes a regular curve with fixed endpoints', () => {
  const api = studio();
  const points = Array.from({ length: 25 }, (_, i) => ({
    x: i * 10,
    y: 55 * Math.sin(i / 24 * Math.PI) + (i % 3 - 1) * 4
  }));
  const object = action('arc', 'seta', points);
  api.cleanDrawnLine(object);
  assert.equal(object.curva, true);
  assert.deepEqual(coordinates(object.pontos[0]), points[0]);
  assert.deepEqual(coordinates(object.pontos.at(-1)), points.at(-1));
  const secondDifferences = object.pontos.slice(2).map((p, i) =>
    p.y - 2 * object.pontos[i + 1].y + object.pontos[i].y
  );
  assert.ok(Math.max(...secondDifferences) - Math.min(...secondDifferences) < 1e-6);
});

test('circular movement keeps its shape and saved geometry does not drift on reload', () => {
  const api = studio();
  const object = action('d', 'seta_zigzag', Array.from({ length: 61 }, (_, i) => ({ x: 150 + 70 * Math.cos(i / 60 * Math.PI * 2), y: 150 + 70 * Math.sin(i / 60 * Math.PI * 2) })));
  api.cleanDrawnLine(object);
  assert.ok(Math.max(...object.pontos.map(p => p.x)) - Math.min(...object.pontos.map(p => p.x)) > 130);
  assert.ok(Math.max(...object.pontos.map(p => p.y)) - Math.min(...object.pontos.map(p => p.y)) > 130);
  const original = JSON.stringify(object.pontos);
  let current = scene(1, [object]);
  for (let i = 0; i < 3; i++) current = api.normalizeScene({ id: 1, estado: api.stateFor(current) });
  assert.equal(JSON.stringify(current.objects[0].pontos), original);
});

test('shot draws two separated shafts and moves only the ball', () => {
  const api = studio(), ctx = recordingCanvas();
  const shot = action('shot', 'lancamento', [{ x: 0, y: 0 }, { x: 200, y: 0 }]);
  api.drawLine(ctx, shot);
  const starts = ctx.strokes[0].filter(p => p.move);
  assert.equal(starts.length, 2);
  assert.equal(Math.abs(starts[0].y - starts[1].y), 10);
  const initial = scene(1, [marker('p', 0, 0), marker('ball', 0, 0, 'bola'), shot]);
  const halfway = api.animatedObjects(initial, 0, .5);
  assert.equal(halfway.find(o => o.id === 'p').x, 0);
  assert.equal(halfway.find(o => o.id === 'ball').x, 100);
  const next = api.continuationObjects(initial);
  assert.equal(next.find(o => o.tipo === 'bola').x, 200);
  assert.equal(next.length, 2);
});

test('preview reads each scene then moves all its players together before advancing', () => {
  const api = studio();
  const first = scene(1, [marker('p', 0, 0), marker('other', 200, 0),
    action('a', 'seta', [{ x: 0, y: 0 }, { x: 200, y: 0 }]),
    action('b', 'seta', [{ x: 200, y: 0 }, { x: 400, y: 0 }]),
    action('note', 'caneta', [{ x: 0, y: 100 }, { x: 30, y: 100 }])]);
  const second = scene(2, [marker('q', 400, 0), action('c', 'seta', [{ x: 400, y: 0 }, { x: 500, y: 0 }])]);
  const original = JSON.stringify([first, second]);
  api.setScenes([first, second]);
  const at = ms => api.previewAt(ms / api.previewDuration());
  assert.equal(at(0).reading, true);
  assert.ok(at(400).objects.every(o => !o.hidden));
  const movement = at(1125);
  assert.equal(movement.reading, false);
  assert.ok(movement.objects.filter(o => o.pontos).every(o => o.hidden));
  assert.equal(movement.objects.find(o => o.id === 'p').x, 100);
  assert.equal(movement.objects.find(o => o.id === 'other').x, 300);
  assert.equal(api.previewDuration(), 2 * api.times.read + api.times.move);
  assert.equal(at(1550).scene.id, 2);
  assert.equal(at(1550).reading, true);
  assert.ok(at(1550).objects.every(o => !o.hidden));
  assert.equal(at(1900).objects.find(o => o.id === 'q').x, 400);
  assert.equal(api.previewAt(1).objects.find(o => o.id === 'q').x, 400);
  assert.equal(JSON.stringify([first, second]), original);
});

test('compiled playback is repeatable when seeking backwards and leaves saved scenes untouched', () => {
  const api = studio();
  const initial = scene(1, [marker('p', 0, 0), marker('other', 200, 0),
    action('a', 'seta', [{ x: 0, y: 0 }, { x: 200, y: 0 }]),
    action('b', 'seta_zigzag', [{ x: 200, y: 0 }, { x: 300, y: 100 }, { x: 400, y: 0 }])]);
  const final = scene(2, [marker('p', 200, 0), marker('other', 400, 0)]);
  const original = JSON.stringify([initial, final]);
  api.setScenes([initial, final]); api.preparePreview();
  const at = ms => api.previewAt(ms / api.previewDuration());
  assert.equal(at(1125).objects.find(o => o.id === 'p').x, 100);
  assert.equal(at(1125).objects.find(o => o.id === 'other').x, 300);
  assert.equal(at(1125).objects.find(o => o.id === 'other').y, 100);
  assert.equal(api.previewAt(1).objects.find(o => o.id === 'p').x, 200);
  assert.equal(api.previewAt(1).objects.find(o => o.id === 'other').x, 400);
  assert.equal(at(1125).objects.find(o => o.id === 'p').x, 100);
  assert.equal(at(1125).objects.find(o => o.id === 'other').y, 100);
  assert.ok(at(1125).objects.filter(o => o.pontos).every(o => o.hidden));
  assert.equal(at(100).reading, true);
  assert.equal(JSON.stringify([initial, final]), original);
});

test('short trajectory segments interpolate continuously', () => {
  const api = studio();
  assert.equal(api.pointAlong([{ x: 0, y: 0 }, { x: .5, y: 0 }], .5).x, .25);
});

test('movements start together even with different legacy groups and static scenes stay visible', () => {
  const api = studio();
  const a = action('a', 'seta', [{ x: 0, y: 0 }, { x: 150, y: 0 }]);
  const b = action('b', 'seta', [{ x: 150, y: 0 }, { x: 300, y: 0 }]);
  a.grupo = 'first'; b.grupo = 'second';
  const output = api.animatedObjects(scene(1, [marker('p1', 0, 0), marker('p2', 150, 0), a, b]), 0, .5);
  assert.equal(output.find(o => o.id === 'p1').x, 75);
  assert.equal(output.find(o => o.id === 'p2').x, 225);
  api.setScenes([
    scene(1, [marker('p1', 0, 0), marker('p2', 150, 0), a, b]),
    scene(2, [marker('p1', 150, 0), marker('p2', 300, 0)])
  ]);
  api.preparePreview();
  assert.equal(api.previewDuration(), 2 * api.times.read + api.times.move);
  assert.equal(api.previewAt(1125 / api.previewDuration()).objects.find(o => o.id === 'p2').x, 225);
  api.setScenes([scene(1, [marker('p', 10, 20)])]);
  assert.equal(api.previewAt(1).reading, true);
});

test('a player movement and a pass share the same playback interval', () => {
  const api = studio();
  api.setScenes([
    scene(1, [
      marker('player', 0, 0), marker('ball', 300, 0, 'bola'),
      action('run', 'seta', [{ x: 0, y: 0 }, { x: 200, y: 0 }]),
      action('pass', 'seta_tracejada', [{ x: 300, y: 0 }, { x: 500, y: 0 }])
    ]),
    scene(2, [marker('player', 200, 0), marker('ball', 500, 0, 'bola')])
  ]);
  api.preparePreview();
  const halfway = api.previewAt(1125 / api.previewDuration()).objects;
  assert.equal(halfway.find(o => o.id === 'player').x, 100);
  assert.equal(halfway.find(o => o.id === 'ball').x, 400);
});

test('the last scene keeps its drawn positions even when it contains arrows', () => {
  const api = studio();
  const last = scene(1, [marker('player', 20, 30), marker('ball', 25, 35, 'bola'),
    action('run', 'seta', [{ x: 20, y: 30 }, { x: 200, y: 30 }]),
    action('shot', 'lancamento', [{ x: 25, y: 35 }, { x: 300, y: 50 }])]);
  const original = JSON.stringify(last);
  api.setScenes([last]);

  assert.equal(api.previewDuration(), api.times.read);
  for (const progress of [0, .5, 1]) {
    const frame = api.previewAt(progress);
    assert.equal(frame.reading, true);
    assert.deepEqual(coordinates(frame.objects.find(o => o.id === 'player')), { x: 20, y: 30 });
    assert.deepEqual(coordinates(frame.objects.find(o => o.id === 'ball')), { x: 25, y: 35 });
    assert.ok(frame.objects.filter(o => o.pontos).every(o => !o.hidden));
  }
  assert.equal(JSON.stringify(last), original);
});

test('the next scene fixes the destination even when the drawn path ends elsewhere', () => {
  const api = studio();
  const firstPlayer = { ...marker('first-player', 10, 20), numero: 1 };
  const nextPlayer = { ...marker('next-player', 150, 40), numero: 1 };
  const first = scene(1, [firstPlayer,
    action('run', 'seta_curva', [{ x: 12, y: 20 }, { x: 60, y: 80 }, { x: 100, y: 20 }])]);
  const second = scene(2, [nextPlayer]);
  const original = JSON.stringify([first, second]);
  api.setScenes([first, second]);
  const at = ms => api.previewAt(ms / api.previewDuration());

  assert.equal(at(700).objects.find(o => o.id === 'first-player').x, 10);
  const halfway = at(1125).objects.find(o => o.id === 'first-player');
  const pathMidpoint = api.pointAlong(first.objects[1].pontos, .5);
  assert.ok(Math.abs(halfway.x - (pathMidpoint.x + 24)) < 1e-9);
  assert.ok(Math.abs(halfway.y - (pathMidpoint.y + 10)) < 1e-9);
  assert.ok(Math.abs(at(1549).objects.find(o => o.id === 'first-player').x - 150) < .1);
  assert.deepEqual(coordinates(at(1550).objects.find(o => o.id === 'next-player')), { x: 150, y: 40 });
  assert.equal(JSON.stringify([first, second]), original);
});

test('players without drawn paths still arrive at their trainer-defined next positions', () => {
  const api = studio();
  const first = scene(1, [
    { ...marker('attack-old', 20, 20), numero: 1 },
    { ...marker('defense-old', 100, 20, 'jogador_defesa'), numero: 1 }
  ]);
  const second = scene(2, [
    { ...marker('defense-new', 80, 60, 'jogador_defesa'), numero: 1 },
    { ...marker('attack-new', 160, 80), numero: 1 }
  ]);
  api.setScenes([first, second]);
  assert.equal(api.previewDuration(), 2 * api.times.read + api.times.move);
  const halfway = api.previewAt(1125 / api.previewDuration()).objects;
  assert.deepEqual(coordinates(halfway.find(o => o.id === 'attack-old')), { x: 90, y: 50 });
  assert.deepEqual(coordinates(halfway.find(o => o.id === 'defense-old')), { x: 90, y: 40 });
  assert.deepEqual(coordinates(api.previewAt(1550 / api.previewDuration()).objects.find(o => o.id === 'attack-new')), { x: 160, y: 80 });
});

test('a dribbler and the ball finish at the positions placed in the next scene', () => {
  const api = studio();
  const first = scene(1, [
    { ...marker('player-old', 10, 10), numero: 1 }, marker('ball-old', 18, 14, 'bola'),
    action('dribble', 'seta_zigzag', [{ x: 10, y: 10 }, { x: 60, y: 80 }, { x: 110, y: 10 }])
  ]);
  const second = scene(2, [
    { ...marker('player-new', 150, 30), numero: 1 }, marker('ball-new', 160, 35, 'bola')
  ]);
  api.setScenes([first, second]);
  const halfway = api.previewAt(1125 / api.previewDuration()).objects;
  assert.equal(halfway.find(o => o.id === 'player-old').y, 90);
  assert.equal(halfway.find(o => o.id === 'ball-old').y, 94.5);
  const next = api.previewAt(1550 / api.previewDuration()).objects;
  assert.deepEqual(coordinates(next.find(o => o.id === 'player-new')), { x: 150, y: 30 });
  assert.deepEqual(coordinates(next.find(o => o.id === 'ball-new')), { x: 160, y: 35 });
});

test('a different numbered player is not mistaken for the previous actor', () => {
  const api = studio();
  api.setScenes([
    scene(1, [{ ...marker('old', 0, 0), numero: 1 }, action('run', 'seta', [{ x: 0, y: 0 }, { x: 100, y: 0 }])]),
    scene(2, [{ ...marker('new', 300, 0), numero: 2 }])
  ]);
  const before = api.previewAt(1549 / api.previewDuration()).objects.find(o => o.id === 'old');
  assert.ok(Math.abs(before.x - 100) < .1);
});
