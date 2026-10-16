"""Production audit mutations, fixed arithmetic expectations and exact CLI tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import evidence_audit as audit
import review_guard as review
import decision_guard as decision
import snapshot_guard as stock
import audit_fixtures as fixtures
import financial_history

BASE=json.loads((ROOT/'assets/review.example.json').read_text())
RESEARCH=json.loads((ROOT/'assets/snapshot.example.json').read_text())
count=0


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def encode(x):return (json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def validate(record,research=None,dec=None):
    research=deepcopy(research or RESEARCH)
    raw=encode(research)
    record=deepcopy(record)
    record['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
    draw=None
    if dec:
        dec=deepcopy(dec);dec['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
        draw=encode(dec);record['decision_reference']['sha256']=hashlib.sha256(draw).hexdigest()
    return review.validate(record,research,raw,dec,draw,True)


def claim(record,key):return next(x for x in record['evidence_audit']['claims'] if x['id']==key)


def decision_case():
    s=json.loads((ROOT/'tests/research.decision.example.json').read_text())
    d=json.loads((ROOT/'assets/decision.example.json').read_text())
    r=deepcopy(BASE);r.update(security=s['security'],mode='decision',analysis_at=d['analysis_at'])
    r['decision_reference']=dict(reference='attachment:decision.json',sha256='0'*64,rule_version=d['rule_version'],model_version=d['model_version'])
    r['research_reference'].update(rule_version=s['rule_version'],model_version=s['model_version'])
    template=deepcopy(r['tasks'][0]);r['tasks']=[]
    for name in review.required_tasks(s,True):
        t=deepcopy(template);t['id']=name;t['attempts'][0]['request']='合成核對'+name;r['tasks'].append(t)
    r['evidence_audit']=fixtures.make_audit(s,d)
    fixtures.finish_review(r,s,d)
    return r,s,d


def main():
    check(review.validate(BASE,RESEARCH,(ROOT/'assets/snapshot.example.json').read_bytes())['valid'],'published audit binds exact bytes')
    check(len(BASE['evidence_audit']['claims'])==34,'fixed synthetic claim count')
    check(BASE['assessment']['claim_audit']['material_unresolved']==[],'no synthetic unresolved claims')
    # Expected arithmetic values are literals, not calls to a duplicate scorer.
    for method,inputs,expected in [('sum',[1,2,3],6),('product',[5,26],130),('subtract',[120,30],90),('divide',[100,5],20),('ratio_pct',[30,120],25),('change_pct',[120,100],19.999999999999996)]:
        check(audit.calculate(dict(method=method,inputs=inputs))==expected,'fixed arithmetic '+method)
    for method,inputs in [('divide',[1,0]),('change_pct',[1,-2]),('sum',[]),('product',[True,2]),('subtract',[3]),('eval',[2,3])]:
        try:audit.calculate(dict(method=method,inputs=inputs));rejected=False
        except ValueError:rejected=True
        check(rejected,'invalid arithmetic rejected '+method)
    # Each broken artifact runs through the production review validator.
    mutations=[
        ('missing target coverage',lambda r:r['evidence_audit']['claims'].pop(0)),
        ('wrong bound value',lambda r:claim(r,'metric_price').update(value=101)),
        ('claim period differs from metric',lambda r:claim(r,'metric_price').update(period='2025')),
        ('claim unit differs from metric',lambda r:claim(r,'metric_price').update(unit='USD/ADR')),
        ('unknown target',lambda r:claim(r,'metric_price').update(targets=['research:/metrics/not_here/value'])),
        ('duplicate target',lambda r:claim(r,'metric_eps_ttm')['targets'].append('research:/metrics/price/value')),
        ('nonmaterial required target',lambda r:claim(r,'metric_price').update(material=False)),
        ('source not registered',lambda r:claim(r,'metric_price')['sources'][0].update(url='https://unknown.invalid/doc')),
        ('future evidence',lambda r:claim(r,'metric_price')['sources'][0].update(published_at='2099-01-01')),
        ('model memory',lambda r:claim(r,'metric_price')['sources'][0].update(retrieval='memory')),
        ('wrong period',lambda r:claim(r,'metric_price')['sources'][0].update(period='另一期間')),
        ('wrong basis',lambda r:claim(r,'metric_price')['sources'][0].update(basis='ADR每單位')),
        ('wrong source value',lambda r:claim(r,'metric_price')['sources'][0].update(value=99)),
        ('absent selected source',lambda r:claim(r,'metric_price').update(selected_source=None)),
        ('bad selected index',lambda r:claim(r,'metric_price').update(selected_source=100)),
        ('fact as assumption',lambda r:claim(r,'metric_price').update(kind='assumption',verdict='reviewed')),
        ('judgment as fact',lambda r:claim(r,'score_growth0').update(kind='fact')),
        ('verified assumption',lambda r:claim(r,'assumption_0_eps').update(verdict='supported')),
        ('missing calculation',lambda r:claim(r,'metric_pe_ttm').update(calculation=None)),
        ('wrong operands',lambda r:claim(r,'metric_pe_ttm')['calculation'].update(inputs=[100,4])),
        ('wrong calculation method',lambda r:claim(r,'metric_pe_ttm')['calculation'].update(method='product')),
        ('unverified input',lambda r:claim(r,'metric_eps_ttm').update(verdict='unresolved')),
        ('missing premise',lambda r:claim(r,'score_growth0').update(premises=['absent'])),
        ('circular premises',lambda r:claim(r,'metric_price').update(premises=['metric_pe_ttm'])),
        ('missing counter case',lambda r:r['evidence_audit']['counter_cases'].pop()),
        ('missing invalidation',lambda r:r['evidence_audit'].update(invalidation_conditions=[])),
        ('unbound thesis',lambda r:r['evidence_audit']['invalidation_conditions'][0].update(thesis_index=100)),
        ('invented report excerpt',lambda r:r['evidence_audit']['counter_cases'][0].update(report_excerpt='正文沒有這句話')),
        ('missing counter evidence',lambda r:r['evidence_audit']['counter_cases'][0].update(claim_ids=[])),
        ('insufficient thesis with signal',lambda r:r['evidence_audit'].update(thesis_status='insufficient')),
    ]
    for label,mutation in mutations:
        r=deepcopy(BASE);mutation(r);z=validate(r)
        check(not z['valid'],label+' rejected')
    # Conflicts use source authority before recency; no averaging / voting.
    for rank,published,value,expected in [('secondary','2026-10-01',99,True),('primary','2026-10-01',99,False),('primary','2026-07-01',99,True)]:
        r=deepcopy(BASE);c=claim(r,'metric_price');other=deepcopy(c['sources'][0]);other.update(rank=rank,published_at=published,value=value);c['sources'].append(other)
        z=validate(r);check(z['valid']==expected,'primary then date conflict priority')
    r=deepcopy(BASE);c=claim(r,'metric_price');other=deepcopy(c['sources'][0]);other.update(basis='不同股數／證券口徑',published_at='2026-10-01',value=99);c['sources'].append(other)
    check(validate(r)['valid'],'different basis is not a comparable conflict')
    r=deepcopy(BASE);c=claim(r,'metric_price');other=deepcopy(c['sources'][0]);other['value']=99;c['sources'].append(other)
    check(not validate(r)['valid'],'equally authoritative same-date conflicting facts cannot be resolved by order')
    # A refuted body sentence must be removed even if called non-material.
    r=deepcopy(BASE);s=deepcopy(RESEARCH);extra=deepcopy(claim(r,'metric_price'))
    extra.update(id='old_error',targets=[],report_excerpt='這個未移除的錯誤事實。',statement='這個未移除的錯誤事實。',material=False,verdict='refuted')
    r['evidence_audit']['claims'].append(extra);s['report_markdown']+='\n'+extra['report_excerpt'];s['report_sha256']=stock.report_hash(s)
    check(not validate(r,s)['valid'],'refuted nonmaterial text cannot remain in final report')
    extra.update(report_excerpt='',statement='已移除的歷史錯句');s=deepcopy(RESEARCH)
    check(validate(r,s)['valid'],'removed historical error can remain in ledger')
    # Python bool == int must never substitute a factual boolean for a number.
    r=deepcopy(BASE);c=claim(r,'metric_price');extra=deepcopy(c)
    extra.update(id='boolean_input',targets=['research:/major_risk/confirmed'],value=False)
    extra['sources'][0]['value']=False;r['evidence_audit']['claims'].append(extra)
    c=claim(r,'metric_pe_ttm');c.update(premises=['boolean_input','metric_price']);c['calculation'].update(method='sum',inputs=[0,100])
    # A zero numeric input must not accept a False premise.
    c['premises']=['boolean_input'];c['calculation'].update(method='sum',inputs=[0]);
    s=deepcopy(RESEARCH)
    # Exercise operand checking directly so stock P/E rules cannot mask it.
    c['targets']=[];c['report_excerpt']='合成布林運算案例';c['value']=0;s['report_markdown']+='\n合成布林運算案例'
    errors=audit.validate(r['evidence_audit'],s,None,{x['url'] for x in s['sources']},__import__('rules_core').timestamp(s['data_cutoff_at']))
    check(any('operands differ' in x for x in errors),'boolean premise cannot equal numeric zero')
    # Completion and investment direction never become a new confidence score.
    r=deepcopy(BASE);r['evidence_audit']['status']='partial';z=validate(r)
    check(z['valid'] and z['derived']['workflow_status']=='incomplete','partial audit remains honest incomplete work')
    check(z['derived']['evidence_status']=='insufficient','partial audit does not certify evidence sufficiency')
    r=deepcopy(BASE);r['evidence_audit']['counter_cases'][0]['disposition']='unresolved';z=validate(r)
    check(z['valid'] and z['derived']['evidence_status']=='insufficient','unresolved counter case lowers evidence readiness')
    check(z['derived']['research_confidence']=='high','audit does not rewrite research confidence or direction')
    r,s,d=decision_case();check(validate(r,s,d)['valid'],'current staged decision has a fully linked audit')
    for change in (lambda r:r['evidence_audit'].update(status='partial'),lambda r:r['evidence_audit']['counter_cases'][0].update(disposition='unresolved')):
        bad=deepcopy(r);change(bad);check(not validate(bad,s,d)['valid'],'entry/staging requires finished critical audit')
    # ETF uses the same production record, not a stock-only alternate pathway.
    s=json.loads((ROOT/'assets/etf.example.json').read_text());r=deepcopy(BASE);r['security']=s['security'];r['evidence_audit']=fixtures.make_audit(s)
    r['financial_history']=financial_history.initialize(is_etf=True)
    t=deepcopy(r['tasks'][0]);r['tasks']=[]
    for name in review.required_tasks(s,False):
        item=deepcopy(t);item['id']=name;item['attempts'][0]['request']='合成ETF'+name;r['tasks'].append(item)
    fixtures.finish_review(r,s);check(validate(r,s)['valid'],'ETF shares claim audit')
    old=json.loads((ROOT/'tests/review.rule-1.11.0.json').read_text());oldsource=(ROOT/'tests/snapshot.rule-1.11.0.json').read_bytes()
    check(review.validate(old,json.loads(oldsource),oldsource)['valid'],'exact previous review still validates')
    old['research_reference'].update(rule_version=RESEARCH['rule_version'],sha256=hashlib.sha256(encode(RESEARCH)).hexdigest())
    check(not review.validate(old,RESEARCH,encode(RESEARCH))['valid'],'old schema cannot bypass new audit')
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp);source=p/'research.json';source.write_bytes((ROOT/'assets/snapshot.example.json').read_bytes());record=p/'review.json';record.write_text(json.dumps(BASE,ensure_ascii=False))
        cmd=[sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),str(record),'--research',str(source)]
        for args in ([],['--render'],['--derive']):
            z=subprocess.run(cmd+args,capture_output=True,text=True);check(z.returncode==0,'real CLI '+str(args)+': '+z.stdout)
        z=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),'--research',str(source),'--init'],capture_output=True,text=True)
        check(z.returncode==0,'CLI initializes a new audit')
        draft=json.loads(z.stdout)
        check(draft['schema_version']=='1.2' and not draft['evidence_audit']['claims'] and draft['financial_history']['status']=='not_run','initialization invents no evidence')
        check(draft['assessment']['workflow_status']=='incomplete','new draft cannot claim completion')
        bad=deepcopy(BASE);claim(bad,'metric_price')['sources'][0]['value']=999;record.write_text(json.dumps(bad,ensure_ascii=False))
        z=subprocess.run(cmd,capture_output=True,text=True);check(z.returncode==2,'real CLI rejects corrupted evidence')
    print(json.dumps(dict(passed=True,checks=count,scope='synthetic claims, arithmetic, conflicts, invalidation, decision binding, ETF, archives and real CLI; no external truth or performance validation')))


if __name__=='__main__':main()
