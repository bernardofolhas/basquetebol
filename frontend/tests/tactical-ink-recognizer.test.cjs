const test = require('node:test');
const assert = require('node:assert/strict');
const recognizer = require('../static/js/tactical-ink-recognizer.js');

const stroke = (pontos, id = Math.random()) => ({ id, tipo: 'caneta', cor: '#172033', largura: 4, pontos });
const line = (...pairs) => pairs.map(([x, y]) => ({ x, y }));
const arc = (cx, cy, rx, ry, start, end, steps = 30) => Array.from({ length: steps }, (_, i) => {
  const angle = start + (end - start) * i / (steps - 1);
  return { x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry };
});

test('converts a handwritten number to an attacker and preserves an unrelated movement line', () => {
  const three = stroke([
    ...arc(50, 35, 22, 18, -Math.PI / 2, Math.PI / 2, 15),
    ...arc(50, 70, 22, 18, -Math.PI / 2, Math.PI / 2, 15),
  ], 'three');
  const movement = stroke(line([140, 180], [220, 130], [310, 150]), 'movement');
  const result = recognizer.interpret([three, movement], { nextAttack: 1 });
  assert.equal(result.recognised, 1);
  assert.equal(result.objects.find(item => item.tipo === 'jogador_ataque').numero, 3);
  assert.equal(result.objects.find(item => item.id === 'movement'), movement);
});

test('converts a circled number to one attacker with a ball', () => {
  const circle = stroke(arc(100, 100, 48, 52, 0, Math.PI * 2), 'circle');
  const seven = stroke(line([80, 70], [118, 70], [94, 130]), 'seven');
  const result = recognizer.interpret([circle, seven]);
  assert.equal(result.recognised, 1);
  assert.equal(result.consumed, 2);
  assert.equal(result.objects.find(item => item.tipo === 'jogador_ataque').numero, 7);
  assert.ok(result.objects.some(item => item.tipo === 'bola'));
  assert.equal(result.objects.filter(item => item.tipo === 'caneta').length, 0);
});

test('converts two crossing strokes to a defender and keeps its sequential number', () => {
  const first = stroke(line([20, 20], [65, 70]), 'first');
  const second = stroke(line([65, 20], [20, 70]), 'second');
  const result = recognizer.interpret([first, second], { nextDefence: 4 });
  const defender = result.objects.find(item => item.tipo === 'jogador_defesa');
  assert.equal(result.recognised, 1);
  assert.equal(defender.numero, 4);
  assert.ok(Math.abs(defender.x - 42.5) < 1);
  assert.equal(result.nextDefence, 5);
});

test('converts a continuous handwritten cross to a defender', () => {
  const cross = stroke(line([20, 20], [65, 70], [65, 20], [20, 70]), 'cross');
  const result = recognizer.interpret([cross], { nextDefence: 2 });
  assert.equal(result.recognised, 1);
  assert.equal(result.objects[0].tipo, 'jogador_defesa');
  assert.equal(result.objects[0].numero, 2);
});

test('supports a two-digit handwritten player number', () => {
  const one = stroke(line([20, 28], [28, 20], [28, 80]), 'one');
  const seven = stroke(line([38, 20], [68, 20], [48, 80]), 'seven');
  const result = recognizer.interpret([one, seven]);
  assert.equal(result.recognised, 1);
  assert.equal(result.objects[0].tipo, 'jogador_ataque');
  assert.equal(result.objects[0].numero, 17);
});

test('recognises zero as a visible attacker number', () => {
  const zero = stroke(arc(50, 55, 20, 34, 0, Math.PI * 2), 'zero');
  const result = recognizer.interpret([zero]);
  assert.equal(result.recognised, 1);
  assert.equal(result.objects[0].tipo, 'jogador_ataque');
  assert.equal(result.objects[0].numero, 0);
});

test('does not alter the input and refuses unsafe large or incomplete shapes', () => {
  const original = [stroke(line([0, 0], [300, 260]), 'long'), stroke(arc(50, 50, 12, 10, 0, Math.PI), 'open')];
  const snapshot = JSON.stringify(original);
  const result = recognizer.interpret(original);
  assert.equal(result.recognised, 0);
  assert.equal(JSON.stringify(original), snapshot);
  assert.deepEqual(result.objects, original);
});
