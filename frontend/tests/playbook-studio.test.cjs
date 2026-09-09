const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function studio() {
  const source = fs.readFileSync(path.join(__dirname, '../static/js/playbook-studio.js'), 'utf8');
  const sandbox = { document: { querySelector: selector => selector === '[data-playbook-studio]' ? { dataset: {} } : null }, window: {} };
  vm.runInNewContext(source.replace('  init();', `
    globalThis.api = { drawLine, cleanDrawnLine, normalizeScene, stateFor, continuationObjects,
      animatedObjects, previewAt, previewDuration, zigzagPoints, pointAlong,
      setScenes(value) { scenes = value; } };
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

test('preview reads each whole scene then hides drawings for all movements and preserves completed positions', () => {
  const api = studio();
  const first = scene(1, [marker('p', 0, 0),
    action('a', 'seta', [{ x: 0, y: 0 }, { x: 200, y: 0 }]),
    action('b', 'seta', [{ x: 200, y: 0 }, { x: 400, y: 0 }]),
    action('note', 'caneta', [{ x: 0, y: 100 }, { x: 30, y: 100 }])]);
  const second = scene(2, [marker('q', 400, 0), action('c', 'seta', [{ x: 400, y: 0 }, { x: 500, y: 0 }])]);
  const original = JSON.stringify([first, second]);
  api.setScenes([first, second]);
  const at = ms => api.previewAt(ms / api.previewDuration());
  assert.equal(at(0).reading, true);
  assert.ok(at(1000).objects.every(o => !o.hidden));
  const movement = at(2150);
  assert.equal(movement.reading, false);
  assert.ok(movement.objects.filter(o => o.pontos).every(o => o.hidden));
  assert.equal(movement.objects.find(o => o.id === 'p').x, 100);
  assert.equal(at(2900).objects.find(o => o.id === 'p').x, 200);
  assert.equal(at(3650).objects.find(o => o.id === 'p').x, 300);
  assert.equal(at(4400).scene.id, 2);
  assert.equal(at(4400).reading, true);
  assert.ok(at(4400).objects.every(o => !o.hidden));
  assert.equal(api.previewAt(1).objects.find(o => o.id === 'q').x, 500);
  assert.equal(JSON.stringify([first, second]), original);
});

test('simultaneous grouped movements start together and static scenes stay visible', () => {
  const api = studio();
  const a = action('a', 'seta', [{ x: 0, y: 0 }, { x: 150, y: 0 }]);
  const b = action('b', 'seta', [{ x: 150, y: 0 }, { x: 300, y: 0 }]);
  a.grupo = b.grupo = 'together';
  const output = api.animatedObjects(scene(1, [marker('p1', 0, 0), marker('p2', 150, 0), a, b]), 0, .5);
  assert.equal(output.find(o => o.id === 'p1').x, 75);
  assert.equal(output.find(o => o.id === 'p2').x, 225);
  api.setScenes([scene(1, [marker('p', 10, 20)])]);
  assert.equal(api.previewAt(1).reading, true);
});
