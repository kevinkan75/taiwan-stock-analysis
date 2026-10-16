"""Production decision calls, source binding, report mutation and exhaustive safety properties."""
from copy import deepcopy
import hashlib
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import decision_guard as d
import snapshot_guard as g

BASE = json.loads((ROOT/'tests/decision.rule-1.9.0.json').read_text())
count = 0


def check(ok, why):
    global count
    count += 1
    if not ok: raise AssertionError(why)


def stock_source(signal='yellow'):
    s = json.loads((ROOT/'tests/snapshot.rule-1.9.0.json').read_text())
    if signal == 'green':
        for group in s['scores'].values():
            for x in group['items']: x['score'] = 2
    elif signal == 'unknown':
        for key in ('quote_verified', 'quote_is_current'):
            s['eligibility'][key] = 'fail'
            next(x for x in s['validation'] if x['check'] == key)['status'] = 'fail'
        s['quote_at'] = None
    elif signal == 'red':
        s['major_risk'].update(confirmed=True, reason='合成已確認重大風險', source_urls=[s['sources'][0]['url']])
    result = g.validate(s, True); check(result['valid'], str(result['errors']))
    s = g.derived_snapshot(s, result)
    overall = s['overall']
    s['report_markdown'] = '\n'.join(x for x in s['report_markdown'].splitlines() if '整體投資訊號' not in x)
    s['report_markdown'] += '\n整體投資訊號：%s；總分：%s；暫定：%s；信心：%s' % (
        d.SIGNAL_LABELS[overall['signal']], overall['score'] if overall['score'] is not None else '不計分',
        '是' if overall['provisional'] else '否', {'high':'高','medium':'中','low':'低',None:'未評定'}[overall['confidence']])
    s['report_sha256'] = g.report_hash(s)
    check(g.validate(s)['valid'], 'valid stock fixture')
    return s


def serialize(research):
    raw = (json.dumps(research, ensure_ascii=False, indent=2) + '\n').encode()
    return raw, hashlib.sha256(raw).hexdigest()


def record(research, signals, action='staged', clause=4):
    s = deepcopy(BASE); raw, sha = serialize(research)
    s['security'] = deepcopy(research['security'])
    s['research_reference'].update(sha256=sha, model_version=research['model_version'], rule_version=research.get('rule_version'),
        analysis_at=research['analysis_at'], data_cutoff_at=research['data_cutoff_at'],
        verification='manual_etf' if research['model_version']=='etf-1.0' else 'stock_snapshot')
    url = s['sources'][0]['url']
    s['gates'] = [{'number':n,'signal':signal,'reason':'合成人工判定，非真實投資證據',
                   'source_urls':[] if signal=='unknown' else [url]} for n,signal in enumerate(signals,1)]
    s['conditions']['waiting_for'] = [{'target':target,'description':'補齊並重新核對'+target+'所需的原始資料'}
                                     for target in ['quote']+['gate_%d'%n for n in range(1,9)]]
    s['conditions']['batches'] = [{'trigger':'第一批：資料缺口及不利條件已完成重新核對後評估',
                                  'requires_clearance':['gate_%d'%n for n in range(1,9)]},
                                 {'trigger':'第二批：後續正式資料支持論點後再評估','requires_clearance':['gate_3']}] if action=='staged' else []
    if action != 'wait': s['conditions']['waiting_for'] = []
    s['conclusion'].update(action=action, clause=clause)
    s['report_markdown'] = research.get('report_markdown', '') + '\n' + d.report_block(s, s['conclusion'])
    s['report_sha256'] = hashlib.sha256(s['report_markdown'].encode()).hexdigest()
    return s, raw, sha


def run(s, research, sha, action, clause):
    original = deepcopy(research)
    result = d.validate(s, research, sha, True)
    check(result['valid'], str(result['errors']))
    check((result['derived']['action'], result['derived']['clause']) == (action,clause), str(result['derived']))
    out = d.derived_record(s, result)
    result = d.validate(out, research, sha)
    check(result['valid'], str(result['errors']))
    check(research == original, 'research source unchanged')
    check(d.derived_record(out, d.validate(out, research, sha, True)) == out, 'idempotent decision')
    return out


def reject(s, research, sha, fragment):
    result = d.validate(s, research, sha)
    check(not result['valid'] and any(fragment in x for x in result['errors']), str(result['errors']))


def main():
    # The expected actions are stored human decisions, never supplied by classify.
    shapes = {
        'A':['unknown']*8,
        'B':['green']*6+['yellow','yellow'],
        'C':['yellow','red','green','green','green','green','red','green'],
        'D':['yellow']*7+['red'],
        'E':['green','yellow','green','green','green','yellow','yellow','green'],
        'F':['green','green','green','unknown','green','green','yellow','green'],
        'G':['green']*6+['red','green'],
        'H':['green']*8,
    }
    cases = json.loads((ROOT/'tests/decision_cases.json').read_text())['cases']
    for case in cases:
        research = stock_source(shapes[case['id']][0])
        s, raw, sha = record(research, shapes[case['id']], case['action'], case['clause'])
        if case['id']=='A': s['quote_context']['latest_completed_session_at'] = None
        out = run(s,research,sha,case['action'],case['clause'])
        if case['id']=='F': check(out['conclusion']['first_batch_requirements'] == ['gate_4'], 'unknown market must precede first batch')
    research = stock_source(); s, raw, sha = record(research, ['yellow','yellow','yellow','green','green','yellow','yellow','green'])
    out = run(s,research,sha,'staged',4)
    for change, fragment in [
        (lambda x:x['conclusion'].update(action='enter'), 'conclusion'),
        (lambda x:x['conclusion'].update(clause=3), 'conclusion'),
        (lambda x:x['research_reference'].update(sha256='0'*64), 'source file hash'),
        (lambda x:x['security'].update(symbol='OTHER'), 'security'),
        (lambda x:x['gates'][0].update(signal='green'), 'gate_1'),
        (lambda x:x['gates'][1].update(number=1), 'unique gates'),
        (lambda x:x['gates'][2].update(source_urls=[]), 'evidence URLs'),
        (lambda x:x['conditions'].update(batches=[]), 'two conditional batches'),
        (lambda x:x.update(validator_version='9.0.0'), 'release profile'),
        (lambda x:x['quote_context'].update(latest_completed_session_at='2026-10-09T13:30:00+08:00'), 'latest completed session'),
    ]:
        bad = deepcopy(out); change(bad); reject(bad,research,sha,fragment)
    bad = deepcopy(out); bad['gates'].append(deepcopy(bad['gates'][0])); reject(bad,research,sha,'too many items')
    bad = deepcopy(out); bad['report_markdown'] = bad['report_markdown'].replace('行動結論：分批','行動結論：進場');bad['report_sha256']=hashlib.sha256(bad['report_markdown'].encode()).hexdigest();reject(bad,research,sha,'action/clause line')
    bad = deepcopy(out); bad['report_markdown'] = bad['report_markdown'].replace('| 2 | 估值紀律 | 🟡','| 2 | 估值紀律 | 🟢');bad['report_sha256']=hashlib.sha256(bad['report_markdown'].encode()).hexdigest();reject(bad,research,sha,'gate table')
    bad = deepcopy(out); bad['report_markdown'] += '\nchanged';reject(bad,research,sha,'text hash')
    # Freshness uses the current decision context, not the old source's pass flag alone.
    stale = deepcopy(out); stale['analysis_at']='2026-10-09T18:05:00+08:00';stale['data_cutoff_at']='2026-10-09T13:30:00+08:00'
    stale['quote_context'].update(latest_completed_session_at='2026-10-09T13:30:00+08:00',verified_at='2026-10-09T18:05:00+08:00')
    result=d.validate(stale,research,sha,True);check(result['valid'] and result['derived']['action']=='wait','stale source cannot enter')
    check(result['research_refresh_required'], 'previous trading day requires new research before buying')
    reject(stale,research,sha,'waiting_for')
    stale['conditions']['waiting_for']=[{'target':'research','description':'重新完成10月9日的研究及報價核對後再判斷'}]
    stale['conditions']['batches']=[]
    stale['report_markdown']=research['report_markdown']+'\n'+d.report_block(stale,result['derived'])
    stale=d.derived_record(stale,d.validate(stale,research,sha,True))
    check(d.validate(stale,research,sha)['valid'],'stale source can support a clearly scoped waiting record')
    equivalent=deepcopy(out);equivalent['quote_context']['latest_completed_session_at']='2026-10-08T05:30:00Z';check(d.validate(equivalent,research,sha)['valid'],'timezone equivalent session')
    check(not d.validate(equivalent,research,sha)['research_refresh_required'],'equivalent timezone is not a new trading day')
    previous=deepcopy(out);previous['quote_context']['latest_completed_session_at']='2026-10-07T13:30:00+08:00'
    check(d.validate(previous,research,sha)['valid'] and not d.validate(previous,research,sha)['research_refresh_required'],'fresh quote newer than last completed session needs no refresh')
    badsource=deepcopy(research);badsource['overall']['score']=99;reject(out,badsource,sha,'research:')
    # Required follow-ups/clearance are derived, not generic commentary.
    market=['yellow','yellow','green','unknown','green','red','unknown','green']
    partial, _, psha=record(research,market);partial=run(partial,research,psha,'staged',4)
    check(partial['conclusion']['first_batch_requirements']==['gate_4','gate_7','gate_6'],'first-batch clearance list')
    partial['conditions']['batches'][0]['requires_clearance']=[];reject(partial,research,psha,'missing required gate clearance')
    unknown=stock_source('unknown');white,_,wsha=record(unknown,['unknown']*8,'wait',2);white['quote_context']['latest_completed_session_at']=None
    white=run(white,unknown,wsha,'wait',2)
    bad=deepcopy(white);bad['conclusion'].update(action='enter',clause=3);bad['report_markdown']=bad['report_markdown'].replace('行動結論：等待；命中條款：2','行動結論：進場；命中條款：3');bad['report_sha256']=hashlib.sha256(bad['report_markdown'].encode()).hexdigest();reject(bad,unknown,wsha,'conclusion')
    bad=deepcopy(white);bad['conditions']['waiting_for']=[{'target':'research','description':'再觀察'}];reject(bad,unknown,wsha,'concrete follow-up')
    # ETF is a manual source envelope: action validation must not certify ETF scores.
    etf=deepcopy(research);etf.update(model_version='etf-1.0',validated=False,subtype='市值型');etf['security']['instrument']='etf'
    candidate,_,esha=record(etf,['yellow','yellow','yellow','green','green','yellow','yellow','green']);candidate=run(candidate,etf,esha,'staged',4)
    check(d.validate(candidate,etf,esha)['research_verification']=='manual_etf','manual ETF scope retained')
    bad=deepcopy(candidate);bad['research_reference']['verification']='stock_snapshot';reject(bad,etf,esha,'verification scope')
    badetf=deepcopy(etf);badetf['validated']=True;reject(candidate,badetf,esha,'validated must be false')
    badetf=deepcopy(etf);badetf['subtype']='槓反／期貨／商品／加密';reject(candidate,badetf,esha,'supported, manually verified subtype')
    badetf=deepcopy(etf);badetf['metrics']='malformed';reject(candidate,badetf,esha,'positive matching price')
    # Exhaustive safety properties, not a copied four-clause oracle.
    enters=0;states=0
    for colors in product(('green','yellow','red','unknown'),repeat=8):
        signals=dict(enumerate(colors,1));original=dict(signals)
        yes=d.classify(signals,True);no=d.classify(signals,False);states+=1
        if yes['action']=='enter':
            enters+=1
            if not (all(colors[i-1]=='green' for i in (1,2,3,5,8)) and all(colors[i-1] in ('green','yellow') for i in (4,6,7))):
                raise AssertionError('unsafe enter')
        if no['action'] not in ('abandon','wait'): raise AssertionError('unready quote may not buy')
        if colors[0]=='red' or colors[7]=='red':
            if yes['action']!='abandon' or no['action']!='abandon': raise AssertionError('confirmed veto priority')
        if signals != original: raise AssertionError('classification mutated evidence')
    check(states==65536 and enters==8,'all signal combinations and exact entry combinations')
    # Actual CLI: byte hash binding, derivation and final report checks.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);src=path/'research.json';src.write_bytes(raw);inp=path/'decision.json';inp.write_text(json.dumps(out,ensure_ascii=False))
        p=subprocess.run([sys.executable,str(ROOT/'scripts/decision_guard.py'),str(inp),'--research',str(src)],capture_output=True,text=True)
        check(p.returncode==0 and json.loads(p.stdout)['valid'],'CLI final validation')
        p=subprocess.run([sys.executable,str(ROOT/'scripts/decision_guard.py'),str(inp),'--research',str(src),'--render'],capture_output=True,text=True)
        check(p.returncode==0 and 'report_block' in json.loads(p.stdout),'CLI render derived fragment')
        p=subprocess.run([sys.executable,str(ROOT/'scripts/decision_guard.py'),str(inp),'--research',str(src),'--derive'],capture_output=True,text=True)
        check(p.returncode==0 and json.loads(p.stdout)['conclusion']['action']=='staged','CLI derive')
        src.write_bytes(raw+b' ')
        p=subprocess.run([sys.executable,str(ROOT/'scripts/decision_guard.py'),str(inp),'--research',str(src)],capture_output=True,text=True)
        check(p.returncode==2 and not json.loads(p.stdout)['valid'],'CLI source bytes cannot silently change')
    print(json.dumps({'passed':True,'checks':count,'exhaustive_signal_combinations':states,'scope':'decision conclusions, binding and report/plan format; gate facts remain manual'}))


if __name__=='__main__':main()
