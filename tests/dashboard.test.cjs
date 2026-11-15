// Dependency-free UI controller tests. These do not replace browser layout QA.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../registry/dashboard.html'), 'utf8');
const source = html.split('<script>')[1].split('</script>')[0];

class Element {
  constructor() { this.value = ''; this.textContent = ''; this.hidden = false; this.open = false; this.listeners = {}; this.children = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  querySelectorAll() { return []; }
  reset() {}
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
  focus() {}
  select() {}
}
function fixture() {
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
  const requests = [], records = new Map(), timers = [];
  const secret = 'test-only-credential';
  const context = vm.createContext({
    document: {getElementById: id => { assert.ok(nodes.has(id), `Missing DOM ID ${id}`); return nodes.get(id); }, createElement: () => new Element()},
    window: {addEventListener() {}}, navigator: {clipboard: {async writeText() {}}},
    URLSearchParams, AbortController, setTimeout, clearTimeout, setInterval(fn) { timers.push(fn); },
    fetch: async (url, options) => {
      requests.push({url, ...options});
      const id = decodeURIComponent(url.split('/')[3] || '');
      const row = records.get(id);
      const reply = (status, data) => ({ok:status < 400, status, async json() { return data; }});
      if (url === '/v1/health') return reply(200, {ttl_seconds:30, heartbeat_interval_seconds:10});
      if (options.method === 'GET') return url.includes('?') ? reply(200, [...records.values()]) : row ? reply(200, row) : reply(404, {});
      const body = options.body ? JSON.parse(options.body) : null;
      if (url === '/v1/agents') {
        const existing = records.get(body.agent_id);
        if (existing && options.headers.Authorization !== 'Bearer ' + secret) return reply(401, {});
        const result = {...body, registered_at:'2026-01-01T00:00:00Z', updated_at:'2026-01-01T00:00:00Z', last_heartbeat:'2026-01-01T00:00:00Z', lease_expires_at:'2026-01-01T00:00:30Z', status:'ONLINE'};
        records.set(body.agent_id, result);
        return reply(existing ? 200 : 201, existing ? result : {...result, credential:secret});
      }
      if (options.headers.Authorization !== 'Bearer ' + secret) return reply(401, {});
      if (!row) return reply(404, {});
      if (options.method === 'DELETE') { records.delete(id); return reply(204, null); }
      if (url.endsWith('/heartbeat') && row.status === 'UNREACHABLE') return reply(409, {});
      const result = {...row, ...body}; records.set(id, result); return reply(200, result);
    }
  });
  vm.runInContext(source, context);
  return {nodes, requests, records, context, secret, timers, run: expression => vm.runInContext(expression, context)};
}
async function create(f, id = 'generic-1') {
  f.run("openEditor('create')");
  const values = {agent_id:id, name:'Generic Agent', domain:'documents', version:'1', capabilities:'extract_text, summarize\nclassify', endpoint:'https://example.test/run', description:'<img src=x onerror=alert(1)>'};
  for (const [key,value] of Object.entries(values)) f.nodes.get('card-' + key).value = value;
  await f.nodes.get('card-form').listeners.submit({preventDefault() {}});
}

test('general registration sends the full card; credential is isolated and cleared', async () => {
  const f = fixture(); await create(f);
  const request = f.requests.find(r => r.method === 'POST');
  assert.equal(request.headers.Authorization, undefined);
  assert.deepEqual(JSON.parse(request.body).capabilities, ['extract_text','summarize','classify']);
  assert.equal(f.nodes.get('secret').open, true);
  assert.equal(f.nodes.get('new-token').value, f.secret);
  assert.equal(f.nodes.get('secret-done').disabled, true);
  f.nodes.get('saved-token').checked = true;
  f.nodes.get('saved-token').onchange(); f.nodes.get('secret-done').onclick();
  assert.equal(f.nodes.get('new-token').value, '');
  assert.doesNotMatch(html, /localStorage|sessionStorage|weather_forecast|Weather Agent/);
  assert.doesNotMatch(source, /innerHTML/);
});

test('ownership gates mutation; PATCH omits ID and delete needs exact confirmation', async () => {
  const f = fixture(); await create(f);
  await f.run("openManager('generic-1')");
  f.nodes.get('manage-token').value = f.secret;
  f.nodes.get('edit-agent').onclick();
  assert.equal(f.nodes.get('manage-token').value, '');
  f.nodes.get('card-endpoint').value = 'https://example.test/v2';
  await f.nodes.get('card-form').listeners.submit({preventDefault() {}});
  const patch = f.requests.find(r => r.method === 'PATCH');
  assert.equal(JSON.parse(patch.body).agent_id, undefined);
  assert.equal(patch.headers.Authorization, 'Bearer ' + f.secret);
  assert.equal(f.nodes.get('editor-token').value, '');
  assert.equal(f.records.get('generic-1').endpoint, 'https://example.test/v2');
  await f.run("openManager('generic-1')"); f.nodes.get('manage-token').value = f.secret;
  f.nodes.get('delete-agent').onclick(); f.nodes.get('delete-id').value = 'different';
  await f.nodes.get('confirm-delete').onclick();
  assert.ok(f.records.has('generic-1'));
  f.nodes.get('delete-id').value = 'generic-1'; await f.nodes.get('confirm-delete').onclick();
  assert.equal(f.records.has('generic-1'), false);
  assert.equal(f.nodes.get('manager').open, false);
});

test('expired heartbeat reports recovery, re-registration preserves ownership', async () => {
  const f = fixture(); await create(f); f.records.get('generic-1').status = 'UNREACHABLE';
  await f.run("openManager('generic-1')"); f.nodes.get('manage-token').value = f.secret;
  f.nodes.get('reregister-agent').onclick();
  await f.nodes.get('card-form').listeners.submit({preventDefault() {}});
  assert.equal(f.records.get('generic-1').status, 'ONLINE');
  const registration = f.requests.filter(r => r.url === '/v1/agents').at(-1);
  assert.equal(registration.headers.Authorization, 'Bearer ' + f.secret);
});

test('switching Agent clears credentials and arbitrary card text remains plain text', async () => {
  const f = fixture(); await create(f); await create(f, 'generic-2');
  await f.run("openManager('generic-1')"); f.nodes.get('manage-token').value = f.secret;
  f.nodes.get('manager-close').onclick(); await f.run("openManager('generic-2')");
  assert.equal(f.nodes.get('manage-token').value, '');
  assert.equal(f.nodes.get('agent-detail').children[1].textContent, '<img src=x onerror=alert(1)>');
});

test('dashboard has no heartbeat request or button', () => { assert.doesNotMatch(source, /\/heartbeat/); assert.doesNotMatch(html, /id="heartbeat-agent"/); });

test('polling only reads and updates an open detail dialog', async () => {
  const f = fixture(); await create(f);
  await f.run("openManager('generic-1')");
  f.records.get('generic-1').status = 'SUSPECT';
  const before = f.requests.length;
  await f.timers[0]();
  assert.ok(f.requests.slice(before).length > 0);
  assert.ok(f.requests.slice(before).every(r => r.method === 'GET'));
  assert.equal(f.nodes.get('agent-detail').children[0].textContent, 'SUSPECT');
});
