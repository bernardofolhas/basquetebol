const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../static/js/training-plan-ui.js'), 'utf8');

function setup() {
  const listeners = {}, windowListeners = {}, formListeners = {}, timers = new Map(), calls = [];
  let id = 0;
  const status = {dataset: {}};
  const input = value => ({value, style: {}, scrollHeight: 110, getClientRects: () => [1], matches: () => true});
  const form = {
    dataset: {trainingNotes: '42'}, isConnected: true, action: '/treino/exercicios/42/notas',
    elements: {organizacao: input('Grupos de quatro.'), coaching_points: input('Passe e corte.')},
    querySelector: () => status,
    addEventListener: (name, callback) => { formListeners[name] = callback; },
  };
  const root = {querySelectorAll: selector => selector === '[data-training-notes]' ? [form] : []};
  const response = (sucesso = true) => ({ok: sucesso, headers: {get: () => 'application/json'}, json: async () => ({sucesso})});
  const context = vm.createContext({
    document: {
      readyState: 'loading', addEventListener: (name, cb) => { listeners[name] = cb; },
      querySelector: () => null, querySelectorAll: () => [], getElementById: () => null,
      createElement: () => ({attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(k, cb) { this[k] = cb; }}),
    },
    window: {addEventListener: (name, cb) => { windowListeners[name] = cb; }},
    FormData: class { constructor(f) { this.organizacao = f.elements.organizacao.value; this.coaching_points = f.elements.coaching_points.value; } },
    AbortController,
    setTimeout: (fn, delay) => { timers.set(++id, {fn, delay}); return id; }, clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => { calls.push(options); return response(); },
  });
  vm.runInContext(script, context);
  const api = context.window.TrainingPlanUI;
  api.init(root);
  const edit = value => { form.elements.organizacao.value = value; formListeners.input({target: form.elements.organizacao}); };
  return {api, context, form, status, calls, response, timers, edit, listeners, windowListeners};
}

test('notas gravam automaticamente sem mover o foco ou substituir texto', async () => {
  const h = setup();
  h.edit('Novo texto');
  assert.equal(h.status.textContent, 'Por guardar');
  await [...h.timers.values()].find(t => t.delay === 800).fn();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].body.organizacao, 'Novo texto');
  assert.equal(h.status.textContent, 'Guardado');
  assert.equal(h.form.elements.organizacao.style.height, '112px');
});

test('notas serializam pedidos e nao perdem alteracoes durante a gravacao', async () => {
  const h = setup();
  let finish;
  h.context.fetch = (_url, options) => { h.calls.push(options); return new Promise(resolve => { finish = resolve; }); };
  h.edit('Primeira versao');
  const saving = h.api.saveNotes(h.form);
  h.edit('Segunda versao');
  const repeated = h.api.saveNotes(h.form);
  assert.equal(h.calls.length, 1);
  finish(h.response());
  await Promise.all([saving, repeated]);
  assert.equal(h.form.elements.organizacao.value, 'Segunda versao');
  assert.equal(h.status.textContent, 'Por guardar');
  const last = [...h.timers.values()].find(t => t.delay === 300).fn();
  assert.equal(h.calls[1].body.organizacao, 'Segunda versao');
  finish(h.response());
  await last;
  assert.equal(h.status.textContent, 'Guardado');
});

test('falha permite repetir Guardar sem perder notas e avisa antes de sair', async () => {
  const h = setup();
  h.edit('Manter isto');
  h.context.fetch = async () => h.response(false);
  await h.api.saveNotes(h.form);
  assert.equal(h.status.dataset.error, 'true');
  let prevented = false;
  h.windowListeners.beforeunload({preventDefault: () => { prevented = true; }});
  assert.equal(prevented, true);
  h.context.fetch = async () => h.response();
  await h.api.saveNotes(h.form);
  assert.equal(h.form.elements.organizacao.value, 'Manter isto');
  assert.equal(h.status.dataset.error, 'false');
});

test('pagina de login nunca e apresentada como gravacao bem sucedida', async () => {
  const h = setup();
  h.edit('Manter isto');
  h.context.fetch = async () => ({ok: true, headers: {get: () => 'text/html'}});
  await h.api.saveNotes(h.form);
  assert.equal(h.status.dataset.error, 'true');
  assert.match(h.status.textContent, /Sessão/);
});

test('exercicio removido nao inicia pedidos de gravacao', async () => {
  const h = setup();
  h.edit('Nao gravar');
  h.form.isConnected = false;
  await h.api.saveNotes(h.form);
  assert.equal(h.calls.length, 0);
});

test('campos ficam visiveis numa lista e adicionar desloca apenas o scroll interior', () => {
  const h = setup();
  const card = id => ({querySelector: selector => selector === 'canvas' ? {id, dataset: {campoTipo: 'meio'}} : null, getBoundingClientRect: () => ({top: 600})});
  const cards = [card('one'), card('two')];
  const count = {};
  const grid = {scrollTop: 0, getBoundingClientRect: () => ({top: 100})};
  const panel = {querySelectorAll: () => cards, querySelector: selector => selector === '[data-court-count]' ? count : grid};
  h.api.courts(panel);
  assert.equal(cards[0].hidden, false);
  assert.equal(cards[1].hidden, false);
  assert.equal(grid.scrollTop, 0);
  const original = cards[0];
  cards.push(card('three'));
  h.api.courts(panel, 'three');
  assert.equal(cards[0], original);
  assert.equal(cards[0].hidden, false);
  assert.equal(cards[2].hidden, false);
  assert.equal(grid.scrollTop, 500);
  assert.equal(count.textContent, '3 campos');
  cards.pop();
  h.api.courts(panel);
  assert.equal(cards[0].hidden, false);
  assert.equal(count.textContent, '2 campos');
  cards.splice(0);
  h.api.courts(panel);
  assert.equal(count.textContent, '0 campos');
});

test('PDF conserva campos compactos e nao importa os estilos do editor', () => {
  const pdf = fs.readFileSync(path.join(__dirname, '../templates/treino/plano_print.html'), 'utf8');
  assert.match(pdf, /\.court img\s*\{[^}]*max-height:\s*27mm/);
  assert.doesNotMatch(pdf, /training-(ink|plan)\.css/);
  const editor = fs.readFileSync(path.join(__dirname, '../templates/treino/plano.html'), 'utf8');
  assert.match(editor, />Coaching Points<\/label>/);
  assert.doesNotMatch(editor, />Pontos de intervenção</);
});
