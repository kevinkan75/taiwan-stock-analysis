"""Independent expected workflow states, report mutations, archives and real CLI."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import snapshot_guard as stock
import decision_guard as decision
import etf_guard as etf
import review_guard as review
import report_checks
import rules_core as core

BASE=json.loads((ROOT/'tests/review.rule-1.11.0.json').read_text())
RESEARCH=json.loads((ROOT/'tests/snapshot.rule-1.11.0.json').read_text())
count=0


def check(ok,why):
    global count
    count+=1
    if not ok:raise AssertionError(why)


def encode(x):return (json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()


def bind(record,research,dec=None):
    raw=encode(research);rec=deepcopy(record)
    rec['research_reference'].update(sha256=hashlib.sha256(raw).hexdigest(),model_version=research['model_version'],rule_version=research['rule_version'])
    draw=None
    if dec:
        dec['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
        draw=encode(dec);rec['decision_reference'].update(sha256=hashlib.sha256(draw).hexdigest(),model_version=dec['model_version'],rule_version=dec['rule_version'])
    return rec,raw,draw


def task(record,name):return next(x for x in record['tasks'] if x['id']==name)


def finish(record,research,dec=None):
    rec,raw,draw=bind(record,research,dec)
    result=review.validate(rec,research,raw,dec,draw,True)
    check(result['valid'],str(result['errors']))
    rec['assessment']=result['derived']
    obj=dec if dec else research
    obj['report_markdown']='\n'.join(line for line in obj['report_markdown'].splitlines()
        if not line.startswith(('作業檢核：','決策證據：','等待原因：','資料查核紀錄：',review.SCOPE_LINE)))
    obj['report_markdown']+='\n'+review.report_block(rec['assessment'])
    obj['report_sha256']=hashlib.sha256(obj['report_markdown'].encode()).hexdigest()
    if dec:
        raw=encode(research);dec['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
    rec,raw,draw=bind(rec,research,dec)
    result=review.validate(rec,research,raw,dec,draw)
    check(result['valid'],str(result['errors']))
    return rec,research,dec,raw,draw


def decision_case():
    research=json.loads((ROOT/'tests/research.decision.example.json').read_text())
    raw=(ROOT/'tests/research.decision.example.json').read_bytes()
    dec=json.loads((ROOT/'tests/decision.rule-1.11.0.json').read_text())
    dec['gates'][4].update(signal='red',reason='合成今日法說尚未舉行')
    dec['conditions'].update(batches=[],waiting_for=[dict(target='gate_5',description='取得法說結果後重新核對')])
    result=decision.validate(dec,research,hashlib.sha256(raw).hexdigest(),True)
    check(result['valid'],str(result['errors']))
    dec=decision.derived_record(dec,result)
    dec['report_markdown']=research['report_markdown']+'\n'+decision.report_block(dec,dec['conclusion'])
    dec['report_sha256']=hashlib.sha256(dec['report_markdown'].encode()).hexdigest()
    check(decision.validate(dec,research,hashlib.sha256(raw).hexdigest())['valid'],'event-only waiting decision validates')
    rec=deepcopy(BASE);rec.update(security=research['security'],mode='decision',analysis_at=dec['analysis_at'])
    rec['decision_reference']=dict(reference='attachment:decision.json',sha256='0'*64,rule_version=dec['rule_version'],model_version=dec['model_version'])
    template=deepcopy(rec['tasks'][0]);rec['tasks']=[]
    for name in review.required_tasks(research,True):
        x=deepcopy(template);x['id']=name;x['attempts'][0]['request']='合成'+name;rec['tasks'].append(x)
    return finish(rec,research,dec)


def main():
    raw=(ROOT/'tests/snapshot.rule-1.11.0.json').read_bytes()
    check(review.validate(BASE,RESEARCH,raw)['valid'],'bundled review validates with exact source bytes')
    rec,research,dec,raw,draw=decision_case()
    check(rec['assessment']['workflow_status']=='complete','known event is not unfinished work')
    check(rec['assessment']['evidence_status']=='sufficient','known event is not missing evidence')
    check(rec['assessment']['waiting_reasons']==['event_pending'],'event-only wait is not a price/data claim')
    mixed=deepcopy(rec);mixed_research=deepcopy(research);mixed_decision=deepcopy(dec)
    task(mixed,'technical')['status']='partial'
    mixed,_,_,_,_=finish(mixed,mixed_research,mixed_decision)
    check(mixed['assessment']['waiting_reasons']==['data_pending','event_pending'],'waiting reasons are multi-select, not first-hit only')
    check(mixed['assessment']['workflow_status']=='incomplete' and mixed['assessment']['evidence_status']=='insufficient','partial task does not certify readiness')
    # Data/valuation unavailable after minimum attempts is complete work but
    # insufficient evidence; not_run and partial remain incomplete work.
    for status in ('not_run','partial','access_failed','conflicting','incompatible'):
        s=deepcopy(RESEARCH);v=deepcopy(BASE)
        s['eligibility']['valuation_supported']='fail'
        next(x for x in s['validation'] if x['check']=='valuation_supported')['status']='fail'
        for x in s['scores']['valuation']['items']:x['score']=None
        s['valuation'].update(scenarios=[],band=None,multiple_basis=None,eps_basis=None)
        s['valuation']['guardrails']['r2'].update(status='not_applicable',reason='無歷史模型',annual_roe_pct=[],ttm_roe_pct=None)
        r=stock.validate(s,True);check(r['valid'],str(r['errors']));s=stock.derived_snapshot(s,r)
        s['report_markdown']=s['report_markdown'].split('整體投資訊號')[0]+'整體投資訊號：⚪；總分：不計分；暫定：否；信心：未評定'
        s['report_sha256']=hashlib.sha256(s['report_markdown'].encode()).hexdigest()
        t=task(v,'valuation');t['status']=status
        if status=='not_run':t['attempts']=[]
        else:
            outcome={'partial':'unavailable','access_failed':'blocked','conflicting':'conflict','incompatible':'incompatible'}[status]
            t['attempts'][0]['result']=outcome
            alt=deepcopy(t['attempts'][0]);alt['stage']='alternative';alt['request']='合成替代路徑'
            if status!='partial':t['attempts'].append(alt)
        v,s,_,_,_=finish(v,s)
        check(v['assessment']['workflow_status']==('incomplete' if status in ('not_run','partial') else 'complete'),'independent workflow '+status)
        check(v['assessment']['evidence_status']=='insufficient','unavailable valuation does not imply evidence sufficiency')
    # ETF uses the same format/validator and its own canonical task list.
    e=json.loads((ROOT/'tests/etf.rule-1.11.0.json').read_text());v=deepcopy(BASE);v['security']=e['security'];template=deepcopy(v['tasks'][0]);v['tasks']=[]
    for name in review.required_tasks(e,False):
        t=deepcopy(template);t['id']=name;t['attempts'][0]['request']='合成ETF'+name;v['tasks'].append(t)
    v,e,_,_,_=finish(v,e);check(v['assessment']['workflow_status']=='complete','shared ETF workflow')
    # Explicit rejection cases exercise production validation, not copies of rules.
    rec,research,dec,raw,draw=decision_case()
    bad=deepcopy(rec);bad['research_reference']['sha256']='f'*64
    check(not review.validate(bad,research,raw,dec,draw)['valid'],'reject changed source bytes')
    for change in (lambda x:x['tasks'].pop(),lambda x:x['tasks'].append(deepcopy(x['tasks'][0])),
                   lambda x:task(x,'valuation').update(status='not_applicable'),
                   lambda x:task(x,'quote')['attempts'][0].update(source_url='https://unknown.invalid/x'),
                   lambda x:task(x,'quote')['attempts'][0].update(at='2099-01-01T00:00:00+08:00'),
                   lambda x:task(x,'quote')['attempts'].append(deepcopy(task(x,'quote')['attempts'][0])),
                   lambda x:task(x,'quote').update(status='not_run'),
                   lambda x:task(x,'quote')['attempts'][0].update(authority_basis='')):
        bad=deepcopy(rec);change(bad);check(not review.validate(bad,research,raw,dec,draw)['valid'],'invalid task/attempt is rejected')
    # Detect real previously observed defects, tolerate conditional and negative prose.
    for text in ['本次建議現在立即買進。','操作說明：本次可以直接買入。','資料不足，但現在建議立即買進。','目前研究信心為高。','本次回覆可靠度為85／100。','信心指數85%。','整體勝率為90%。']:
        check(bool(report_checks.report_errors(text,'wait',None)),'reject assertion '+text)
    for text in ['若法說後條件成立，再考慮買進。','目前不建議立即買進。','且尚無足夠估值依據支持立即買進。','單純跌價或法說利多，均不足以直接轉成買進。','不得宣稱信心85／100。','範例：建議現在立即買進。','引用：分析師認為可以買進。','營收成長85%，不代表勝率。','研究信心：未評定。']:
        check(not report_checks.report_errors(text,'wait',None),'allow explicit conditional/negative/quote '+text)
    bad=deepcopy(dec);bad['report_markdown']+='\n操作說明：本次建議現在立即買進。';bad['report_sha256']=stock.report_hash(bad)
    check(not decision.validate(bad,research,hashlib.sha256(raw).hexdigest())['valid'],'current decision actually calls prose checker')
    for name,validator in [('snapshot.example.json',stock),('etf.example.json',etf)]:
        bad=json.loads((ROOT/'assets'/name).read_text());bad['report_markdown']+='\n本次可靠度為85／100。';bad['report_sha256']=stock.report_hash(bad)
        check(not validator.validate(bad)['valid'],'current research prose checker '+name)
    # Historical rule 1.10 bytes and behavior are preserved, never upgraded in place.
    for name,validator in [('snapshot.rule-1.10.0.json',stock),('etf.rule-1.10.0.json',etf)]:
        path=ROOT/'tests'/name;oldraw=path.read_bytes();old=json.loads(oldraw)
        result=validator.validate(old,True)
        check(result['valid'],'previous release input still validates '+name)
        derived=stock.derived_snapshot(old,result) if validator==stock else etf.derived_snapshot(old,result)
        check(validator.validate(derived)['valid'],'previous release derived output still validates '+name)
        check(path.read_bytes()==oldraw,'archived bytes unchanged '+name)
    old=json.loads((ROOT/'tests/decision.rule-1.10.0.json').read_text());rpath=ROOT/'tests/research.decision.example.json';oldraw=rpath.read_bytes()
    check(decision.validate(old,json.loads(oldraw),hashlib.sha256(oldraw).hexdigest())['valid'],'old decision profile preserved')
    # CLI must require the final report block, bind bytes and reject stale source.
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);source=p/'research.json';source.write_bytes((ROOT/'tests/snapshot.rule-1.11.0.json').read_bytes());record=p/'review.json';record.write_text(json.dumps(BASE,ensure_ascii=False))
        cmd=[sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),str(record),'--research',str(source)]
        z=subprocess.run(cmd,capture_output=True,text=True);check(z.returncode==0,'real review CLI validates')
        z=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/review_guard.py'),'--research',str(source),'--init'],capture_output=True,text=True)
        check(z.returncode==0,'CLI initializes worklist')
        draft=json.loads(z.stdout)
        check(all(x['status']=='not_run' and not x['attempts'] for x in draft['tasks']),'initializer does not fabricate attempts')
        check(draft['assessment']['workflow_status']=='incomplete' and draft['assessment']['evidence_status']=='insufficient','initializer cannot certify a finished analysis')
        for mode in ('--render','--derive'):
            z=subprocess.run(cmd+[mode],capture_output=True,text=True);check(z.returncode==0,'real CLI '+mode)
        source.write_bytes(source.read_bytes()+b' ');z=subprocess.run(cmd,capture_output=True,text=True);check(z.returncode==2,'CLI rejects byte mutation')
    print(json.dumps({'passed':True,'checks':count,'scope':'shared stock/ETF workflow, attempt logs, explicit prose mutations, CLI and archived profiles; synthetic only'}))


if __name__=='__main__':main()
