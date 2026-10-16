"""Independent expected boundaries, production mutations and actual ETF/decision CLI calls."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import etf_guard as e
import decision_guard as d
import rules_core as core

BASE=json.loads((ROOT/'tests/etf.rule-1.9.0.json').read_text())
count=0


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def item(s,name):return next(x for group in s['scores'].values() for x in group['items'] if x['check']==name)


def report(s):
    o=s['overall']
    s['report_markdown']='\n'.join(['規則版本 '+s['rule_version'],'估值位置：合成驗收','下一個催化劑：尚未確認','最大單一風險：僅合成資料','關鍵缺口：合成資料不是實際投資證據',
        '整體投資訊號：%s；總分：%s；暫定：%s；信心：%s'%(d.SIGNAL_LABELS[o['signal']],o['score'] if o['score'] is not None else '不計分','是' if o['provisional'] else '否',{'high':'高','medium':'中','low':'低',None:'未評定'}[o['confidence']]),
        '集中度上限：'+{'none':'未觸發','yellow':'🟡','unknown':'待確認'}[o['concentration_cap']],e.SCOPE_LINE])
    s['report_sha256']=hashlib.sha256(s['report_markdown'].encode()).hexdigest()


def seal(s):
    before=deepcopy(s)
    r=e.validate(s,True);check(r['valid'],str(r['errors']))
    out=e.derived_snapshot(s,r);report(out)
    check(e.validate(out)['valid'],str(e.validate(out)['errors']))
    check(s==before,'derivation must not mutate source')
    return out


def reject(s,fragment):
    r=e.validate(s,True)
    check(not r['valid'] and any(fragment in x for x in r['errors']),str(r['errors']))


def qualifier(s,key,status):
    s['eligibility'][key]=status
    next(x for x in s['validation'] if x['check']==key)['status']=status


def omit(s,checks):
    for name in checks:item(s,name)['score']=None
    if 'concentration' in checks:s['concentration'].update(method='missing',max_weight_pct=None,top10_weight_pct=None,holdings_complete=False,holdings=[],as_of=None)


def coverage(s,key,value):
    s['coverage'][key].update(method='reported',weight_pct=value,contributors=[])
    # Independent coverage scenarios use a published valuation, not a contradictory computed constituent list.
    s['metrics']['weighted_pe'].update(value_status='reported',inputs=None,formula=None)


def main():
    global BASE
    check(e.validate(BASE)['valid'],'bundled example validates')
    check(len({x['score'] for g in BASE['scores'].values() for x in g['items']})>1,'example does not anchor identical perfect scores')
    BASE=deepcopy(BASE)
    for group in BASE['scores'].values():
        for x in group['items']:x['score']=2
    BASE=e.derived_snapshot(BASE,e.validate(BASE,True));report(BASE)
    schema=json.loads((ROOT/'assets/etf.schema.json').read_text());e.stock.audit_keywords(schema)
    check(set(schema['properties']['scores']['properties'])==set(core.ETF_DIMENSIONS),'ETF dimensions independent of stock schema')
    for mutate,fragment in [
        (lambda s:s.update(model_version='etf-1.0'),'Legacy ETF'),
        (lambda s:s.update(subtype='槓反／期貨／商品／加密'),'not in enum'),
        (lambda s:s['fund'].update(leverage_ratio=2),'wrong constant'),
        (lambda s:s['security'].update(instrument='ordinary'),'wrong constant'),
        (lambda s:s['scores']['instrument'].update(weight=.25),'fixed weight'),
        (lambda s:item(s,'index_methodology').update(check='concentration'),'fixed checks'),
        (lambda s:item(s,'total_cost').update(score=True),'not in enum'),
        (lambda s:item(s,'total_cost').update(source_urls=[]),'source required'),
        (lambda s:s['metrics']['nav'].update(value=0),'invalid per-unit value'),
        (lambda s:s['metrics']['premium_discount_pct'].update(value=1),'arithmetic mismatch'),
        (lambda s:s['metrics']['premium_discount_pct']['inputs'].update(price=101),'input price'),
        (lambda s:s['metrics']['nav'].update(as_of='2026-10-07'),'same trading day'),
        (lambda s:s['metrics']['nav'].update(currency='USD'),'currency mismatch'),
        (lambda s:s['metrics']['yield_ttm_pct'].update(value=4),'arithmetic mismatch'),
        (lambda s:s['metrics']['distribution_ttm_per_unit'].update(actual_or_estimate='estimate'),'actual, not annualized'),
        (lambda s:s['metrics']['weighted_pe'].update(value=30),'arithmetic mismatch'),
        (lambda s:s['metrics']['weighted_pe']['inputs']['constituents'][0].update(pe_ttm=0),'zero constituent PE'),
        (lambda s:s['metrics']['weighted_pe']['inputs']['constituents'][0].update(id='C01'),'duplicate constituent'),
        (lambda s:s['coverage']['holdings_quality'].update(weight_pct=99),'coverage arithmetic mismatch'),
        (lambda s:s['coverage']['holdings_quality']['contributors'][0].update(id='C01'),'invalid coverage contributors'),
        (lambda s:s['concentration'].update(max_weight_pct=10),'arithmetic mismatch'),
        (lambda s:s['concentration']['holdings'][0].update(weight_pct=10),'weights exceed 100%'),
        (lambda s:s['concentration'].update(holdings_complete=False),'exact calculation'),
        (lambda s:s['concentration'].update(method='reported',max_weight_pct=6),'disagree with complete holdings'),
        (lambda s:s['concentration'].update(method='reported',max_weight_pct=6,holdings=[],holdings_complete=False),'complete PE constituent weights'),
        (lambda s:s['metrics']['weighted_pe'].update(value=0),'nonpositive aggregate'),
        (lambda s:s['valuation_history'].update(years=2),'3-year band'),
        (lambda s:s['fund'].update(inception_date='2026-04-01'),'complete year'),
        (lambda s:s['fund'].update(inception_date=None),'complete year'),
        (lambda s:s['validation'][0].update(status='limited'),'matching validation'),
        (lambda s:s['sources'][0].update(published_at='2026-10-09'),'published after cutoff'),
        (lambda s:s['metrics']['price'].update(value=float('inf')),'expected number'),
    ]:
        bad=deepcopy(BASE);mutate(bad);reject(bad,fragment)
    # Known total and missing-data denominators, not the production function as oracle.
    s=deepcopy(BASE)
    for name in ('index_methodology','total_cost','tracking_quality'):item(s,name)['score']=1
    out=seal(s);check(out['overall']['raw_score']==90 and out['overall']['score']==90,'20% instrument weighting gives total 90')
    s=deepcopy(BASE);omit(s,['index_methodology','total_cost','tracking_quality'])
    out=seal(s);check(out['overall']['raw_score']==100 and out['overall']['signal']=='yellow' and out['overall']['provisional'] and out['overall']['confidence']=='low','four dimensions normalize 80% weights; missing dimension cannot be green')
    s=deepcopy(BASE);omit(s,['index_methodology','total_cost','tracking_quality','fund_scale','liquidity'])
    out=seal(s);check(out['overall']['score'] is None and out['overall']['signal']=='unknown','nine observations and only three assessable dimensions cannot form total')
    s=deepcopy(BASE);omit(s,['band_position','relative_valuation'])
    out=seal(s);check(out['overall']['signal']=='unknown' and out['scores']['valuation']['raw_score'] is None,'valuation needs two items regardless of other coverage')
    # 70/80% thresholds and null handling.
    for name,minimum in core.ETF_COVERAGE_MIN.items():
        s=deepcopy(BASE);coverage(s,name,minimum-.001);reject(s,'insufficient weight coverage')
        item(s,name)['score']=None;seal(s)
        s=deepcopy(BASE);coverage(s,name,minimum)
        if name=='relative_valuation':qualifier(s,'valuation_supported','limited')
        seal(s)
    s=deepcopy(BASE);coverage(s,'relative_valuation',75);reject(s,'low coverage requires')
    s=deepcopy(BASE);s['coverage']['band_position']['contributors'][0]['data_available']=False
    s['coverage']['band_position']['weight_pct']=95;reject(s,'PE constituent coverage mismatch')
    # Concentration equality boundaries, theme thresholds and upper-limit priority.
    for subtype,a,b,expected in [('市值型',25,60,2),('市值型',25.001,60,1),('市值型',40,80,1),('市值型',40.001,80,0),('市值型',40,80.001,0),('產業／主題型',25,70,2),('產業／主題型',40,90,1),('產業／主題型',40,90.001,0)]:
        s=deepcopy(BASE);s['subtype']=subtype;s['concentration'].update(method='reported',max_weight_pct=a,top10_weight_pct=b,holdings_complete=False,holdings=[])
        s['metrics']['weighted_pe'].update(value_status='reported',inputs=None,formula=None)
        item(s,'concentration')['score']=expected;out=seal(s)
        check(e.concentration_score(s)==expected,'independent concentration boundary')
        if expected==0:check(out['overall']['signal']=='yellow' and out['overall']['concentration_cap']=='yellow','concentration zero caps otherwise attractive total')
    s=deepcopy(BASE);omit(s,['concentration']);out=seal(s)
    check(out['overall']['signal']=='yellow' and out['overall']['confidence']=='medium','unknown concentration never gives green/high confidence')
    # R4 and R6 use the lowest applicable confidence cap.
    for flags,provisional,confidence in [([('quote_verified','limited')],False,'medium'),([('quote_verified','limited'),('valuation_supported','limited')],True,'low'),([('holdings_financials_verified','fail')],False,None),([('valuation_supported','fail')],False,None)]:
        s=deepcopy(BASE)
        for k,v in flags:qualifier(s,k,v)
        out=seal(s);check((out['overall']['provisional'],out['overall']['confidence'])==(provisional,confidence),'qualification confidence')
    s=deepcopy(BASE);item(s,'band_position')['score']=1;item(s,'relative_valuation')['score']=1
    out=seal(s);check(out['sensitivity']['fragile'] and out['overall']['confidence']=='medium','single valuation perturbation changes light and caps confidence')
    s=deepcopy(BASE);s['major_risk'].update(confirmed=True,source_urls=[s['sources'][0]['url']]);omit(s,['band_position','relative_valuation'])
    out=seal(s);check(out['overall']['signal']=='major_risk' and out['overall']['score'] is None,'major risk precedes missing valuations')
    # Positive, zero and negative earnings growth do not use unstable multiples.
    for old,new,nav,expected in [(100,110,10,2),(100,110,20,1),(100,110,20.001,0),(100,100,1,0),(100,100,0,1),(100,90,-20,1),(0,100,5,None)]:
        s=deepcopy(BASE);s['earnings_support_inputs'].update(previous_earnings=old,current_earnings=new,nav_return_pct=nav)
        item(s,'earnings_support')['score']=expected;seal(s);check(e.earnings_score(s)==expected,'earnings edge from original inputs')
    # Harmonic valuation includes loss makers and refuses nonpositive aggregate yields.
    for entries,expected,coverage_value in [([{'id':'A','weight_pct':50,'pe_ttm':10},{'id':'B','weight_pct':50,'pe_ttm':20}],Fraction(40,3),100),([{'id':'A','weight_pct':80,'pe_ttm':10},{'id':'B','weight_pct':20,'pe_ttm':None}],Fraction(10),80),([{'id':'A','weight_pct':50,'pe_ttm':10},{'id':'B','weight_pct':50,'pe_ttm':-10}],None,100),([{'id':'A','weight_pct':69,'pe_ttm':10},{'id':'B','weight_pct':31,'pe_ttm':None}],None,69)]:
        m=deepcopy(BASE['metrics']['weighted_pe']);m['inputs']={'constituents':entries}
        value,covered=e.arithmetic('weighted_pe',m);check(value==expected and covered==coverage_value,'harmonic PE and weight renormalization')
    m=deepcopy(BASE['metrics']['premium_discount_pct']);m['inputs']={'daily_premium_pct':[-1,1]*10}
    check(e.arithmetic('premium_abs_mean20_pct',m)[0]==1 and e.arithmetic('premium_abs_max20_pct',m)[0]==1,'absolute 20-day premiums')
    m['inputs']={'annual_periods':[{'start':'2025-01-01','end':'2025-12-31','fund_return_pct':10,'index_return_pct':11,'fund_currency':'TWD','index_currency':'TWD','total_return':True}]}
    check(e.arithmetic('tracking_difference_pct',m)[0]==-1,'complete-year tracking difference')
    s=deepcopy(BASE);s['metrics']['tracking_difference_pct']=deepcopy(m);s['metrics']['tracking_difference_pct'].update(value=-1,unit='%',currency=None)
    seal(s);s['metrics']['tracking_difference_pct']['inputs']['annual_periods'][0]['total_return']=False;reject(s,'total returns')
    # Default validation binds totals, summaries, scope, sensitivity and final text.
    for mutate,fragment in [(lambda s:s['overall'].update(score=99),'overall.score'),(lambda s:s['overall'].update(confidence='low'),'overall.confidence'),(lambda s:s['scores']['instrument'].update(coverage=2),'instrument.coverage'),(lambda s:s['sensitivity'].update(fragile=True),'sensitivity'),(lambda s:s.update(report_sha256='0'*64),'hash mismatch')]:
        bad=deepcopy(BASE);mutate(bad);r=e.validate(bad);check(not r['valid'] and any(fragment in x for x in r['errors']),str(r['errors']))
    # Actual CLI draft -> finalize -> default verification, then verified ETF decision binding.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);inp=path/'etf.json';inp.write_text(json.dumps(BASE,ensure_ascii=False))
        cmd=[sys.executable,'-B',str(ROOT/'scripts/etf_guard.py'),str(inp)]
        p=subprocess.run(cmd+['--derive'],capture_output=True,text=True);draft=json.loads(p.stdout)
        check(p.returncode==0 and draft['validated'] is False,'draft does not claim final validation')
        inp.write_text(json.dumps(draft,ensure_ascii=False));p=subprocess.run(cmd+['--finalize'],capture_output=True,text=True);final=json.loads(p.stdout)
        check(p.returncode==0 and final['validated'] is True,'finalize runs default checks before certification')
        inp.write_text(json.dumps(final,ensure_ascii=False));p=subprocess.run(cmd,capture_output=True,text=True)
        check(p.returncode==0 and json.loads(p.stdout)['valid'],'final ETF CLI validation')
        source_raw=inp.read_bytes();decision=json.loads((ROOT/'tests/decision.rule-1.9.0.json').read_text())
        decision['security']=final['security'];decision['research_reference'].update(reference='attachment:etf.json',sha256=hashlib.sha256(source_raw).hexdigest(),model_version=final['model_version'],rule_version=final['rule_version'],analysis_at=final['analysis_at'],data_cutoff_at=final['data_cutoff_at'],verification='etf_snapshot')
        decision['gates'][0]['signal']='green';decision['gates'][1]['signal']='yellow'
        r=d.validate(decision,final,hashlib.sha256(source_raw).hexdigest(),True);check(r['valid'],str(r['errors']))
        decision=d.derived_record(decision,r);decision['report_markdown']=final['report_markdown']+'\n'+d.report_block(decision,decision['conclusion']);decision=d.derived_record(decision,r)
        dec=path/'decision.json';dec.write_text(json.dumps(decision,ensure_ascii=False));p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/decision_guard.py'),str(dec),'--research',str(inp)],capture_output=True,text=True)
        check(p.returncode==0 and json.loads(p.stdout)['research_verification']=='etf_snapshot','decision revalidates actual finalized ETF')
        final['overall']['score']=99;r=d.validate(decision,final,hashlib.sha256(source_raw).hexdigest());check(not r['valid'],'ETF total tampering cannot pass decision source validation')
    legacy=json.loads((ROOT/'tests/decision.rule-1.8.0.json').read_text());research_raw=(ROOT/'tests/research.decision.example.json').read_bytes()
    check(d.validate(legacy,json.loads(research_raw),hashlib.sha256(research_raw).hexdigest())['valid'],'old decision release still validates')
    print(json.dumps({'passed':True,'checks':count,'scope':'production ETF arithmetic, score gates, confidence, report and decision binding; synthetic only'}))


if __name__=='__main__':main()
