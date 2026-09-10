const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('the individual edit button opens a populated content dialog', () => {
  const listeners = {};
  const documentListeners = {};
  const makeTarget = () => ({
    disabled: false,
    addEventListener(type, handler) { listeners[this.key + ':' + type] = handler; },
  });
  const save = Object.assign(makeTarget(), { key: 'save' });
  const add = Object.assign(makeTarget(), { key: 'add' });
  const status = { textContent: '', className: '' };
  const submit = { disabled: false, textContent: '' };
  const fields = {
    area: { value: '', focus() {} },
    subarea: { value: '' },
    nome: { value: '', focus() {} },
  };
  const form = {
    elements: fields,
    reset() { Object.values(fields).forEach(field => { field.value = ''; }); },
    querySelector() { return submit; },
    addEventListener(type, handler) { listeners['form:' + type] = handler; },
  };
  const dialog = {
    open: false,
    showModal() { this.open = true; },
    close() { this.open = false; },
    addEventListener(type, handler) { listeners['dialog:' + type] = handler; },
  };
  const title = { textContent: '' };
  const kicker = { textContent: '' };
  const map = {
    dataset: { createUrl: '/conteudos', saveUrl: '/prioridades' },
    querySelector(selector) {
      return ({
        '[data-mapa-save]': save,
        '[data-mapa-save-status]': status,
        '[data-content-dialog]': dialog,
        '[data-content-form]': form,
        '[data-content-status]': status,
        '[data-mapa-add]': add,
        '[data-content-dialog-title]': title,
        '[data-content-dialog-kicker]': kicker,
        '[data-content-submit]': submit,
      })[selector] || null;
    },
    querySelectorAll() { return []; },
    addEventListener(type, handler) { listeners['map:' + type] = handler; },
    contains() { return true; },
  };
  const document = {
    fullscreenEnabled: false,
    fullscreenElement: null,
    querySelector() { return null; },
    querySelectorAll(selector) { return selector === '[data-mapa-conteudos]' ? [map] : []; },
    addEventListener(type, handler) { documentListeners[type] = handler; },
  };
  const window = {
    location: { pathname: '/planeamento/anuais/1', href: '/planeamento/anuais/1' },
    sessionStorage: { getItem() { return null; }, removeItem() {}, setItem() {} },
    setTimeout(handler) { handler(); },
    addEventListener() {},
    confirm() { return true; },
  };
  const source = fs.readFileSync(path.join(__dirname, '../static/js/mapa-conteudos.js'), 'utf8');
  vm.runInNewContext(source, { document, window, fetch: async () => {}, DOMParser: class {} });
  documentListeners.DOMContentLoaded();

  const edit = {
    dataset: {
      editUrl: '/conteudos/4/editar',
      contentArea: 'Tática Ofensiva',
      contentSubarea: 'Transição',
      contentName: 'Contra-ataque',
    },
  };
  listeners['map:click']({
    target: { closest: () => edit },
    preventDefault() {},
    stopPropagation() {},
  });

  assert.equal(dialog.open, true);
  assert.equal(fields.area.value, 'Tática Ofensiva');
  assert.equal(fields.subarea.value, 'Transição');
  assert.equal(fields.nome.value, 'Contra-ataque');
  assert.equal(title.textContent, 'Editar conteúdo');
  assert.equal(submit.textContent, 'Guardar alterações');
});
