/* Node-only DOM contract tests. Does not test browser layout, CSP or rendering. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
let checks = 0;
function check(ok, message) { checks++; assert.ok(ok, message); }
class Element {
  constructor(id) { this.id = id; this.hidden = false; this.attrs = {}; this.listeners = {}; this.dataset = {}; this.open = false; }
  setAttribute(key, value) { this.attrs[key] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  focus() { focused = this.id; }
  fire(name, event = {}) { this.listeners[name](event); }
}
let focused = null;
const tabs = ['overview','financials','valuation','risks'].map(x => new Element('tab-'+x));
const panels = ['overview','financials','valuation','risks'].map(x => new Element(x));
const keys = ['revenue','gross_margin','operating_margin','net_income_parent','diluted_eps','roe','fcf','revenue_yoy','eps_yoy'];
const figures = keys.map(x => { const e = new Element(x); e.dataset.series = x; return e; });
const elements = Object.fromEntries(['indicator','view-toggle','charts','annual-table','print'].map(x => [x, new Element(x)]));
elements.indicator.value = 'revenue';
const details = [new Element('closed-detail'), new Element('open-detail')];
details[1].open = true;
const events = {};
let printed = 0;
const window = {addEventListener:(name,fn)=>{events[name]=fn;},print:()=>{printed++;}};
const document = {
  querySelectorAll: selector => ({'[role="tab"]':tabs,'[role="tabpanel"]':panels,'[data-series]':figures,'details:not([open])':details.filter(x=>!x.open)})[selector],
  getElementById: id => elements[id]
};
const script = fs.readFileSync(path.join(__dirname,'../assets/html-report/report.js'),'utf8');
vm.runInNewContext(script,{window,document});
check(panels.filter(x=>!x.hidden).map(x=>x.id).join()==='overview','initial overview only');
check(tabs[0].attrs['aria-selected']==='true' && tabs[1].tabIndex===-1,'initial ARIA and roving focus');
check(figures.filter(x=>!x.hidden).map(x=>x.id).join()==='revenue','initial revenue chart only');
check(elements['annual-table'].hidden && !elements.charts.hidden,'initial chart view');
tabs[1].fire('click');
check(!panels[1].hidden && panels[0].hidden,'click financial tab');
let prevented = false;
tabs[1].fire('keydown',{key:'End',preventDefault:()=>{prevented=true;}});
check(prevented && focused==='tab-risks' && !panels[3].hidden,'End selects last tab and focus');
tabs[3].fire('keydown',{key:'ArrowRight',preventDefault:()=>{}});
check(focused==='tab-overview' && !panels[0].hidden,'right arrow wraps');
tabs[0].fire('keydown',{key:'ArrowLeft',preventDefault:()=>{}});
check(focused==='tab-risks','left arrow wraps');
tabs[3].fire('keydown',{key:'Home',preventDefault:()=>{}});
check(focused==='tab-overview','Home selects first tab');
for (const key of keys) {
  elements.indicator.value=key;elements.indicator.fire('change');
  check(figures.filter(x=>!x.hidden).map(x=>x.id).join()===key,'switch indicator '+key);
}
elements['view-toggle'].fire('click');
check(elements.charts.hidden && !elements['annual-table'].hidden && elements['view-toggle'].attrs['aria-pressed']==='true','table toggle with ARIA');
elements['view-toggle'].fire('click');
check(!elements.charts.hidden && elements['annual-table'].hidden,'chart toggle back');
elements.print.fire('click');check(printed===1,'print button delegates to native print');
tabs[2].fire('click');events.beforeprint();
check(details.every(x=>x.open),'print expands every detail');
events.afterprint();
check(!details[0].open && details[1].open,'print restores prior disclosure state');
check(!panels[2].hidden && tabs[2].attrs['aria-selected']==='true','print restores selected tab');
check(figures.filter(x=>!x.hidden).map(x=>x.id).join()==='eps_yoy','print restores indicator');
console.log(JSON.stringify({passed:true,checks,scope:'Node DOM contract only; no actual browser, viewport, offline loading or print layout verification'}));
