// Optional Node checks of data and selection logic; browser layout is checked separately.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'static/app.js'), 'utf8');
const ids = new Set(Array.from(html.matchAll(/\bid="([^"]+)"/g), match => match[1]));
for (const match of source.matchAll(/\$\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing HTML node: ${match[1]}`);
assert.ok(!source.includes('innerHTML'), 'Remote strings must be rendered as text');
const marker = '  $("language-toggle").addEventListener';
assert.ok(source.includes(marker));
const isolated = source.slice(0, source.indexOf(marker)) + `
  globalThis.api = {normalizeSnapshot, normalizeServers, makeContext, chartSegments, metricValue,
    bytes, uptime, calendarDate, t, COPY, BACKEND_MESSAGES, renderData, renderStatus, renderTraffic, renderSidebar,
    performPoll, selectServer, reconnect, handleRequestError,
    setLanguage(value) { language = value; applyLanguage(); },
    configure(items, id, snapshot = null, freeze = false) {
      servers = normalizeServers(items); selectedServer = id;
      liveSnapshot = viewedSnapshot = snapshot ? normalizeSnapshot(snapshot) : null;
      paused = freeze; renderSidebar(); renderData(); renderStatus();
    },
    state() { return { language, selectedServer, paused, liveSnapshot, viewedSnapshot, reconnectBusy }; }
  };
})();`;

class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.attributes = {};
    this.textContent = ''; this.hidden = false; this.clientWidth = 600; this.offsetWidth = 120;
    this.firstChild = {textContent:''}; this.queries = new Map();
    this.classList = {toggle() {}};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
  querySelector(selector) {
    if (!this.queries.has(selector)) this.queries.set(selector,new Node());
    return this.queries.get(selector);
  }
  querySelectorAll(selector) {
    if (!this.queries.has(selector)) this.queries.set(selector,[new Node(),new Node()]);
    return this.queries.get(selector);
  }
}
function harness(initialLanguage = 'ru', savedLanguage = null) {
  const nodes = new Map(Array.from(ids, id => [id, new Node()]));
  const extras = new Map();
  const axes = Array.from({length:5}, () => new Node());
  const metrics = ['cpu','memory','swap','disk'].map(key=>{
    const node = new Node('button'); node.dataset.metric = key; return node;
  });
  nodes.get('x-axis').children = Array.from({length:5}, () => new Node());
  const storage = new Map(savedLanguage ? [['monitor-language', savedLanguage]] : []);
  const document = {
    documentElement: {}, getElementById: id => nodes.get(id),
    querySelectorAll: selector => selector === '.y-axis span' ? axes : selector === '[data-metric]' ? metrics : [],
    querySelector(selector) {
      if (selector === 'meta[name="monitor-token"]') return {content:'test'};
      if (selector === 'meta[name="monitor-language"]') return {content:initialLanguage};
      if (!extras.has(selector)) extras.set(selector, new Node());
      return extras.get(selector);
    },
    createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag),
    createDocumentFragment: () => new Node('fragment'),
  };
  const requests = [];
  let timer = 0;
  const context = {console, Intl, Date, Map, Set, Math, Number, AbortController,
    document, localStorage: {getItem:key=>storage.get(key) ?? null, setItem:(key,value)=>storage.set(key,value)},
    window:{location:{reload() {}}},
    setTimeout:()=>++timer, clearTimeout() {},
    fetch(url, options) {
      return new Promise((resolve, reject) => requests.push({url, options, resolve(value) {
        resolve({ok:true, status:200, json:async()=>value});
      }, reject}));
    },
  };
  vm.createContext(context);
  vm.runInContext(isolated, context);
  return {f:context.api, document, nodes, extras, requests};
}
const flush = async () => { for (let index=0; index<20; index++) await Promise.resolve(); };
const now = 2000000;
const sample = (ts, percent) => ({ts, cpu:{percent}, memory:{percent:0}, swap:{percent:0,enabled:false}, disk:{percent:120}});
const snapshot = (id, percent, extra = {}) => ({server_id:id, name:`Server ${id}`, alias:`ssh-${id}`, status:'connected', interval:2,server_time:now,latest:{...sample(now,percent),...extra},history:[]});
const servers = [{id:'0',name:'First <server>',alias:'first',status:'connected'}, {id:'1',name:'Second',alias:'second',status:'connected'}];

async function main() {
  const {f,document,nodes,extras,requests} = harness();
  const normalized = f.normalizeSnapshot({interval:2,server_time:now,latest:sample(now,20),history:[
    sample(now-2000,0),sample(now-12000,40),sample(now-18000,10),sample(now-16000,null),sample(now-2000,10)
  ]});
  assert.equal(normalized.history.length,5);
  assert.equal(normalized.history[0].ts,now-18000);
  assert.equal(f.metricValue(sample(now,0),'cpu'),0);
  assert.equal(f.metricValue(sample(now,null),'cpu'),null);
  assert.equal(f.metricValue(sample(now,5),'swap'),null);
  const chart = f.makeContext(normalized);
  assert.equal(chart.stats.cpu.count,4);
  assert.equal(chart.stats.cpu.mean,20);
  assert.equal(chart.stats.cpu.peak,40);
  assert.equal(chart.stats.disk.scale,125);
  assert.equal(f.chartSegments(chart,'cpu').length,3);
  assert.equal(f.bytes(1073741824),'1,00 \u0413\u0438\u0411');
  assert.equal(f.bytes(-1024),'−1,00 \u041a\u0438\u0411');
  assert.equal(f.uptime(90061),'1 \u0434 1 \u0447 1 \u043c\u0438\u043d');
  assert.equal(f.makeContext(null).samples.length,0);
  assert.throws(()=>f.normalizeSnapshot({}),{message:f.t('invalidResponse')});
  assert.throws(()=>f.normalizeServers([{id:'0'},{id:'0'}]),{message:f.t('invalidResponse')});
  for (const match of html.matchAll(/data-i18n(?:-aria|-title)?="([^"]+)"/g)) assert.ok(f.COPY[match[1]], `Missing translation ${match[1]}`);
  for (const [key, copy] of Object.entries(f.COPY)) {
    assert.ok(copy.length === 2 && copy.every(value=>typeof value==='string' && value), `Incomplete translation ${key}`);
    assert.doesNotMatch(copy[1],/\p{Script=Cyrillic}/u,`English copy must not contain Cyrillic: ${key}`);
  }
  assert.equal(harness('en').f.state().language,'en');
  assert.equal(harness('en','ru').f.state().language,'ru');
  f.setLanguage('en');
  assert.equal(document.title,'Server monitor');
  assert.equal(nodes.get('language-toggle').title,'Switch to Russian');
  assert.equal(nodes.get('language-toggle').attributes['aria-label'],'Switch to Russian');
  assert.equal(f.bytes(1073741824),'1.00 GiB');
  assert.equal(f.uptime(90061),'1 d 1 h 1 min');
  assert.equal(f.t('cadence',{seconds:2}),'Every 2 s');
  assert.equal(f.calendarDate('2026-10-07'),'07/10');
  assert.equal(f.t('lifetimeTitle').includes('exceed 100%'),true);
  f.configure(servers,'0',snapshot('0',25,{processes:[{pid:10,name:'<unsafe>',cpu_percent:125,memory_bytes:null}],traffic:null}),true);
  assert.equal(nodes.get('server-list').children[0].children[1].textContent,'First <server>');
  const selfMenu = harness();
  selfMenu.f.setLanguage('ru');
  selfMenu.f.configure([
    {id:'offline',name:'Offline',alias:'offline',status:'error'},
    {id:'wsl',name:'WSL: Ubuntu',alias:'Ubuntu',source:'wsl',status:'connected'},
    {id:'self',name:'self',alias:'self',source:'self',status:'error'},
  ],'self');
  assert.deepEqual(Array.from(selfMenu.nodes.get('server-list').children, button => button.children[1].textContent),
    ['SELF','WSL: Ubuntu','Offline'],'SELF must stay first even when its collector is in error');
  assert.equal(selfMenu.nodes.get('server-alias').textContent,'SELF');
  assert.equal(nodes.get('process-list').children[0].children[0].textContent,'<unsafe>');
  assert.equal(nodes.get('process-list').children[0].children[2].textContent,'125%');
  assert.equal(nodes.get('process-list').children[0].children[3].textContent,'—');
  assert.equal(nodes.get('traffic-panel').hidden,true);
  const oldPoll = f.performPoll();
  assert.equal(requests[0].url,'/api/snapshot?server=0');
  f.selectServer('1');
  assert.equal(requests[0].options.signal.aborted,true);
  assert.equal(f.state().paused,false);
  assert.equal(f.state().viewedSnapshot,null);
  assert.equal(nodes.get('cpu-value').textContent,'—');
  assert.equal(requests[1].url,'/api/snapshot?server=1');
  assert.equal(requests[1].options.headers['X-Monitor-Token'],'test');
  requests[1].resolve(snapshot('1',66));
  await flush();
  assert.equal(f.state().liveSnapshot.server_id,'1');
  requests[0].resolve(snapshot('0',11));
  await oldPoll;
  assert.equal(f.state().liveSnapshot.latest.cpu.percent,66,'Late previous-server response must be ignored');
  assert.equal(nodes.get('cpu-value').textContent,'66.0');
  const reconnecting = f.reconnect();
  await flush();
  assert.equal(requests[2].url,'/api/reconnect?server=1');
  assert.equal(requests[2].options.method,'POST');
  f.selectServer('0');
  assert.equal(requests[3].url,'/api/snapshot?server=0');
  requests[2].resolve({ok:true});
  await reconnecting;
  assert.equal(f.state().selectedServer,'0');
  assert.equal(f.state().reconnectBusy,false);
  requests[3].resolve(snapshot('0',33));
  await flush();
  assert.equal(f.state().liveSnapshot.latest.cpu.percent,33);
  const traffic = {updated_at:now,default_interface:'eth1',interfaces:[
    {name:'eth0',rx:100,tx:0,days:[{date:'2026-10-06',rx:100,tx:0}]},
    {name:'eth1',rx:null,tx:50,days:[{date:'2026-10-06',rx:null,tx:null},{date:'2026-10-07',rx:null,tx:50}]}
  ]};
  f.configure(servers,'0',snapshot('0',44,{traffic,processes:null}));
  assert.equal(nodes.get('traffic-panel').hidden,false);
  assert.equal(nodes.get('interface-name').textContent,'eth1');
  assert.equal(nodes.get('traffic-rx').textContent,'—');
  assert.equal(nodes.get('traffic-tx').textContent,'50 B');
  assert.equal(nodes.get('traffic-days').children[0].children[0].children[0].className,'traffic-missing');
  assert.equal(nodes.get('traffic-days').children[1].children[0].children.length,1,'Null RX must not be drawn as measured zero');
  assert.equal(nodes.get('traffic-days').children[1].children[0].children[0].className,'traffic-bar tx');
  assert.equal(nodes.get('process-empty').textContent,'Process list unavailable');
  f.configure(servers,'0',{...snapshot('0',44),status:'reconnecting',message:'SSH authentication failed. Check the user, key or ssh-agent. Enter passwords in the launch window.'});
  assert.match(nodes.get('status-message').textContent,/authentication failed.*ssh-agent/);
  for (const source of ['self', 'wsl']) {
    const local = [{id:source, name:source, alias:source, source, status:'connecting'}];
    f.configure(local,source);
    assert.equal(extras.get('.protocol-badge').textContent,source.toUpperCase());
    assert.match(nodes.get('status-message').textContent,/Starting local metric collection/);
    assert.doesNotMatch(nodes.get('status-message').textContent,/SSH/);
    f.configure(local,source,{...snapshot(source,44),source,message:'Local metric collection is running.'});
    assert.equal(extras.get('.protocol-badge').textContent,source.toUpperCase());
    assert.equal(nodes.get('status-message').textContent,'Local metric collection is running.');
  }
  const localBackend = fs.readFileSync(path.join(root,'monitor/local.py'),'utf8');
  for (const [,message] of localBackend.matchAll(/^\s+"[a-z_]+": "([^"]+)",$/gm)) {
    f.configure([{id:'self',name:'self',source:'self'}],'self',
      {...snapshot('self',44),source:'self',status:'error',message});
    assert.doesNotMatch(nodes.get('status-message').textContent,/\p{Script=Cyrillic}/u,
      `Local backend message must be translated: ${message}`);
    f.setLanguage('ru'); f.renderStatus();
    assert.match(nodes.get('status-message').textContent,/\p{Script=Cyrillic}/u,
      `Local backend message must have Russian localization: ${message}`);
    f.setLanguage('en'); f.renderStatus();
    assert.equal(nodes.get('status-message').textContent,message);
  }
  for (const [message, russian] of f.BACKEND_MESSAGES) {
    f.configure(servers,'0',{...snapshot('0',44),status:'error',message});
    f.setLanguage('ru'); f.renderStatus();
    assert.equal(nodes.get('status-message').textContent,russian,'Backend messages must localize in Russian');
    f.setLanguage('en'); f.renderStatus();
    assert.equal(nodes.get('status-message').textContent,message,'Switching back must restore English');
    assert.doesNotMatch(message,/\p{Script=Cyrillic}/u,'API message identifiers must be English');
  }
  f.handleRequestError(new Error('offline'));
  f.setLanguage('ru'); f.renderStatus();
  assert.equal(nodes.get('status-message').textContent,f.t('networkError'),'Errors must translate when language changes');
  console.log('Frontend checks PASS: metric gaps/statistics, RU/EN, safe text, server selection/races, reconnect targeting, process CPU, traffic interfaces/null dates.');
}
main().catch(error => { console.error(error); process.exitCode=1; });
