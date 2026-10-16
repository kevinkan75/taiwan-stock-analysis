"""Fixed annual arithmetic, missingness, reconciliation, CLI and frozen releases."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import financial_history as history
import financial_history_fixtures as fixtures
import review_guard as review
import snapshot_guard as stock
import etf_guard as etf
import decision_guard as decision
import audit_fixtures
from rules_core import timestamp

BASE=json.loads((ROOT/'assets/review.example.json').read_bytes())
RESEARCH=json.loads((ROOT/'assets/snapshot.example.json').read_bytes())
count=0


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def encode(x):return (json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def validate(h,source=None,derive=True):
    record=deepcopy(BASE);research=deepcopy(RESEARCH);record['financial_history']=deepcopy(h)
    if source:record['sources']=[source]
    raw=encode(research);record['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
    return review.validate(record,research,raw,derive_only=derive)


def finalize(h):
    record=deepcopy(BASE);research=deepcopy(RESEARCH);record['financial_history']=deepcopy(h)
    audit_fixtures.finish_review(record,research)
    return record,research


def main():
    h=deepcopy(BASE['financial_history'])
    z=validate(h);check(z['valid'],str(z['errors']));out=z['derived']['financial_history']
    check(json.loads((ROOT/'assets/review.schema.json').read_bytes())['properties']['financial_history']==history.schema(),'published schema mirrors canonical annual input shape')
    check(out['status']=='complete' and out['periods']==3,'three actual full years complete')
    check(len(out['checks'])==8 and all(c['status']=='pass' for c in out['checks']),'two checks/year plus two equity bridges')
    # Literal expected values are independent of the production formula helpers.
    for key,expected in [('revenue',144000000),('net_income_parent',18000000),('diluted_eps',1.8),('fcf',18000000),
                         ('gross_margin',40),('operating_margin',20),('revenue_change',24000000)]:
        check(out['rows'][-1][key]==expected,'fixed annual '+key)
    check(math.isclose(out['rows'][-1]['roe'],26.666666666666668),'average parent equity, not year-end total equity')
    check(math.isclose(out['rows'][-1]['revenue_yoy'],20),'same annual revenue YoY')
    check(math.isclose(out['rows'][-1]['eps_yoy'],50),'same annual EPS YoY')
    check(math.isclose(out['revenue_cagr_two_intervals'],20),'three observations have two annual intervals')
    check(out['rows'][-1]['gross_margin_change_pp']==0,'margin changes use percentage points')
    check(out['rows'][0]['revenue_yoy'] is None,'no invented fourth annual observation')
    check(z['derived']['research_confidence']==RESEARCH['overall']['confidence'],'supplement does not invent research confidence')
    for mode in ('negative_capex','scaled_units','positive_loss_turnaround','nonpositive_revenue','nonpositive_equity'):
        x=deepcopy(h);a=x['periods'][0]['inputs'];b=x['periods'][1]['inputs']
        if mode=='negative_capex':a['cash_ppe_purchases']['raw_value']=-8
        if mode=='scaled_units':a['total_assets'].update(raw_value=200000,scale=1000)
        if mode=='positive_loss_turnaround':a['diluted_eps']['raw_value']=-1
        if mode=='nonpositive_revenue':a['revenue']['raw_value']=0
        if mode=='nonpositive_equity':a['parent_equity_begin']['raw_value']=-40
        r=validate(x);check(r['valid'],mode+str(r['errors']));f=r['derived']['financial_history']
        if mode=='negative_capex':check(f['rows'][0]['fcf']==12000000,'retain signed raw capex, subtract cash purchase magnitude')
        if mode=='scaled_units':check(f['checks'][0]['status']=='pass','different reported units normalize before reconciliation')
        if mode=='positive_loss_turnaround':check(f['rows'][1]['eps_yoy'] is None and f['rows'][1]['eps_change']==2.2,'negative EPS base retains amount, no misleading percent')
        if mode=='nonpositive_revenue':check(f['rows'][0]['gross_margin'] is None and f['rows'][1]['revenue_yoy'] is None and f['revenue_cagr_two_intervals'] is None,'zero base never becomes positive growth claim')
        if mode=='nonpositive_equity':check(f['rows'][0]['roe'] is None,'negative opening equity cannot imply positive ROE efficiency')
    # Missing inputs and missing years do not pass by an empty warnings list.
    x=deepcopy(h)
    for period in x['periods']:
        for cell in period['inputs'].values():fixtures.missing(cell)
    r=validate(x);check(r['valid'],str(r['errors']));f=r['derived']['financial_history']
    check(f['status']=='partial' and len(f['missing_inputs'])==42,'all null is incomplete data')
    check(all(c['status']=='unavailable' for c in f['checks']),'missing operands never reconcile as pass')
    check(f['revenue_cagr_two_intervals'] is None,'missing series cannot produce CAGR')
    for n in (0,1,2):
        x=deepcopy(h);x['periods']=x['periods'][3-n:] if n else []
        r=validate(x);check(r['valid'],str(r['errors']));f=r['derived']['financial_history']
        check(f['status']=='partial' and f['missing_periods']==3-n,'missing annual periods disclosed '+str(n))
        check(f['revenue_cagr_two_intervals'] is None,'short annual series has no two-interval CAGR')
    x=history.initialize();r=validate(x)
    check(r['valid'] and r['derived']['workflow_status']=='incomplete','not_run is unfinished workflow')
    check('financial_history' in r['derived']['pending_tasks'],'unfinished annual work is visible')
    check(not validate(history.initialize(is_etf=True))['valid'],'ordinary stock cannot use ETF exemption')
    # Mismatches retain input facts and disclose the exact residual.
    for key,delta,check_name in [('total_assets',5,'balance_equation'),('cash_cf_end',5,'cash_end_match'),('parent_equity_begin',5,'equity_opening_match')]:
        x=deepcopy(h);x['periods'][1]['inputs'][key]['raw_value']+=delta
        r=validate(x);check(r['valid'],str(r['errors']));f=r['derived']['financial_history']
        check(f['status']=='conflicting' and any(c['check']==check_name and c['status']=='conflict' for c in f['checks']),'expose '+check_name)
        check(r['derived']['evidence_status']=='insufficient' and 'financial_history' in r['derived']['unresolved_tasks'],'conflict cannot certify evidence readiness')
        check(x['periods'][1]['inputs'][key]['raw_value']==h['periods'][1]['inputs'][key]['raw_value']+delta,'derive never repairs source values')
    for residual,expected in [(1.5,'pass'),(1.500001,'conflict')]:
        x=deepcopy(h);x['periods'][0]['inputs']['total_assets']['raw_value']+=residual
        r=validate(x);check(r['valid'],str(r['errors']));c=r['derived']['financial_history']['checks'][0]
        check(c['status']==expected and c['tolerance']==1500000,'raw printed-unit rounding boundary '+str(residual))
    mutations=[
        ('boolean',lambda x:x['periods'][0]['inputs']['revenue'].update(raw_value=True)),
        ('NaN',lambda x:x['periods'][0]['inputs']['revenue'].update(raw_value=float('nan'))),
        ('infinity',lambda x:x['periods'][0]['inputs']['revenue'].update(raw_value=float('inf'))),
        ('overflow',lambda x:x['periods'][0]['inputs']['revenue'].update(raw_value=1e308)),
        ('absent field',lambda x:x['periods'][0]['inputs'].pop('cfo')),
        ('unregistered source',lambda x:x['periods'][0]['inputs']['revenue'].update(source_url='https://unknown.invalid')),
        ('no source',lambda x:x['periods'][0]['inputs']['revenue'].update(source_url=None)),
        ('zero scale',lambda x:x['periods'][0]['inputs']['revenue'].update(scale=0)),
        ('negative scale',lambda x:x['periods'][0]['inputs']['revenue'].update(scale=-1)),
        ('scaled EPS',lambda x:x['periods'][0]['inputs']['diluted_eps'].update(scale=1000000)),
        ('wrong source year',lambda x:x['periods'][0]['inputs']['cfo'].update(period_end='2024-12-31')),
        ('instant used as flow',lambda x:x['periods'][0]['inputs']['revenue'].update(period_start=None)),
        ('wrong opening balance date',lambda x:x['periods'][0]['inputs']['parent_equity_begin'].update(period_end='2023-12-31')),
        ('quarter substitution',lambda x:x['periods'][0].update(period_start='2023-10-01')),
        ('duplicate year',lambda x:x['periods'].__setitem__(1,deepcopy(x['periods'][0]))),
        ('nonascending years',lambda x:x['periods'].reverse()),
        ('missing currency',lambda x:x.update(currency=None)),
        ('mixed scope',lambda x:x.update(basis='standalone')),
        ('stale latest-year claim',lambda x:x.update(latest_period_end='2024-12-31')),
        ('future year',lambda x:x.update(latest_period_end='2099-12-31')),
        ('not_run retaining numbers',lambda x:x.update(status='not_run')),
        ('negative assets',lambda x:x['periods'][0]['inputs']['total_assets'].update(raw_value=-1)),
        ('blank source locator',lambda x:x['periods'][0]['inputs']['revenue'].update(locator='  ')),
        ('blank reason',lambda x:x.update(reason='  ')),
        ('blank one-off scope',lambda x:x['periods'][0].update(one_off_note='  ')),
    ]
    for label,mutation in mutations:
        x=deepcopy(h);mutation(x)
        check(not validate(x)['valid'],'reject '+label)
    for key,value in [('published_at','2099-01-01'),('published_at','2020-01-01'),('retrieved_at','2099-01-01T00:00:00+08:00'),('source_type','external_estimate')]:
        source=deepcopy(BASE['sources'][0]);source[key]=value
        check(not validate(h,source)['valid'],'reject annual source '+key)
    record,research=finalize(h);raw=encode(research)
    check(review.validate(record,research,raw)['valid'],'actual final annual block binds')
    for mutation in (lambda s:s['report_markdown'].replace('| 營收 | 100.00','| 營收 | 999.00'),
                     lambda s:s['report_markdown']+'\n'+history.render(record['assessment']['financial_history']),
                     lambda s:history.strip_report(s['report_markdown'])):
        s=deepcopy(research);s['report_markdown']=mutation(s);s['report_sha256']=stock.report_hash(s)
        r=deepcopy(record);payload=encode(s);r['research_reference']['sha256']=hashlib.sha256(payload).hexdigest()
        check(not review.validate(r,s,payload)['valid'],'tampered/missing/duplicate annual report rejected even after rehash')
    bad=deepcopy(record);bad['assessment']['financial_history']['rows'][-1]['revenue']=999
    check(not review.validate(bad,research,raw)['valid'],'derived annual numbers cannot be replaced by analyst')
    # A real current decision is validated against the same annual review.
    from check_evidence_audit import decision_case
    r,s,d=decision_case();payload=encode(s);d['research_reference']['sha256']=hashlib.sha256(payload).hexdigest();draw=encode(d)
    r['research_reference']['sha256']=hashlib.sha256(payload).hexdigest();r['decision_reference']['sha256']=hashlib.sha256(draw).hexdigest()
    check(review.validate(r,s,payload,d,draw)['valid'],'existing action still supported with reconciled annual evidence')
    for state in ('not_run','conflict'):
        bad=deepcopy(r)
        if state=='not_run':bad['financial_history']=history.initialize()
        else:bad['financial_history']['periods'][0]['inputs']['total_assets']['raw_value']+=10
        check(not review.validate(bad,s,payload,d,draw,True)['valid'],'entry/staging refuses '+state+' annual review')
    # Frozen pre-change bytes and outputs come from the old release, never new answers.
    baseline=json.loads((ROOT/'tests/release-1.12.0.baseline.json').read_bytes())
    for name,expected in baseline['files'].items():check(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,'preserve '+name)
    for name,validator in [('snapshot',stock),('etf',etf)]:
        payload=(ROOT/'tests'/f'{name}.rule-1.12.0.json').read_bytes();s=json.loads(payload);z=validator.validate(s,True)
        check(z['valid'],'old research still validates '+name)
        derived=validator.derived_snapshot(s,z)
        check(hashlib.sha256(json.dumps(derived,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==baseline['derived'][name],'old full derived output preserved '+name)
    oldraw=(ROOT/'tests/snapshot.rule-1.12.0.json').read_bytes();old=json.loads((ROOT/'tests/review.rule-1.12.0.json').read_bytes())
    check(review.validate(old,json.loads(oldraw),oldraw)['valid'],'old review uses frozen schema without annual backfill')
    oldsource=(ROOT/'tests/research.decision.example.json').read_bytes();olddecision=json.loads((ROOT/'tests/decision.rule-1.12.0.json').read_bytes())
    check(decision.validate(olddecision,json.loads(oldsource),hashlib.sha256(oldsource).hexdigest())['valid'],'frozen decision 1.12.0 still validates')
    old['research_reference'].update(rule_version=RESEARCH['rule_version'],sha256=hashlib.sha256(encode(RESEARCH)).hexdigest())
    check(not review.validate(old,RESEARCH,encode(RESEARCH))['valid'],'old review cannot bypass current annual checks')
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);source=p/'research.json';source.write_bytes(encode(research));rec=p/'review.json';rec.write_bytes(encode(record))
        cmd=[sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),str(rec),'--research',str(source)]
        for extra in ([],['--render'],['--derive']):
            z=subprocess.run(cmd+extra,capture_output=True,text=True);check(z.returncode==0,'production CLI '+str(extra)+': '+z.stdout)
            if extra==['--render']:check('financial_history_report' in json.loads(z.stdout),'CLI exports exact annual table')
        z=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),'--research',str(source),'--init'],capture_output=True,text=True)
        check(z.returncode==0 and json.loads(z.stdout)['financial_history']['status']=='not_run','CLI invents no annual evidence')
        bad=deepcopy(record);bad['financial_history']['periods'][0]['inputs']['revenue']['raw_value']=True;rec.write_bytes(encode(bad))
        z=subprocess.run(cmd+['--derive'],capture_output=True,text=True);check(z.returncode==2,'CLI derive cannot bypass bad raw input')
    print(json.dumps(dict(passed=True,checks=count,scope='annual input provenance/periods/units, fixed arithmetic, statement reconciliation, missingness, report binding, action guard, production CLI and frozen release; no external truth verification')))


if __name__=='__main__':main()
