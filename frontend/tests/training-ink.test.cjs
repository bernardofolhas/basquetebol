const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname, '../templates/treino/plano.html'), 'utf8');
const script = template.match(/<script>\s*(const CANVAS_ESTADO[\s\S]*?)<\/script>/)[1];

function setup() {
  const listeners = {};
  const images = [];
  const timers = new Map();
  let timerId = 0;
  const status = {dataset: {}};
  const makeContext = () => Object.fromEntries(['save', 'restore', 'setLineDash', 'beginPath', 'moveTo', 'lineTo', 'quadraticCurveTo', 'stroke', 'clearRect', 'drawImage'].map(name => [name, () => {}]));
  const canvas = {
    id: 'court', width: 887, height: 777, style: {},
    dataset: {trainingInk: '', campoTipo: 'meio', exercicioId: '42', campoNumero: '1'},
    getBoundingClientRect: () => ({left: 0, top: 0, width: 887, height: 777}),
    closest: () => ({querySelector: () => status}),
    addEventListener: (type, callback) => { listeners[type] = callback; },
    setPointerCapture() {}, releasePointerCapture() {},
  };
  canvas.getContext = () => ctx;
  const ctx = makeContext();
  ctx.canvas = canvas;
  const calls = [];
  const context = vm.createContext({
    document: {
      addEventListener() {},
      getElementById: id => id === 'court' ? canvas : null,
      querySelector: () => null,
      createElement: () => {
        const output = {toDataURL: () => 'data:image/png;base64,export'};
        output.getContext = () => Object.assign(makeContext(), {canvas: output});
        return output;
      },
    },
    window: {PointerEvent: true, confirm: () => true},
    Image: class { set src(value) { this.value = value; images.push(this); } get src() { return this.value; } },
    setTimeout: callback => { const id = ++timerId; timers.set(id, callback); return id; },
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => { calls.push(JSON.parse(options.body)); return {ok: true, json: async () => ({sucesso: true})}; },
  });
  vm.runInContext(script, context);
  const run = code => vm.runInContext(code, context);
  const event = (type, pointerType = 'pen', extra = {}) => {
    const e = {type, pointerType, pointerId: 7, button: 0, buttons: 1, clientX: 10, clientY: 10, preventDefault() {}, ...extra};
    listeners[type]?.(e);
  };
  const stroke = () => {
    event('pointerdown');
    event('pointermove', 'pen', {clientX: 40, clientY: 40});
    event('pointerup', 'pen', {clientX: 50, clientY: 50});
  };
  return {context, run, event, stroke, canvas, calls, status, timers, images};
}

test('plano oferece caneta e campos inline sem Studio, dialogo ou formularios aninhados', () => {
  assert.ok(template.includes('data-training-ink'));
  assert.ok(template.includes('data-court-template="meio"'));
  assert.ok(template.includes('data-court-template="completo"'));
  assert.ok(!template.includes('/studio'));
  assert.ok(!template.includes('modal_desenho_'));
  const macro = template.split('{% macro campo_desenho')[1].split('{% endmacro %}')[0];
  assert.ok(!macro.includes('<form'));
  assert.ok(!macro.includes('tactical_toolbar'));
});

test('primeiro campo de um exercicio criado sem recarregar e inicializado', () => {
  const fluxo = template.split('async function adicionarExercicioSemRecarregar(evento) {')[1]
    .split("addForm?.addEventListener('submit', adicionarExercicioSemRecarregar)")[0];
  assert.match(fluxo, /novoCartao\.querySelectorAll\('canvas\[data-training-ink\]'\)\.forEach\(canvas => inicializarDesenho\(canvas\.id\)\)/);
  assert.ok(fluxo.indexOf("novoCartao.querySelectorAll('canvas[data-training-ink]')") < fluxo.indexOf('addForm.reset()'));
});

test('so a caneta desenha; rato, dedo e uma segunda caneta nao alteram o traco', async () => {
  const h = setup();
  await h.run("inicializarDesenho('court')");
  for (const type of ['mouse', 'touch']) {
    h.event('pointerdown', type);
    h.event('pointermove', type, {clientX: 90});
    h.event('pointerup', type);
  }
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 0);
  h.event('pointerdown');
  h.event('pointermove', 'touch', {pointerId: 8, clientX: 900});
  h.event('pointerdown', 'pen', {pointerId: 9});
  h.event('pointermove', 'pen', {clientX: 20});
  h.event('pointerup', 'pen', {clientX: 30});
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  assert.equal(h.run('CANVAS_ESTADO.court.objectos[0].pontos.at(-1).x'), 30);
  assert.equal(h.run('CANVAS_ESTADO.court.pointerActivo'), null);
});

test('cancelamento restaura o estado anterior sem deixar riscos nem borracha pendente', async () => {
  const h = setup();
  await h.run("inicializarDesenho('court')");
  h.stroke();
  h.event('pointerdown');
  h.event('pointermove', 'pen', {clientX: 80});
  h.event('pointercancel');
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  assert.equal(h.run('CANVAS_ESTADO.court.linhaMultipla'), null);
  h.event('pointerdown', 'pen', {button: 5, buttons: 32});
  h.event('lostpointercapture');
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  assert.equal(h.run('CANVAS_ESTADO.court.apagarComPonteiro'), false);
});

test('amostras da caneta, desfazer e limpar conservam o desenho e o historico', async () => {
  const h = setup();
  await h.run("inicializarDesenho('court')");
  h.event('pointerdown');
  h.event('pointermove', 'pen', {clientX: 50, getCoalescedEvents: () => [{clientX: 20, clientY: 20}, {clientX: 30, clientY: 30}]});
  h.event('pointerup', 'pen', {clientX: 60});
  assert.ok(h.run('CANVAS_ESTADO.court.objectos[0].pontos.length') >= 5);
  h.run("limparCampoTreino('court')");
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 0);
  h.run("desfazerTracoTreino('court')");
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  h.run("desfazerTracoTreino('court')");
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 0);
});

test('estado antigo conserva metadados e e escalado uma so vez independentemente do tamanho visual', async () => {
  const h = setup();
  h.canvas.dataset.estado = JSON.stringify({largura: 100, altura: 100, actions: [{id: 'original'}], objectos: [{tipo: 'caneta', pontos: [{x: 10, y: 10}, {x: 20, y: 20}], largura: 1}]});
  await h.run("inicializarDesenho('court')");
  h.canvas.getBoundingClientRect = () => ({left: 0, top: 0, width: 100, height: 100});
  await h.run("inicializarDesenho('court')");
  const state = h.run('estadoDesenhoParaGuardar(CANVAS_ESTADO.court)');
  assert.ok(Math.abs(state.objectos[0].pontos[0].x - 88.7) < 1e-8);
  assert.equal(state.actions[0].id, 'original');
  assert.equal(state.campoTipo, 'meio');
  assert.equal(state.largura, 887);
});

test('gravacao usa snapshot e serializa pedidos mesmo com novos riscos durante a resposta', async () => {
  const h = setup();
  await h.run("inicializarDesenho('court')");
  h.stroke();
  let resolveFetch;
  h.context.fetch = (_url, options) => {
    h.calls.push(JSON.parse(options.body));
    return new Promise(resolve => { resolveFetch = resolve; });
  };
  const first = h.run("guardarDesenho('court', 42, 1)");
  h.stroke();
  const second = h.run("guardarDesenho('court', 42, 1)");
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].estado.objectos.length, 1);
  resolveFetch({ok: true, json: async () => ({sucesso: true})});
  await Promise.all([first, second]);
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 2);
  assert.equal(h.run('CANVAS_ESTADO.court.revisaoGuardada'), 1);
  assert.equal(h.status.textContent, 'Por guardar');
  const final = h.run("guardarDesenho('court', 42, 1)");
  resolveFetch({ok: true, json: async () => ({sucesso: true})});
  await final;
  assert.equal(h.calls[1].estado.objectos.length, 2);
  assert.equal(h.status.textContent, 'Guardado');
});

test('erro de gravacao mantem os dados e permite tentar novamente', async () => {
  const h = setup();
  await h.run("inicializarDesenho('court')");
  h.stroke();
  const fetch = h.context.fetch;
  h.context.fetch = async () => ({ok: false, json: async () => ({sucesso: false, erro: 'Falha de rede'})});
  await h.run("guardarDesenho('court', 42, 1)");
  assert.equal(h.status.dataset.error, 'true');
  assert.equal(h.run('CANVAS_ESTADO.court.revisaoGuardada'), 0);
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  h.context.fetch = fetch;
  await h.run("guardarDesenho('court', 42, 1)");
  assert.equal(h.status.textContent, 'Guardado');
  assert.equal(h.status.dataset.error, 'false');
});

test('desenho antigo nao bloqueia a caneta nem e substituido antes de carregar', async () => {
  const h = setup();
  h.canvas.dataset.desenho = 'data:image/png;base64,anterior';
  h.context.window.TacticalLegacy = {aguardarRecortes: async () => {}, eRecorte: () => false, decomporImagem: () => { throw new Error('Conversao pesada nao deve ocorrer'); }};
  h.run("inicializarDesenho('court')");
  assert.equal(h.status.textContent, 'Pronto para desenhar');
  h.stroke();
  assert.equal(h.run('CANVAS_ESTADO.court.objectos.length'), 1);
  const saving = h.run("guardarDesenho('court', 42, 1)");
  assert.equal(h.calls.length, 0);
  h.images[0].onload();
  await saving;
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].estado.fundoLegado, 'data:image/png;base64,anterior');
  assert.equal(h.calls[0].estado.objectos.length, 1);
  assert.equal(h.status.textContent, 'Guardado');
});

test('falha do desenho antigo deixa estado explicito sem o apagar', async () => {
  const h = setup();
  h.canvas.dataset.desenho = 'data:image/png;base64,anterior';
  h.run("inicializarDesenho('court')");
  h.images[0].onerror();
  await h.run('CANVAS_ESTADO.court.carregarFundo.catch(() => {})');
  assert.equal(h.run('CANVAS_ESTADO.court.pronto'), true);
  assert.equal(h.status.dataset.error, 'true');
  h.stroke();
  await h.run("guardarDesenho('court', 42, 1)");
  assert.equal(h.calls.length, 0);
  assert.equal(h.status.dataset.error, 'true');
});

test('imagem antiga lenta nao reaparece depois do limite de carregamento', async () => {
  const h = setup();
  h.canvas.dataset.desenho = 'data:image/png;base64,anterior';
  h.run("inicializarDesenho('court')");
  const limite = [...h.timers.values()][0];
  limite();
  await h.run('CANVAS_ESTADO.court.carregarFundo.catch(() => {})');
  assert.equal(h.images[0].onload, null);
  assert.equal(h.run('CANVAS_ESTADO.court.pronto'), true);
  assert.equal(h.status.dataset.error, 'true');
});

test('limpar e desfazer incluem a imagem antiga de fundo', async () => {
  const h = setup();
  h.canvas.dataset.desenho = 'data:image/png;base64,anterior';
  h.run("inicializarDesenho('court')");
  h.images[0].onload();
  await h.run('CANVAS_ESTADO.court.carregarFundo');
  h.run("limparCampoTreino('court')");
  assert.equal(h.run('estadoDesenhoParaGuardar(CANVAS_ESTADO.court).fundoLegado'), null);
  h.run("desfazerTracoTreino('court')");
  assert.equal(h.run('estadoDesenhoParaGuardar(CANVAS_ESTADO.court).fundoLegado'), 'data:image/png;base64,anterior');
});
