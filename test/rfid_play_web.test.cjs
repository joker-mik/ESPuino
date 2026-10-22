const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('html/management.html', 'utf8');
const start = html.indexOf('const rfidListSavedAssignments =');
const end = html.indexOf('async function eraseNVSRFID()', start);
assert.ok(start >= 0 && end > start, 'RFID UI section exists');
const source = html.slice(start, end);

function element(tag = 'div') {
  return {
    tag, children: [], attrs: {}, listeners: {}, disabled: false, value: '',
    classList: {values: new Set(), add(...values) {values.forEach(v => this.values.add(v));}, toggle(value, force) {const add = force === undefined ? !this.values.has(value) : !!force; if (add) this.values.add(value); else this.values.delete(value); return add;}},
    appendChild(child) {this.children.push(child); return child;},
    setAttribute(key, value) {this.attrs[key] = value;},
    addEventListener(event, handler) {this.listeners[event] = handler;},
    set innerHTML(value) {this.children = [];}
  };
}
function setup(fetchImpl) {
  const ids = {};
  const messages = {success: [], error: []};
  const context = vm.createContext({
    document: {
      getElementById(id) {return ids[id] ||= element();},
      createElement: element,
      createTextNode(text) {return {text};}
    },
    knownMediaHubServers: [], host: 'espuino.test', console: {log() {}}, fetch: fetchImpl,
    AbortController, setTimeout, clearTimeout,
    i18next: {t: key => key},
    toaster: {success: text => messages.success.push(text), error: text => messages.error.push(text)},
  });
  vm.runInContext(source, context);
  return {context, messages, ids};
}

test('Play buttons precede Delete for music and modification cards', async () => {
  const cards = [
    {id: '000000000042', playMode: 3, fileOrUrl: '/Audiobook'},
    {id: '900000000002', modId: 110}
  ];
  const calls = [];
  const {context, ids} = setup(async (url, options) => {
    calls.push({url, options});
    return options ? {status: 202} : {json: async () => cards};
  });
  await context.rebuildRFIDList();
  const rows = ids.rfidListSavedAssignments.children;
  assert.equal(rows.length, 2);
  for (let i = 0; i < rows.length; ++i) {
    const actions = rows[i].children.at(-1);
    const [play, remove] = actions.children;
    assert.equal(actions.children.length, 2);
    assert.ok(play.classList.values.has('btn-success'));
    assert.equal(play.type, 'button');
    assert.ok(play.attrs['aria-label'].includes(cards[i].id));
    assert.equal(play.attrs['data-bs-target'], undefined);
    assert.equal(remove.attrs['data-bs-target'], '#deleteRFIDModal');
    assert.equal(remove.attrs['data-rfid'], cards[i].id);
    await play.listeners.click();
    assert.equal(calls.at(-1).url, 'http://espuino.test/rfidplay?id=' + cards[i].id);
    assert.equal(calls.at(-1).options.method, 'POST');
  }
});

test('leading zeroes are retained and success means queued only', async () => {
  let url;
  const {context, messages} = setup(async address => {url = address; return {status: 202};});
  const button = element('button');
  await context.playRFID('000000000001', button);
  assert.equal(url, 'http://espuino.test/rfidplay?id=000000000001');
  assert.deepEqual(messages.success, ['rfidPlayback.queued']);
  assert.equal(button.disabled, false);
});

test('double-click while pending sends only one request', async () => {
  let finish;
  let calls = 0;
  const {context} = setup(() => {calls++; return new Promise(resolve => {finish = resolve;});});
  const button = element('button');
  const pending = context.playRFID('900000000002', button);
  assert.equal(button.disabled, true);
  await context.playRFID('900000000002', button);
  assert.equal(calls, 1);
  finish({status: 202});
  await pending;
  assert.equal(button.disabled, false);
});

for (const status of [200, 400, 404, 501, 503]) {
  test('HTTP ' + status + ' is not reported as successful playback', async () => {
    const {context, messages} = setup(async () => ({status, statusText: ''}));
    const button = element('button');
    await context.playRFID('900000000002', button);
    assert.equal(messages.success.length, 0);
    assert.equal(messages.error.length, 1);
    assert.ok(messages.error[0].includes('HTTP ' + status));
    assert.equal(button.disabled, false);
  });
}

test('network errors restore the button and show an error', async () => {
  const {context, messages} = setup(async () => {throw new Error('offline');});
  const button = element('button');
  await context.playRFID('900000000002', button);
  assert.equal(messages.success.length, 0);
  assert.ok(messages.error[0].includes('offline'));
  assert.equal(button.disabled, false);
});

test('translations exist in every supported language', () => {
  for (const language of ['de', 'en', 'fr']) {
    const labels = JSON.parse(fs.readFileSync('html/locales/' + language + '.json')).rfidPlayback;
    for (const key of ['trigger', 'queued', 'error']) {
      assert.ok(typeof labels[key] === 'string' && labels[key].length > 0);
    }
  }
});
