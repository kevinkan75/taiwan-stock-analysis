"""Offline synthetic export integrity tests; not browser visual acceptance."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import html_export as export
import review_guard as review
import snapshot_guard as stock
import etf_guard as etf
import decision_guard as decision
import audit_fixtures
import financial_history_fixtures as annual_fixtures

count=0
S=json.loads((ROOT/'assets/snapshot.example.json').read_bytes())
R=json.loads((ROOT/'assets/review.example.json').read_bytes())
AT='2026-10-16T12:00:00+08:00'


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def encode(x):return (json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def pair(mutator=None):
    s=deepcopy(S);r=deepcopy(R)
    if mutator:mutator(s,r)
    audit_fixtures.finish_review(r,s)
    return s,r,encode(s),encode(r)


class Inspect(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.tags=[];self.attrs=[];self.original=[];self.in_original=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.tags.append(tag);self.attrs.append(a)
        if a.get('id')=='original-report':self.in_original=True
    def handle_endtag(self,tag):
        if tag=='pre':self.in_original=False
    def handle_data(self,data):
        if self.in_original:self.original.append(data)


def main():
    args=pair();s,r,raw,rr=args;before=(deepcopy(s),deepcopy(r),raw,rr)
    output=export.render(*args,AT)
    check(export.verify(output,*args)['valid'],'exact deterministic render verifies')
    check(export.render(*args,AT)==output,'same source and export timestamp reproducible')
    check((s,r,raw,rr)==before,'renderer does not mutate inputs or research judgments')
    p=Inspect();p.feed(output)
    check(''.join(p.original)==s['report_markdown'],'full original report preserved as literal text')
    check(p.tags.count('section')==4,'exact four panels')
    check(sum(a.get('role')=='tab' for a in p.attrs)==4,'four accessible tabs')
    check(sum(a.get('role')=='tabpanel' for a in p.attrs)==4,'four linked panels')
    native_tabs=[a for tag,a in zip(p.tags,p.attrs) if a.get('role')=='tab']
    check([a.get('href') for a in native_tabs]==['#overview','#financials','#valuation','#risks'],'native chapter targets work without JavaScript')
    check(all(tag=='a' for tag,a in zip(p.tags,p.attrs) if a.get('role')=='tab'),'chapter controls are native links')
    check(all('hidden' not in a and 'tabindex' not in a for a in p.attrs if a.get('role')=='tabpanel'),'all four chapters readable and not focus-boxed without JavaScript')
    check('href="#print-help"' in output and 'id="print-help"' in output and 'iPhone／iPad' in output,'native print help available without script')
    cells=[a for tag,a in zip(p.tags,p.attrs) if tag=='td']
    check(cells and all(a.get('data-label') for a in cells),'all table cells retain mobile field labels')
    check('data-label="指標"' in output and 'data-label="期間與口徑"' in output,'valuation card labels use independent expected column names')
    hostile_header=export.table(['<img src=x onerror=alert(1)>'],[['safe']], 'safe')
    check('data-label="&lt;img' in hostile_header and '<img' not in hostile_header,'mobile header attributes remain escaped')

    check(sum('data-series' in a for a in p.attrs)==9,'nine annual indicators')
    check(p.tags.count('svg')==9,'all charts embedded SVG')
    check(p.tags.count('script')==2,'only fixed script and non-executable manifest')
    check(all(not any(k.lower().startswith('on') for k in a) for a in p.attrs),'no source-authored event handlers')
    check(all('src' not in a for a in p.attrs),'no external fetch resources')
    check(not any(tag in p.tags for tag in ('iframe','object','embed','img','link')),'no external embed tags')
    check('connect-src &#x27;none&#x27;' not in output and "connect-src 'none'" in output,'CSP forbids network requests')
    check('18.00' in output and '26.67' in output and '2025-12-31' in output,'independent annual numeric expectations')
    check('報價／模型幣別' in output and '年度財報幣別' in output,'separate quote and financial currencies')
    check('查核作業<b>已完成' in output and '證據充分性<b>足夠' in output,'separate workflow and evidence')
    check('未宣稱目前仍未發生' in output,'scheduled event limited to source cutoff')
    check('合成資料' in output,'synthetic source labels remain visible')
    check('請見原報告；來源未提供獨立摘要行' not in output,'all four validated source summaries shown')
    check('100.00' in output and 'TWD/share' in output,'price value and original quote unit preserved')
    bad=deepcopy(s);bad['metrics']['price']['value']=101
    try:export.render(bad,r,raw,rr,AT)
    except ValueError:check(True,'invalid source rejected without repair')
    else:check(False,'invalid source exported')
    for old,new in [('18.00','19.00'),('證據充分性<b>足夠','證據充分性<b>不足'),('原研究訊號','偽造訊號'),('1.0.1','9.9.9')]:
        try:export.verify(output.replace(old,new,1),*args)
        except ValueError:check(True,'reject tampered '+old)
        else:check(False,'tampered export accepted '+old)
    for invalid in ['no manifest',output.replace('id="export-manifest"','id="wrong"')]:
        try:export.verify(invalid,*args)
        except ValueError:check(True,'reject missing manifest')
        else:check(False,'missing manifest accepted')
    # Missing CFO and an independent cash residual must survive all presentation layers.
    def conflict(s,r):
        annual_fixtures.missing(r['financial_history']['periods'][1]['inputs']['cfo'])
        r['financial_history']['periods'][2]['inputs']['cash_cf_end']['raw_value']=32
    conflict_args=pair(conflict);o=export.render(*conflict_args,AT);f=conflict_args[1]['assessment']['financial_history']
    check(f['status']=='conflicting','valid conflict not repaired into complete')
    check(f['rows'][1]['fcf'] is None,'missing annual cash flow stays null')
    check('查核作業<b>已完成' in o and '證據充分性<b>不足' in o,'valid structure is not all-green evidence')
    check('⚠ 限制與提醒' in o and '衝突' in o and '-2,000,000.00' in o,'residual and warning explicit')
    svg=export.chart(f['rows'],'fcf','FCF','百萬',1e6)
    check('<polyline' not in svg and svg.count('<circle')==2 and '未取得' in svg,'do not connect across null or draw null as zero')
    check(export.verify(o,*conflict_args)['valid'],'honest conflict allowed to export')
    for n in [0,1,2]:
        def short(s,r):r['financial_history']['periods']=r['financial_history']['periods'][-n:] if n else []
        a=pair(short);f=a[1]['assessment']['financial_history'];o=export.render(*a,AT)
        check(f['periods']==n and len(f['rows'])==n,'do not manufacture third annual row '+str(n))
        check(export.verify(o,*a)['valid'],'valid incomplete export '+str(n))
    def injection(s,r):
        payload='</script><img src=x onerror="alert(1)">&<svg onload=alert(2)>'
        s['security']['name']=payload;r['security']['name']=payload
        s['data_gaps'].append(payload);s['report_markdown']+='\n'+payload
    a=pair(injection);o=export.render(*a,AT);p=Inspect();p.feed(o)
    check(p.tags.count('script')==2 and 'img' not in p.tags,'untrusted source cannot close script or inject tags')
    check(all(not any(k.lower().startswith('on') for k in x) for x in p.attrs),'untrusted event handlers escaped')
    check(''.join(p.original)==a[0]['report_markdown'],'hostile report exact text preserved')
    for url in ['javascript:alert(1)','data:text/html,<script>','file:///etc/passwd','https://example.invalid/\nattack','https://[invalid']:
        check('<a ' not in export.safe_link(url),'unsafe URL is text '+url)
    check('href="https://example.invalid/?x=&quot;a&quot;&amp;y=b"' in export.safe_link('https://example.invalid/?x="a"&y=b'),'safe href attribute escaped')
    check(export.number(None)=='— 未取得' and export.number(0)=='0.00','null and actual zero distinct')
    # Frozen release bytes and calculations must remain unchanged.
    baseline=json.loads((ROOT/'tests/release-1.13.0.baseline.json').read_bytes())
    for name,sha in baseline['files'].items():check(export.digest((ROOT/name).read_bytes())==sha,'frozen bytes '+name)
    for name,g in [('snapshot',stock),('etf',etf)]:
        obj=json.loads((ROOT/('tests/'+name+'.rule-1.13.0.json')).read_bytes());result=g.validate(obj)
        check(result['valid'],'archived release remains valid '+name)
        out=stock.derived_snapshot(obj,result) if name=='snapshot' else result['derived']
        check(export.digest(export.encode(out).encode())==baseline['derived'][name],'frozen derived '+name)
    d=json.loads((ROOT/'tests/decision.rule-1.13.0.json').read_bytes());dr=(ROOT/'tests/research.decision.example.json').read_bytes()
    check(decision.validate(d,json.loads(dr),export.digest(dr))['valid'],'archived decision remains fully valid')
    oldraw=(ROOT/'tests/snapshot.rule-1.13.0.json').read_bytes();oldrr=(ROOT/'tests/review.rule-1.13.0.json').read_bytes()
    olds=json.loads(oldraw);oldr=json.loads(oldrr)
    legacy=deepcopy(oldr);legacy.update(schema_version='1.1',model_version='review-1.1',skill_version='1.12.0',rule_version='1.12.0',validator_version='1.1.0');legacy.pop('financial_history');legacy['assessment'].pop('financial_history')
    check(not review.validate(legacy,olds,oldraw)['valid'],'archived annual research cannot be wrapped by an older review')
    o=export.render(olds,oldr,oldraw,oldrr,AT)
    check(export.verify(o,olds,oldr,oldraw,oldrr)['valid'] and '原研究規則 1.13.0' in o,'old release exported without relabeling source')
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);source=d/'s.json';record=d/'r.json';target=d/'report.html'
        source.write_bytes(raw);record.write_bytes(rr)
        command=[sys.executable,str(ROOT/'scripts/html_export.py'),'--research',str(source),'--review',str(record)]
        def cli(tail):return subprocess.run(command+tail,capture_output=True,text=True)
        check(cli(['--output',str(target),'--exported-at',AT]).returncode==0,'actual CLI exports')
        check(cli(['--verify',str(target)]).returncode==0,'actual CLI verifies')
        check(cli(['--output',str(target)]).returncode==2,'existing output not overwritten')
        check(cli(['--output',str(source)]).returncode==2 and source.read_bytes()==raw,'source overwrite refused')
        record.write_bytes(rr+b' ')
        check(cli(['--verify',str(target)]).returncode==2,'review exact byte change rejected by export fingerprint')
        record.write_bytes(rr)
        source.write_bytes(raw+b' ')
        check(cli(['--output',str(d/'bad.html')]).returncode==2 and not (d/'bad.html').exists(),'source byte mismatch refused before output')
        source.write_bytes(raw)
        wrong=deepcopy(r);wrong['mode']='decision';record.write_bytes(encode(wrong))
        check(cli(['--output',str(d/'decision.html')]).returncode==2,'decision export refused')
        source.write_bytes((ROOT/'assets/etf.example.json').read_bytes())
        check(cli(['--output',str(d/'etf.html')]).returncode==2,'ETF export refused')
        source.write_bytes(raw);wrong=deepcopy(r);wrong['schema_version']='1.1';record.write_bytes(encode(wrong))
        check(cli(['--output',str(d/'legacy.html')]).returncode==2,'old review schema not backfilled')
    css=(ROOT/'assets/html-report/report.css').read_text()
    check('@media print' in css and '#annual-table[hidden]' in css and 'section[hidden]' in css and 'figure[hidden]' in css,'print CSS explicitly reveals all panels/charts/table')
    check('@media(max-width:640px)' in css and 'grid-template-columns:1fr' in css and 'overflow-x:auto' in css,'mobile CSS and table scrolling specified')
    check('max-width:1440px' in css and 'max-width:1180px' in css and 'evidence-cards' in css,'desktop width and tablet evidence layout specified')
    check('@media screen and (max-width:760px)' in css and 'content:attr(data-label)' in css and '.table-scroll td{display:block' in css,'mobile tables stack independently of JavaScript')
    check('.js-only{display:none}' in css and '.js-ready .controls{display:flex}' in css,'nonfunctional enhanced-only controls hidden until script succeeds')
    check('focus-visible' in css and 'content-visibility:visible' in css,'focus and expanded print details specified')
    print(json.dumps({'passed':True,'checks':count,'scope':'synthetic export, CLI, security and frozen-source integrity; browser visual acceptance not tested'},ensure_ascii=False))


if __name__=='__main__':main()
