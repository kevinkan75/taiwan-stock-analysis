"""Independent numeric boundaries and actual production decision/ETF round trips."""
from copy import deepcopy
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import numeric_rules as nr
import decision_guard as d
import etf_guard as e
import snapshot_guard as stock

BASE=json.loads((ROOT/'assets/decision.example.json').read_text())
RAW=(ROOT/'tests/research.decision.example.json').read_bytes();RESEARCH=json.loads(RAW)
ETF=json.loads((ROOT/'assets/etf.example.json').read_text())
count=0


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def report_research(s):
    o=s['overall'];cap=s.get('overall',{}).get('concentration_cap')
    s['report_markdown']='\n'.join(['規則版本 '+s['rule_version'],'估值位置：合成數值','下一個催化劑：尚未確認','最大單一風險：僅合成來源','關鍵缺口：僅核對程式規則',
        '整體投資訊號：%s；總分：%s；暫定：%s；信心：%s'%(d.SIGNAL_LABELS[o['signal']],o['score'] if o['score'] is not None else '不計分','是' if o['provisional'] else '否',{'high':'高','medium':'中','low':'低',None:'未評定'}[o['confidence']])])
    if cap is not None:s['report_markdown']+='\n集中度上限：'+{'none':'未觸發','yellow':'🟡','unknown':'待確認'}[cap]+'\n'+e.SCOPE_LINE
    s['report_sha256']=hashlib.sha256(s['report_markdown'].encode()).hexdigest()


def seal_etf(s):
    r=e.validate(s,True);check(r['valid'],str(r['errors']));out=e.derived_snapshot(s,r);report_research(out);out['validated']=True
    check(e.validate(out)['valid'],str(e.validate(out)['errors']));return out


def candidate(research):
    s=deepcopy(BASE);s['security']=research['security'];s['gates'][0]['signal']=d.research_gate(research)
    raw=(json.dumps(research,ensure_ascii=False)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
    s['research_reference'].update(sha256=sha,model_version=research['model_version'],rule_version=research.get('rule_version'),analysis_at=research['analysis_at'],data_cutoff_at=research['data_cutoff_at'],verification='etf_snapshot' if research['security']['instrument']=='etf' else 'stock_snapshot')
    if research['security']['instrument']=='etf':
        n=s['numeric_inputs']['gate_2'];n.update(origin='provider',kind='bond_yield' if research['subtype']=='債券型' else 'etf_equity_multiple',metric_key='current_ytm_pct' if research['subtype']=='債券型' else 'weighted_pe')
        if research['subtype']=='債券型':n['point'].update(current=5,low=2,median=4,high=7,scenario_price=90,downside_pct=10)
        else:n['point'].update(current=20,low=10,median=20,high=30,scenario_price=None,downside_pct=0)
        s['numeric_inputs']['gate_6']['point']['premium_pct']=research['metrics']['premium_discount_pct']['value']
        n=s['numeric_inputs']['gate_7'];n.update(origin='research',kind='etf_score',window_start=None,window_end=None)
        for k,v in n['point'].items():n['point'][k]=False if isinstance(v,bool) else None
    return s,raw,sha


def roundtrip(s,research,sha,expected=None):
    original=deepcopy(research);r=d.validate(s,research,sha,True);check(r['valid'],str(r['errors']))
    out=d.derived_record(s,r)
    if expected is not None:check(out['numeric_checks']['gates'][expected[0]]['signal']==expected[1],str(out['numeric_checks']))
    action=out['conclusion']['action'];out['conditions']['batches']=[];out['conditions']['waiting_for']=[]
    if action=='staged':out['conditions']['batches']=[{'trigger':'補齊所有前置條件後再評估','requires_clearance':out['conclusion']['first_batch_requirements']},{'trigger':'後續來源支持再評估','requires_clearance':['gate_3']}]
    if action=='wait':out['conditions']['waiting_for']=[{'target':target,'description':'補查'+target+'原始資料並重新核對'} for target in ['quote','research']+['gate_%d'%n for n in range(1,9)]]
    out['report_markdown']=research['report_markdown']+'\n'+d.report_block(out,out['conclusion']);out=d.derived_record(out,r)
    check(d.validate(out,research,sha)['valid'],str(d.validate(out,research,sha)['errors']))
    check(research==original,'decision must not alter original research');return out


def reject(s,research,sha,fragment,derive=False):
    r=d.validate(s,research,sha,derive);check(not r['valid'] and any(fragment in x for x in r['errors']),str(r['errors']))


def main():
    # Explicit expected answers, independent of the production validator.
    p=deepcopy(BASE['numeric_inputs']['gate_2']['point'])
    for cur,mid,down,expected in [(19,20,15,'green'),(20,20,15,'yellow'),(19,20,15.001,'yellow'),(19,20,30,'yellow'),(19,20,30.001,'red'),(23.8,20,10,'red')]:
        x=dict(p,current=cur,median=mid,downside_pct=down);check(nr.gate_2(x,'stock_multiple',True)['signal']==expected,'gate 2 exact bounds')
    for value,expected in [(79.999,'yellow'),(80,'red')]:
        x=dict(p,percentile_pct=value);check(nr.gate_2(x,'stock_multiple',True)['signal']==expected,'percentile boundary')
    for down,expected in [(15,'green'),(15.001,'yellow'),(30,'yellow'),(30.001,'red')]:
        x=dict(p,current=6,low=2,median=5,high=7,downside_pct=down);check(nr.gate_2(x,'bond_yield',True)['signal']==expected,'bond yield direction')
    x=dict(p,current=19,low=20,median=20,high=20);check(nr.gate_2(x,'stock_multiple',True)['signal']=='unknown','degenerate band is not green')
    x=dict(p,current=19,low=10,median=20,high=30,downside_pct=15.001);check(nr.gate_2(x,'etf_equity_multiple',True)['signal']=='green','ETF own gate 2 does not use stock 15% condition')
    p=BASE['numeric_inputs']['gate_6']['point']
    for rsi,expected in [(40,'green'),(64.999,'green'),(65,'yellow'),(75,'yellow'),(75.001,'red'),(39.999,'yellow')]:check(nr.gate_6(dict(p,rsi14=rsi),False)['signal']==expected,'RSI bounds')
    for close,sma,expected in [(108,100,'yellow'),(115,100,'yellow'),(115.001,100,'red'),(85,100,'yellow'),(100,120,'yellow')]:
        x=dict(p,close=close,sma20=sma,sma60=80,sma120=80);check(nr.gate_6(x,False)['signal']==expected,'signed deviation bounds')
    for premium,expected in [(1,'green'),(1.001,'yellow'),(3,'yellow'),(3.001,'red')]:check(nr.gate_6(dict(p,premium_pct=premium),True)['signal']==expected,'ETF current premium caps')
    x=dict(p,sma20=None,rsi14=76);check(nr.gate_6(x,False)['signal']=='red','confirmed overheating precedes missing SMA')
    x=dict(p,close=80,macd=None);check(nr.gate_6(x,False)['signal']=='unknown','weak price plus missing MACD cannot be neutral')
    p=BASE['numeric_inputs']['gate_7']['point']
    for old,new,oldp,newp,expected in [(100,110,100,110,'green'),(100,110,100,120,'yellow'),(100,110,100,120.001,'red'),(100,100,100,101,'red'),(100,100,100,100,'yellow'),(100,90,100,100,'red'),(100,90,110,100,'yellow'),(0,100,100,100,'unknown')]:
        x=dict(p,previous_earnings=old,current_earnings=new,previous_price=oldp,current_price=newp);check(nr.gate_7(x)['signal']==expected,'growth bounds and zero/negative base')
    check(nr.gate_7(dict(p,previous_earnings=None,quality_issue_confirmed=True))['signal']=='red','confirmed earnings quality issue first')
    # Actual production binding, numeric derivation and final report validation.
    s,raw,sha=candidate(RESEARCH);out=roundtrip(s,RESEARCH,sha)
    for change,fragment in [(lambda x:x['gates'][5].update(signal='yellow'),'gate_6'),(lambda x:x['numeric_checks']['gates']['gate_2'].update(signal='green'),'numeric_checks'),(lambda x:x['numeric_inputs']['gate_2']['point'].update(reference_price=99),'referenced research'),(lambda x:x['numeric_inputs']['gate_2']['point'].update(downside_pct=11),'downside arithmetic'),(lambda x:x['numeric_inputs']['gate_6']['point'].update(rsi14=76),'referenced research'),(lambda x:x['numeric_inputs']['gate_6'].update(recent_sessions=['2026-10-07']),'latest completed'),(lambda x:x['numeric_inputs']['gate_7']['point'].update(current_earnings=6),'known_current_earnings')]:
        bad=deepcopy(out);change(bad);reject(bad,RESEARCH,sha,fragment)
    s,_,sha=candidate(RESEARCH);s['numeric_inputs']['gate_2']['origin']='provider';s['numeric_inputs']['gate_2']['point'].update(low=10,median=25,high=30)
    roundtrip(s,RESEARCH,sha,('gate_2','green'))
    s['numeric_inputs']['gate_2']['sample'].update(kind='short',years=0);roundtrip(s,RESEARCH,sha,('gate_2','yellow'))
    s['numeric_inputs']['gate_2']['point']['percentile_pct']=80;roundtrip(s,RESEARCH,sha,('gate_2','red'))
    s['numeric_inputs']['gate_2']['point']['current']=12;reject(s,RESEARCH,sha,'known_current_metric',True)
    s,_,sha=candidate(RESEARCH);n=s['numeric_inputs']['gate_6'];n['origin']='provider';n['quality']='conflicting';n['alternatives']=[dict(n['point'],rsi14=76)];roundtrip(s,RESEARCH,sha,('gate_6','red'))
    n['alternatives']=[];reject(s,RESEARCH,sha,'explicit numeric alternatives',True)
    n['origin']='research';n['alternatives']=[dict(n['point'],rsi14=76)];reject(s,RESEARCH,sha,'referenced research',True)
    s,_,sha=candidate(RESEARCH);s['numeric_inputs']['gate_6'].update(origin='provider',as_of='2026-10-07');roundtrip(s,RESEARCH,sha,('gate_6','unknown'))
    s,_,sha=candidate(RESEARCH);n=s['numeric_inputs']['gate_7'];n['point'].update(previous_earnings=2.5,previous_price=50);n['window_start']=None;roundtrip(s,RESEARCH,sha,('gate_7','unknown'))
    n['point']['quality_issue_confirmed']=True;roundtrip(s,RESEARCH,sha,('gate_7','red'))
    # ETF gate 7 cannot be supplied independently of its research score.
    source=seal_etf(deepcopy(ETF));s,raw,sha=candidate(source);out=roundtrip(s,source,sha,('gate_7','green'))
    bad=deepcopy(out);bad['gates'][6]['signal']='yellow';reject(bad,source,sha,'gate_7')
    bad=deepcopy(out);bad['numeric_inputs']['gate_7']['origin']='provider';reject(bad,source,sha,'directly use research',True)
    negative=deepcopy(ETF);negative['earnings_support_inputs'].update(previous_earnings=100,current_earnings=90,nav_return_pct=0)
    next(x for x in negative['scores']['valuation']['items'] if x['check']=='earnings_support')['score']=1
    source=seal_etf(negative);s,_,sha=candidate(source);roundtrip(s,source,sha,('gate_7','yellow'))
    # ETF source and numeric input tampering cannot masquerade as validation.
    for mutate,fragment in [(lambda x:x['subtype_inputs']['premium'].update(observations=19),'numeric score'),(lambda x:x['subtype_inputs']['premium'].update(mean_abs20_pct=1.1),'numeric score')]:
        bad=deepcopy(ETF);mutate(bad);r=e.validate(bad,True);check(not r['valid'] and any(fragment in x for x in r['errors']),str(r['errors']))
    for mean,maximum,expected in [(.5,1.5,2),(.50001,1.5,1),(1.5,4,1),(1.50001,4,0),(.5,4.0001,0)]:check(nr.premium_score(mean,maximum,True)==expected,'cross-border premium thresholds')
    for excess,expected in [(0,2),(-.001,1),(-2,1),(-2.001,0)]:check(nr.active_score(excess)==expected,'active excess thresholds')
    for subtype in ('跨境股票型','主動式'):
        x=deepcopy(ETF);u=x['sources'][0]['url'];x['subtype']=subtype
        if subtype=='跨境股票型':
            x['subtype_inputs']['cross_border']=True;x['subtype_inputs']['fx_hedging'].update(status='unhedged',source_urls=[u]);item=next(t for t in x['scores']['risk']['items'] if t['check']=='structural_risk')
            r=e.validate(x,True);check(not r['valid'] and any('cap is one' in z for z in r['errors']),'unhedged cap enforcement');item['score']=1;seal_etf(x)
            x['subtype_inputs']['fx_hedging']['status']='unknown';r=e.validate(x,True);check(not r['valid'],'unknown hedge cannot retain a known score');item['score']=None
            unknown=seal_etf(x);check(unknown['overall']['signal']!='green' and unknown['overall']['confidence'] in ('medium','low',None),'unknown FX must not improve the headline or confidence')
        else:
            x['subtype_inputs']['active_management']=True;x['subtype_inputs']['active_return'].update(net_annual_excess_pct=-2,complete_years=1,start='2025-10-09',end='2026-10-08',same_currency=True,total_return=True,net_of_fees=True,source_urls=[u]);m=deepcopy(x['metrics']['tracking_difference_pct']);m.update(value=-2,value_status='reported');x['metrics']['tracking_difference_pct']=m
            next(t for t in x['scores']['instrument']['items'] if t['check']=='tracking_quality')['score']=1;seal_etf(x)
            x['subtype_inputs']['active_return']['net_of_fees']=False;r=e.validate(x,True);check(not r['valid'],'gross excess cannot be claimed as net score')
    # Bond inputs are numeric, while the four research assessments are explicitly manual.
    x=deepcopy(ETF);u=x['sources'][0]['url'];x['subtype']='債券型';x['fund']['underlying_asset']='bond';x['metrics']['weighted_pe'].update(value=None,value_status='missing',inputs=None,formula=None);x['earnings_support_inputs'].update(basis='bond_manual',previous_earnings=None,current_earnings=None,nav_return_pct=None)
    b=x['subtype_inputs']['bond'];b.update(modified_duration=8,yield_shift_pct=1,approx_price_change_pct=-8,current_ytm_pct=5,benchmark_ytm_pct=4,credit_spread_pct=1,credit_maturity_comparable=True,rate_trend='rising',source_urls=[u])
    for a in b['manual_assessments'].values():a.update(status='checked',reason='合成已人工核對，評分不是程式判定',source_urls=[u])
    bond=seal_etf(x);s,_,sha=candidate(bond);roundtrip(s,bond,sha,('gate_2','green'))
    bad=deepcopy(x);bad['subtype_inputs']['bond']['approx_price_change_pct']=8;r=e.validate(bad,True);check(not r['valid'] and any('duration approximation' in z for z in r['errors']),'duration sign')
    bad=deepcopy(x);bad['subtype_inputs']['bond']['credit_spread_pct']=2;r=e.validate(bad,True);check(not r['valid'] and any('spread mismatch' in z for z in r['errors']),'credit spread arithmetic')
    bad=deepcopy(x);bad['subtype_inputs']['bond']['manual_assessments']['band_position']['status']='insufficient';r=e.validate(bad,True);check(not r['valid'],'bond manual check cannot be omitted')
    # Archived bytes and complete ETF derivation remain unchanged.
    baseline=json.loads((ROOT/'tests/etf_rules.baseline.json').read_text());raw=(ROOT/baseline['input']).read_bytes();old=json.loads(raw);r=e.validate(old,True);check(r['valid'],'archived ETF accepts old schema')
    derived=e.derived_snapshot(old,r);canonical=json.dumps(derived,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    check(hashlib.sha256(raw).hexdigest()==baseline['input_sha256'] and hashlib.sha256(canonical).hexdigest()==baseline['derived_sha256'],'exact frozen ETF record and output hashes')
    # Current CLI derives the numeric gates, then checks a complete final record.
    s,raw,sha=candidate(RESEARCH);out=roundtrip(s,RESEARCH,sha)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);src=path/'research.json';src.write_bytes(raw);inp=path/'decision.json';inp.write_text(json.dumps(out,ensure_ascii=False))
        cmd=[sys.executable,'-B',str(ROOT/'scripts/decision_guard.py'),str(inp),'--research',str(src)]
        p=subprocess.run(cmd,capture_output=True,text=True);check(p.returncode==0 and json.loads(p.stdout)['scope']=='decision_numeric_gates_and_conclusion','current CLI default validation')
        p=subprocess.run(cmd+['--render'],capture_output=True,text=True);check(p.returncode==0 and d.numeric.SCOPE_LINE in json.loads(p.stdout)['report_block'],'current CLI renders correct scope')
        p=subprocess.run(cmd+['--derive'],capture_output=True,text=True);check(p.returncode==0 and json.loads(p.stdout)['numeric_checks']==out['numeric_checks'],'CLI numeric derivation')
    print(json.dumps({'passed':True,'checks':count,'scope':'numeric gates, subtype boundaries, binding, actual CLI and archived ETF output; synthetic only'}))


if __name__=='__main__':main()
