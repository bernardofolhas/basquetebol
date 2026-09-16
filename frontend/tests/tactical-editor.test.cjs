const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const template = fs.readFileSync(path.join(root, 'templates/treino/plano.html'), 'utf8');
const editor = template.match(/<script>\s*(const CANVAS_ESTADO[\s\S]*?)<\/script>/)?.[1];
assert.ok(editor, 'O script do editor deve existir no plano de treino.');

function editorContext(toolbar = null) {
  const context = vm.createContext({
    document: {addEventListener() {}, getElementById: () => toolbar},
    window: {},
  });
  vm.runInContext(editor, context);
  return context;
}

function drawingContext() {
  const operations = [];
  const ctx = {};
  for (const name of ['save', 'restore', 'setLineDash', 'beginPath', 'moveTo', 'lineTo', 'quadraticCurveTo', 'stroke', 'clearRect']) {
    ctx[name] = (...args) => operations.push({name, args});
  }
  return {ctx, operations};
}

test('o formato curva conserva a acao selecionada', () => {
  const buttons = ['reta', 'curva'].map(formato => ({
    dataset: {formatoLinha: formato},
    classList: {toggle() {}},
    setAttribute(name, value) { this[name] = value; },
  }));
  const context = editorContext({querySelectorAll: () => buttons});
  vm.runInContext("CANVAS_ESTADO.campo = {ferramenta: 'seta_tracejada', formatoLinha: 'reta', linhaMultipla: null}", context);
  vm.runInContext("definirFormatoLinha('campo', 'curva')", context);
  assert.equal(vm.runInContext('CANVAS_ESTADO.campo.ferramenta', context), 'seta_tracejada');
  assert.equal(vm.runInContext('CANVAS_ESTADO.campo.formatoLinha', context), 'curva');
  assert.equal(buttons[1]['aria-pressed'], 'true');
});

test('todas as acoes mantem a sua identidade num percurso curvo', () => {
  const context = editorContext();
  const points = [{x: 10, y: 10}, {x: 20, y: 20}, {x: 30, y: 25}, {x: 40, y: 20}, {x: 50, y: 10}];
  for (const tipo of ['seta', 'seta_tracejada', 'seta_zigzag', 'lancamento', 'bloqueio', 'linha']) {
    const {ctx, operations} = drawingContext();
    context.ctx = ctx;
    context.linha = {tipo, curva: true, pontos: points, cor: '#172033', largura: 4};
    vm.runInContext('desenharLinhaMultipla(ctx, linha, null)', context);
    assert.ok(operations.some(operation => operation.name === 'stroke'), `${tipo} deve ser desenhado`);
    if (tipo === 'seta_zigzag') {
      assert.ok(operations.filter(operation => operation.name === 'lineTo').length > 4, 'O drible deve seguir a curva em zigzag.');
    } else {
      assert.ok(operations.some(operation => operation.name === 'quadraticCurveTo'), `${tipo} deve ter um percurso curvo`);
    }
    if (tipo === 'lancamento') {
      assert.ok(operations.filter(operation => operation.name === 'stroke').length >= 3, 'O lancamento deve ter duas linhas e a seta.');
    }
  }
});

test('o gesto curvo fica fixado como a acao escolhida', () => {
  for (const tipo of ['seta', 'seta_tracejada', 'seta_zigzag', 'lancamento', 'bloqueio', 'linha']) {
    const context = editorContext();
    const {ctx} = drawingContext();
    const canvas = {width: 100, height: 100, getBoundingClientRect: () => ({left: 0, top: 0, width: 100, height: 100})};
    ctx.canvas = canvas;
    context.est = {ctx, canvas, ferramenta: tipo, formatoLinha: 'curva', objectos: [], linhaMultipla: null, aDesconhar: false, posicaoCursor: null, larguraLinha: 4, corLinha: '#172033'};
    vm.runInContext('CANVAS_ESTADO.campo = est', context);
    vm.runInContext("aoPremir('campo', {clientX: 10, clientY: 10, button: 0})", context);
    vm.runInContext("aoMover('campo', {clientX: 30, clientY: 25})", context);
    vm.runInContext("aoMover('campo', {clientX: 50, clientY: 10})", context);
    vm.runInContext("aoSoltar('campo', {clientX: 50, clientY: 10})", context);
    assert.equal(context.est.objectos.length, 1, `${tipo} deve ficar guardado no campo`);
    assert.equal(context.est.objectos[0].tipo, tipo);
    assert.equal(context.est.objectos[0].curva, true);
    assert.ok(context.est.objectos[0].pontos.length >= 3);
  }
});
