// Execute the emitted viewer, with only the DOM surface it actually consumes.
const vm = require('node:vm');
const fs = require('node:fs');
const {html, actions = []} = JSON.parse(fs.readFileSync(0, 'utf8'));
function element(tagName = '') {
  return {tagName, value: '', checked: false, textContent: '', innerHTML: '', children: [], listeners: {},
    appendChild(node) {this.children.push(node); return node;},
    addEventListener(event, fn) {this.listeners[event] = fn;}};
}
const elements = Object.fromEntries(['cat', 'q', 'sort', 'onlyout', 'main', 'stat'].map(id => [id, element()]));
elements.sort.value = 'size';
const document = {getElementById: id => elements[id], createElement: tag => element(tag)};
const context = vm.createContext({document, URL});
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
vm.runInContext(script, context, {timeout: 1000});
function snapshot() {
  return JSON.parse(vm.runInContext(`JSON.stringify({
    clusters: CLUSTERS, html: document.getElementById('main').innerHTML,
    stat: document.getElementById('stat').textContent,
    options: document.getElementById('cat').children.map(o => ({text: o.textContent, value: o.value})),
    optionHTML: document.getElementById('cat').innerHTML,
    finite: CLUSTERS.every(c => ['min','max','med'].every(k => c[k] === null || Number.isFinite(c[k])) && Number.isFinite(c.spread)),
    medians: [median([]), median([3]), median([1,3]), median([1,2,9])]
  })`, context));
}
const states = [snapshot()];
for (const action of actions) {
  for (const [id, value] of Object.entries(action)) {
    elements[id][id === 'onlyout' ? 'checked' : 'value'] = value;
  }
  elements[Object.keys(action)[0]].listeners.input();
  states.push(snapshot());
}
process.stdout.write(JSON.stringify(states));
